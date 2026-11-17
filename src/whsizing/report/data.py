"""F9a data gathering: everything a report reads, loaded once.

`load_report_data(run, lang)` takes the in-memory `RunOutput` (results, finances, comparison,
sensitivity, manifest) and reads what it lacks from the run folder: the catalog snapshot
(`inputs/catalog`), `inputs/basis.yaml`, `profile/demand_profile.json`, `design/design_day.json`,
`dq/{dq_report,ingest_manifest}.json`, the daily series and every scenario's `trace.jsonl`
(`Tracer.load_jsonl`; a missing file gives an empty Tracer, as for a scenario not computed).
The report tables are built from it (`report.tables.build_tables`) and stored in `.tables`.

Tracer extension (the only one): `<sid>.report.n_warnings` (typ world), the number of non-info
flags that `ComparisonRow.n_warnings` shows. F6 traces the flags that carry a value, not their
count, and the comparison cell must still resolve to one node (IC1). Added in memory (runs are
immutable, §2.4: the scenarios' trace.jsonl files are never touched), so `ReportData.tracers` is
the place to find it, for the trace index of the report too. `export_trace(data, path)` writes
every scenario's nodes plus this one as the report stage's `trace.jsonl` (§2.1): the exported
trace in which every cited node id resolves. The extension is skipped when the loaded trace
already holds the node: the day F6 / F8 record the count, the report uses theirs.

Errors: a run folder file that cannot be read or is not valid (JSON model, trace, daily series)
and an unsupported language raise `ConfigError`, never a raw library exception.
"""

from __future__ import annotations

import dataclasses
import unicodedata
from dataclasses import dataclass
from pathlib import Path

import polars as pl
from pydantic import BaseModel, ValidationError

from whsizing.catalog import Catalog, load_catalog
from whsizing.design import load_basis
from whsizing.errors import ConfigError, WhsizingError
from whsizing.report.i18n import LANGS, Lang
from whsizing.schemas import (
    DemandProfile,
    DesignBasis,
    DesignDay,
    IngestManifest,
    ReportTable,
    ScenarioResult,
)
from whsizing.schemas.ingest import DQReport
from whsizing.schemas.run import RunOutput
from whsizing.schemas.trace import Tracer


@dataclass(frozen=True, eq=False)
class ReportData:
    run: RunOutput
    lang: Lang
    basis: DesignBasis
    catalog: Catalog
    profile: DemandProfile
    design_day: DesignDay
    dq: DQReport
    ingest: IngestManifest
    daily: pl.DataFrame  # canonical daily series (date, lines, orders, is_operating, ...)
    tracers: dict[str, Tracer]  # scenario id → its trace (all three worlds, F6 + F7 nodes)
    tables: dict[str, ReportTable]  # the twelve tables, keyed by `tables.TABLE_IDS`

    @property
    def run_id(self) -> str:
        return self.run.manifest.run_id

    @property
    def source_note(self) -> str:
        """The footer of every chart: engine and catalog versions and the run id."""
        m = self.run.manifest
        return f"engine {m.engine_version} · catalog {m.catalog_version} · run {m.run_id}"

    def computed(self) -> list[str]:
        """Ids of the scenarios that were sized, in scenarios.yaml order."""
        return [sid for sid, r in self.run.results.items() if r.status == "computed"]


def used_params(data: ReportData) -> set[str]:
    """Ids of the catalog Params that some trace node reads (`param:<id>`), all scenarios."""
    refs = {
        ref.removeprefix("param:")
        for tracer in data.tracers.values()
        for node in tracer.nodes
        for ref in node.inputs.values()
        if ref.startswith("param:")
    }
    return refs & set(data.catalog.params)


BIDI_FORMATS = dict.fromkeys(
    [*range(0x202A, 0x202F), *range(0x2066, 0x206A)]
)  # embeddings, overrides, isolates


def printable(text: str, keep: str = "") -> str:
    """`text` as plain text: each control character (a form feed, a NUL, a tab...) and each line or
    paragraph separator (U+2028, U+2029) is a space, except those in `keep`; the bidirectional
    overrides (U+202A-202E, U+2066-2069) are dropped, as one prints the name reversed. A form feed
    in the HTML body garbles the PDF text layer of its page."""
    flat = "".join(
        " " if c not in keep and unicodedata.category(c) in ("Cc", "Zl", "Zp") else c for c in text
    )
    return flat.translate(BIDI_FORMATS)


def load_report_data(run: RunOutput, lang: Lang) -> ReportData:
    """Gather the inputs of a report once and build its tables (see the module docstring)."""
    from whsizing.report.tables import build_tables  # tables import this module's types

    if lang not in LANGS:
        raise ConfigError(f"report: unsupported language {lang!r} (use one of {', '.join(LANGS)})")
    d = Path(run.run_dir)
    for rel in ("inputs/catalog", "inputs/basis.yaml", "profile/demand_profile.json"):
        if not (d / rel).exists():
            raise ConfigError(f"report: {d / rel} is missing: not a finished run folder")
    profile = _model(DemandProfile, d, "profile/demand_profile.json")
    basis = load_basis(d / "inputs" / "basis.yaml")
    data = ReportData(
        run=run,
        lang=lang,
        basis=basis.model_copy(
            update={"client": printable(basis.client), "site": printable(basis.site)}
        ),
        catalog=load_catalog(d / "inputs" / "catalog"),
        profile=profile,
        design_day=_model(DesignDay, d, "design/design_day.json"),
        dq=_model(DQReport, d, "dq/dq_report.json"),
        ingest=_model(IngestManifest, d, "dq/ingest_manifest.json"),
        daily=_daily(d / profile.daily_series_path),
        tracers=_tracers(run),
        tables={},
    )
    return dataclasses.replace(data, tables=build_tables(data))


def _model[M: BaseModel](model: type[M], run_dir: Path, rel: str) -> M:
    """A JSON file of the run folder as `model`; `ConfigError` when unreadable or invalid."""
    path = run_dir / rel
    try:
        return model.model_validate_json(path.read_text(encoding="utf-8"))
    except OSError as e:
        raise ConfigError(f"report: cannot read {path} ({e.strerror})") from e
    except ValidationError as e:
        first = e.errors()[0]["msg"] if e.errors() else "invalid"
        raise ConfigError(f"report: {path} is not a valid {model.__name__}: {first}") from e


def _daily(path: Path) -> pl.DataFrame:
    try:
        return pl.read_parquet(path, glob=False)  # I75 i: a path with [ ] * ? is literal
    except (pl.exceptions.PolarsError, OSError) as e:
        raise ConfigError(f"report: cannot read the daily series {path}: {e}") from e


def _tracers(run: RunOutput) -> dict[str, Tracer]:
    out: dict[str, Tracer] = {}
    for sid, result in run.results.items():
        path = Path(run.run_dir) / result.trace_path
        try:
            tracer = Tracer.load_jsonl(path) if path.is_file() else Tracer(sid)
        except (ValueError, OSError) as e:  # ValidationError is a ValueError
            raise ConfigError(f"report: cannot read the trace {path}: {e}") from e
        if result.status == "computed":
            _record_n_warnings(tracer, sid, result)
        out[sid] = tracer
    return out


def export_trace(data: ReportData, path: Path | str) -> Path:
    """Write the nodes of every scenario trace (and the report's own) to `path` as JSON lines,
    scenarios in `scenarios.yaml` order, nodes in recording order: the same run gives the same
    bytes. A node id recorded with two contents is a `WhsizingError`."""
    merged = Tracer()
    try:
        for tracer in data.tracers.values():
            for n in tracer.nodes:
                merged.record(n.id, n.label, n.value, n.unit, n.formula, n.inputs, n.scope, n.world)
    except ValueError as e:
        raise WhsizingError(f"report: the scenario traces disagree: {e}") from e
    out = Path(path)
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        merged.export_jsonl(out)
    except OSError as e:
        raise WhsizingError(f"report: cannot write the trace {out} ({e.strerror})") from e
    return out


def _record_n_warnings(tracer: Tracer, sid: str, result: ScenarioResult) -> None:
    node_id = f"{sid}.report.n_warnings"
    if any(n.id == node_id and n.world == "typ" for n in tracer.nodes):
        return  # recorded upstream (F6 / F8): theirs stands
    raised = [f for f in result.flags if f.severity != "info"]
    tracer.record(
        node_id,
        "Flags of severity warning or blocking",
        float(len(raised)),
        "-",
        "count(flags with severity != info)",
        {"flags": f"data:{sid}.flags"},
        scope=sid,  # a loaded Tracer is scoped "global"
    )

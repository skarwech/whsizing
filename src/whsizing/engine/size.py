"""F6z: `size_scenario` runs eligibility → storage → throughput and equipment → labor → area →
queue → flags once per world (lo = pessimistic, typ, hi = optimistic) and merges the worlds into
Ranges (ADR-002); `write_scenario` writes `scenarios/<id>/result.json` and `trace.jsonl`.

    sku = sku_frame(tables, sku_master)                                   # I58, once per run
    dd = select_design_day(profile, basis, tables.daily, sku=sku, catalog=catalog)
    tracer = Tracer(scenario.id)                                          # one per scenario
    result = size_scenario(profile, basis, dd, scenario, catalog, sku, tables.daily, tracer,
                           lines=tables.lines)                            # I61
    write_scenario(result, tracer, project_dir)

Booleans, docks, queue pools, flags and the bottleneck are the typical world's; every world is
traced in full (I62). Flags follow the I46 order, each code carrying its I46 suffix
(`F_HEIGHT_LIMIT:<class>`, `F_ELIG_ASSUMED:<share, 6 decimals>`, `F_UNSTABLE:<pool>`,
`F_LOW_CONFIDENCE:<n>`). Trace ids added here (typ world): `<sid>.low_confidence_params`
(I47, inputs = the Params counted) and `<sid>.flags.<code>` for every flag with a value, the
code without a numeric `:<value>` suffix (`flags.F_LOW_CONFIDENCE`, `flags.F_RATIO_DRIFT:units`).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import NamedTuple

import polars as pl

from whsizing.catalog import Catalog
from whsizing.catalog.models import CatalogParam
from whsizing.engine.area import AreaWorld, area_result, size_area
from whsizing.engine.inputs import WORLDS, WorldInputs, to_range, world_inputs
from whsizing.engine.labor import LaborDays, labor_days, labor_result, size_labor
from whsizing.engine.queue import QueueWorld, queue_result, size_queue
from whsizing.engine.shifts import LaborWorld
from whsizing.engine.storage import StorageWorld, size_storage, storage_result
from whsizing.engine.throughput import ThroughputWorld, size_throughput
from whsizing.errors import ConfigError
from whsizing.schemas import (
    DemandProfile,
    DesignBasis,
    DesignDay,
    FamilyId,
    Flag,
    ScenarioDef,
    ScenarioResult,
    World,
)
from whsizing.schemas.trace import Tracer

# I30, I35: the manual cost Params an automated scenario does not pay in its overflow zone
NOT_IN_OVERFLOW = frozenset({"wms_adaptation_fixed_eur", "software_eur_year"})
SCENARIO_ID = re.compile(r"[A-Za-z0-9_-]+")  # one path segment of scenarios/<id>/
# trace key of the quantity a flag's value is (the rest: design-day flags, data:design_day.*)
FLAG_SOURCE = {
    "F_NO_FIT": "area.deficit_m2",
    "F_ELIG_LOW": "eligibility.share_lines",
    "F_ELIG_ASSUMED": "eligibility.assumed_share_lines",
    "F_ROBOT_DENSITY": "equipment.{density}",
    "F_DOCK_SHORTFALL": "docks.shortfall",
    "F_UNSTABLE": "queue.{pool}.offered_load",
    "F_SLA_RISK": "queue.{pool}.p_wait_gt_t",
    "F_LOW_CONFIDENCE": "low_confidence_params",
}
DENSITY = {"cube_asrs": "robots_per_grid_m2", "amr_gtp": "robots_per_storage_m2"}


class Sized(NamedTuple):
    """One world of one scenario."""

    inp: WorldInputs
    storage: StorageWorld
    throughput: ThroughputWorld
    labor: LaborWorld
    area: AreaWorld
    queue: QueueWorld


def size_scenario(
    profile: DemandProfile,
    basis: DesignBasis,
    design_day: DesignDay,
    scenario: ScenarioDef,
    catalog: Catalog,
    sku: pl.DataFrame,
    daily: pl.DataFrame,
    tracer: Tracer,
    *,
    lines: pl.DataFrame,
) -> ScenarioResult:
    """F6 for one scenario (spec order, every world). `sku` = `sku_frame` (I58), `daily` and
    `lines` = the F3 `ProfileTables.daily` and `.lines` (I61). `profile` is kept for the spec
    signature: share_S (I15) comes from the shipped lines (`LaborDays.single_line_share`), the
    one value F6c and F6d both use. Edge cases are the parts': zero eligible lines degenerate
    to manual (I48, F_ELIG_LOW), levels floor at 1 (F_HEIGHT_LIMIT), F_NO_FIT never stops."""
    del profile  # I61 signature; nothing of F3's profile is read here (share_S: LaborDays)
    _check_id(scenario.id)
    worlds: dict[World, Sized] = {}
    days: LaborDays | None = None
    for w in WORLDS:
        inp = world_inputs(basis, design_day, scenario, catalog, sku, w, tracer)
        st = size_storage(inp)
        tp = size_throughput(inp, st)
        days = days or labor_days(inp, daily, lines)  # data only: the same in every world
        lw = size_labor(inp, tp, days)
        aw = size_area(inp, st, tp, roster=lw.roster, share_s=days.single_line_share)
        worlds[w] = Sized(inp, st, tp, lw, aw, size_queue(inp, tp, aw))
    typ = worlds["typ"]
    return ScenarioResult(
        scenario=scenario,
        eligibility=typ.inp.eligibility,
        storage=storage_result({w: s.storage for w, s in worlds.items()}, typ.inp.eligibility),
        equipment={
            k: to_range({w: s.throughput.equipment[k] for w, s in worlds.items()}, "-")
            for k in typ.throughput.equipment
        },
        bottleneck=typ.throughput.bottleneck,
        labor=labor_result({w: s.labor for w, s in worlds.items()}),
        area=area_result({w: s.area for w, s in worlds.items()}),
        queue=queue_result({w: s.queue for w, s in worlds.items()}),
        flags=_flags(typ),
        trace_path=f"scenarios/{scenario.id}/trace.jsonl",
    )


def write_scenario(result: ScenarioResult, tracer: Tracer, project_dir: Path | str) -> Path:
    """Write `<project_dir>/scenarios/<id>/result.json` (pydantic JSON: fixed field order, same
    bytes for the same result) and `trace.jsonl` (`Tracer.export_jsonl`); returns the folder."""
    out = Path(project_dir) / "scenarios" / _check_id(result.scenario.id)
    out.mkdir(parents=True, exist_ok=True)
    (out / "result.json").write_text(result.model_dump_json(indent=2) + "\n", encoding="utf-8")
    tracer.export_jsonl(out / "trace.jsonl")
    return out


def _check_id(sid: str) -> str:
    """The scenario id names the folder `scenarios/<id>/`: letters, digits, `_` and `-` only."""
    if not SCENARIO_ID.fullmatch(sid):
        raise ConfigError(f"scenario id {sid!r}: use letters, digits, '_' or '-' only")
    return sid


def _flags(typ: Sized) -> list[Flag]:
    """I46 order (typ world, I62): F_NO_FIT, F_HEIGHT_LIMIT:<class>, F_ELIG_LOW,
    F_ELIG_ASSUMED:<share>, F_SCALE_LOW, F_ROBOT_DENSITY, F_DOCK_SHORTFALL, F_UNSTABLE /
    F_SLA_RISK:<pool>, the design-day flags in F4's order (F_DEFAULT_UPP last, I59) with the
    severities F4 gave them, F_LOW_CONFIDENCE:<n> (I47) when n ≥ 1."""
    inp, area = typ.inp, typ.area.flags
    elig = inp.eligibility
    suffix = {"F_ELIG_ASSUMED": f"F_ELIG_ASSUMED:{elig.assumed_share_lines:.6f}"}
    n = len(_low_confidence(inp))
    low = Flag(
        code=f"F_LOW_CONFIDENCE:{n}",
        severity="info",
        message=f"the result depends on {n} parameter(s) of confidence L",
        value=float(n),
    )
    flags = [
        *(f for f in area if f.code == "F_NO_FIT"),
        *typ.storage.flags,  # F_HEIGHT_LIMIT:<class>
        *(f.model_copy(update={"code": suffix.get(f.code, f.code)}) for f in elig.flags),
        *typ.throughput.flags,  # F_SCALE_LOW, F_ROBOT_DENSITY
        *(f for f in area if f.code != "F_NO_FIT"),  # F_DOCK_SHORTFALL
        *typ.queue.flags,
        *inp.design_day.flags,  # severities as F4 wrote them (I70, I77)
        *([low] if n else []),
    ]
    for f in flags:
        _trace_flag(inp, f)
    return flags


def _trace_flag(inp: WorldInputs, flag: Flag) -> None:
    """`<sid>.flags.<code>` = the flag's value, from the quantity it reports (T6.11)."""
    if flag.value is None:
        return
    key = re.sub(r":[0-9.]+$", "", flag.code)  # F_LOW_CONFIDENCE:30 → F_LOW_CONFIDENCE
    base, _, pool = key.partition(":")
    density = DENSITY.get(inp.scenario.family, "")
    source = (
        inp.tid(FLAG_SOURCE[base].format(pool=pool, density=density))
        if base in FLAG_SOURCE
        else "data:design_day.lines"
        if base == "F_SCALE_LOW"
        else "data:design_day.flags"
    )
    inp.record(f"flags.{key}", f"Value of {key}", flag.value, "-", "flag value", {"of": source})


def _low_confidence(inp: WorldInputs) -> list[str]:
    """I47: the distinct confidence-L catalog Param blocks the scenario's formulas read: every
    `param:` of its typ-world F6 trace, plus the F7 cost Params (I29-I35): the family's capex
    and opex Params, for an automated family the manual ones of its overflow zone (all but
    wms_adaptation_fixed_eur, software_eur_year), finance.packaging_eur_per_order, and
    finance.kwh_per_station_year with stations or ports. Traced as `low_confidence_params`."""
    catalog, fam, sid = inp.catalog, inp.scenario.family, inp.scenario.id
    read = {
        ref.removeprefix("param:")
        for n in inp.tracer.nodes
        if n.world == "typ" and n.scope == sid
        for ref in n.inputs.values()
        if ref.startswith("param:")
    }
    read |= _cost_params(catalog, fam, frozenset()) | {"finance.packaging_eur_per_order"}
    if fam != "manual_p2p":
        read |= _cost_params(catalog, "manual_p2p", NOT_IN_OVERFLOW)
        read |= {"finance.kwh_per_station_year"}
    ids = sorted(p for p in read if p in catalog.params and catalog.params[p].confidence == "L")
    inp.record(
        "low_confidence_params",
        "Parameters of confidence L the scenario reads",
        float(len(ids)),
        "-",
        "count(distinct confidence-L Params read by F6 and F7)",
        {p: f"param:{p}" for p in ids},
    )
    return ids


def _cost_params(catalog: Catalog, fam: FamilyId, skip: frozenset[str]) -> set[str]:
    """Ids of the Param blocks in the capex and opex sections of a family file."""
    f = catalog.families[fam]
    return {
        f"{fam}.{key}"
        for section in (f.capex, f.opex)
        for key, value in section
        if isinstance(value, CatalogParam) and key not in skip
    }

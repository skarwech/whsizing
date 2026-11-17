"""F9a tables of the data side: design_basis, demand_profile, design_day, assumptions,
data_quality and methodology (see `tables`). No scenario columns, so no trace ids (IC1 covers
the scenario tables); every value is the raw number of the run's own JSON files."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from whsizing.report.cells import EMPTY, key, num, text
from whsizing.report.data import used_params
from whsizing.schemas import (
    Cell,
    DemandProfile,
    DesignDay,
    ReportTable,
    SeriesStats,
    TableBlock,
    TableColumn,
    TableRow,
)
from whsizing.schemas.report import CellFmt

if TYPE_CHECKING:
    from whsizing.report.data import ReportData

STATS = ("mean", "p50", "p90", "p95", "p98", "max", "cv")
SHARE_COLUMNS = ("n_skus", "sku_share", "line_share", "cube_share")
FIXED_LIMITS = ("indicative", "placeholders", "ranges", "ranking", "scope", "model")
FORMULAS_KEY = "methodology.formulas"


def cols(*names: str, prefix: str = "col.") -> list[TableColumn]:
    return [TableColumn(key=n, label=key(f"{prefix}{n}")) for n in names]


def block(
    block_key: str,
    columns: list[TableColumn],
    rows: list[TableRow],
    label_header: str | None = None,
) -> TableBlock:
    return TableBlock(
        key=block_key,
        title=key(f"block.{block_key}"),
        label_header=None if label_header is None else key(label_header),
        columns=columns,
        rows=rows,
    )


def row(row_key: str, label: Cell, *cells: Cell) -> TableRow:
    return TableRow(key=row_key, label=label, cells=list(cells))


def table(table_id: str, blocks: list[TableBlock], notes: Sequence[Cell] = ()) -> ReportTable:
    return ReportTable(
        id=table_id, title=key(f"table.{table_id}"), blocks=blocks, notes=list(notes)
    )


def design_basis(data: ReportData) -> ReportTable:
    """Every basis field (F4 assumptions): dotted key, value, unit, origin, note."""
    rows = [
        row(
            f"basis.{a.key}",
            text(a.key),
            num(a.value, "num", a.unit) if isinstance(a.value, float) else text(str(a.value)),
            text(a.unit),
            key(f"origin.{a.origin}"),
            text(a.note),
        )
        for a in data.design_day.assumptions
    ]
    columns = cols("value", "unit", "origin", "note")
    return table("design_basis", [block("design_basis", columns, rows, "col.field")])


def _stats_rows(prefix: str, items: list[tuple[str, SeriesStats]]) -> list[TableRow]:
    rows: list[TableRow] = []
    for name, s in items:
        fmt: CellFmt = (
            "dec2" if name in ("cube_m3", "cube_per_order_m3", "units_per_line") else "dec1"
        )
        cells = [num(getattr(s, st), "dec2" if st == "cv" else fmt) for st in STATS]
        rows.append(row(f"{prefix}.{name}", key(f"series.{name}"), *cells))
    return rows


def value_block(block_key: str, prefix: str, items: list[tuple[str, Cell]]) -> TableBlock:
    """A block of one value column: row `<prefix>.<name>` labelled `row.<name>`."""
    rows = [row(f"{prefix}.{k}", key(f"row.{k}"), c) for k, c in items]
    return block(block_key, cols("value"), rows)


def demand_profile(data: ReportData) -> ReportTable:
    p = data.profile
    return table(
        "demand_profile",
        [*_profile_stats(p), *_profile_abc(p), *_profile_seasonality(p), _profile_split(p)],
    )


def _profile_stats(p: DemandProfile) -> list[TableBlock]:
    """Data period, daily series and order structure (EIQ)."""
    stat_cols = cols(*STATS, prefix="stat.")
    info = [
        ("period_start", Cell(value=p.period_start.isoformat(), fmt="date")),
        ("period_end", Cell(value=p.period_end.isoformat(), fmt="date")),
        ("operating_days", num(p.operating_days, "int")),
        ("dims_coverage_lines", num(p.dims_coverage_lines, "pct")),
        ("peak_hour_share", num(p.peak_hour_share, "pct")),
        ("intraday_confidence", text(p.intraday_confidence)),
    ]
    eiq = p.eiq
    eiq_items = [
        ("lines_per_order", eiq.lines_per_order),
        ("units_per_line", eiq.units_per_line),
        ("units_per_order", eiq.units_per_order),
        ("cube_per_order_m3", eiq.cube_per_order_m3),
        ("weight_per_order_kg", eiq.weight_per_order_kg),
    ]
    classes = [("single_line_share", num(eiq.single_line_share, "pct"))]
    classes += [(f"order_class.{c}", num(v, "pct")) for c, v in eiq.order_class_shares.items()]
    return [
        value_block("profile_period", "profile", info),
        block(
            "profile_daily", stat_cols, _stats_rows("daily", list(p.daily.items())), "col.series"
        ),
        block("profile_eiq", stat_cols, _stats_rows("eiq", eiq_items), "col.series"),
        value_block("profile_order_classes", "eiq", classes),
    ]


def _profile_abc(p: DemandProfile) -> list[TableBlock]:
    out: list[TableBlock] = []
    for name, by in (
        ("lines", p.abc.by_lines),
        ("cube_movement", p.abc.by_cube_movement),
        ("stock_cube", p.abc.by_stock_cube),
    ):
        rows = [
            row(
                f"abc.{name}.{c}",
                text(c),
                num(s.n_skus, "int"),
                num(s.sku_share, "pct"),
                num(s.line_share, "pct"),
                num(s.cube_share, "pct"),
            )
            for c, s in by.items()
        ]
        out.append(block(f"profile_abc_{name}", cols(*SHARE_COLUMNS), rows, "col.class"))
    return out


def _profile_seasonality(p: DemandProfile) -> list[TableBlock]:
    s = p.seasonality
    months = [
        row(f"season.month.{m}", key(f"month.{m}"), num(v, "dec2"))
        for m, v in enumerate(s.monthly_index, 1)
    ]
    weekdays = [
        row(f"season.weekday.{d}", key(f"weekday.{d}"), num(v, "dec2"))
        for d, v in enumerate(s.weekday_index)
    ]
    stats = [
        ("peak_to_average", num(s.peak_to_average, "dec2")),
        ("trend_cagr", num(s.trend_cagr, "pct")),
        ("trend_confidence", text(s.trend_confidence)),
        ("confidence", text(s.confidence)),
    ]
    return [
        block("profile_monthly", cols("value"), months, "col.month"),
        block("profile_weekday", cols("value"), weekdays, "col.weekday"),
        value_block("profile_seasonality", "season", stats),
    ]


def _profile_split(p: DemandProfile) -> TableBlock:
    sp = p.shipment_split
    shares = (
        "parcel_share_orders",
        "pallet_share_orders",
        "parcel_share_lines",
        "pallet_share_lines",
    )
    items = [(k, num(getattr(sp, k), "pct")) for k in shares]
    items.append(("mean_parcels_per_order", num(sp.mean_parcels_per_order, "dec2")))
    return value_block("profile_split", "split", items)


def design_day(data: ReportData) -> ReportTable:
    d = data.design_day
    basics = [
        ("percentile", num(d.percentile, "num")),
        ("growth_rate", num(d.growth_rate, "pct")),
        ("horizon_years", num(d.horizon_years, "int")),
        ("reference_date", Cell(value=d.reference_date.isoformat(), fmt="date")),
        ("design_weekday", key(f"weekday.{d.design_weekday}")),
        ("peak_hour_lines", num(d.peak_hour_lines, "dec1")),
        ("stock_units", num(d.stock_units, "int")),
        ("stock_cube_m3", num(d.stock_cube_m3, "dec1")),
    ]
    blocks = [
        value_block("dd_basics", "dd", basics),
        block(
            "dd_metrics", cols("ratio_derived", "percentile_value"), _metric_rows(d), "col.metric"
        ),
        block("dd_hourly", cols("lines", "share"), _hourly_rows(d), "col.hour"),
        _inbound_block(d),
    ]
    flags = _design_day_flags(d)
    if flags:
        blocks.append(block("dd_flags", cols("value"), flags))
    return table("design_day", blocks)


def _metric_rows(d: DesignDay) -> list[TableRow]:
    names = ("orders", "lines", "units", "cube_m3", "weight_kg", "parcels", "pallets_out")
    return [
        row(
            f"metric.{m}",
            key(f"metric.{m}"),
            num(getattr(d, m), "dec2"),
            num(d.percentile_values.get(m), "dec2"),
        )
        for m in names
    ]


def _hourly_rows(d: DesignDay) -> list[TableRow]:
    total = sum(d.hourly_lines) or 1.0
    return [
        row(f"hour.{h}", text(f"{h:02d}:00"), num(v, "dec1"), num(v / total, "pct"))
        for h, v in enumerate(d.hourly_lines)
    ]


def _inbound_block(d: DesignDay) -> TableBlock:
    ib = d.inbound
    items = [
        ("mode", key(f"inbound.mode.{ib.mode}")),
        ("units_per_day", num(ib.units_per_day, "int")),
        ("pallets_per_day", num(ib.pallets_per_day, "dec1")),
        ("receipt_lines_per_day", num(ib.receipt_lines_per_day, "int")),
        ("trucks_per_day", num(ib.trucks_per_day, "dec1")),
        ("peak_factor", num(ib.peak_factor, "dec2")),
        ("cases_per_day", num(ib.cases_per_day, "int")),
    ]
    return value_block("dd_inbound", "inbound", items)


def _design_day_flags(d: DesignDay) -> list[TableRow]:
    return [
        row(
            f"flag.{f.code}",
            key(f"flag.{f.code.split(':')[0]}", detail=_detail(f.code)),
            num(f.value, "dec2") if f.value is not None else key(f"severity.{f.severity}"),
        )
        for f in [*d.flags, *d.inbound.flags]
    ]


def _detail(code: str) -> str:
    return code.partition(":")[2]


def scenario_overrides(data: ReportData) -> dict[str, dict[str, float]]:
    """Scenario id -> {param id: value} of the overrides the run sized with (the `<sid>:<pid>` keys
    of the manifest's params_snapshot, I88), in scenario order; scenarios with none are left out."""
    found: dict[str, dict[str, float]] = {}
    for k, v in data.run.manifest.params_snapshot.items():
        sid, sep, pid = k.partition(":")
        if sep:
            found.setdefault(sid, {})[pid] = v
    return {sid: found[sid] for sid in data.run.results if sid in found}


def assumptions(data: ReportData) -> ReportTable:
    """One row per catalog Param: the value used by every scenario without an override (typ after
    the client's basis overrides), and one column headed by the scenario id per scenario that
    overrides some Param (I88): the cell holds the value that scenario was sized with, empty when
    it did not override the Param (a table note says so). Origin `override` marks a Param some
    scenario overrides (even when the client's basis overrides it too: the base value column then
    holds the client's value and the scenario column its own); `client` a Param only the basis
    overrides."""
    snap = data.run.manifest.params_snapshot
    overrides = scenario_overrides(data)
    overridden = {pid for o in overrides.values() for pid in o}
    client = data.basis.overrides
    rows: list[TableRow] = []
    for pid, p in sorted(data.catalog.params.items()):
        origin = "override" if pid in overridden else "client" if pid in client else "default"
        scenario_cells = [
            num(o[pid], "num", p.unit) if pid in o else EMPTY for o in overrides.values()
        ]
        rows.append(
            row(
                f"param.{pid}",
                text(pid),
                text(pid.split(".", 1)[1].replace("_", " ")),
                num(snap.get(pid, p.typ), "num", p.unit),
                text(p.unit),
                num(p.min, "num"),
                num(p.typ, "num"),
                num(p.max, "num"),
                text(p.source),
                text(p.confidence),
                text(p.validated_by or ""),
                key(f"origin.{origin}"),
                text(p.note or ""),
                *scenario_cells,
            )
        )
    names = (
        "label", "value_used", "unit", "min", "typ", "max", "source", "confidence",
        "validated_by", "origin", "note",
    )  # fmt: skip
    columns = cols(*names) + [
        TableColumn(key=f"override.{sid}", label=text(sid)) for sid in overrides
    ]
    notes = (
        [key("assumptions.scenario_columns", scenarios=", ".join(overrides))] if overrides else []
    )
    return table("assumptions", [block("assumptions", columns, rows, "col.id")], notes)


def data_quality(data: ReportData) -> ReportTable:
    dq, ing = data.dq, data.ingest
    coverage = {**ing.coverage, **dq.coverage}
    cov_rows = [
        row(
            f"dq.coverage.{k}",
            key(f"dq.coverage.{k}"),
            num(v, "dec1" if k.endswith("months") else "pct"),
        )
        for k, v in coverage.items()
    ]
    dropped = [
        row(
            f"dq.rows.{d.dataset}",
            key(f"dataset.{d.dataset}"),
            num(d.rows_in, "int"),
            num(d.rows_out, "int"),
            num(sum(d.dropped_by_rule.values()), "int"),
        )
        for d in ing.datasets
    ]
    rule_cols = cols("dataset", "severity", "count", "share", "dropped", "message")
    blocks = [
        block("dq_score", cols("value"), _dq_score_rows(data)),
        block("dq_coverage", cols("value"), cov_rows),
        block("dq_rules", rule_cols, _dq_rule_rows(data), "col.rule"),
        block("dq_rows", cols("rows_in", "rows_out", "dropped"), dropped, "col.dataset"),
    ]
    return table("data_quality", blocks, [text(n) for n in dq.notes])


def _dq_score_rows(data: ReportData) -> list[TableRow]:
    dq = data.dq
    rows = [
        row("dq.score", key("row.dq_score"), num(dq.score, "dec1", "/100")),
        row("dq.band", key("row.dq_band"), key(f"dq.band.{dq.band}")),
    ]
    return rows + [
        row(f"dq.points.{k}", key(f"dq.points.{k}"), num(v, "dec1", signed=True))
        for k, v in dq.score_breakdown.items()
    ]


def _dq_rule_rows(data: ReportData) -> list[TableRow]:
    return [
        row(
            f"dq.rule.{r.rule}.{r.dataset}",
            key(f"dq.rule.{r.rule}"),
            text(r.dataset),
            key(f"severity.{r.severity}"),
            num(r.count, "int"),
            num(r.share, "pct"),
            num(r.dropped, "int"),
            text(r.message),
        )
        for r in data.dq.rules
    ]


def finance_notes(data: ReportData) -> list[Cell]:
    """The notes of the finance results (scope of the client baseline, why NPV, IRR or payback is
    None), each once with the scenarios it applies to. F7 writes them in English: shown as is."""
    by_note: dict[str, list[str]] = {}
    for sid, fin in data.run.finances.items():
        for note in fin.notes:
            by_note.setdefault(note, []).append(sid)
    return [text(f"{', '.join(sids)}: {note}") for note, sids in by_note.items()]


def methodology(data: ReportData) -> ReportTable:
    m, cat = data.run.manifest, data.catalog
    used = used_params(data)
    low_used = sum(cat.params[p].confidence == "L" for p in used)
    todo_used = sum(cat.params[p].source == "TODO" for p in used)
    versions = [
        ("run_id", text(m.run_id)),
        ("engine_version", text(m.engine_version)),
        ("catalog_version", text(m.catalog_version)),
        ("git_sha", text(m.git_sha)),
        ("created_at", Cell(value=m.created_at.date().isoformat(), fmt="date")),
        ("n_params", num(len(cat.params), "int")),
        ("n_params_used", num(len(used), "int")),
        ("n_todo_catalog", num(cat.todo_count, "int")),
        ("n_todo_used", num(todo_used, "int")),
        ("n_low_confidence_used", num(low_used, "int")),
    ]
    limits = [row(f"limit.{k}", key(f"limit.{k}")) for k in FIXED_LIMITS]
    limits += _generated_limits(data, len(used), todo_used, low_used)
    return table(
        "methodology",
        [
            block(
                "methodology_versions",
                cols("value"),
                [row(f"method.{k}", key(f"row.{k}"), c) for k, c in versions],
            ),
            block("methodology_limits", [], limits),
            block("methodology_formulas", [], [row("formulas", key(FORMULAS_KEY))]),
        ],
        [key("banner.indicative")],
    )


def _generated_limits(data: ReportData, n_used: int, n_todo: int, n_low: int) -> list[TableRow]:
    """The limitations generated from the run: TODO-sourced and confidence-L parameters, the
    flags raised, scenarios not computed, no baseline, the finance notes (§8 of the PDF)."""
    out = [
        row("limit.gen.todo", key("limit.gen.todo", n=n_todo, total=n_used)),
        row("limit.gen.low_confidence", key("limit.gen.low_confidence", n=n_low, total=n_used)),
        row("limit.gen.dq", key(f"limit.gen.dq.{data.dq.band}", score=data.dq.score)),
    ]
    for r in data.run.comparison.rows:
        sid = r.scenario_id
        if r.status == "not_computed":
            out.append(
                row(
                    f"limit.gen.not_computed.{sid}",
                    key("limit.gen.not_computed", scenario=sid, reason=r.status_reason or ""),
                )
            )
            continue
        raised = [f.code for f in data.run.results[sid].flags if f.severity != "info"]
        out.append(
            row(
                f"limit.gen.confidence.{sid}",
                key("limit.gen.confidence", scenario=sid, n=r.n_low_confidence_params),
            )
        )
        if raised:
            out.append(
                row(
                    f"limit.gen.flags.{sid}",
                    key("limit.gen.flags", scenario=sid, flags=", ".join(raised)),
                )
            )
    if not any(r.npv_vs_baseline is not None for r in data.run.comparison.rows):
        out.append(row("limit.gen.no_baseline", key("limit.gen.no_baseline")))
    out += [row(f"limit.gen.finance.{i}", c) for i, c in enumerate(finance_notes(data))]
    return out

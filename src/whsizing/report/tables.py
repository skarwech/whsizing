"""F9a report tables: one typed model for the Excel sheets and the PDF sections.

`build_tables(data)` returns the twelve `ReportTable`s keyed by `TABLE_IDS` (the sheet / section
names of the spec); `load_report_data` stores them in `ReportData.tables`. Cells hold raw values
(`whsizing.schemas.report`); labels are i18n keys, formatted at render time. This module builds
the scenario-side tables (summary, scenarios); `tables_fin` the business case (fte, capex_opex,
cash_flow, sensitivity) and `tables_data` the data side (design basis, demand profile, design
day, assumptions, data quality, methodology). `used_keys(tables)` lists every i18n key a set of
tables needs (IC8).

Edge cases: a scenario not computed keeps its columns, greyed (`TableColumn.disabled_reason`)
with empty cells; with no baseline the NPV and payback rows are left out (the business-case
tables then show absolute values), and so is the ranking by payback when nothing is ranked.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import TYPE_CHECKING

from whsizing.report.cells import Tr, key, num, text, union
from whsizing.report.grid import Getter, Grid, Value
from whsizing.report.i18n import NUMERIC_TAIL as NUMERIC_SUFFIX  # `F_ELIG_ASSUMED:0.25`: a value
from whsizing.schemas import (
    Cell,
    ComparisonRow,
    Range,
    ReportTable,
    StorageClassResult,
    TableBlock,
    TableColumn,
    TableRow,
)
from whsizing.schemas.report import CellFmt

if TYPE_CHECKING:
    from whsizing.report.data import ReportData

TABLE_IDS = (
    "summary",
    "design_basis",
    "demand_profile",
    "design_day",
    "scenarios",
    "fte",
    "capex_opex",
    "cash_flow",
    "sensitivity",
    "assumptions",
    "data_quality",
    "methodology",
)


def build_tables(data: ReportData) -> dict[str, ReportTable]:
    from whsizing.report import tables_data as d
    from whsizing.report import tables_fin as f

    built = [
        summary(data),
        d.design_basis(data),
        d.demand_profile(data),
        d.design_day(data),
        scenarios(data),
        f.fte(data),
        f.capex_opex(data),
        f.cash_flow(data),
        f.sensitivity(data),
        d.assumptions(data),
        d.data_quality(data),
        d.methodology(data),
    ]
    return {t.id: t for t in built}


def summary(data: ReportData) -> ReportTable:
    g = Grid(data)
    comparison = TableBlock(
        key="comparison",
        title=key("block.summary.comparison"),
        columns=g.columns,
        rows=_comparison_rows(g),
    )
    return ReportTable(
        id="summary",
        title=key("table.summary"),
        blocks=[_study_block(data), comparison, _ranking_block(data)],
        notes=[key("banner.indicative"), _confidence_note(data)],
    )


def _comparison_rows(g: Grid) -> list[TableRow]:
    """The comparison table, one traced row per `ComparisonRow` field (T9.2); NPV and payback
    only when some scenario has them (a baseline)."""
    cmp = g.data.run.comparison
    by_id = {r.scenario_id: r for r in cmp.rows}

    def of(attr: str) -> Getter:
        return lambda sid: getattr(by_id[sid], attr)

    rows = [
        g.row(
            "eligible_share",
            "row.eligible_share",
            "eligibility.share_lines",
            of("eligible_line_share"),
            "pct",
        ),
        g.row("fit", "row.fit", "area.fit", of("fit"), "bool"),
        g.row(
            "storage_area",
            "row.storage_area",
            "storage.total_area_m2",
            of("storage_area_m2"),
            "int",
        ),
        g.row("total_area", "row.total_area", "area.total", of("total_area_m2"), "int"),
    ]
    for eq in union(r.equipment for r in cmp.rows):

        def get(sid: str, eq: str = eq) -> Range | None:
            return by_id[sid].equipment.get(eq)

        rows.append(g.row(f"equipment.{eq}", f"equipment.{eq}", f"equipment.{eq}", get, "int"))
    rows += [
        g.row("fte_design_day", "row.fte_design_day", "labor.total.heads", of("fte_design_day")),
        g.row("core_fte_y1", "row.core_fte_y1", "labor.core_fte.y1", of("core_fte_year1")),
        g.row("roster", "row.roster", "labor.total.roster", of("roster")),
    ]
    return [*rows, *_money_rows(g, of, cmp.rows)]


def _money_rows(g: Grid, of: Callable[[str], Getter], rows: list[ComparisonRow]) -> list[TableRow]:
    """Capex, opex, TCO, NPV and payback (only with a baseline), cost per line, warnings."""
    out = [
        g.row("capex", "row.capex", "capex.total", of("capex"), "eur"),
        g.row("opex_y1", "row.opex_y1", "opex.y1.total", of("opex_year1"), "eur"),
        g.row("tco", "row.tco", "finance.tco", of("tco"), "eur"),
    ]
    if any(r.npv_vs_baseline is not None for r in rows):  # a baseline: NPV and payback
        by_id = {r.scenario_id: r for r in rows}
        out.append(
            g.row("npv", "row.npv", "finance.npv", of("npv_vs_baseline"), "eur", signed=True)
        )
        out.append(
            g.payback_row(
                "payback", lambda s: by_id[s].npv_vs_baseline, lambda s: by_id[s].payback_years
            )
        )
    return [
        *out,
        g.row(
            "cost_per_line",
            "row.cost_per_line",
            "finance.cost_per_line",
            of("cost_per_line"),
            "dec2",
        ),
        g.row("n_warnings", "row.n_warnings", "report.n_warnings", of("n_warnings"), "int"),
        g.row(
            "n_low_confidence",
            "row.n_low_confidence",
            "low_confidence_params",
            of("n_low_confidence_params"),
            "int",
        ),
    ]


def _study_block(data: ReportData) -> TableBlock:
    m, basis, dq = data.run.manifest, data.basis, data.dq
    base = data.run.comparison.baseline_id
    rows = [
        ("client", text(basis.client)),
        ("site", text(basis.site)),
        ("run_id", text(m.run_id)),
        ("date", Cell(value=m.created_at.date().isoformat(), fmt="date")),
        ("engine_version", text(m.engine_version)),
        ("catalog_version", text(m.catalog_version)),
        ("dq_band", key(f"dq.band.{dq.band}")),
        ("dq_score", num(dq.score, "dec1", "/100")),
        ("baseline", _baseline_cell(base)),
    ]
    return TableBlock(
        key="study",
        title=key("block.summary.study"),
        columns=[TableColumn(key="value", label=key("col.value"))],
        rows=[TableRow(key=k, label=key(f"row.{k}"), cells=[c]) for k, c in rows],
    )


def _baseline_cell(baseline_id: str | None) -> Cell:
    if baseline_id is None:
        return key("baseline.none")
    if baseline_id == "client_current":
        return key("baseline.client_current")
    return text(baseline_id)


def _ranking_block(data: ReportData) -> TableBlock:
    cmp = data.run.comparison
    rows = [
        TableRow(
            key=f"ranking.{name}",
            label=key(f"row.ranking_{name}"),
            cells=[text(" < ".join(ids))],
        )
        for name, ids in (("tco", cmp.ranking_tco), ("payback", cmp.ranking_payback))
        if ids  # no baseline, or no payback reached: no empty "ranking by payback" row
    ]
    return TableBlock(
        key="ranking",
        title=key("block.summary.ranking"),
        columns=[TableColumn(key="value", label=key("col.value"))],
        rows=rows,
    )


def _confidence_note(data: ReportData) -> Cell:
    """`Comparison.confidence_note` localised from `Comparison.overlaps` (F8 leaves it to F9)."""
    pairs = "; ".join(f"{a} – {b}" for a, b in data.run.comparison.overlaps)
    if not pairs:
        return key("summary.confidence.clear")
    return key("summary.confidence.overlap", pairs=pairs)


def scenarios(data: ReportData) -> ReportTable:
    g = Grid(data)
    res = data.run.results
    blocks = [
        ("eligibility", _eligibility(g)),
        ("storage", _storage(g)),
        ("equipment", _equipment_rows(g)),
        ("area", _area(g, union(r.area.zones for r in res.values()))),
        ("flags", _flags(g)),
    ]
    return ReportTable(
        id="scenarios",
        title=key("table.scenarios"),
        blocks=[
            TableBlock(key=k, title=key(f"block.scenarios.{k}"), columns=g.columns, rows=rows)
            for k, rows in blocks
        ],
    )


def _eligibility(g: Grid) -> list[TableRow]:
    res = g.data.run.results
    fields: list[tuple[str, CellFmt]] = [
        ("share_lines", "pct"),
        ("share_stock_cube", "pct"),
        ("share_skus", "pct"),
        ("assumed_share_lines", "pct"),
        ("n_skus_eligible", "int"),
        ("n_skus_total", "int"),
    ]
    return [
        g.row(
            f"eligibility.{n}",
            f"row.elig.{n}",
            f"eligibility.{n}",
            lambda sid, n=n: getattr(res[sid].eligibility, n),
            fmt,
        )
        for n, fmt in fields
    ]


def _classes(g: Grid, sid: str) -> dict[tuple[str, str], StorageClassResult]:
    return {(c.zone, c.storage_class): c for c in g.data.run.results[sid].storage.classes}


STORAGE_FIELDS = ("n_skus", "positions", "levels", "area_m2", "pods", "grid_area_m2")


def _storage(g: Grid) -> list[TableRow]:
    res = g.data.run.results
    classes = {sid: _classes(g, sid) for sid in res}
    present = union([[f"{z}.{c}" for z, c in cs] for cs in classes.values()])
    rows: list[TableRow] = []
    for zc in present:
        zone, cls = zc.split(".")
        trace_prefix = f"storage.{'overflow.' if zone == 'overflow' else ''}{cls}"
        rows.append(g.section(f"storage.{zc}", key(f"storage.class.{zone}.{cls}")))
        for name in STORAGE_FIELDS:

            def get(sid: str, name: str = name, zone: str = zone, cls: str = cls) -> Value:
                c = classes[sid].get((zone, cls))
                return None if c is None else getattr(c, name)

            if any(get(sid) is not None for sid in res):
                rows.append(
                    g.row(
                        f"storage.{zc}.{name}",
                        f"storage.field.{name}",
                        f"{trace_prefix}.{name}",
                        get,
                        "int",
                    )
                )
    rows.append(
        g.row(
            "storage.total_area_m2",
            "row.storage_total",
            "storage.total_area_m2",
            lambda sid: res[sid].storage.total_area_m2,
            "int",
            kind="total",
        )
    )
    rows.append(
        g.row(
            "storage.height_utilisation",
            "row.height_utilisation",
            "storage.height_utilisation",
            lambda sid: res[sid].storage.height_utilisation,
            "pct",
        )
    )
    return rows


def _equipment_rows(g: Grid) -> list[TableRow]:
    res = g.data.run.results
    rows = [
        g.row(
            f"equipment.{k}",
            f"equipment.{k}",
            f"equipment.{k}",
            lambda sid, k=k: res[sid].equipment.get(k),
            "int",
        )
        for k in union(r.equipment for r in res.values())
    ]

    def bottleneck(sid: str, tr: Tr) -> Cell:
        return Cell(value=f"equipment.{res[sid].bottleneck}", fmt="key")

    return [*rows, g.custom("bottleneck", key("row.bottleneck"), bottleneck)]


def _area(g: Grid, zones: list[str]) -> list[TableRow]:
    res = g.data.run.results
    rows = [
        g.row(
            f"area.zone.{z}",
            f"zone.{z}",
            f"area.{z}",
            lambda sid, z=z: res[sid].area.zones.get(z),
            "int",
        )
        for z in zones
    ]
    rows.append(
        g.row(
            "area.total",
            "row.area_total",
            "area.total",
            lambda sid: res[sid].area.total_m2,
            "int",
            kind="total",
        )
    )
    scalars: list[tuple[str, str, str, str, CellFmt, str]] = [
        ("area.building_m2", "row.building_m2", "area.building_m2", "building_m2", "int", "m2"),
        ("area.docks_in", "row.docks_in", "docks.in", "docks_in_required", "dec1", ""),
        ("area.docks_out", "row.docks_out", "docks.out", "docks_out_required", "dec1", ""),
        (
            "area.icpe_volume_m3",
            "row.icpe_volume",
            "area.icpe_volume_m3",
            "icpe_volume_m3",
            "int",
            "m3",
        ),
        ("area.fit", "row.fit", "area.fit", "fit", "bool", ""),
        ("area.utilisation", "row.utilisation", "area.utilisation", "utilisation", "pct", ""),
        ("area.deficit_m2", "row.deficit", "area.deficit_m2", "deficit_m2", "int", ""),
    ]
    rows += [
        g.row(rk, label, tkey, lambda sid, a=attr: getattr(res[sid].area, a), fmt, unit=unit)
        for rk, label, tkey, attr, fmt, unit in scalars
    ]

    def regime(sid: str, tr: Tr) -> Cell | None:
        label = res[sid].area.icpe_regime
        return text(label) if label else None

    return [*rows, g.custom("area.icpe_regime", key("row.icpe_regime"), regime)]


def _flags(g: Grid) -> list[TableRow]:
    """One row per distinct flag code (`F_UNSTABLE:packing` is one row per pool); the cell is the
    flag's value (traced `<sid>.flags.<code>`) or its severity when it has none."""
    res = g.data.run.results
    codes = union([[NUMERIC_SUFFIX.sub("", f.code) for f in r.flags] for r in res.values()])
    rows: list[TableRow] = []
    for code in codes:
        base, _, detail = code.partition(":")

        def fn(sid: str, tr: Tr, code: str = code) -> Cell | None:
            for f in res[sid].flags:
                if NUMERIC_SUFFIX.sub("", f.code) == code:
                    if f.value is None:
                        return Cell(value=f"severity.{f.severity}", fmt="key")
                    fmt: CellFmt = "int" if float(f.value).is_integer() else "dec2"
                    return tr.scalar(f"flags.{code}", f.value, fmt)
            return None

        rows.append(g.custom(f"flags.{code}", key(f"flag.{base}", detail=detail), fn))
    return rows


def iter_cells(tables: dict[str, ReportTable]) -> Iterator[tuple[str, Cell]]:
    """(location, cell) of every cell of `tables`: titles, notes, column labels and groups, row
    labels and the cells themselves. Location = `<table>/<block>/<row>/<column>`."""
    for table in tables.values():
        yield f"{table.id}/title", table.title
        for i, n in enumerate(table.notes):
            yield f"{table.id}/note{i}", n
        for block in table.blocks:
            where = f"{table.id}/{block.key}"
            if block.title is not None:
                yield f"{where}/title", block.title
            if block.label_header is not None:
                yield f"{where}/label_header", block.label_header
            for col in block.columns:
                yield f"{where}/{col.key}/label", col.label
                if col.group is not None:
                    yield f"{where}/{col.key}/group", col.group
            for row in block.rows:
                yield f"{where}/{row.key}/label", row.label
                for col, cell in zip(block.columns, row.cells, strict=False):
                    yield f"{where}/{row.key}/{col.key}", cell


def used_keys(tables: dict[str, ReportTable]) -> set[str]:
    """Every i18n key the cells, column labels and titles of `tables` use (IC8)."""
    return {
        str(c.value) for _, c in iter_cells(tables) if c.fmt == "key" and isinstance(c.value, str)
    }

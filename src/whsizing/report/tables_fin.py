"""F9a tables of the sized results: fte, capex_opex, cash_flow and sensitivity (see `tables`)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from whsizing.report.cells import EMPTY, Tr, key, num, text, union
from whsizing.report.grid import Getter, Grid
from whsizing.report.tables_data import cols, finance_notes
from whsizing.schemas import (
    Cell,
    Range,
    ReportTable,
    Sensitivity,
    TableBlock,
    TableColumn,
    TableRow,
)
from whsizing.schemas.report import CellFmt

if TYPE_CHECKING:
    from whsizing.report.data import ReportData

LABOR_TOTALS = (("hours", "total_hours"), ("heads", "total_heads"), ("roster", "roster"))
ANNUAL: tuple[tuple[str, CellFmt], ...] = (
    ("annual_hours", "int"),
    ("core_fte", "dec1"),
    ("temp_hours", "int"),
)


def fte(data: ReportData) -> ReportTable:
    """Hours, heads and roster per activity (and in total) on the design day, then the annual
    hours, core FTE and temporary hours of years 1..T, each scenario in lo / typ / hi."""
    g = Grid(data)
    res = data.run.results
    activities = union([[a.activity for a in r.labor.activities] for r in res.values()])
    blocks: list[TableBlock] = []
    for metric, total_attr in LABOR_TOTALS:
        rows = [
            g.row(
                f"fte.{metric}.{a}", f"activity.{a}", f"labor.{a}.{metric}", _activity(g, a, metric)
            )
            for a in activities
        ]
        rows.append(
            g.row(
                f"fte.{metric}.total",
                "row.total",
                f"labor.total.{metric}",
                lambda sid, attr=total_attr: getattr(res[sid].labor, attr),
                kind="total",
            )
        )
        blocks.append(
            TableBlock(key=metric, title=key(f"block.fte.{metric}"), columns=g.columns, rows=rows)
        )
    years = max((len(r.labor.core_fte) for r in res.values()), default=0)
    for name, fmt in ANNUAL:
        rows = [
            g.row(
                f"fte.{name}.y{t}", "row.year", f"labor.{name}.y{t}", _annual(g, name, t), fmt, n=t
            )
            for t in range(1, years + 1)
        ]
        blocks.append(
            TableBlock(key=name, title=key(f"block.fte.{name}"), columns=g.columns, rows=rows)
        )
    return ReportTable(id="fte", title=key("table.fte"), blocks=blocks)


def _activity(g: Grid, activity: str, metric: str) -> Getter:
    def get(sid: str) -> Range | None:
        for a in g.data.run.results[sid].labor.activities:
            if a.activity == activity:
                return getattr(a, metric)
        return None

    return get


def _annual(g: Grid, name: str, t: int) -> Getter:
    def get(sid: str) -> Range | None:
        series: list[Range] = getattr(g.data.run.results[sid].labor, name)
        return series[t - 1] if t <= len(series) else None

    return get


def capex_opex(data: ReportData) -> ReportTable:
    """Capex by item and the totals (lo / typ / hi), then the opex of each year by item (typical
    world: FinancialResult holds no lo / hi per year). NPV and payback only with a baseline; the
    notes of the finance results (baseline scope, why a metric is None) under the table."""
    g = Grid(data)
    blocks = [
        TableBlock(
            key="capex",
            title=key("block.capex_opex.capex"),
            columns=g.columns,
            rows=_capex_rows(g),
        ),
        TableBlock(
            key="totals",
            title=key("block.capex_opex.totals"),
            columns=g.columns,
            rows=_business_rows(g),
        ),
        _opex_by_year(data),
    ]
    return ReportTable(
        id="capex_opex",
        title=key("table.capex_opex"),
        blocks=blocks,
        notes=finance_notes(data),
    )


def _fin(g: Grid, attr: str) -> Getter:
    fins = g.data.run.finances
    return lambda sid: getattr(fins[sid], attr) if sid in fins else None


def _capex_rows(g: Grid) -> list[TableRow]:
    fins = g.data.run.finances
    items = union([list(f.capex) for f in fins.values()])
    rows = [
        g.row(
            f"capex.{i}",
            f"capex.item.{i}",
            f"capex.{i}",
            lambda sid, i=i: fins[sid].capex.get(i) if sid in fins else None,
            "eur",
        )
        for i in items
    ]
    total = g.row(
        "capex.total", "row.total", "capex.total", _fin(g, "capex_total"), "eur", kind="total"
    )
    return [*rows, total]


def _business_rows(g: Grid) -> list[TableRow]:
    """Opex of year 1, TCO, cost per line, and with a baseline the NPV and the payback."""
    fins = g.data.run.finances
    rows = [
        g.row("business.opex_y1", "row.opex_y1", "opex.y1.total", _fin(g, "opex_year1"), "eur"),
        g.row("business.tco", "row.tco", "finance.tco", _fin(g, "tco"), "eur"),
        g.row(
            "business.cost_per_line",
            "row.cost_per_line",
            "finance.cost_per_line",
            _fin(g, "cost_per_line"),
            "dec2",
        ),
    ]
    if any(f.npv_vs_baseline is not None for f in fins.values()):  # a baseline
        npv = _fin(g, "npv_vs_baseline")
        rows.append(g.row("business.npv", "row.npv", "finance.npv", npv, "eur", signed=True))
        rows.append(
            g.payback_row(
                "business.payback",
                lambda s: fins[s].npv_vs_baseline if s in fins else None,
                lambda s: fins[s].payback_years if s in fins else None,
            )
        )
    return rows


def _opex_by_year(data: ReportData) -> TableBlock:
    g = Grid(data, worlds=False)
    fins = data.run.finances
    years = max((len(f.opex_by_year) for f in fins.values()), default=0)
    items = union([list(row) for f in fins.values() for row in f.opex_by_year])

    def year_item(t: int, item: str | None) -> Getter:
        def get(sid: str) -> float | None:
            f = fins.get(sid)
            if f is None or t > len(f.opex_by_year):
                return None
            year = f.opex_by_year[t - 1]
            return sum(year.values()) if item is None else year.get(item)

        return get

    rows: list[TableRow] = []
    for t in range(1, years + 1):
        rows.append(g.section(f"opex.y{t}", key("row.year", n=t)))
        rows += [
            g.row(
                f"opex.y{t}.{i}",
                f"opex.item.{i}",
                f"opex.y{t}.{i}",
                year_item(t, i),
                "eur",
                unit="eur",
            )
            for i in items
        ]
        rows.append(
            g.row(
                f"opex.y{t}.total",
                "row.total",
                f"opex.y{t}.total",
                year_item(t, None),
                "eur",
                unit="eur",
                kind="total",
            )
        )
    return TableBlock(
        key="opex_by_year", title=key("block.capex_opex.opex"), columns=g.columns, rows=rows
    )


def cash_flow(data: ReportData) -> ReportTable:
    """Years 0..T: each scenario's own cash flow, its Δ against the baseline and the cumulative
    Δ (IC6). Without any baseline the cumulative is that of the own flow. When the baseline is a
    scenario, its Δ against itself is 0 by definition: it has no Δ and no cumulative column, so
    the cumulative columns all mean the same thing. All signed, typical world."""
    fins = data.run.finances
    vs_baseline = any(f.delta_cash_flows_typ for f in fins.values())
    columns: list[TableColumn] = []
    series: list[list[Cell]] = []  # per column: its cell for each year
    for sid in data.run.results:
        cols_, cells = _scenario_flows(data, sid, vs_baseline)
        columns += cols_
        series += cells
    years = max((len(f.cash_flows_typ) for f in fins.values()), default=1)
    rows = [
        TableRow(
            key=f"cash.y{t}",
            label=key("row.year", n=t),
            cells=[cells[t] if t < len(cells) else EMPTY for cells in series],
        )
        for t in range(years)
    ]
    block = TableBlock(
        key="cash_flow", title=key("block.cash_flow.flows"), columns=columns, rows=rows
    )
    baselines = [sid for sid, f in fins.items() if vs_baseline and not f.delta_cash_flows_typ]
    notes = [key("cash.baseline_scenario", baseline=", ".join(baselines))] if baselines else []
    return ReportTable(id="cash_flow", title=key("table.cash_flow"), blocks=[block], notes=notes)


def _scenario_flows(
    data: ReportData, sid: str, vs_baseline: bool
) -> tuple[list[TableColumn], list[list[Cell]]]:
    """The columns of one scenario (own flow, Δ if it has a baseline, cumulative) and the cells
    of each, year 0 first. `vs_baseline`: some scenario has a Δ, so a computed scenario without
    one is the baseline."""
    r, f = data.run.results[sid], data.run.finances.get(sid)
    group = text(f"{sid} · {r.scenario.name}")
    reason = r.status_reason if r.status == "not_computed" else None
    tr = Tr(data.tracers[sid], sid)
    own = f.cash_flows_typ if f else []
    delta = f.delta_cash_flows_typ if f else []
    spec = [("cash_flow", "finance.cash_flow.y", own)]
    if delta:
        spec.append(("delta", "finance.delta_cf.y", delta))
    columns = [_col(sid, kind, group, reason) for kind, _, _ in spec]
    cells = [
        [tr.scalar(f"{tkey}{t}", v, "eur", "eur", signed=True) for t, v in enumerate(vals)]
        for _, tkey, vals in spec
    ]
    if f is not None and vs_baseline and not delta:  # the baseline scenario: Δ = 0, no cumulative
        return columns, cells
    flows = delta or own
    columns.append(_col(sid, "cumulative", group, reason))
    cells.append([num(sum(flows[: t + 1]), "eur", "eur", signed=True) for t in range(len(flows))])
    return columns, cells


def _col(sid: str, kind: str, group: Cell, reason: str | None) -> TableColumn:
    return TableColumn(
        key=f"{sid}.{kind}",
        label=key(f"col.{kind}"),
        group=group,
        scenario_id=sid,
        world="typ",
        kind=kind,
        disabled_reason=reason,
    )


def sensitivity(data: ReportData) -> ReportTable:
    s = data.run.sensitivity
    title = key("table.sensitivity")
    if s is None:
        return ReportTable(
            id="sensitivity", title=title, blocks=[], notes=[key("sensitivity.not_run")]
        )
    return ReportTable(
        id="sensitivity",
        title=title,
        blocks=[_tornado_block(s), _break_even_block(s), _sweep_block(s)],
    )


def _tornado_block(s: Sensitivity) -> TableBlock:
    rows = [
        TableRow(
            key=f"tornado.{b.scenario_id}.{b.param}",
            label=key(f"sens.param.{b.param}"),
            cells=[
                text(b.scenario_id),
                num(b.low_input, "num"),
                num(b.high_input, "num"),
                num(b.tco_low, "eur", "eur"),
                num(b.tco_high, "eur", "eur"),
                num(b.delta_tco, "eur", "eur"),
                num(b.payback_low, "dec1", "years"),
                num(b.payback_high, "dec1", "years"),
                num(b.fte_low, "dec1", "FTE"),
                num(b.fte_high, "dec1", "FTE"),
            ],
        )
        for b in s.tornado
    ]
    names = (
        "scenario_id",
        "low_input",
        "high_input",
        "tco_low",
        "tco_high",
        "delta_tco",
        "payback_low",
        "payback_high",
        "fte_low",
        "fte_high",
    )
    return TableBlock(
        key="tornado",
        title=key("block.sensitivity.tornado"),
        label_header=key("col.param"),
        columns=cols(*names),
        rows=rows,
    )


def _break_even_block(s: Sensitivity) -> TableBlock:
    rows = [
        TableRow(
            key=f"break_even.{b.scenario_id}",
            label=text(b.scenario_id),
            cells=[
                num(b.target_payback_years, "dec1", "years"),
                num(b.labor_cost_multiplier, "dec2"),
                _break_even_sentence(
                    b.scenario_id, b.labor_cost_multiplier, b.target_payback_years
                ),
            ],
        )
        for b in s.break_even
    ]
    return TableBlock(
        key="break_even",
        title=key("block.sensitivity.break_even"),
        label_header=key("col.scenario_id"),
        columns=cols("target_payback", "labor_cost_multiplier", "sentence"),
        rows=rows,
    )


def _sweep_block(s: Sensitivity) -> TableBlock:
    eq = union([list(p.equipment) for p in s.percentile_sweep])
    rows = [
        TableRow(
            key=f"sweep.{p.scenario_id}.p{p.percentile:g}",
            label=text(p.scenario_id),
            cells=[
                num(p.percentile, "num"),
                num(p.design_lines, "int"),
                *(num(p.equipment.get(e), "int") for e in eq),
                num(p.fte, "dec1", "FTE"),
                num(p.capex, "eur", "eur"),
                num(p.tco, "eur", "eur"),
            ],
        )
        for p in s.percentile_sweep
    ]
    columns = cols("percentile", "design_lines")
    columns += [TableColumn(key=f"eq.{e}", label=key(f"equipment.{e}")) for e in eq]
    columns += cols("fte", "capex", "tco")
    return TableBlock(
        key="percentile_sweep",
        title=key("block.sensitivity.sweep"),
        label_header=key("col.scenario_id"),
        columns=columns,
        rows=rows,
    )


def _break_even_sentence(sid: str, multiplier: float | None, years: float) -> Cell:
    if multiplier is None:
        return key("sens.break_even.none", scenario=sid, years=years)
    return key("sens.break_even.sentence", scenario=sid, years=years, pct=multiplier * 100)

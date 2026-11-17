"""F9a integrity checks IC1-IC8 (spec F9): a failed check fails the build (exit 5).

    issues = check_integrity(run)                  # [] on a sound report
    issues = check_integrity(run, html=rendered)   # + IC8 on the rendered HTML
    assert_integrity(run, html)                    # ReportIntegrityError listing the issues

The checks read the report tables (what is rendered) and the scenario traces, not result.json,
so a tampered table or trace is caught. `check_integrity(run, data=...)` reuses a `ReportData`
the caller already loaded.

IC1  every numeric cell in a scenario column of summary, scenarios, fte and capex_opex has a
     trace id, that `(id, world)` is a node of the scenario's tracer and holds the cell's value
IC2  every TraceNode input resolves to `param:<id>` (a catalog Param or constant), a `data:`
     node, or a node of the same tracer and world
IC3  no Param used by a trace without a source; the methodology table reports the count of
     source TODO parameters (§8) and it equals the count recomputed from the traces
IC4  area budget total = sum of the zones within 0.5 m² (every scenario column)
IC5  FTE hours, heads and roster totals = sums of the activities
IC6  each cumulative cash flow = running sum of the Δ cash flows (of the scenario's own cash
     flows when no scenario has a baseline); the baseline scenario has no cumulative column, so
     the table has no other reading of "cumulative"
IC7  every non-negative quantity (unit m2, h, eur, or a cell shown as euros) is >= 0; cells marked
     `signed` (NPV, Δ and own cash flows, cumulative, sensitivity deltas) are signed by nature
IC8  no `{{ missing:<key> }}` sentinel in the rendered HTML; without HTML, every i18n key and
     placeholder the tables use renders in both languages
"""

from __future__ import annotations

import math
import re

from whsizing.errors import ReportIntegrityError
from whsizing.report.data import ReportData, load_report_data, used_params
from whsizing.report.i18n import LANGS, MISSING_PREFIX, render_cell
from whsizing.report.tables import iter_cells
from whsizing.schemas import Cell, IntegrityIssue, ReportTable, TableBlock, TableRow
from whsizing.schemas.report import CheckId
from whsizing.schemas.run import RunOutput

IC1_TABLES = ("summary", "scenarios", "fte", "capex_opex")
AREA_TOLERANCE_M2 = 0.5
NON_NEGATIVE_UNITS = frozenset({"m2", "h", "eur"})
SENTINEL = re.compile(r"\{\{ missing[^}]*\}\}")
MAX_LISTED = 20


def check_integrity(
    run: RunOutput, *, html: str | None = None, data: ReportData | None = None
) -> list[IntegrityIssue]:
    """IC1-IC8 on `run` (see the module docstring); `html` = a rendered report, for IC8."""
    return run_checks(data or load_report_data(run, "en"), html)


def assert_integrity(
    run: RunOutput, html: str | None = None, *, data: ReportData | None = None
) -> None:
    """Raise `ReportIntegrityError` (exit 5) when `check_integrity` finds an issue."""
    issues = check_integrity(run, html=html, data=data)
    if issues:
        listed = "\n".join(f"  {i.id} {i.location}: {i.message}" for i in issues[:MAX_LISTED])
        more = f"\n  ... and {len(issues) - MAX_LISTED} more" if len(issues) > MAX_LISTED else ""
        raise ReportIntegrityError(f"report integrity: {len(issues)} issue(s)\n{listed}{more}")


def run_checks(data: ReportData, html: str | None = None) -> list[IntegrityIssue]:
    """The eight checks on already loaded data (the tamper tests change `data` and call this)."""
    return [
        *ic1_trace_ids(data),
        *ic2_trace_inputs(data),
        *ic3_sources(data),
        *ic4_area(data),
        *ic5_fte(data),
        *ic6_cash_flow(data),
        *ic7_units(data),
        *ic8_i18n(data, html),
    ]


def _issue(check: CheckId, message: str, location: str) -> IntegrityIssue:
    return IntegrityIssue(id=check, severity="error", message=message, location=location)


def _num(cell: Cell) -> float | None:
    """The raw number of a numeric cell, None for text, i18n keys, dates and empty cells."""
    v = cell.value
    return (
        float(v) if isinstance(v, int | float) and cell.fmt not in ("text", "key", "date") else None
    )


def _close(a: float, b: float, tol: float = 1e-9) -> bool:
    return math.isclose(a, b, rel_tol=tol, abs_tol=tol)


def _scenario_cells(table: ReportTable):
    """(location, column scenario id, cell) of the cells in scenario columns of `table`."""
    for block in table.blocks:
        for row in block.rows:
            for col, cell in zip(block.columns, row.cells, strict=False):
                if col.scenario_id is not None:
                    yield f"{table.id}/{block.key}/{row.key}/{col.key}", col.scenario_id, cell


def ic1_trace_ids(data: ReportData) -> list[IntegrityIssue]:
    issues: list[IntegrityIssue] = []
    nodes = {sid: {(n.id, n.world): n.value for n in t.nodes} for sid, t in data.tracers.items()}
    for name in IC1_TABLES:
        for where, sid, cell in _scenario_cells(data.tables[name]):
            value = _num(cell)
            if value is None:
                continue
            if cell.trace_id is None:
                issues.append(_issue("IC1", "numeric cell without a trace id", where))
                continue
            traced = nodes.get(sid, {}).get((cell.trace_id, cell.world or "typ"))
            if traced is None:
                msg = f"trace node {cell.trace_id} ({cell.world or 'typ'}) does not exist"
                issues.append(_issue("IC1", msg, where))
            elif not _close(traced, value):
                msg = f"cell value {value} differs from trace node {cell.trace_id}: {traced}"
                issues.append(_issue("IC1", msg, where))
    return issues


def ic2_trace_inputs(data: ReportData) -> list[IntegrityIssue]:
    issues: list[IntegrityIssue] = []
    known = set(data.catalog.params) | set(data.catalog.constants)
    for sid, tracer in data.tracers.items():
        present = {(n.id, n.world) for n in tracer.nodes}
        for n in tracer.nodes:
            for symbol, ref in n.inputs.items():
                if ref.startswith("param:"):
                    ok = ref.removeprefix("param:") in known
                else:
                    ok = ref.startswith("data:") or (ref, n.world) in present
                if not ok:
                    msg = f"input {symbol} = {ref} resolves to no Param, data or node ({n.world})"
                    issues.append(_issue("IC2", msg, f"trace {sid}/{n.id}"))
    return issues


def ic3_sources(data: ReportData) -> list[IntegrityIssue]:
    issues = [
        _issue("IC3", f"Param {pid} is used without a source", f"catalog/{pid}")
        for pid in sorted(used_params(data))
        if not data.catalog.params[pid].source.strip()
    ]
    used = used_params(data)
    expected = sum(data.catalog.params[p].source == "TODO" for p in used)
    reported = _limit_arg(data.tables["methodology"], "limit.gen.todo", "n")
    if reported is None or reported != expected:
        msg = f"the TODO-source count reported for §8 is {reported}, the traces use {expected}"
        issues.append(_issue("IC3", msg, "methodology/limit.gen.todo"))
    return issues


def _limit_arg(table: ReportTable, row_key: str, arg: str) -> float | str | None:
    for block in table.blocks:
        for row in block.rows:
            if row.key == row_key:
                return row.label.args.get(arg)
    return None


def _block(table: ReportTable, key: str) -> TableBlock | None:
    return next((b for b in table.blocks if b.key == key), None)


def _column_sum(rows: list[TableRow], i: int) -> float:
    return sum(v for r in rows if (v := _num(r.cells[i])) is not None)


def ic4_area(data: ReportData) -> list[IntegrityIssue]:
    block = _block(data.tables["scenarios"], "area")
    if block is None:
        return []
    zones = [r for r in block.rows if r.key.startswith("area.zone.")]
    total = next((r for r in block.rows if r.key == "area.total"), None)
    issues: list[IntegrityIssue] = []
    for i, col in enumerate(block.columns):
        want = None if total is None else _num(total.cells[i])
        if want is None or col.disabled_reason:
            continue
        gap = abs(_column_sum(zones, i) - want)
        if gap > AREA_TOLERANCE_M2:
            msg = f"area total differs from the sum of the zones by {gap:.2f} m2"
            issues.append(_issue("IC4", msg, f"scenarios/area/{col.key}"))
    return issues


def ic5_fte(data: ReportData) -> list[IntegrityIssue]:
    issues: list[IntegrityIssue] = []
    for metric in ("hours", "heads", "roster"):
        block = _block(data.tables["fte"], metric)
        if block is None:
            continue
        total = next((r for r in block.rows if r.key == f"fte.{metric}.total"), None)
        parts = [r for r in block.rows if r is not total]
        for i, col in enumerate(block.columns):
            want = None if total is None else _num(total.cells[i])
            if want is None or col.disabled_reason:
                continue
            got = _column_sum(parts, i)
            if not _close(got, want, 1e-6):
                msg = f"{metric} total {want:.4f} differs from the sum of the activities {got:.4f}"
                issues.append(_issue("IC5", msg, f"fte/{metric}/{col.key}"))
    return issues


def ic6_cash_flow(data: ReportData) -> list[IntegrityIssue]:
    block = _block(data.tables["cash_flow"], "cash_flow")
    if block is None:
        return []
    issues: list[IntegrityIssue] = []
    by_kind = {(c.scenario_id, c.kind): i for i, c in enumerate(block.columns)}
    vs_baseline = any(kind == "delta" for _, kind in by_kind)  # Δ columns exist: sum those only
    for (sid, kind), i in by_kind.items():
        if kind != "cumulative" or block.columns[i].disabled_reason:
            continue
        src = by_kind.get((sid, "delta" if vs_baseline else "cash_flow"))
        if src is None:
            msg = "cumulative column without the Δ cash flow column it should sum"
            issues.append(_issue("IC6", msg, f"cash_flow/{sid}"))
            continue
        running = 0.0
        for row in block.rows:
            running += _num(row.cells[src]) or 0.0
            shown = _num(row.cells[i])
            if shown is not None and not _close(shown, running, 1e-6):
                msg = f"cumulative {shown} differs from the sum of the flows {running}"
                issues.append(_issue("IC6", msg, f"cash_flow/{row.key}/{sid}"))
    return issues


def ic7_units(data: ReportData) -> list[IntegrityIssue]:
    issues: list[IntegrityIssue] = []
    for where, cell in iter_cells(data.tables):
        value = _num(cell)
        unit = cell.unit if cell.unit in NON_NEGATIVE_UNITS else "eur" if cell.fmt == "eur" else ""
        if value is not None and value < 0 and unit and not cell.signed:
            issues.append(_issue("IC7", f"negative value {value} with unit {unit}", where))
    return issues


def ic8_i18n(data: ReportData, html: str | None) -> list[IntegrityIssue]:
    if html is not None:
        return [
            _issue("IC8", f"untranslated text {m} in the rendered HTML", "html")
            for m in sorted(set(SENTINEL.findall(html)))
        ]
    issues: list[IntegrityIssue] = []
    for where, cell in iter_cells(data.tables):
        if cell.fmt != "key":
            continue
        for lang in LANGS:
            if MISSING_PREFIX in render_cell(cell, lang):
                msg = f"i18n key {cell.value} has no {lang} text (or a placeholder without value)"
                issues.append(_issue("IC8", msg, where))
    return issues

"""F9c generated text of the PDF: the key messages and caveats of the executive summary, the
scenario descriptions of section 4, the limitations of section 8 and the trace index of Appendix C.

Nothing is recomputed: every number in a sentence is a `Cell` of the report model printed by
`render_cell`; the one derived figure is the overflow share of section 4 (1 - the eligible share
of lines), which the F9a hand-off leaves to this module (there is no trace node for it).
The trace index reads `ReportData.tracers`: for each Summary number (typical world) the trace id,
the formula and the direct inputs with their values; `param:` inputs print the value used,
`data:basis.*` inputs the basis value, other `data:` inputs are dataset leaves (I79).
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from typing import Any

from whsizing.report.data import ReportData
from whsizing.report.i18n import Lang, fmt_number, fmt_pct, render_cell, t, unit_label
from whsizing.report.pdf_view import box
from whsizing.report.style import scenario_colours
from whsizing.schemas import Cell, TableBlock, TableRow
from whsizing.schemas.params import World
from whsizing.schemas.trace import Tracer

TRACE_LEVELS = 1  # 1: the Summary numbers; 2 adds the nodes they read; and so on
MAX_PARAM_INPUTS = 8  # a node reading more catalog parameters than this prints their count
LIMIT_FIXED_PREFIX = "limit.gen."
CAVEAT_KEYS = ("limit.indicative", "limit.gen.todo", "limit.gen.low_confidence", "limit.gen.dq")


def block_of(data: ReportData, table_id: str, block_key: str) -> TableBlock:
    return next(b for b in data.tables[table_id].blocks if b.key == block_key)


def row_of(block: TableBlock, row_key: str) -> TableRow | None:
    return next((r for r in block.rows if r.key == row_key), None)


def typ_cells(data: ReportData, table_id: str, block_key: str, row_key: str) -> dict[str, Cell]:
    """scenario id → the typical-world cell of a row, computed scenarios with a value only."""
    block = block_of(data, table_id, block_key)
    row = row_of(block, row_key)
    if row is None:
        return {}
    return {
        col.scenario_id: cell
        for col, cell in zip(block.columns, row.cells, strict=True)
        if col.scenario_id
        and col.world == "typ"
        and not col.disabled_reason
        and cell.value is not None
    }


def per_scenario(cells: dict[str, Cell], lang: Lang) -> str:
    """`S0: 12,3; S1: 9,8` from the cells of one row."""
    return "; ".join(f"{sid}: {box(c, lang).text}" for sid, c in cells.items())


def key_messages(data: ReportData) -> list[str]:
    """Three messages generated from the run (no 'recommended' label): the cost ranking with the
    overlap note, the business case, the labor and the space."""
    lang = data.lang
    cmp = data.run.comparison
    if not cmp.ranking_tco:
        return [t("msg.none", lang)]
    tco = typ_cells(data, "summary", "comparison", "tco")
    lowest = cmp.ranking_tco[0]
    cost = t(
        "msg.cost",
        lang,
        ranking=" < ".join(cmp.ranking_tco),
        scenario=lowest,
        tco=render_cell(tco[lowest], lang),
        note=render_cell(data.tables["summary"].notes[1], lang),
    )
    return [cost, _business_message(data), _people_space_message(data)]


def _business_message(data: ReportData) -> str:
    lang = data.lang
    payback = typ_cells(data, "summary", "comparison", "payback")
    if payback:
        study = block_of(data, "summary", "study")
        baseline = render_cell(row_of(study, "baseline").cells[0], lang)  # pyright: ignore[reportOptionalMemberAccess]
        return t("msg.payback", lang, baseline=baseline, items=per_scenario(payback, lang))
    per_line = typ_cells(data, "summary", "comparison", "cost_per_line")
    return t("msg.absolute", lang, items=per_scenario(per_line, lang))


def _people_space_message(data: ReportData) -> str:
    lang = data.lang
    heads = typ_cells(data, "summary", "comparison", "fte_design_day")
    areas = typ_cells(data, "summary", "comparison", "total_area")
    fits = typ_cells(data, "summary", "comparison", "fit")
    building = typ_cells(data, "scenarios", "area", "area.building_m2")
    area_text = render_cell(next(iter(building.values())), lang) if building else ""
    misfit = [sid for sid, c in fits.items() if not c.value]
    if misfit:
        fit = t("msg.fit_not", lang, scenarios=", ".join(misfit), building=area_text)
    else:
        fit = t("msg.fit_all", lang, building=area_text)
    return t(
        "msg.people_space",
        lang,
        heads=per_scenario(heads, lang),
        areas=per_scenario(areas, lang),
        fit=fit,
    )


def caveats(data: ReportData) -> list[str]:
    rows = {r.key: r for r in block_of(data, "methodology", "methodology_limits").rows}
    return [render_cell(rows[k].label, data.lang) for k in CAVEAT_KEYS if k in rows]


def limits(data: ReportData) -> tuple[list[str], list[str]]:
    """(fixed, generated) limitation texts of section 8."""
    fixed: list[str] = []
    generated: list[str] = []
    for r in block_of(data, "methodology", "methodology_limits").rows:
        text = render_cell(r.label, data.lang)
        (generated if r.key.startswith(LIMIT_FIXED_PREFIX) else fixed).append(text)
    return fixed, generated


@dataclass(frozen=True)
class ScenarioText:
    sid: str
    name: str
    family: str
    description: str
    computed: bool
    reason: str
    eligible: str
    overflow: str
    colour: str


def scenario_texts(data: ReportData) -> list[ScenarioText]:
    """One entry per scenario of scenarios.yaml: name, family paragraph (i18n), eligible share
    of lines and the overflow share (picked manually in an overflow zone)."""
    lang = data.lang
    share = typ_cells(data, "scenarios", "eligibility", "eligibility.share_lines")
    colours = scenario_colours(data.run.results)
    out: list[ScenarioText] = []
    for sid, r in data.run.results.items():
        fam = r.scenario.family
        cell = share.get(sid)
        out.append(
            ScenarioText(
                sid=sid,
                name=r.scenario.name,
                family=t(f"family.{fam}.name", lang),
                description=t(f"family.{fam}.description", lang),
                computed=r.status == "computed",
                reason=r.status_reason or "",
                eligible=render_cell(cell, lang) if cell else "",
                overflow=fmt_pct(1.0 - float(cell.value or 0.0), lang) if cell else "",
                colour=colours[sid],
            )
        )
    return out


# ---------------------------------------------------------------- trace index
@dataclass(frozen=True)
class TraceInput:
    symbol: str
    ref: str
    value: str  # "" for a dataset leaf without a value
    shown: str  # `ref` as printed: without the scenario prefix (the table says which scenario)

    @property
    def text(self) -> str:
        """`symbol = id`, or the id alone when it already contains the symbol."""
        return self.shown if self.symbol in self.shown else f"{self.symbol} = {self.shown}"


@dataclass(frozen=True)
class TraceItem:
    id: str
    label: str
    value: str
    formula: str
    inputs: list[TraceInput]
    note: str = ""  # replaces the inputs when they are only catalog parameters, many of them


@dataclass(frozen=True)
class TraceIndex:
    sid: str
    name: str
    items: list[TraceItem]


def trace_number(value: float, lang: Lang) -> str:
    """Two decimals (four below 1) so that the printed inputs add up to the printed total; a whole
    number (a count of flags or of parameters) is printed without decimals."""
    if value == round(value):
        return fmt_number(value, lang, 0)
    return fmt_number(value, lang, 2 if abs(value) >= 1 else 4)


def _basis_value(data: ReportData, ref: str) -> float | None:
    """`data:basis.a.b` → the number at that path of the design basis, None if there is none."""
    obj: Any = data.basis
    for part in ref.removeprefix("data:basis.").split("."):
        obj = obj.get(part) if isinstance(obj, dict) else getattr(obj, part, None)
    return float(obj) if isinstance(obj, int | float) and not isinstance(obj, bool) else None


def _param_value(data: ReportData, sid: str, pid: str) -> float | None:
    snap = data.run.manifest.params_snapshot
    param = data.catalog.params.get(pid)
    return snap.get(f"{sid}:{pid}", snap.get(pid, param.typ if param else None))


def _input_value(data: ReportData, tracer: Tracer, sid: str, ref: str, world: World) -> str:
    lang = data.lang
    value: float | None = None
    if ref.startswith("param:"):
        value = _param_value(data, sid, ref.removeprefix("param:"))
    elif ref.startswith("data:basis."):
        value = _basis_value(data, ref)
    elif not ref.startswith("data:"):
        try:
            value = tracer.get(ref, world).value
        except KeyError:
            value = None
    return "" if value is None else trace_number(value, lang)


def _short(ref: str, sid: str) -> str:
    return ref.removeprefix(f"{sid}.")


def _item(data: ReportData, tracer: Tracer, sid: str, node_id: str, world: World) -> TraceItem:
    node = tracer.get(node_id, world)
    unit = unit_label(node.unit) if node.unit not in ("", "-") else ""
    value = f"{trace_number(node.value, data.lang)} {unit}".strip()
    inputs = [
        TraceInput(sym, ref, _input_value(data, tracer, sid, ref, world), _short(ref, sid))
        for sym, ref in node.inputs.items()
    ]
    only_params = all(i.ref.startswith("param:") for i in inputs)
    if inputs and only_params and len(inputs) > MAX_PARAM_INPUTS:
        note = t("pdf.trace.params_n", data.lang, n=len(inputs))
        return TraceItem(node.id, "", value, node.formula, [], note)
    return TraceItem(node.id, "", value, node.formula, inputs)


def trace_index(data: ReportData) -> list[TraceIndex]:
    """The trace index of Appendix C: per computed scenario, the Summary numbers (typical world)
    with id, formula and inputs; `TRACE_LEVELS` > 1 adds the nodes those inputs are."""
    block = block_of(data, "summary", "comparison")
    out: list[TraceIndex] = []
    for sid in data.computed():
        tracer = data.tracers[sid]
        items: list[TraceItem] = []
        seen: set[str] = set()
        frontier: list[tuple[str, str]] = []
        for row in block.rows:
            cell = next(
                (
                    c
                    for col, c in zip(block.columns, row.cells, strict=True)
                    if col.scenario_id == sid and col.world == "typ" and c.trace_id
                ),
                None,
            )
            if cell is not None and cell.trace_id and cell.trace_id not in seen:
                seen.add(cell.trace_id)
                frontier.append((cell.trace_id, render_cell(row.label, data.lang)))
        for _ in range(TRACE_LEVELS):
            nxt: list[tuple[str, str]] = []
            for node_id, label in frontier:
                try:
                    item = _item(data, tracer, sid, node_id, "typ")
                except KeyError:  # a node the traces lack: IC1 reports it, the gate stops the build
                    continue
                items.append(dataclasses.replace(item, label=label))
                for i in item.inputs:
                    if i.ref not in seen and i.value and not i.ref.startswith(("param:", "data:")):
                        seen.add(i.ref)
                        nxt.append((i.ref, ""))
            frontier = nxt
        out.append(TraceIndex(sid, data.run.results[sid].scenario.name, items))
    return out


def break_even_sentences(data: ReportData) -> list[str]:
    """One sentence per scenario of the break-even block (empty without a sensitivity run)."""
    block = next((b for b in data.tables["sensitivity"].blocks if b.key == "break_even"), None)
    return [render_cell(r.cells[2], data.lang) for r in block.rows] if block else []

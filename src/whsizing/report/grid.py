"""F9a scenario-side table grid: one column per scenario (or lo / typ / hi each) and rows whose
cells come from a scenario's result, each traced to `<scenario id>.<trace key>`."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from whsizing.report.cells import EMPTY, WORLDS, Tr, key, text
from whsizing.schemas import Cell, Range, TableColumn, TableRow
from whsizing.schemas.report import CellFmt, RowKind

if TYPE_CHECKING:
    from whsizing.report.data import ReportData

Value = Range | float | bool | None
Getter = Callable[[str], Value]  # scenario id -> the value of this row
CellsFn = Callable[[str, Tr], "Cell | list[Cell] | None"]


class Grid:
    def __init__(self, data: ReportData, worlds: bool = True) -> None:
        self.data = data
        self.width = 3 if worlds else 1
        self.trs = {sid: Tr(data.tracers[sid], sid) for sid in data.run.results}

    @property
    def columns(self) -> list[TableColumn]:
        out: list[TableColumn] = []
        for sid, r in self.data.run.results.items():
            reason = r.status_reason if r.status == "not_computed" else None
            group = text(f"{sid} · {r.scenario.name}")
            for w in WORLDS if self.width == 3 else ("typ",):
                out.append(
                    TableColumn(
                        key=f"{sid}.{w}",
                        label=key(f"col.{w}"),
                        group=group,
                        scenario_id=sid,
                        world=w,
                        disabled_reason=reason,
                    )
                )
        return out

    def row(
        self,
        row_key: str,
        label_key: str,
        trace_key: str,
        get: Getter,
        fmt: CellFmt = "dec1",
        *,
        unit: str = "",
        signed: bool = False,
        kind: RowKind = "data",
        **label_args: str | float,
    ) -> TableRow:
        """A row traced to `<sid>.<trace_key>`: a Range gives lo / typ / hi cells, a number or a
        bool the typ cell, None an empty cell."""

        def cells(sid: str, tr: Tr) -> Cell | list[Cell] | None:
            v = get(sid)
            if isinstance(v, Range):
                return tr.range(trace_key, v, fmt, signed)
            return None if v is None else tr.scalar(trace_key, v, fmt, unit, signed)

        return self.custom(row_key, key(label_key, **label_args), cells, kind)

    def payback_row(
        self,
        row_key: str,
        npv: Callable[[str], object],
        payback: Callable[[str], float | None],
    ) -> TableRow:
        """Payback in years. A scenario with a baseline (an NPV) whose payback is None did not
        reach it within the horizon: the cell says so instead of staying empty."""

        def cells(sid: str, tr: Tr) -> Cell | None:
            years = payback(sid)
            if years is not None:
                return tr.scalar("finance.payback_years", years, unit="years")
            return key("payback.not_reached") if npv(sid) is not None else None

        return self.custom(row_key, key("row.payback"), cells)

    def custom(self, row_key: str, label: Cell, fn: CellsFn, kind: RowKind = "data") -> TableRow:
        """A row of cells made by `fn(sid, tr)` (a list of 3, one Cell for the typ column, or
        None); scenarios not computed get empty cells."""
        cells: list[Cell] = []
        for sid, r in self.data.run.results.items():
            got = fn(sid, self.trs[sid]) if r.status == "computed" else None
            cells += self._spread(got)
        return TableRow(key=row_key, label=label, cells=cells, kind=kind)

    def section(self, row_key: str, label: Cell) -> TableRow:
        n = self.width * len(self.data.run.results)
        return TableRow(key=row_key, label=label, cells=[EMPTY] * n, kind="section")

    def _spread(self, got: Cell | list[Cell] | None) -> list[Cell]:
        if got is None:
            return [EMPTY] * self.width
        if isinstance(got, Cell):
            return [EMPTY, got, EMPTY] if self.width == 3 else [got]
        return got if self.width == 3 else [got[1]]

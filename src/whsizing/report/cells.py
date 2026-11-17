"""F9a cell builders: raw values with the id of the TraceNode they come from.

`Tr(tracer, sid)` makes the cells of one scenario. The trace id of a result field is
`<sid>.<key>` (the F6 mapping of tests/unit/test_f6_size.py T6.11 and the F7 ids of
`whsizing.finance`); a Range's lo / hi are the min / max of that node over the three worlds, so a
lo or hi cell takes the world whose node holds the value (`Cell.world`), found by value.
A key with no node still gets its id: the integrity check IC1 reports the gap, never the builder.
"""

from __future__ import annotations

import math
from collections.abc import Iterable

from whsizing.schemas import Cell, Range, World
from whsizing.schemas.report import CellFmt
from whsizing.schemas.trace import Tracer

WORLDS: tuple[World, ...] = ("lo", "typ", "hi")
EMPTY = Cell()


def text(value: str) -> Cell:
    return Cell(value=value, fmt="text")


def key(i18n_key: str, **args: str | float) -> Cell:
    return Cell(value=i18n_key, fmt="key", args=dict(args))


def num(value: float | None, fmt: CellFmt = "dec1", unit: str = "", signed: bool = False) -> Cell:
    """An untraced number (statistics of the data, parameters: not a sized result)."""
    return Cell(value=None if value is None else float(value), fmt=fmt, unit=unit, signed=signed)


class Tr:
    """The traced cells of one scenario."""

    def __init__(self, tracer: Tracer, sid: str) -> None:
        self.sid = sid
        self._values = {(n.id, n.world): n.value for n in tracer.nodes}

    def tid(self, trace_key: str) -> str:
        return f"{self.sid}.{trace_key}"

    def scalar(
        self,
        trace_key: str,
        value: float | bool | None,
        fmt: CellFmt = "dec1",
        unit: str = "",
        signed: bool = False,
    ) -> Cell:
        """A typical-world number (booleans as 1.0 / 0.0); None gives an empty cell."""
        if value is None:
            return EMPTY
        return Cell(
            value=float(value),
            unit=unit,
            fmt=fmt,
            trace_id=self.tid(trace_key),
            world="typ",
            signed=signed,
        )

    def range(
        self,
        trace_key: str,
        r: Range | None,
        fmt: CellFmt = "dec1",
        signed: bool = False,
    ) -> list[Cell]:
        """[lo, typ, hi] cells of a Range; three empty cells for None."""
        if r is None:
            return [EMPTY, EMPTY, EMPTY]
        tid = self.tid(trace_key)
        values: tuple[tuple[World, float], ...] = (("lo", r.lo), ("typ", r.typ), ("hi", r.hi))
        return [
            Cell(
                value=v,
                unit=r.unit,
                fmt=fmt,
                trace_id=tid,
                world=self._world(tid, w, v),
                signed=signed,
            )
            for w, v in values
        ]

    def _world(self, tid: str, column: World, value: float) -> World:
        """The world whose node holds `value`: the column's own first, then the others."""
        order: list[World] = [column, *(w for w in WORLDS if w != column)]
        for w in order:
            node = self._values.get((tid, w))
            if node is not None and math.isclose(node, value, rel_tol=1e-9, abs_tol=1e-12):
                return w
        return column


def union(rows: Iterable[Iterable[str]]) -> list[str]:
    """Keys of several lists in order of first appearance, each once."""
    seen: dict[str, None] = {}
    for keys in rows:
        seen.update(dict.fromkeys(keys))
    return list(seen)

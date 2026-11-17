"""Calculation trace (§2.6). The Tracer is deliberately stateful: one per scenario run."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel

from whsizing.schemas.params import World


class TraceNode(BaseModel, frozen=True, extra="forbid"):
    id: str  # "S1.labor.picking.hours_design_day"
    label: str  # "Picking hours on design day"
    value: float
    unit: str
    formula: str  # "workload / productivity * (1 + pfd)"
    inputs: dict[
        str, str
    ]  # symbol → TraceNode id or Param id ("param:amr_gtp.station_rate_lines_h")
    scope: str  # scenario id or "global"
    world: World = "typ"


class Tracer:
    """Records TraceNodes keyed by (id, world); the same id may exist once per world."""

    def __init__(self, scope: str = "global", world: World = "typ") -> None:
        self.scope = scope
        self.world: World = world
        self._nodes: dict[tuple[str, World], TraceNode] = {}

    def record(
        self,
        id: str,
        label: str,
        value: float,
        unit: str,
        formula: str,
        inputs: dict[str, str],
        scope: str | None = None,
        world: World | None = None,
    ) -> float:
        """Store a node and return `value` for chaining. Re-recording a different node raises."""
        node = TraceNode(
            id=id,
            label=label,
            value=value,
            unit=unit,
            formula=formula,
            inputs=inputs,
            scope=scope or self.scope,
            world=world or self.world,
        )
        key = (id, node.world)
        old = self._nodes.get(key)
        if old is not None and old != node:
            raise ValueError(
                f"trace node {id!r} ({node.world}) recorded twice with different content"
            )
        self._nodes[key] = node
        return value

    def get(self, id: str, world: World = "typ") -> TraceNode:
        return self._nodes[(id, world)]

    @property
    def nodes(self) -> list[TraceNode]:
        return list(self._nodes.values())

    def export_jsonl(self, path: Path | str) -> None:
        Path(path).write_text("".join(n.model_dump_json() + "\n" for n in self._nodes.values()))

    @classmethod
    def load_jsonl(cls, path: Path | str) -> Tracer:
        tracer = cls()
        for line in Path(path).read_text().splitlines():
            if line.strip():
                node = TraceNode.model_validate_json(line)
                tracer._nodes[(node.id, node.world)] = node
        return tracer

    def tree(self, id: str, world: World = "typ") -> dict[str, Any]:
        """Expand a node recursively down to `param:` leaves (for the UI drill-down)."""
        return self._expand(id, world, frozenset())

    def _expand(self, ref: str, world: World, seen: frozenset[str]) -> dict[str, Any]:
        if ref.startswith("param:"):
            return {"id": ref, "kind": "param"}
        node = self._nodes.get((ref, world))
        if node is None or ref in seen:
            return {"id": ref, "kind": "unresolved" if node is None else "cycle"}
        seen = seen | {ref}
        return {
            "id": node.id,
            "kind": "node",
            "label": node.label,
            "value": node.value,
            "unit": node.unit,
            "formula": node.formula,
            "inputs": {sym: self._expand(r, world, seen) for sym, r in node.inputs.items()},
        }

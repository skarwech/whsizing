"""docs/assumptions.md generator (C4): every catalog parameter with its provenance.

Regenerate after any catalog change: `uv run python -m whsizing.catalog.assumptions`.
"""

from __future__ import annotations

import sys
from pathlib import Path

from whsizing.catalog.loader import load_catalog
from whsizing.catalog.models import Catalog


def render_assumptions_md(catalog: Catalog) -> str:
    params = sorted(catalog.params.values(), key=lambda p: p.id)
    n_low = sum(p.confidence == "L" for p in params)
    out = [
        "# Assumptions",
        "",
        "Generated from `catalog/` (C4) by `uv run python -m whsizing.catalog.assumptions`;"
        " do not edit by hand.",
        "Every value is a placeholder `[P]` until the `[EXPERT]` validates it (`validated_by`).",
        "",
        f"Catalog version: `{catalog.version}`. {len(params)} ranged parameters:"
        f" {catalog.todo_count} with source TODO, {n_low} with confidence L.",
        "The pessimistic world takes each parameter at its pessimistic end (ADR-002).",
        "",
        "## Ranged parameters",
        "",
        "| id | unit | min | typ | max | pessimistic end | source | confidence | validated by"
        " | date | note |",
        "|---|---|---:|---:|---:|---|---|---|---|---|---|",
    ]
    for p in params:
        cells = [p.id, p.unit, _num(p.min), _num(p.typ), _num(p.max), p.pessimistic_end]
        cells += [p.source, p.confidence, p.validated_by or "", p.date.isoformat(), p.note or ""]
        out.append("| " + " | ".join(c.replace("|", "\\|") for c in cells) + " |")
    out += ["", "## Structural constants", "", "| id | value |", "|---|---:|"]
    out += [f"| {k} | {_num(v)} |" for k, v in sorted(catalog.constants.items())]
    return "\n".join(out) + "\n"


def _num(v: float) -> str:
    return str(int(v)) if v.is_integer() else f"{v:g}"


if __name__ == "__main__":
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("catalog")
    dest = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("docs/assumptions.md")
    dest.write_text(render_assumptions_md(load_catalog(src)), encoding="utf-8")
    print(f"wrote {dest}")

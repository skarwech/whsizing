"""What a visitor of the public demo may size, and what the server tells them (no Streamlit import).

The demo runs on somebody else's server: one process for every visitor, whose commands run one at
a time (`calls._LOCK`) and cannot be interrupted. Plain widgets can ask the engine for minutes of
work or gigabytes, measured on the demo study: a 320-year horizon takes 53 s and 2.9 GB, 30
scenarios take 104 s, and an `engine.max_equipment_count` of 10^12 lifts the guard against a
queue of 2.8 million packing stations. The library allows all of it (the user's machine is theirs),
so the public demo bounds the inputs that cost the most; the full app has no limits.
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from pydantic import TypeAdapter, ValidationError

from whsizing.app import demo
from whsizing.catalog import Catalog

MAX_HORIZON_YEARS = 20  # [P] `finance` and `projection` horizons: 20 years compare in about 8 s
MAX_SCENARIOS = 6  # [P] compare and the sensitivity cost grows with each; a report reads to 8 (I81)
MIN_FOLDER_LENGTH = 4  # a folder name shorter than this ("/", "/tmp") is not worth hiding
Problem = tuple[str, dict[str, Any]]  # the key of a text in app/strings.py, and its placeholders
_FLOAT = TypeAdapter(float)  # how the library reads `overrides: dict[str, float]` and the horizons


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _number(value: object) -> float | None:
    """`value` as the library reads a number: pydantic takes numeric text too ("0.000055", " 5 ",
    and "1e-5", which PyYAML reads as text), so the limits must as well. None for what is no number
    (the library refuses it itself) and for a bool (so does it)."""
    if isinstance(value, bool):
        return None
    try:
        return _FLOAT.validate_python(value)
    except ValidationError:
        return None


def _override_problem(pid: str, value: object, catalog: Catalog) -> Problem | None:
    """Constants (the structural scalars, the engine's guards among them) stay what the catalog
    says; a parameter stays inside the range the catalog documents for it."""
    if pid in catalog.constants:
        return "demo.limit.constant", {"id": pid}
    param = catalog.params.get(pid)
    number = _number(value)
    if param is not None and number is not None and not param.min <= number <= param.max:
        return "demo.limit.range", {"id": pid, "lo": param.min, "hi": param.max}
    return None


def limit_problems(
    basis: Mapping[str, Any], scenarios: Mapping[str, Any], catalog: Catalog
) -> list[Problem]:
    """What of this design basis and these scenarios (the nested dicts the pages hold) the public
    demo refuses to size: a horizon over `MAX_HORIZON_YEARS`, more than `MAX_SCENARIOS` scenarios,
    an override of a constant, or of a parameter outside its catalog range. Empty in the full
    app."""
    if not demo.demo_only():
        return []
    problems: list[Problem] = []
    for section in ("projection", "finance"):
        years = _number(_mapping(basis.get(section)).get("horizon_years"))
        if years is not None and years > MAX_HORIZON_YEARS:
            name = f"{section}.horizon_years"
            problems.append(("demo.limit.horizon", {"name": name, "max": MAX_HORIZON_YEARS}))
    items = scenarios.get("scenarios")
    cards = [c for c in items if isinstance(c, Mapping)] if isinstance(items, list) else []
    if len(cards) > MAX_SCENARIOS:
        problems.append(("demo.limit.scenarios", {"max": MAX_SCENARIOS}))
    seen: set[str] = set()
    for overrides in (
        _mapping(basis.get("overrides")),
        *(_mapping(c.get("overrides")) for c in cards),
    ):
        for pid, value in overrides.items():
            problem = _override_problem(str(pid), value, catalog)
            if problem is not None and problem[1]["id"] not in seen:
                seen.add(problem[1]["id"])
                problems.append(problem)
    return problems


def scrub(text: str) -> str:
    """`text` without the folders of the server (public demo): a message of the library or of a
    command names the run folder it was working in, which tells a visitor nothing they can use."""
    if not demo.demo_only():
        return text
    hidden = {
        "<runs>": os.environ.get("WHSIZING_RUNS", ""),
        "<work>": str(demo.work_dir()),
        "<app>": str(Path.cwd()),
        "<tmp>": tempfile.gettempdir(),
    }
    folders: list[tuple[str, str]] = []
    for label, folder in hidden.items():
        if folder:
            # as the commands print it (resolved: /tmp is /private/tmp) and, when it is absolute,
            # as given; a relative name ("runs") would also hit the word in "runs are immutable"
            spellings = {str(Path(folder).resolve())}
            if os.path.isabs(folder):
                spellings.add(folder)
            folders += [(spelling, label) for spelling in spellings]
    for folder, label in sorted(folders, key=lambda item: len(item[0]), reverse=True):
        if len(folder) >= MIN_FOLDER_LENGTH:
            text = text.replace(folder, label)
    return text

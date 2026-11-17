"""What a visitor of the public demo may size, and what the server tells them (no Streamlit import).

The demo runs on somebody else's server: one process for every visitor, whose commands run one at
a time (`calls._LOCK`) and cannot be interrupted. Plain widgets can ask the engine for minutes of
work or gigabytes, measured on the demo study: a `finance.horizon_years` of 320 takes 51 s and
2.4 GB, 30 scenarios take 102 s, 300 shifts per day take 34 s and 2.1 GB, and a 2 MB YAML box is
parsed again on every rerun. The engine's own guard (`engine.max_equipment_count`) refuses a queue
model that needs millions of stations, so an override of a constant (it would lift the guard) and
of a parameter far outside its catalog range (it trips the guard) are refused as well. The library
allows all of it (the user's machine is theirs), so the public demo bounds the inputs that cost the
most; the full app has no limits.
"""

from __future__ import annotations

import os
import sys
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from pydantic import TypeAdapter, ValidationError

from whsizing.app import demo
from whsizing.catalog import Catalog

MAX_HORIZON_YEARS = 20  # [P] `finance` and `projection` horizons: 20 years compare in about 8 s
MAX_SCENARIOS = 6  # [P] compare and the sensitivity cost grows with each; a report reads to 8 (I81)
MAX_SHIFTS = (
    4  # [P] `operations.shifts_per_day`: plants run one to three; each costs (300: 34 s, 2 GB)
)
MAX_TEXT_CHARS = 200  # [P] one name or label: the demo's longest is 47; PDF text costs 25 s per MB
MAX_YAML_CHARS = 10_000  # [P] the YAML box of an override list: all 72 parameters are about 3 000
MAX_TEXT_PROBLEMS = 3  # more long texts than this are not listed one by one
MAX_DEPTH = 8  # how deep into the nested dicts and lists the search for long texts goes
# basis field -> the largest value the demo sizes
MAXIMA: Mapping[str, float] = {"operations.shifts_per_day": MAX_SHIFTS}
MIN_FOLDER_LENGTH = 4  # a folder name shorter than this ("/", "/tmp") is not worth hiding
Problem = tuple[str, dict[str, Any]]  # the key of a text in app/strings.py, and its placeholders
_FLOAT = TypeAdapter(float)  # how the library reads `overrides: dict[str, float]` and the horizons


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _number(value: object) -> float | None:
    """`value` as the library reads a number: pydantic takes numeric text ("0.000055", " 5 ", and
    "1e-5", which PyYAML reads as text) and a bool (as 0 or 1: a scenario override) too, so the
    limits must as well. None for what is no number (the library refuses it itself)."""
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


def _value_problems(basis: Mapping[str, Any]) -> list[Problem]:
    """The horizons over `MAX_HORIZON_YEARS` and the basis fields over their `MAXIMA`."""
    problems: list[Problem] = []
    for section in ("projection", "finance"):
        years = _number(_mapping(basis.get(section)).get("horizon_years"))
        if years is not None and years > MAX_HORIZON_YEARS:
            name = f"{section}.horizon_years"
            problems.append(("demo.limit.horizon", {"name": name, "max": MAX_HORIZON_YEARS}))
    for path, maximum in MAXIMA.items():
        section, _, field = path.partition(".")
        value = _number(_mapping(basis.get(section)).get(field))
        if value is not None and value > maximum:
            problems.append(("demo.limit.maximum", {"name": path, "max": maximum}))
    return problems


def _override_problems(
    basis: Mapping[str, Any], cards: list[Mapping[str, Any]], catalog: Catalog
) -> list[Problem]:
    """Each override of the basis and of the scenario cards, once per parameter id."""
    problems: list[Problem] = []
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


def _long_texts(value: object, path: str, depth: int = 0) -> list[str]:
    """The paths, in the nested dicts and lists of `value`, of the texts (and of the keys) over
    `MAX_TEXT_CHARS`: the client's name, a scenario's id or label, an override's id."""
    if isinstance(value, str):
        return [path] if len(value) > MAX_TEXT_CHARS else []
    if depth >= MAX_DEPTH:
        return []
    found: list[str] = []
    if isinstance(value, Mapping):
        for key, item in value.items():
            label = str(key)
            if len(label) > MAX_TEXT_CHARS:
                found.append(f"{path}.{label[:20]}...")
            found += _long_texts(item, f"{path}.{label[:60]}", depth + 1)
    elif isinstance(value, list):
        for i, item in enumerate(value):
            found += _long_texts(item, f"{path}[{i}]", depth + 1)
    return found


def _text_problems(basis: Mapping[str, Any], cards: list[Mapping[str, Any]]) -> list[Problem]:
    """A text over `MAX_TEXT_CHARS` anywhere in the basis or the scenarios: it reaches the PDF and
    the Excel (25 s per MB under the lock), the messages and the drafts on disk."""
    found = [*_long_texts(basis, "basis"), *_long_texts(cards, "scenarios")][:MAX_TEXT_PROBLEMS]
    return [("demo.limit.text", {"name": path, "max": MAX_TEXT_CHARS}) for path in found]


def limit_problems(
    basis: Mapping[str, Any], scenarios: Mapping[str, Any], catalog: Catalog
) -> list[Problem]:
    """What of this design basis and these scenarios (the nested dicts the pages hold) the public
    demo refuses to size: a horizon over `MAX_HORIZON_YEARS`, more than `MAXIMA` shifts, more than
    `MAX_SCENARIOS` scenarios, an override of a constant or of a parameter outside its catalog
    range, a text over `MAX_TEXT_CHARS`. Empty in the full app."""
    if not demo.demo_only():
        return []
    items = scenarios.get("scenarios")
    cards = [c for c in items if isinstance(c, Mapping)] if isinstance(items, list) else []
    problems = _value_problems(basis)
    if len(cards) > MAX_SCENARIOS:
        problems.append(("demo.limit.scenarios", {"max": MAX_SCENARIOS}))
    cards = cards[: MAX_SCENARIOS + 1]  # the count is refused above: do not walk a million cards
    return [*problems, *_override_problems(basis, cards, catalog), *_text_problems(basis, cards)]


def yaml_too_long(text: str) -> bool:
    """A YAML box over `MAX_YAML_CHARS` in the public demo: it is parsed again on every rerun, in
    the visitor's own thread and outside the locks (2 MB cost 5.7 s of CPU each time)."""
    return demo.demo_only() and len(text) > MAX_YAML_CHARS


def _home() -> str:
    try:
        return str(Path.home())
    except (RuntimeError, KeyError):  # no home directory to find
        return ""


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
        "<home>": _home(),
        "<python>": sys.prefix,
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

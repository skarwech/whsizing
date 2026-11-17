"""G1f: every `[EXPERT]` / `[VERIFY]` marker of the interpretations register is listed once in the
"Open expert rulings" section at the end of the golden case notes. Part of T1.5. Reads the
Markdown only (no `whsizing`, no oracle)."""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

REGISTER = Path(__file__).resolve().parents[2] / "docs" / "INTERPRETATIONS.md"
MARKER = re.compile(r"\[(?:EXPERT|VERIFY)\]")
UNMARKED = {33}  # named by review #1 without a marker: the temp-hours double count (I33)
SECTION = "## Open expert rulings"
ITEM = re.compile(r"^- \*\*I(\d+)\*\*", flags=re.MULTILINE)


def marked_entries(text: str) -> set[int]:
    """Ids of the register entries (`**I<n> —`, between `## Register` and `## Golden case notes`)
    that carry a marker."""
    register = text.split("## Register", 1)[1].split("## Golden case notes", 1)[0]
    parts = re.split(r"^\*\*I(\d+) —", register, flags=re.MULTILINE)[1:]
    return {int(n) for n, body in zip(parts[::2], parts[1::2], strict=True) if MARKER.search(body)}


def check(text: str) -> tuple[set[int], set[int], list[int]]:
    """(marked entries missing from the section, entries listed without a marker bar UNMARKED,
    entries listed more than once)."""
    marked = marked_entries(text)
    listed = Counter(int(n) for n in ITEM.findall(text.split(SECTION, 1)[1]))
    missing, stale = marked - set(listed), set(listed) - marked - UNMARKED
    return missing, stale, [n for n, c in listed.items() if c > 1]


def test_T1_5_open_expert_rulings_list_every_marker_once() -> None:
    """Each marked entry (I46, I48, I53, I54, I64, I65, I67, I69 at the time of writing) is listed
    once, and nothing else is, bar I33."""
    text = REGISTER.read_text(encoding="utf-8")
    assert {46, 48, 53, 54, 64, 65, 67, 69} <= marked_entries(text)
    missing, stale, twice = check(text)
    assert not missing, f"marked entries missing from 'Open expert rulings': {sorted(missing)}"
    assert not stale, f"listed without a marker in the register: {sorted(stale)}"
    assert not twice, f"listed twice: {twice}"
    assert {int(n) for n in ITEM.findall(text.split(SECTION, 1)[1])} >= UNMARKED


def test_T1_5_open_expert_rulings_check_rejects_a_missing_a_duplicate_and_a_stale_entry() -> None:
    """The check itself: drop I69's item, repeat I46's, list I1 (no marker); I33 stays allowed."""
    head, section = REGISTER.read_text(encoding="utf-8").split(SECTION)
    lines = section.split("\n")
    i69 = next(i for i, ln in enumerate(lines) if ln.startswith("- **I69**"))
    i46 = next(i for i, ln in enumerate(lines) if ln.startswith("- **I46**"))
    mutated = [*lines[:i69], *lines[i69 + 1 :], lines[i46], "- **I1** stale"]
    missing, stale, twice = check(head + SECTION + "\n".join(mutated))
    assert missing == {69} and stale == {1} and twice == [46]

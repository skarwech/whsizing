"""F11 step 9: update a catalog from a single-site calibration. Work on a COPY of the catalog.

    changes = update_catalog(copy_dir, fit_report, reviewer="J. Martin", site="Site A")

For each fitted activity whose multiplier is identified, every catalog Param it scales gets
`typ = typ_prior × effective multiplier`, only when the new typ stays within the Param's current
[min, max] (a single site never widens a range). With a `reviewer` the Param also gets
`confidence: M` (never lowered) and `validated_by`; without one only `typ` changes. Applied and
skipped changes are logged in `CHANGELOG.md` of the copy. The indirect share is a constant, not a
ranged Param: it is reported, never written. Files are edited line by line (flow-style Param
blocks), so comments and layout survive; the copy must still load with `load_catalog`.
"""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

import yaml

from whsizing.calibration.models import CatalogChange, FitReport
from whsizing.catalog import load_catalog
from whsizing.errors import ConfigError

SHARE_ID = "labor.indirect_share_of_direct_hours"
BLOCK = re.compile(r"\{[^{}]*\}")


def update_catalog(
    catalog_dir: Path | str,
    fit: FitReport,
    reviewer: str | None = None,
    site: str = "",
    today: date | None = None,
) -> list[CatalogChange]:
    """Apply the calibration to the catalog in `catalog_dir` (a copy!) and log it."""
    root = Path(catalog_dir)
    files = [root / "labor_standards.yaml", *sorted((root / "families").glob("*.yaml"))]
    if not files[0].is_file():
        raise ConfigError(f"{root}: not a catalog folder (no labor_standards.yaml)")
    texts = {f: f.read_text(encoding="utf-8").splitlines(keepends=True) for f in files}
    original = {f: list(t) for f, t in texts.items()}
    changes: list[CatalogChange] = []
    try:
        for act, targets in fit.targets.items():
            if act == "indirect":  # a constant: reported by `_indirect`
                continue
            row = next((t for t in fit.theta if t.name == f"m:{act}"), None)
            if row is None or row.effective is None or not row.identified:
                continue
            for target in targets:
                changes.append(
                    _apply(texts, target.param, target.typ_prior, row.effective, reviewer)
                )
        changes += _indirect(fit)
        if any(c.applied for c in changes):
            for f, lines in texts.items():
                f.write_text("".join(lines), encoding="utf-8")
            load_catalog(root)  # the copy must still validate
            _log(root / "CHANGELOG.md", changes, reviewer, site, fit.sites, today or date.today())
    except Exception:
        for f, lines in original.items():
            f.write_text("".join(lines), encoding="utf-8")
        raise
    return changes


def _indirect(fit: FitReport) -> list[CatalogChange]:
    row = next((t for t in fit.theta if t.name == "m:indirect" and t.identified), None)
    target = next(iter(fit.targets.get("indirect", ())), None)
    if row is None or target is None:
        return []
    return [
        CatalogChange(
            param=SHARE_ID,
            old_typ=target.typ_prior,
            new_typ=target.typ_prior / row.fitted,
            applied=False,
            reason="a constant, not a ranged Param: set share_of_direct_hours by hand",
        )
    ]


def _find(texts: dict[Path, list[str]], param: str) -> tuple[list[str], int, re.Match[str]]:
    """The file lines, line index and `{...}` match of the Param block with id `param`."""
    own = re.compile(rf"\bid:\s*{re.escape(param)}\s*,")
    for lines in texts.values():
        for i, line in enumerate(lines):
            for m in BLOCK.finditer(line):
                if own.search(m.group()):
                    return lines, i, m
    raise ConfigError(f"catalog copy: no Param block with id {param!r}")


def _apply(
    texts: dict[Path, list[str]], param: str, prior: float, effective: float, reviewer: str | None
) -> CatalogChange:
    lines, i, m = _find(texts, param)
    block = yaml.safe_load(m.group())
    old, lo, hi = block["typ"], block["min"], block["max"]
    new = float(f"{prior * effective:.6g}")
    if not lo <= new <= hi:
        reason = f"outside the current range [{lo}, {hi}]"
        return CatalogChange(param=param, old_typ=old, new_typ=new, applied=False, reason=reason)
    line = lines[i]
    lines[i] = line[: m.start()] + _rewrite(m.group(), block, new, reviewer) + line[m.end() :]
    return CatalogChange(param=param, old_typ=old, new_typ=new, applied=True)


def _rewrite(text: str, block: dict[str, object], new: float, reviewer: str | None) -> str:
    text = re.sub(r"\btyp:\s*[-+0-9.eE]+", f"typ: {new:g}", text, count=1)
    if reviewer is None:
        return text
    if block["confidence"] == "L":
        text = re.sub(r"\bconfidence:\s*L\b", "confidence: M", text, count=1)
    name = json.dumps(reviewer)  # a JSON string is a valid YAML scalar
    if "validated_by" in block:
        return re.sub(r"\bvalidated_by:\s*[^,}]*", f"validated_by: {name}", text, count=1)
    return text[:-1].rstrip() + f", validated_by: {name}" + "}"


def _log(
    path: Path, changes: list[CatalogChange], reviewer: str | None, site: str, sites: int, day: date
) -> None:
    head = f"## calibration, {sites} site(s){f' ({site})' if site else ''} — {day.isoformat()}"
    who = (
        f"reviewer: {reviewer}"
        if reviewer
        else "not reviewed: confidence and validated_by unchanged"
    )
    rows = [
        f"- `{c.param}` typ {c.old_typ:g} → {c.new_typ:g}"
        if c.applied
        else f"- `{c.param}` not changed ({c.old_typ:g} → {c.new_typ:g}): {c.reason}"
        for c in changes
    ]
    old = path.read_text(encoding="utf-8") if path.exists() else "# Catalog changelog\n"
    path.write_text(
        f"{old.rstrip()}\n\n{head}\n\n{who}.\n\n" + "\n".join(rows) + "\n", encoding="utf-8"
    )

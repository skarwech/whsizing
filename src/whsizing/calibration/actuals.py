"""F11 step 1: `actuals.csv` + `activity_map.yaml` -> monthly paid hours per target activity.

`actuals.csv`: `month` (yyyy-mm), `activity_client`, `hours` (paid hours, temps and overtime
included), optional `headcount` and `temp_hours`; `,` or `;` delimited (`;` allows a decimal comma).
One row per (month, label) and a row for every month of every label (write 0 for none).

Rules: a row with `headcount` but no `hours` gets `headcount × paid_hours_per_month` (flag
`I_HEADCOUNT_ONLY`); labels missing from the map go to `indirect` (flag `W_UNMAPPED_ACTIVITY`);
a map target that is not a model activity must be declared in `client_activities`: it becomes a
client-specific activity driven by orders (`F_CLIENT_ACTIVITY`); `temp_hours` is informational:
`hours` already holds the temps, so without it the temps are not separated (`I_TEMPS_COMBINED`).
"""

from __future__ import annotations

import csv
import difflib
import io
from collections.abc import Collection
from dataclasses import dataclass, replace
from pathlib import Path

import numpy as np
from pydantic import ValidationError

from whsizing.calibration.models import ActivityMap, ActualRow, norm_label
from whsizing.config import load_yaml_model
from whsizing.errors import ConfigError, DataQualityError
from whsizing.schemas import Flag

COLUMNS = ("month", "activity_client", "hours", "headcount", "temp_hours")
INDIRECT = "indirect"


@dataclass(frozen=True)
class Actuals:
    """Monthly hours per target (a model activity or a client-specific one), months sorted."""

    months: tuple[str, ...]
    hours: dict[str, np.ndarray]
    client_activities: tuple[str, ...]
    temp_share: float | None  # Σ temp_hours / Σ hours when every row gives temp_hours, else None
    flags: tuple[Flag, ...]


def read_actuals(
    path: Path | str, paid_hours_per_month: float | None = None
) -> tuple[list[ActualRow], set[str]]:
    """Parse `actuals.csv` with clear errors (line numbers). Headcount-only rows get hours;
    returns the rows and the (normalised) labels that had such rows."""
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8-sig")
    except OSError as e:
        raise DataQualityError(f"{path}: cannot read file ({e.strerror})") from e
    head = text.splitlines()[0] if text.strip() else ""
    delim = ";" if head.count(";") > head.count(",") else ","
    reader = csv.DictReader(io.StringIO(text), delimiter=delim)
    cols = [c.strip() for c in reader.fieldnames or []]
    missing = [c for c in ("month", "activity_client") if c not in cols]
    if missing or not ({"hours", "headcount"} & set(cols)):
        raise DataQualityError(
            f"{path}: needs columns month, activity_client and hours (or headcount); found {cols}"
        )
    rows = [_row(path, n, r, delim, cols) for n, r in enumerate(reader, start=2)]
    if not rows:
        raise DataQualityError(f"{path}: no data row")
    return _fill_hours(path, rows, paid_hours_per_month)


def _row(path: Path, line: int, raw: dict[str, str], delim: str, cols: list[str]) -> ActualRow:
    if None in raw:
        raise DataQualityError(f"{path}: line {line}: more cells than the {len(cols)} columns")
    data: dict[str, object] = {}
    for key, cell in zip(cols, raw.values(), strict=True):
        cell = (cell or "").strip()
        if key in ("month", "activity_client"):
            data[key] = cell
        elif cell:
            try:
                data[key] = float(cell.replace(",", ".") if delim == ";" else cell)
            except ValueError:
                raise DataQualityError(
                    f"{path}: line {line}: {key} {cell!r} is not a number"
                ) from None
        else:
            data[key] = None
    try:
        return ActualRow.model_validate(data)
    except ValidationError as e:
        why = "; ".join(f"{'.'.join(map(str, x['loc']))}: {x['msg']}" for x in e.errors())
        raise DataQualityError(f"{path}: line {line}: {why}") from e


def _fill_hours(
    path: Path, rows: list[ActualRow], paid: float | None
) -> tuple[list[ActualRow], set[str]]:
    out: list[ActualRow] = []
    seen: set[tuple[str, str]] = set()
    headcount_only: set[str] = set()
    for r in rows:
        key = (r.month, norm_label(r.activity_client))
        if key in seen:
            raise DataQualityError(
                f"{path}: {r.activity_client!r} appears twice for {r.month}: aggregate it first"
            )
        seen.add(key)
        if r.hours is None and r.headcount is None:
            raise DataQualityError(
                f"{path}: {r.activity_client!r} {r.month}: neither hours nor headcount given"
            )
        if r.hours is None:
            if paid is None:
                raise ConfigError("headcount-only actuals need the paid hours per month")
            headcount_only.add(norm_label(r.activity_client))
            r = r.model_copy(update={"hours": (r.headcount or 0.0) * paid})
        if r.temp_hours is not None and r.temp_hours > (r.hours or 0.0) + 1e-9:
            raise DataQualityError(
                f"{path}: {r.activity_client!r} {r.month}: temp_hours exceeds hours"
            )
        out.append(r)
    return out, headcount_only


def load_actuals(
    actuals_path: Path | str,
    activity_map_path: Path | str,
    groups: Collection[str],
    paid_hours_per_month: float | None = None,
) -> Actuals:
    """Read, map and aggregate the actuals. `groups` = the model activities of the baseline
    family (`predict.GROUPS` available); `indirect` is always a valid target."""
    amap = load_yaml_model(activity_map_path, ActivityMap)
    valid = {*groups, INDIRECT}
    clash = sorted(set(amap.client_activities) & valid)
    if clash:
        raise ConfigError(f"{activity_map_path}: client_activities {clash} are model activities")
    targets = _targets(amap.activities, activity_map_path)
    for label, t in targets.items():
        if t not in valid and t not in amap.client_activities:
            near = difflib.get_close_matches(t, [*valid, *amap.client_activities], n=3)
            raise ConfigError(
                f"{activity_map_path}: {label!r} -> {t!r} is neither a model activity "
                f"{sorted(valid)} nor a declared client_activities entry (did you mean {near}?)"
            )
    rows, headcount_only = read_actuals(actuals_path, paid_hours_per_month)
    months = tuple(sorted({r.month for r in rows}))
    _check_grid(rows, months)
    out = _aggregate(rows, months, targets, tuple(amap.client_activities), actuals_path)
    notes = [
        Flag(
            code=f"W_MISSING_MONTH:{m}",
            severity="warning",
            message=f"no row for any activity in {m}: the months are not consecutive, so the "
            "hold-out (the last months) can span the gap",
        )
        for m in _missing_months(months)
    ]
    notes += [
        Flag(
            code=f"I_HEADCOUNT_ONLY:{label}",
            severity="info",
            message=f"{label!r}: hours = headcount × paid hours per month ({paid_hours_per_month})",
        )
        for label in sorted(headcount_only)
    ]
    if out.temp_share is None:
        notes.append(
            Flag(
                code="I_TEMPS_COMBINED",
                severity="info",
                message="temp hours are not separated: the hours combine permanent staff, "
                "temps and overtime, and the model's temp hours cannot be back-tested",
            )
        )
    return replace(out, flags=(*out.flags, *notes))


def _targets(activities: dict[str, str], source: Path | str) -> dict[str, str]:
    """Normalised label -> target; two keys equal after normalisation must agree."""
    out: dict[str, str] = {}
    for key, target in activities.items():
        label, target = norm_label(key), target.strip()
        if out.setdefault(label, target) != target:
            raise ConfigError(
                f"{source}: {key!r} is the same label as another key (case and spaces are "
                f"ignored) but maps to {target!r} instead of {out[label]!r}"
            )
    return out


def _missing_months(months: tuple[str, ...]) -> list[str]:
    """Calendar months between the first and the last of `months` that are not in it."""
    have = {int(m[:4]) * 12 + int(m[5:7]) - 1 for m in months}
    gaps = [i for i in range(min(have), max(have)) if i not in have]
    return [f"{i // 12:04d}-{i % 12 + 1:02d}" for i in gaps]


def without_months(a: Actuals, drop: Collection[str]) -> Actuals:
    """`a` without the months in `drop` (months stay sorted)."""
    keep = [i for i, m in enumerate(a.months) if m not in drop]
    return replace(
        a,
        months=tuple(a.months[i] for i in keep),
        hours={k: v[keep] for k, v in a.hours.items()},
    )


def _check_grid(rows: list[ActualRow], months: tuple[str, ...]) -> None:
    have: dict[str, set[str]] = {}
    for r in rows:
        have.setdefault(norm_label(r.activity_client), set()).add(r.month)
    for label, ms in sorted(have.items()):
        gap = sorted(set(months) - ms)
        if gap:
            raise DataQualityError(
                f"actuals: {label!r} has no row for {gap[:4]}: add a row with hours 0 for none"
            )


def _aggregate(
    rows: list[ActualRow],
    months: tuple[str, ...],
    targets: dict[str, str],
    client: tuple[str, ...],
    source: Path | str,
) -> Actuals:
    idx = {m: i for i, m in enumerate(months)}
    hours: dict[str, np.ndarray] = {}
    flags: list[Flag] = []
    unmapped: dict[str, float] = {}
    for r in rows:
        label = norm_label(r.activity_client)
        target = targets.get(label, INDIRECT)
        h = r.hours or 0.0
        if label not in targets:
            unmapped[r.activity_client] = unmapped.get(r.activity_client, 0.0) + h
        hours.setdefault(target, np.zeros(len(months)))[idx[r.month]] += h
    for label, total in sorted(unmapped.items()):
        flags.append(
            Flag(
                code=f"W_UNMAPPED_ACTIVITY:{label}",
                severity="warning",
                message=f"client activity {label!r} of {Path(source).name} is not in the "
                f"activity map: its {total:.0f} h go to indirect",
                value=total,
            )
        )
    flags += [
        Flag(
            code=f"F_CLIENT_ACTIVITY:{name}",
            severity="warning",
            message=f"client-specific activity {name!r} (not in the model): hours per order",
        )
        for name in client
        if name in hours
    ]
    return Actuals(
        months, hours, tuple(n for n in client if n in hours), _temp_share(rows), tuple(flags)
    )


def _temp_share(rows: list[ActualRow]) -> float | None:
    if any(r.temp_hours is None for r in rows):
        return None
    total = sum(r.hours or 0.0 for r in rows)
    return sum(r.temp_hours or 0.0 for r in rows) / total if total > 0 else 0.0

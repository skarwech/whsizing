"""scenarios.yaml loader (F8, Appendix E)."""

from __future__ import annotations

import re
from pathlib import Path

from whsizing.config import load_yaml_model
from whsizing.errors import ConfigError
from whsizing.schemas import ScenarioSet

SCENARIO_ID = re.compile(r"[A-Za-z0-9_-]{1,64}")  # one path segment of scenarios/<id>/
CLIENT_CURRENT = "client_current"  # value of `baseline:` for the client's current operation


def load_scenarios(path: Path | str) -> ScenarioSet:
    """scenarios.yaml → ScenarioSet. A duplicate id (T8.1), two ids that differ only by case (one
    folder `scenarios/<id>/` on a case-insensitive filesystem), an id outside `[A-Za-z0-9_-]{1,64}`
    (it names that folder), the reserved id `client_current`, an empty list or an
    `is_baseline: true` scenario other than the one `baseline:` names raise ConfigError (exit 2)."""
    scenarios = load_yaml_model(path, ScenarioSet)
    if not scenarios.scenarios:
        raise ConfigError(f"{path}: no scenario defined")
    folders: dict[str, str] = {}  # casefolded id → the id that took it
    for s in scenarios.scenarios:
        if (first := folders.setdefault(s.id.casefold(), s.id)) != s.id:
            raise ConfigError(
                f"{path}: scenario ids {first!r} and {s.id!r} differ only by case: they would "
                f"share the folder scenarios/{first}/ on a case-insensitive filesystem"
            )
        if not SCENARIO_ID.fullmatch(s.id):
            raise ConfigError(f"{path}: scenario id {s.id!r}: use 1-64 letters, digits, '_' or '-'")
        if s.id == CLIENT_CURRENT:
            raise ConfigError(f"{path}: {CLIENT_CURRENT!r} is reserved for `baseline:`")
        if s.is_baseline and s.id != scenarios.baseline:  # `baseline:` decides; no silent mismatch
            raise ConfigError(
                f"{path}: scenario {s.id!r} has is_baseline: true but `baseline:` is "
                f"{scenarios.baseline!r}; set `baseline: {s.id}` or drop is_baseline"
            )
    return scenarios

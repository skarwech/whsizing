"""RunOutput: what `whsizing.scenarios.run_scenarios` returns (F8)."""

from __future__ import annotations

from pathlib import Path

from whsizing.schemas.comparison import Comparison, Sensitivity
from whsizing.schemas.finance import FinancialResult
from whsizing.schemas.manifest import RunManifest
from whsizing.schemas.params import StrictModel
from whsizing.schemas.result import ScenarioResult


class RunOutput(StrictModel):
    """One finished run. `results` holds every scenario of scenarios.yaml in file order (a
    scenario that could not be sized has status "not_computed" and zero-valued parts);
    `finances` only the computed ones. `sensitivity` is None until F8b writes it or when
    `options.sensitivity` is off."""

    run_dir: Path
    manifest: RunManifest
    results: dict[str, ScenarioResult]
    finances: dict[str, FinancialResult]
    comparison: Comparison
    sensitivity: Sensitivity | None = None

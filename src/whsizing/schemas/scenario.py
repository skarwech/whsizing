"""Scenario definitions and the scenarios.yaml container (§2.5, Appendix E)."""

from __future__ import annotations

from collections import Counter
from typing import Literal, Self

from pydantic import model_validator

from whsizing.schemas.params import FamilyId, StrictModel


class EligibilityCfg(StrictModel):
    use_catalog_limits: bool = True
    assume_eligible_if_missing_dims: bool = False  # conservative default
    extra_max_weight_kg: float | None = None


class ScenarioDef(StrictModel):
    id: str
    name: str
    family: FamilyId
    is_baseline: bool = False
    overrides: dict[str, float] = {}
    eligibility: EligibilityCfg = EligibilityCfg()
    overflow_family: Literal["manual_p2p"] = "manual_p2p"
    notes: str = ""


class ScenarioSet(StrictModel):
    """Top level of scenarios.yaml: scenario ids are unique (T8.1)."""

    scenarios: list[ScenarioDef]
    baseline: str = "client_current"  # "client_current" or a scenario id

    @model_validator(mode="after")
    def _unique_ids(self) -> Self:
        dupes = sorted(k for k, n in Counter(s.id for s in self.scenarios).items() if n > 1)
        if dupes:
            raise ValueError(f"duplicate scenario id(s): {', '.join(dupes)}")
        ids = {s.id for s in self.scenarios}
        if self.baseline != "client_current" and self.baseline not in ids:
            raise ValueError(
                f"baseline {self.baseline!r} is neither 'client_current' nor a scenario id"
            )
        return self

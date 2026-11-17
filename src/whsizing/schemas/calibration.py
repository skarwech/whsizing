"""F11 contracts: the activity map, the actuals rows and the fit.json / holdout.json reports.

Every model forbids unknown keys (§3.1). The reports are plain data, serialised with
`model_dump_json(indent=2)`: the same inputs give the same bytes (no timestamp, no run time).
Re-exported by `whsizing.calibration`; the [P] constants live in `whsizing.calibration.models`.
"""

from __future__ import annotations

from typing import Annotated, Literal, Self

from pydantic import Field, StringConstraints, field_validator, model_validator

from whsizing.schemas.params import StrictModel
from whsizing.schemas.result import Flag

Month = Annotated[str, StringConstraints(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")]
ClientName = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]*$")]


class ActivityMap(StrictModel):
    """`activity_map.yaml`: client label -> model activity (many-to-one), plus the declared
    client-specific activities (not in the model: kitting, VAS), driven by orders."""

    activities: dict[str, str]
    client_activities: list[ClientName] = []

    @field_validator("activities")
    @classmethod
    def _labels(cls, v: dict[str, str]) -> dict[str, str]:
        if any(not k.strip() or not t.strip() for k, t in v.items()):
            raise ValueError("labels and targets must not be empty")
        return v

    @model_validator(mode="after")
    def _unique(self) -> Self:
        if len(set(self.client_activities)) != len(self.client_activities):
            raise ValueError("client_activities lists a name twice")
        return self


class ActualRow(StrictModel):
    """One line of `actuals.csv`."""

    month: Month
    activity_client: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
    hours: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    headcount: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    temp_hours: float | None = Field(default=None, ge=0, allow_inf_nan=False)


class ThetaRow(StrictModel):
    """One fitted parameter. `effective` (multipliers): the productivity multiplier at the basis
    PF&D, `m × (1 + pfd_basis) / (1 + pfd)`: the value to put in the catalog."""

    name: str  # m:<activity>, eta, pfd
    kind: Literal["multiplier", "eta", "pfd"]
    prior: float
    sigma: float
    lo: float
    hi: float
    fitted: float
    effective: float | None = None
    identified: bool
    note: str = ""


class CatalogTarget(StrictModel):
    """A catalog Param the activity's multiplier scales: `typ_prior` is its value in the run."""

    param: str
    typ_prior: float


class ClientActivityFit(StrictModel):
    name: str
    driver: Literal["orders"] = "orders"
    hours_per_order: float


class FitReport(StrictModel):
    """`fit.json`."""

    scenario: str
    family: str
    sites: int
    months_fit: list[str]
    months_holdout: list[str]
    peak_month: str
    peak_definition: str
    theta: list[ThetaRow]
    targets: dict[str, list[CatalogTarget]]  # activity -> catalog Params it scales
    client_activities: list[ClientActivityFit]
    excluded_activities: list[str]  # model activities without actuals (not compared)
    n_points: int
    cost: float
    cost_prior_term: float
    status: int
    n_evals: int
    mape_fit_total: float | None  # in-sample, %
    flags: list[Flag]


class ActivityMetrics(StrictModel):
    mape: float | None  # %
    bias: float | None  # mean signed error %, (pred - actual) / actual


class HoldoutMonth(StrictModel):
    month: str
    actual: dict[str, float]  # activity -> hours; `total` = the compared total
    predicted: dict[str, float]


class HoldoutReport(StrictModel):
    """`holdout.json`."""

    months: list[str]
    peak_month: str
    peak_in_holdout: bool
    per_activity: dict[str, ActivityMetrics]
    total: ActivityMetrics
    peak_month_error_pct: float  # signed (pred - actual) / actual, %
    peak_lines_h_pred: float
    peak_lines_h_observed: float | None
    peak_lines_h_error_pct: float | None
    threshold_pct: float
    accepted: bool  # total MAPE and |peak-month error| <= threshold
    table: list[HoldoutMonth]
    flags: list[Flag]


class CatalogChange(StrictModel):
    """One Param considered by `update_catalog`."""

    param: str
    old_typ: float
    new_typ: float
    applied: bool
    reason: str = ""

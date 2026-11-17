"""F11 constants ([P], spec F11) and label matching; the contracts (ActivityMap, ActualRow,
ThetaRow, FitReport, HoldoutReport, ...) are in `whsizing.schemas.calibration` and re-exported here.
"""

from __future__ import annotations

import re

from whsizing.schemas.calibration import (
    ActivityMap,
    ActivityMetrics,
    ActualRow,
    CatalogChange,
    CatalogTarget,
    ClientActivityFit,
    FitReport,
    HoldoutMonth,
    HoldoutReport,
    ThetaRow,
)

__all__ = [
    "ETA_BOUNDS",
    "HOLDOUT_MAPE_MAX",
    "LAMBDA",
    "M_BOUNDS",
    "NOISE_REL",
    "PARTIAL_MONTH_COVERAGE_MIN",
    "PFD_BOUNDS",
    "ActivityMap",
    "ActivityMetrics",
    "ActualRow",
    "CatalogChange",
    "CatalogTarget",
    "ClientActivityFit",
    "FitReport",
    "HoldoutMonth",
    "HoldoutReport",
    "ThetaRow",
    "norm_label",
]

# [P] spec F11 step 3 / step 4 / acceptance
M_BOUNDS = (0.5, 2.0)  # productivity multiplier per activity
ETA_BOUNDS = (0.6, 1.0)  # flow efficiency
PFD_BOUNDS = (0.05, 0.25)  # PF&D allowance
LAMBDA = 1.0  # weight of the prior term
HOLDOUT_MAPE_MAX = 15.0  # % on total monthly hours and on the peak month
# I74 (e): a month is partial when the calendar range of the daily series covers fewer than this
# share of its days (an extract that starts or ends mid-month); a closed first or last day is not
PARTIAL_MONTH_COVERAGE_MIN = 0.9
# Unit scale of the data term (the spec leaves it open): a residual of 0.3 % of the mean point
# weighs 1, like a 1-sigma move off a prior. On the hours scale the spec writes (w_i proportional
# to the actual hours, in h²) the prior is a tie-breaker: it settles the PF&D / multiplier split
# without shrinking a small activity (replenishment, 2 % of the hours, is recovered within 1 %
# for m up to 1.8).
NOISE_REL = 0.003


_LABEL = re.compile(r"\s+")


def norm_label(s: str) -> str:
    """Client labels compare case-insensitively with collapsed spaces."""
    return _LABEL.sub(" ", s.strip()).casefold()

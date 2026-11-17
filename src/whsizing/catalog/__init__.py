"""Automation catalog (F5): models, strict loader, per-world parameter values, eligibility."""

from whsizing.catalog.eligibility import (
    assumed_mask,
    eligibility_shares,
    eligible_mask,
    units_per_bin,
)
from whsizing.catalog.loader import (
    flat_id,
    infer_pessimistic_end,
    load_catalog,
    snapshot_catalog,
)
from whsizing.catalog.models import Catalog, CatalogParam, Family
from whsizing.catalog.paramset import BASIS_KEYS, ParamSet

__all__ = [
    "BASIS_KEYS",
    "Catalog",
    "CatalogParam",
    "Family",
    "ParamSet",
    "assumed_mask",
    "eligibility_shares",
    "eligible_mask",
    "flat_id",
    "infer_pessimistic_end",
    "load_catalog",
    "snapshot_catalog",
    "units_per_bin",
]

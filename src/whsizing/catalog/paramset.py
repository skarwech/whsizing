"""Parameter values per world, after overrides (ADR-002, §2.5.1)."""

from __future__ import annotations

import difflib
import math
from collections.abc import Mapping
from typing import Literal

from whsizing.catalog.models import Catalog
from whsizing.errors import ConfigError
from whsizing.schemas import Param, World

# Override keys that are basis-level settings, not catalog parameters; read with `basis_value`.
# stock_growth_rate: F4 step 7 (description.md l.760), growth applied to design stock instead of g.
BASIS_KEYS = frozenset({"stock_growth_rate"})

# Constants the engine divides by (a 0 is a ZeroDivisionError or a silent inf, I75 j): an override
# must be > 0. Every other constant (shares, reserves, fixed areas, lags) may be 0. Not listed:
# `<fam>.equipment_life_years` (F7 refuses a life <= 0 with its own ConfigError).
DIVISOR_CONSTANTS = frozenset(
    {
        "engine.eta_flow",
        "engine.receipt_lines_per_pallet_full",
        "engine.receipt_lines_per_pallet_mixed",
        "storage.default_units_per_pallet",
        "storage.skus_per_mixed_bin",
        "storage.shelf_bin_net_cube_m3",
        "area.parcels_per_pallet_equiv",
        "manual_p2p.shelving_bin_pitch_mm",
        "cube_asrs.bin_net_cube_m3",
        "cube_asrs.level_height_mm",
        "amr_gtp.pod_bin_net_cube_m3",
    }
)


class ParamSet:
    """Catalog values for one scenario run.

    `ParamSet(catalog, basis.overrides, scenario.overrides)`: later mappings win. An override
    replaces `typ`; a value outside [min, max] widens the range to include it, so there is no range
    check; but it must be finite, and > 0 for a Param whose catalog `min` is > 0 (ConfigError
    naming the id and the value: a zero rate or OEE is a divisor, I75 j). Constants (structural
    scalars: shares may be 0) can be overridden too, finite only (> 0 for `DIVISOR_CONSTANTS`), and
    are the same in every world.
    World `lo` = pessimistic (each Param at its `pessimistic_end`), `hi` = optimistic (other bound).
    Keys in `BASIS_KEYS` are not parameters: they are kept as given and read with `basis_value`.
    """

    def __init__(self, catalog: Catalog, *overrides: Mapping[str, float]) -> None:
        merged = {k: v for o in overrides for k, v in o.items()}
        self._params = dict(catalog.params)
        self._constants = dict(catalog.constants)
        self._overridden = frozenset(merged)
        self._basis = {k: float(v) for k, v in merged.items() if k in BASIS_KEYS}
        for pid, v in merged.items():
            if not math.isfinite(v):
                raise ConfigError(f"overrides: {pid}: value {v} is not a finite number")
            if pid in BASIS_KEYS:
                continue
            if pid in self._params:
                p = self._params[pid]
                if v <= 0 < p.min:
                    raise ConfigError(
                        f"overrides: {pid}: value {v} must be > 0 "
                        f"(the catalog range [{p.min}, {p.max}] does not include 0)"
                    )
                widened = {"typ": v, "min": min(p.min, v), "max": max(p.max, v)}
                self._params[pid] = Param.model_validate({**p.model_dump(), **widened})
            elif pid in self._constants:
                if pid in DIVISOR_CONSTANTS and v <= 0:
                    raise ConfigError(
                        f"overrides: {pid} = {v}: a divisor in the engine, must be > 0"
                    )
                self._constants[pid] = float(v)
            else:
                known = [*self._params, *self._constants, *BASIS_KEYS]
                near = difflib.get_close_matches(pid, known, n=3)
                hint = f" (did you mean {near}?)" if near else ""
                raise ConfigError(f"overrides: unknown parameter id {pid!r}{hint}")

    def value(self, param_id: str, world: World = "typ") -> float:
        if param_id in self._constants:
            return self._constants[param_id]
        p = self.param(param_id)
        if world == "typ":
            return p.typ
        pessimistic = p.min if p.pessimistic_end == "min" else p.max
        optimistic = p.max if p.pessimistic_end == "min" else p.min
        return pessimistic if world == "lo" else optimistic

    def basis_value(self, key: str, default: float) -> float:
        """A basis-level override (`BASIS_KEYS`), or `default` when the basis does not set it."""
        if key not in BASIS_KEYS:
            raise ConfigError(f"{key!r} is not a basis-level key (known: {sorted(BASIS_KEYS)})")
        return self._basis.get(key, default)

    def param(self, param_id: str) -> Param:
        """The effective Param (after override and widening)."""
        try:
            return self._params[param_id]
        except KeyError:
            raise ConfigError(f"unknown parameter id {param_id!r}") from None

    @property
    def params(self) -> dict[str, Param]:
        """Effective Params by id, for the Assumptions sheet (with `origin`)."""
        return dict(self._params)

    def origin(self, param_id: str) -> Literal["default", "override"]:
        known = param_id in self._params or param_id in self._constants or param_id in BASIS_KEYS
        if not known:
            raise ConfigError(f"unknown parameter id {param_id!r}")
        return "override" if param_id in self._overridden else "default"

    def snapshot(self) -> dict[str, float]:
        """Every value at typ after overrides, and basis keys set (RunManifest.params_snapshot)."""
        return {**{k: p.typ for k, p in self._params.items()}, **self._constants, **self._basis}

"""F5 ParamSet: the three worlds (ADR-002), overrides, widening, snapshot."""

from __future__ import annotations

from pathlib import Path

import pytest

from whsizing.catalog import ParamSet, load_catalog
from whsizing.catalog.paramset import DIVISOR_CONSTANTS
from whsizing.errors import ConfigError

CATALOG = Path(__file__).resolve().parents[2] / "catalog"


@pytest.fixture(scope="module")
def catalog():
    return load_catalog(CATALOG)


def test_rate_param_pessimistic_world_is_its_min(catalog) -> None:
    ps = ParamSet(catalog)
    pid = "cube_asrs.port_rate_lines_h"  # 250 / 350 / 450, pessimistic_end min
    assert (ps.value(pid, "lo"), ps.value(pid, "typ"), ps.value(pid, "hi")) == (250, 350, 450)


def test_cost_param_pessimistic_world_is_its_max(catalog) -> None:
    ps = ParamSet(catalog)
    pid = "cube_asrs.per_port_eur"  # 40000 / 60000 / 90000, pessimistic_end max
    assert (ps.value(pid, "lo"), ps.value(pid, "typ"), ps.value(pid, "hi")) == (90000, 60000, 40000)


def test_every_param_resolves_in_three_worlds(catalog) -> None:
    ps = ParamSet(catalog)
    for pid, p in catalog.params.items():
        lo, typ, hi = (ps.value(pid, w) for w in ("lo", "typ", "hi"))
        assert typ == p.typ
        if p.pessimistic_end == "min":
            assert (lo, hi) == (p.min, p.max), pid
        else:
            assert (lo, hi) == (p.max, p.min), pid
    for cid, v in catalog.constants.items():
        assert ps.value(cid, "lo") == ps.value(cid, "typ") == ps.value(cid, "hi") == v


def test_override_inside_range_replaces_typ_only(catalog) -> None:
    ps = ParamSet(catalog, {"manual_p2p.pick_rate_shelving_lines_h": 62})  # Appendix E basis
    p = ps.param("manual_p2p.pick_rate_shelving_lines_h")
    assert (p.min, p.typ, p.max) == (50, 62, 95)
    assert ps.value(p.id, "lo") == 50
    assert ps.origin(p.id) == "override"
    assert ps.origin("manual_p2p.pick_rate_pallet_lines_h") == "default"
    assert ps.snapshot()[p.id] == 62
    assert ps.params[p.id].source == "TODO"  # provenance kept for the Assumptions sheet


def test_scenario_overrides_win_over_basis(catalog) -> None:
    pid = "amr_gtp.station_rate_lines_h"
    ps = ParamSet(catalog, {pid: 200, "engine.eta_flow": 0.9}, {pid: 230})
    assert ps.value(pid) == 230
    assert ps.value("engine.eta_flow", "lo") == 0.9  # constant override, same in every world
    assert ps.origin("engine.eta_flow") == "override"


@pytest.mark.parametrize(
    ("override", "expected"), [(500.0, (250, 500, 500)), (100.0, (100, 100, 450))]
)
def test_out_of_range_override_widens_the_range(catalog, override, expected) -> None:
    pid = "cube_asrs.port_rate_lines_h"
    ps = ParamSet(catalog, {pid: override})
    p = ps.param(pid)
    assert (p.min, p.typ, p.max) == expected
    assert ps.value(pid, "lo") == expected[0]
    assert ps.value(pid, "hi") == expected[2]
    assert catalog.params[pid].typ == 350  # the catalog itself is unchanged


def test_unknown_override_id_is_a_config_error(catalog) -> None:
    with pytest.raises(
        ConfigError, match=r"cube_asrs\.port_rate_lines_hr.*cube_asrs\.port_rate_lines_h"
    ):
        ParamSet(catalog, {"cube_asrs.port_rate_lines_hr": 300})
    with pytest.raises(ConfigError, match="unknown parameter id"):
        ParamSet(catalog).value("cube_asrs.nope", "typ")
    with pytest.raises(ConfigError, match="unknown parameter id"):
        ParamSet(catalog).origin("cube_asrs.nope")


def test_R7_6_unknown_override_without_a_close_match_has_no_suggestion(catalog) -> None:
    """difflib finding nothing used to print "did you mean []?"; the hint is left out then and
    kept (with the candidates) when there is a near id."""
    with pytest.raises(ConfigError) as far:
        ParamSet(catalog, {"zzzz_nothing_like_it": 1.0})
    assert "unknown parameter id 'zzzz_nothing_like_it'" in str(far.value)
    assert "did you mean" not in str(far.value) and "[]" not in str(far.value)
    with pytest.raises(ConfigError) as near:
        ParamSet(catalog, {"cube_asrs.port_rate_lines_hr": 300})
    assert "(did you mean ['cube_asrs.port_rate_lines_h'" in str(near.value)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_override_is_a_config_error(catalog, value) -> None:
    """YAML `.nan` / `.inf` parse as floats: a NaN escaped as a pydantic error, inf widened max."""
    with pytest.raises(ConfigError, match=r"cube_asrs\.port_rate_lines_h.*not a finite number"):
        ParamSet(catalog, {"cube_asrs.port_rate_lines_h": value})


def test_basis_level_keys_are_accepted_and_exposed(catalog) -> None:
    """F4 step 7: basis.overrides may carry stock_growth_rate, which is not a catalog parameter."""
    ps = ParamSet(catalog, {"stock_growth_rate": 0.02, "engine.eta_flow": 0.9}, {})
    assert ps.basis_value("stock_growth_rate", 0.04) == 0.02
    assert ps.value("engine.eta_flow") == 0.9  # the rest of the mapping still applies
    assert ps.snapshot()["stock_growth_rate"] == 0.02  # recorded in the manifest snapshot
    assert ParamSet(catalog).basis_value("stock_growth_rate", 0.04) == 0.04  # default when unset
    assert "stock_growth_rate" not in ParamSet(catalog).snapshot()
    assert ps.origin("stock_growth_rate") == "override"
    assert ParamSet(catalog).origin("stock_growth_rate") == "default"
    with pytest.raises(ConfigError, match="not a basis-level key"):
        ps.basis_value("cube_asrs.port_rate_lines_h", 0.0)
    with pytest.raises(ConfigError, match=r"unknown parameter id 'stock_growth'.*growth_rate"):
        ParamSet(catalog, {"stock_growth": 0.02})  # any other unknown id still raises


def test_snapshot_has_every_value_at_typ(catalog) -> None:
    snap = ParamSet(catalog).snapshot()
    assert set(snap) == set(catalog.params) | set(catalog.constants)
    assert snap["cube_asrs.per_port_eur"] == 60000
    assert snap["cube_asrs.max_levels"] == 20


# ------------------------------------------------------------------ I75 j: zero divisors
@pytest.mark.parametrize("value", [0.0, -1.0, -0.0001])
@pytest.mark.parametrize("pid", ["amr_gtp.station_rate_lines_h", "amr_gtp.oee"])
def test_I75_j_zero_or_negative_override_of_a_positive_param_is_a_config_error(
    catalog, pid, value
) -> None:
    """A zero rate or OEE is a divisor: it was a raw ZeroDivisionError in engine/throughput.py."""
    assert catalog.params[pid].min > 0
    with pytest.raises(ConfigError, match=rf"{pid}.*value {value}.*> 0"):
        ParamSet(catalog, {pid: value})
    with pytest.raises(ConfigError, match=rf"{pid}.*value {value}"):
        ParamSet(catalog, {}, {pid: value})  # a scenario override, the case of the run


def test_I75_j_the_check_covers_every_param_with_a_positive_min(catalog) -> None:
    positive = [pid for pid, p in catalog.params.items() if p.min > 0]
    assert len(positive) > 50
    for pid in positive:
        with pytest.raises(ConfigError, match="> 0"):
            ParamSet(catalog, {pid: 0})


def test_I75_j_a_param_whose_catalog_range_includes_zero_accepts_zero_and_negatives(
    catalog,
) -> None:
    free = [pid for pid, p in catalog.params.items() if p.min <= 0]
    assert "amr_gtp.charging_per_robot_eur" in free
    for pid in free:
        for v in (0.0, -5.0, 12.5):
            assert ParamSet(catalog, {pid: v}).value(pid) == v


def test_I75_j_no_range_check_against_min_and_max(catalog) -> None:
    """A positive override outside [min, max] still widens the range (sensitivity runs leave it)."""
    pid = "amr_gtp.station_rate_lines_h"
    p = catalog.params[pid]
    ps = ParamSet(catalog, {pid: p.max * 10}, {pid: p.min / 100})
    assert ps.value(pid) == p.min / 100 and ps.param(pid).min == p.min / 100


def test_I75_j_shares_and_basis_keys_keep_finite_only(catalog) -> None:
    """Shares and growth may be 0 or negative: only Params and divisor constants carry > 0."""
    free = ["area.circulation_share", "amr_gtp.contingency_share", "labor.outbound_lag_hours"]
    assert not set(free) & DIVISOR_CONSTANTS
    ps = ParamSet(catalog, dict.fromkeys(free, 0.0))
    assert [ps.value(pid) for pid in free] == [0.0, 0.0, 0.0]
    assert ParamSet(catalog, {"stock_growth_rate": -0.02}).basis_value("stock_growth_rate", 0) < 0
    with pytest.raises(ConfigError, match="not a finite number"):
        ParamSet(catalog, {"area.circulation_share": float("nan")})


def test_I75_j_the_divisor_list_names_catalog_constants(catalog) -> None:
    """A renamed or mistyped id would silently drop its guard."""
    assert set(catalog.constants) >= DIVISOR_CONSTANTS
    assert not DIVISOR_CONSTANTS & set(catalog.params)  # Params are guarded by their own min > 0


@pytest.mark.parametrize("value", [0.0, -1.0])
@pytest.mark.parametrize("pid", sorted(DIVISOR_CONSTANTS))
def test_I75_j_a_zero_or_negative_divisor_constant_is_a_config_error(
    catalog, pid: str, value: float
) -> None:
    """R5 audit 3: eta_flow = 0 was a raw ZeroDivisionError and skus_per_mixed_bin = 0 silently
    gave inf, after the whole ingest. The message names the id and the value (F4 I60 matches it)."""
    for overrides in (({pid: value},), ({}, {pid: value})):  # basis, then scenario override
        with pytest.raises(ConfigError, match=rf"{pid} = {value}.*> 0") as exc:
            ParamSet(catalog, *overrides)
        assert exc.value.exit_code == 2
    assert ParamSet(catalog, {pid: 2.5}).value(pid) == 2.5  # a positive value still replaces

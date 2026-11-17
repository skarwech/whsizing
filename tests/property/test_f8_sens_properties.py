"""F8b properties: the break-even solver finds the known root of any linear payback model (T8.4)
and says None exactly when it is outside the bracket; the labor-cost bar of the tornado grows with
delta and the tornado is always sorted (T8.3); the percentile sweep is monotone in design lines."""

from __future__ import annotations

from hypothesis import assume, given, settings
from hypothesis import strategies as st
from tests.unit.test_f8_sens_fixtures import golden_ctx

from whsizing.finance import metrics
from whsizing.scenarios import breakeven as be
from whsizing.scenarios import percentile_sweep, sensitivity_oat

BRACKET_LO, BRACKET_HI = be.BRACKET


@given(
    investment=st.floats(min_value=10, max_value=1_000),
    saving=st.floats(min_value=1, max_value=500),
    years=st.integers(min_value=2, max_value=10),
    target=st.floats(min_value=0.05, max_value=1.0),  # share of the horizon
)
def test_T8_4_solver_finds_the_known_root_of_a_linear_payback_or_none(
    investment: float, saving: float, years: int, target: float
) -> None:
    """Δcf = [-I, a k, ..., a k]: payback = I / (a k), so the root is k* = I / (a target)."""
    wanted = target * years
    k_true = investment / (saving * wanted)
    assume(abs(k_true - BRACKET_LO) > 1e-4 and abs(k_true - BRACKET_HI) > 1e-4)

    def flows_at(k: float) -> list[float]:
        return [-investment, *[saving * k] * years]

    k = be.solve(flows_at, wanted)
    if BRACKET_LO < k_true < BRACKET_HI:
        assert k is not None and abs(k - k_true) <= 1e-3 * max(1.0, k_true)
        pay = metrics.payback(flows_at(k))
        assert pay is not None and abs(pay - wanted) <= 1e-3
    else:
        assert k is None


@settings(deadline=None, max_examples=15)
@given(d1=st.floats(0, 0.9), d2=st.floats(0, 0.9))
def test_T8_3_labor_cost_bar_grows_with_delta_and_is_zero_at_zero(d1: float, d2: float) -> None:
    ctx = golden_ctx("client_current")
    lo, hi = sorted((d1, d2))

    def bar(delta: float) -> dict[str, float]:
        s = sensitivity_oat(ctx, ["labor_cost"], delta)
        assert [b.delta_tco for b in s.tornado] == sorted(
            (b.delta_tco for b in s.tornado), reverse=True
        )
        return {b.scenario_id: b.delta_tco for b in s.tornado}

    small, large = bar(lo), bar(hi)
    assert all(large[sid] >= small[sid] - 1e-6 for sid in small)  # TCO is linear in labor cost
    if lo == 0:
        assert all(abs(v) < 1e-6 for v in small.values())


@settings(deadline=None, max_examples=8)
@given(delta=st.floats(0, 0.6))
def test_T8_3_tornado_is_sorted_with_one_bar_per_pair_for_any_delta(delta: float) -> None:
    s = sensitivity_oat(golden_ctx("S0"), delta=delta)
    pairs = [(b.scenario_id, b.param) for b in s.tornado]
    assert len(pairs) == len(set(pairs)) == 14
    deltas = [b.delta_tco for b in s.tornado]
    assert deltas == sorted(deltas, reverse=True) and all(d >= 0 for d in deltas)


@settings(deadline=None, max_examples=8)
@given(percentiles=st.lists(st.floats(10, 100), min_size=2, max_size=4, unique=True).map(sorted))
def test_percentile_sweep_is_monotone_in_design_lines(percentiles: list[float]) -> None:
    rows = percentile_sweep(golden_ctx(), percentiles)
    for sid in ("S0", "S2"):
        mine = [r for r in rows if r.scenario_id == sid]
        assert [r.percentile for r in mine] == percentiles
        lines = [r.design_lines for r in mine]
        assert lines == sorted(lines)

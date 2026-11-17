"""T6.4 properties of the F6e Erlang-C check: P_wait is a probability and decreases with the
number of servers; the stable-pool outputs are consistent."""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from whsizing.engine.queue import erlang_c, queue_resource

servers = st.integers(min_value=1, max_value=60)
load_share = st.floats(min_value=0.0, max_value=0.999, allow_nan=False)


@given(servers, load_share)
def test_T6_4_p_wait_is_a_probability(c: int, share: float) -> None:
    """0 ≤ erlang_c(c, a) ≤ 1 for every stable load a = share × c."""
    assert 0.0 <= erlang_c(c, share * c) <= 1.0


@given(servers, load_share)
def test_T6_4_p_wait_decreases_with_servers(c: int, share: float) -> None:
    """Adding a server at the same offered load never raises P_wait (float noise allowed)."""
    a = share * c
    assert erlang_c(c + 1, a) <= erlang_c(c, a) + 1e-12


@given(
    servers,
    load_share,
    st.floats(min_value=0.1, max_value=500.0),
    st.floats(min_value=0.0, max_value=10.0),
)
def test_T6_4_stable_pool_outputs_are_consistent(c: int, share: float, mu: float, t: float) -> None:
    """Stable pool: W_q ≥ 0 and 0 ≤ P(W > t) ≤ P_wait ≤ 1."""
    r = queue_resource("x", c, share * c * mu, mu, t)
    assert r.stable and r.c_min is None
    assert r.p_wait is not None and r.w_q_h is not None and r.p_wait_gt_t is not None
    assert r.w_q_h >= 0.0
    assert 0.0 <= r.p_wait_gt_t <= r.p_wait + 1e-15 <= 1.0 + 1e-15

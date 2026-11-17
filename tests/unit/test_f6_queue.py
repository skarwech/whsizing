"""F6e queue / SLA check: T6.4 (Erlang-C values, closed forms) and the pools on the toy case.

Toy (test_f6_area): pack stations 8, pack_rate 34.375 → μ = 34.375 × 0.85 = 29.21875 orders/h;
peak-hour orders 213; SLA window 3.5 h → t = 1.75 h; orders 1420."""

from __future__ import annotations

import math
import shutil
from pathlib import Path
from typing import Any

import pytest
from tests.unit.test_f6_area import ROSTER, SHARE_S
from tests.unit.test_f6_inputs import build
from tests.unit.test_f6_throughput import toy

from whsizing.catalog import load_catalog
from whsizing.engine import WorldInputs, size_storage, size_throughput
from whsizing.engine.area import size_area
from whsizing.engine.queue import (
    MAX_SERVERS,
    QueueWorld,
    erlang_c,
    queue_resource,
    queue_result,
    size_queue,
)
from whsizing.engine.throughput import ThroughputWorld
from whsizing.errors import SizingInfeasibleError, WhsizingError
from whsizing.schemas import EligibilityCfg, FamilyId

MU_PACK = 34.375 * 0.85
CATALOG_DIR = Path(__file__).resolve().parents[2] / "catalog"


def run(
    family: FamilyId = "manual_p2p", **kw: Any
) -> tuple[WorldInputs, ThroughputWorld, QueueWorld]:
    inp = build(toy(), family, **kw)
    st = size_storage(inp)
    tp = size_throughput(inp, st)
    a = size_area(inp, st, tp, roster=ROSTER, share_s=SHARE_S)
    return inp, tp, size_queue(inp, tp, a)


def test_T6_4_erlang_c_values() -> None:
    """Spec T6.4: erlang_c(1, 0.5) == 0.5 (M/M/1: P_wait = ρ); erlang_c(2, 1.0) = 1/3
    (M/M/2: 2ρ² / (1 + ρ) with ρ = 0.5)."""
    assert erlang_c(1, 0.5) == 0.5
    assert erlang_c(2, 1.0) == pytest.approx(1 / 3, rel=1e-12)
    assert erlang_c(3, 0.0) == 0.0


def test_T6_4_w_q_matches_mm1_closed_form() -> None:
    """c = 1, λ = 3, μ = 5: ρ = 0.6, W_q = ρ / (μ − λ) = 0.3 h; P(W > t) = ρ e^{−(μ−λ)t}."""
    r = queue_resource("x", 1, 3.0, 5.0, 0.5)
    rho = 0.6
    assert r.stable and r.c_min is None
    assert r.p_wait == pytest.approx(rho, rel=1e-12)
    assert r.w_q_h == pytest.approx(rho / (5.0 - 3.0), rel=1e-12)
    assert r.p_wait_gt_t == pytest.approx(rho * math.exp(-2.0 * 0.5), rel=1e-12)


def test_T6_4_w_q_matches_mm2_closed_form() -> None:
    """c = 2, λ = 6, μ = 4: ρ = 0.75, P_wait = 2ρ² / (1 + ρ) = 0.642857,
    W_q = L_q / λ = 2ρ³ / (λ (1 − ρ²)) = 0.321429 h."""
    r = queue_resource("x", 2, 6.0, 4.0, 1.0)
    rho = 0.75
    assert r.offered_load == pytest.approx(1.5)
    assert r.p_wait == pytest.approx(2 * rho**2 / (1 + rho), rel=1e-12)
    assert r.w_q_h == pytest.approx(2 * rho**3 / (6.0 * (1 - rho**2)), rel=1e-12)


@pytest.mark.parametrize(("c", "lam", "mu", "c_min"), [(1, 10.0, 6.0, 3), (2, 8.0, 4.0, 3)])
def test_unstable_pool_has_no_wait_and_suggests_c_min(
    c: int, lam: float, mu: float, c_min: int
) -> None:
    """a ≥ c (a = 1.667 > 1; a = 2 = c) → stable False, P_wait / W_q / P(W > t) None,
    c_min = ceil(a) + 1."""
    r = queue_resource("x", c, lam, mu, 1.0)
    assert not r.stable
    assert (r.p_wait, r.w_q_h, r.p_wait_gt_t, r.c_min) == (None, None, None, c_min)


@pytest.mark.parametrize(("c", "a"), [(0, 0.0), (1, 1.0), (2, 2.5), (2, -0.1)])
def test_erlang_c_rejects_unstable_or_invalid(c: int, a: float) -> None:
    with pytest.raises(WhsizingError):
        erlang_c(c, a)


def test_manual_packing_pool_unstable_when_sla_rate_binds() -> None:
    """λ_s = max(213, 0.6 × 1420 / 3.5 = 243.43) = 243.43 → a = 243.43 / 29.21875 = 8.331 ≥ 8
    stations → F_UNSTABLE:packing, c_min = 10; no ports pool for the manual family."""
    inp, _, q = run()
    (r,) = q.resources
    assert r.resource == "packing" and r.servers == 8
    assert r.arrival_rate_h == pytest.approx(0.6 * 1420 / 3.5, rel=1e-12)
    assert r.service_rate_h == pytest.approx(MU_PACK, rel=1e-12)
    assert r.t_h == pytest.approx(1.75)
    assert not r.stable and r.c_min == 10 and r.p_wait is None
    assert [f.code for f in q.flags] == ["F_UNSTABLE:packing"]
    assert inp.tracer.get(inp.tid("queue.packing.c_min")).value == 10
    assert inp.tracer.get(inp.tid("queue.packing.stable")).value == 0.0
    ids = {n.id for n in inp.tracer.nodes}
    assert "S9.queue.packing.p_wait" not in ids and "S9.queue.packing.w_q_h" not in ids


def test_packing_sla_risk() -> None:
    """same_day_share 0.575: λ_s = 233.21 (SLA term binds), cμ − λ_s = 0.536 orders/h,
    P(W > 1.75 h) = P_wait × e^{−0.938} > 5 % → F_SLA_RISK:packing."""
    _, _, q = run(same_day_share=0.575)
    (r,) = q.resources
    lam = 0.575 * 1420 / 3.5
    gap = 8 * MU_PACK - lam
    assert r.stable and r.p_wait is not None and r.p_wait_gt_t is not None
    assert r.p_wait == pytest.approx(erlang_c(8, lam / MU_PACK), rel=1e-12)
    assert r.w_q_h == pytest.approx(r.p_wait / gap, rel=1e-12)
    assert r.p_wait_gt_t == pytest.approx(r.p_wait * math.exp(-gap * 1.75), rel=1e-12)
    assert r.p_wait_gt_t > 0.05
    assert [f.code for f in q.flags] == ["F_SLA_RISK:packing"]


def test_packing_stable_without_risk() -> None:
    """same_day_share 0.3: λ_s = max(213, 121.7) = 213 (peak hour binds), a = 7.29 < 8, gap 20.75
    → P(W > t) ≈ 0, no flag."""
    _, _, q = run(same_day_share=0.3)
    (r,) = q.resources
    assert r.arrival_rate_h == pytest.approx(213.0)
    assert r.stable and r.p_wait_gt_t is not None and r.p_wait_gt_t < 1e-10
    assert q.flags == ()


def test_cube_ports_offered_load_equals_sizing_load() -> None:
    """I45: λ_s = λ_e + decant_port_load_peak_h × μ, so a = λ_e / (port_rate × oee) + decant load
    = the I23 port load (2 × utilisation 0.54095 = 1.0819) < 2 ports."""
    inp, tp, q = run("cube_asrs", same_day_share=0.3)
    ports = next(r for r in q.resources if r.resource == "ports")
    load = inp.tracer.get(inp.tid("equipment.port_load")).value
    assert ports.servers == 2 and ports.service_rate_h == pytest.approx(350 * 0.85)
    assert ports.offered_load == pytest.approx(load, rel=1e-12)
    assert ports.arrival_rate_h == pytest.approx(tp.lam_e + tp.decant_port_load_peak_h * 297.5)
    assert ports.stable and ports.p_wait == pytest.approx(erlang_c(2, load), rel=1e-12)


def test_amr_gtp_station_pool() -> None:
    """AMR: c = gtp_stations (1), μ = station_rate × oee, λ_s = λ_e (no decant load)."""
    inp, tp, q = run("amr_gtp", same_day_share=0.3)
    pool = next(r for r in q.resources if r.resource == "gtp_stations")
    mu = inp.v("amr_gtp.station_rate_lines_h") * inp.v("amr_gtp.oee")
    assert pool.servers == 1 and pool.arrival_rate_h == pytest.approx(tp.lam_e)
    assert pool.offered_load == pytest.approx(tp.utilisation["gtp_stations"], rel=1e-12)
    assert pool.p_wait == pytest.approx(tp.lam_e / mu, rel=1e-12)  # M/M/1: P_wait = ρ


def test_degenerate_cube_skips_the_ports_pool() -> None:
    """I48: no eligible line (all SKUs heavier than 0.5 kg) → ports 0, λ_e 0 → no ports pool."""
    inp, tp, q = run("cube_asrs", eligibility=EligibilityCfg(extra_max_weight_kg=0.5))
    assert tp.equipment["ports"] == 0
    assert [r.resource for r in q.resources] == ["packing"]
    assert not [n.id for n in inp.tracer.nodes if n.id.startswith("S9.queue.ports.")]


def test_queue_result_is_the_typical_world() -> None:
    _, _, q = run()
    r = queue_result({"lo": QueueWorld((), ()), "typ": q, "hi": QueueWorld((), ())})
    assert r.resources == list(q.resources) and r.flags == list(q.flags)


# --- I85 (b): plausibility bound on c (R8b, final audit M5) ----------------------------------
def test_T6_4_erlang_c_rejects_c_above_the_bound() -> None:
    """The loop is O(c): c above the bound is SizingInfeasibleError (exit 4) before the loop,
    naming the bound and R13; a c at the bound still runs (and in well under a second)."""
    with pytest.raises(
        SizingInfeasibleError, match=r"c = 100,001.*check units and outliers \(R13\)"
    ) as e:
        erlang_c(MAX_SERVERS + 1, 1.0)
    assert e.value.exit_code == 4
    with pytest.raises(SizingInfeasibleError, match="c = 417,235,608"):
        erlang_c(417_235_608, 1.0)  # the audit's 1e12-quantity case: must not loop
    assert erlang_c(MAX_SERVERS, 1.0) == pytest.approx(0.0, abs=1e-12)
    assert erlang_c(10, 1.0, max_c=10) < 1e-6
    with pytest.raises(SizingInfeasibleError):
        erlang_c(11, 1.0, max_c=10)  # the world's bound (a basis override) replaces the default


def test_T6_4_queue_resource_passes_the_bound_to_erlang_c() -> None:
    with pytest.raises(SizingInfeasibleError, match="exceeds the bound 50"):
        queue_resource("ports", 51, 10.0, 5.0, 1.0, max_c=50)


def test_T6_4_default_bound_is_the_catalog_scalar() -> None:
    """`MAX_SERVERS` (erlang_c called without a world) = `engine.max_equipment_count` [P]."""
    inp, _, _ = run()
    assert inp.v("engine.max_equipment_count") == MAX_SERVERS == 100_000
    assert "engine.max_equipment_count" in inp.catalog.constants  # a scalar: no Param (I47)
    assert "engine.max_equipment_count" not in inp.catalog.params


def test_T6_4_a_catalog_copy_without_the_bound_still_loads_with_the_default(
    tmp_path: Path,
) -> None:
    """Run folders made before I85 (b) hold a catalog copy without `max_equipment_count`
    (`report`, `compare`, `rerun`, the app read it): the model default (= MAX_SERVERS) applies."""
    old = tmp_path / "catalog"
    shutil.copytree(CATALOG_DIR, old)
    path = old / "engine_defaults.yaml"
    path.write_text(
        "".join(ln for ln in path.read_text("utf-8").splitlines(True) if "max_equipment" not in ln),
        encoding="utf-8",
    )
    assert "max_equipment_count" not in path.read_text("utf-8")
    assert load_catalog(old).constants["engine.max_equipment_count"] == MAX_SERVERS

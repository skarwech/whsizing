"""F6e queue / SLA check: Erlang-C on the pack stations and on the GTP stations or cube ports
(I45). Trace ids `<sid>.queue.<pool>.<QueueResource field>` (golden keys); a field that is
None (unstable pool, or `c_min` of a stable one) has no trace node."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass

from whsizing.design import sla_window_hours
from whsizing.engine.area import PACK_OEE, AreaWorld
from whsizing.engine.inputs import WorldInputs
from whsizing.engine.throughput import MAX_COUNT, ThroughputWorld
from whsizing.errors import SizingInfeasibleError, WhsizingError
from whsizing.schemas import Flag, QueueResource, QueueResult, World

T_SHARE = "engine.sla_wait_threshold_share"  # t = sla_window_hours × 0.5
RISK = "engine.sla_risk_max_probability"  # F_SLA_RISK if P(W > t) > 5 %
# I85 (b): bound on c of the O(c) Erlang-C loop. The default is the catalog scalar
# engine.max_equipment_count (a test pins them together); the sizing code passes the world's value.
MAX_SERVERS = 100_000
# family → (pool = equipment count, service rate per server, oee)
AUTOMATED = {
    "cube_asrs": ("ports", "cube_asrs.port_rate_lines_h", "cube_asrs.oee"),
    "amr_gtp": ("gtp_stations", "amr_gtp.station_rate_lines_h", "amr_gtp.oee"),
}


@dataclass(frozen=True)
class QueueWorld:
    resources: tuple[QueueResource, ...]
    flags: tuple[Flag, ...]  # F_UNSTABLE:<pool>, F_SLA_RISK:<pool>


def erlang_c(c: int, a: float, *, max_c: int = MAX_SERVERS) -> float:
    """P(wait) of an M/M/c queue with offered load a = λ/μ; requires 0 ≤ a < c (spec F6e).
    `c` above `max_c` (I85 b) is SizingInfeasibleError: the loop is O(c) and such a count means a
    units or outlier problem."""
    if c > max_c:
        raise SizingInfeasibleError(
            f"erlang_c: c = {c:,} servers exceeds the bound {max_c:,} "
            "(engine.max_equipment_count); check units and outliers (R13)"
        )
    if c < 1 or not 0.0 <= a < c:
        raise WhsizingError(f"erlang_c needs c ≥ 1 and 0 ≤ a < c, got c={c}, a={a}")
    b = 1.0  # Erlang-B recursion for numerical stability
    for k in range(1, c + 1):
        b = a * b / (k + a * b)
    rho = a / c
    return b / (1 - rho + rho * b)


def queue_resource(
    resource: str, c: int, lam_s: float, mu: float, t_h: float, *, max_c: int = MAX_SERVERS
) -> QueueResource:
    """One pool: a = λ_s / μ; stable (a < c) → P_wait, W_q = P_wait / (cμ − λ_s) (hours),
    P(W > t) = P_wait × exp(−(cμ − λ_s) t); unstable → those None, c_min = ceil(a) + 1."""
    if not (math.isfinite(mu) and math.isfinite(lam_s) and math.isfinite(t_h)):
        raise WhsizingError(f"queue {resource}: non-finite rate (μ={mu}, λ={lam_s}, t={t_h})")
    if mu <= 0 or lam_s < 0 or c < 0:
        raise WhsizingError(f"queue {resource}: needs μ > 0, λ ≥ 0, c ≥ 0 (μ={mu}, λ={lam_s})")
    a = lam_s / mu
    stable = a < c
    p = erlang_c(c, a, max_c=max_c) if stable else None
    gap = c * mu - lam_s
    return QueueResource(
        resource=resource,
        servers=c,
        arrival_rate_h=lam_s,
        service_rate_h=mu,
        offered_load=a,
        stable=stable,
        p_wait=p,
        w_q_h=None if p is None else p / gap,
        t_h=t_h,
        p_wait_gt_t=None if p is None else p * math.exp(-gap * t_h),
        c_min=None if stable else math.ceil(a) + 1,
    )


def size_queue(inp: WorldInputs, tp: ThroughputWorld, area: AreaWorld) -> QueueWorld:
    """F6e for one world: the packing pool, then the family's stations or ports. A pool with no
    server and no arrivals (manual family, or I48 degenerate cube: ports = 0) is skipped."""
    t_h = sla_window_hours(inp.basis.service) * inp.v(T_SHARE)
    pools = [_packing(inp, area, t_h)]
    if inp.scenario.family in AUTOMATED:
        pools.append(_stations(inp, tp, t_h))
    resources = tuple(r for r in pools if r is not None)
    for r in resources:
        _trace(inp, r)
    risk = inp.v(RISK)
    flags: list[Flag] = []
    for r in resources:
        if not r.stable:
            msg = (
                f"{r.resource}: offered load {r.offered_load:.2f} ≥ {r.servers} servers; "
                f"at least {r.c_min} needed"
            )
            flags.append(
                Flag(
                    code=f"F_UNSTABLE:{r.resource}",
                    severity="warning",
                    message=msg,
                    value=r.offered_load,
                )
            )
        elif r.p_wait_gt_t is not None and r.p_wait_gt_t > risk:
            msg = f"{r.resource}: P(wait > {r.t_h:.2f} h) = {r.p_wait_gt_t:.1%} > {risk:.0%}"
            flags.append(
                Flag(
                    code=f"F_SLA_RISK:{r.resource}",
                    severity="warning",
                    message=msg,
                    value=r.p_wait_gt_t,
                )
            )
    return QueueWorld(resources, tuple(flags))


def queue_result(worlds: Mapping[World, QueueWorld]) -> QueueResult:
    """`QueueResource` holds scalars, not Ranges: the result is the typical world's (every world
    is traced)."""
    typ = worlds["typ"]
    return QueueResult(resources=list(typ.resources), flags=list(typ.flags))


def _max_c(inp: WorldInputs) -> int:
    return int(inp.v(MAX_COUNT))


def _packing(inp: WorldInputs, area: AreaWorld, t_h: float) -> QueueResource | None:
    """I45: c = pack_stations, μ = pack_rate × oee, λ_s = max(peak_hour_orders, same_day_share ×
    orders / sla_window_hours)."""
    dd, svc = inp.design_day, inp.basis.service
    lam_s = max(area.peak_hour_orders, svc.same_day_share * dd.orders / sla_window_hours(svc))
    mu = area.pack_rate * inp.v(PACK_OEE)
    if area.pack_stations == 0 and lam_s == 0:
        return None
    r = queue_resource("packing", area.pack_stations, lam_s, mu, t_h, max_c=_max_c(inp))
    q = "queue.packing."
    inp.record(
        f"{q}servers",
        "Pack stations (servers)",
        float(r.servers),
        "-",
        "pack_stations",
        {"pack_stations": inp.tid("area.pack_stations")},
    )
    inp.record(
        f"{q}service_rate_h",
        "Pack station service rate",
        mu,
        "orders/h",
        "pack_rate × oee",
        {"pack_rate": inp.tid("area.pack_rate"), "oee": f"param:{PACK_OEE}"},
    )
    inp.record(
        f"{q}arrival_rate_h",
        "Order arrival rate (SLA window)",
        lam_s,
        "orders/h",
        "max(peak_hour_orders, same_day_share × orders / sla_window_hours)",
        {
            "peak_hour_orders": inp.tid("area.peak_hour_orders"),
            "same_day_share": "data:basis.service.same_day_share",
            "orders": "data:design_day.orders",
            "sla_window_hours": inp.tid("throughput.sla_window_hours"),
        },
    )
    return r


def _stations(inp: WorldInputs, tp: ThroughputWorld, t_h: float) -> QueueResource | None:
    """I45: cube ports c = ports, μ = port_rate × oee, λ_s = λ_e + decant_port_load_peak_h × μ
    (decant in line-equivalents, I23); AMR stations: the same with λ_s = λ_e (no decant load)."""
    pool, rate, oee = AUTOMATED[inp.scenario.family]
    mu = inp.v(rate) * inp.v(oee)
    lam_s = tp.lam_e + tp.decant_port_load_peak_h * mu
    if tp.equipment[pool] == 0 and lam_s == 0:
        return None
    r = queue_resource(pool, int(tp.equipment[pool]), lam_s, mu, t_h, max_c=_max_c(inp))
    q = f"queue.{pool}."
    inp.record(
        f"{q}servers",
        f"{pool} (servers)",
        float(r.servers),
        "-",
        pool,
        {pool: inp.tid(f"equipment.{pool}")},
    )
    inp.record(
        f"{q}service_rate_h",
        f"{pool} service rate",
        mu,
        "lines/h",
        "rate × oee",
        {"rate": f"param:{rate}", "oee": f"param:{oee}"},
    )
    refs = {"lambda_e": inp.tid("throughput.lambda_e"), "mu": inp.tid(f"{q}service_rate_h")}
    if pool == "ports":
        refs["decant_port_load_peak_h"] = inp.tid("equipment.decant_port_load_peak_h")
    inp.record(
        f"{q}arrival_rate_h",
        f"{pool} arrival rate",
        lam_s,
        "lines/h",
        "lambda_e + decant_port_load_peak_h × mu" if pool == "ports" else "lambda_e",
        refs,
    )
    return r


def _trace(inp: WorldInputs, r: QueueResource) -> None:
    """The fields every pool shares; None fields are not traced."""
    q = f"queue.{r.resource}."
    ids = {k: inp.tid(f"{q}{k}") for k in ("servers", "arrival_rate_h", "service_rate_h")}
    a = {"lambda_s": ids["arrival_rate_h"], "mu": ids["service_rate_h"]}
    inp.record(f"{q}offered_load", "Offered load", r.offered_load, "-", "lambda_s / mu", a)
    load = {"a": inp.tid(f"{q}offered_load"), "c": ids["servers"]}
    inp.record(f"{q}stable", "Stable (a < c)", float(r.stable), "-", "a < c", load)
    inp.record(
        f"{q}t_h",
        "Wait threshold",
        r.t_h,
        "h",
        "sla_window_hours × threshold_share",
        {
            "sla_window_hours": inp.tid("throughput.sla_window_hours"),
            "threshold_share": f"param:{T_SHARE}",
        },
    )
    if r.c_min is not None:
        inp.record(f"{q}c_min", "Minimum stable servers", float(r.c_min), "-", "ceil(a) + 1", load)
    if r.p_wait is None or r.w_q_h is None or r.p_wait_gt_t is None:
        return
    inp.record(f"{q}p_wait", "P(wait)", r.p_wait, "-", "erlang_c(c, a)", load)
    pw = inp.tid(f"{q}p_wait")
    gap = {"p_wait": pw, **ids}
    inp.record(f"{q}w_q_h", "Mean wait", r.w_q_h, "h", "p_wait / (c × mu − lambda_s)", gap)
    inp.record(
        f"{q}p_wait_gt_t",
        "P(wait > t)",
        r.p_wait_gt_t,
        "-",
        "p_wait × exp(−(c × mu − lambda_s) × t)",
        {**gap, "t": inp.tid(f"{q}t_h"), "max_probability": f"param:{RISK}"},
    )

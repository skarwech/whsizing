"""F11 step 2: monthly predicted hours (`baseline_monthly`) and the closed-form θ predictor.

`site_inputs` builds a small synthetic site (F6 toy SKUs and design day, 14 months of daily series
with a November peak) and `synthetic_actuals` the actuals of a site with KNOWN multipliers; both
are shared by the other F11 tests.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import polars as pl
import pytest
from tests.fixtures import mock_basis, mock_design_day
from tests.unit.test_f6_throughput import toy

from whsizing.calibration.actuals import Actuals
from whsizing.calibration.inputs import CalibrationInputs
from whsizing.calibration.predict import (
    INDIRECT,
    Baseline,
    baseline_monthly,
    group_of,
    predict,
    restrict,
)
from whsizing.catalog import load_catalog
from whsizing.engine import size_storage, size_throughput, world_inputs
from whsizing.engine.labor import SHARE, labor_days, size_labor
from whsizing.schemas import FamilyId, ScenarioDef
from whsizing.schemas.trace import Tracer

ROOT = Path(__file__).resolve().parents[2]
CATALOG = load_catalog(ROOT / "catalog")
SKU_SHARES = (("x", 0.5), ("y", 0.2), ("z", 0.3))  # toy SKUs: A shelf, B big (pallet rack), C shelf
# relative order volume of the calendar months 1..12: the peak is November
SEASON = (0.9, 0.85, 0.95, 1.0, 1.0, 0.95, 0.9, 0.85, 1.0, 1.1, 1.4, 1.2)
# multipliers of a known site, on both sides of 1 (T11.1)
KNOWN = {
    "receiving": 1.10,
    "put_away": 1.00,
    "replenishment": 1.05,
    "picking": 1.20,
    "packing": 0.85,
    "shipping": 0.90,
    "returns": 1.00,
    "indirect": 1.10,
}


def site_inputs(
    family: FamilyId = "manual_p2p",
    n_months: int = 14,
    seed: int = 7,
    season: tuple[float, ...] = SEASON,
    orders_per_day: int = 300,
) -> CalibrationInputs:
    """Daily series and shipped lines of `n_months` from 2025-01-01 (Mon-Fri operate)."""
    rng = np.random.default_rng(seed)
    end = date(2025 + (n_months - 1) // 12, (n_months - 1) % 12 + 1, 28)
    rows: list[tuple[str, str, date, int]] = []
    daily: list[tuple[date, bool, float, float, float, float]] = []
    d, n_order = date(2025, 1, 1), 0
    skus = [s for s, _ in SKU_SHARES]
    while d <= end:
        operating = d.weekday() < 5
        n_lines = 0
        if operating:
            k = int(orders_per_day * season[d.month - 1] * rng.uniform(0.9, 1.1))
            per_order = rng.integers(1, 4, size=k)
            picked = rng.choice(skus, size=int(per_order.sum()), p=[p for _, p in SKU_SHARES])
            qty = rng.integers(1, 5, size=len(picked))
            owners = np.repeat(np.arange(n_order, n_order + k), per_order)
            rows += [
                (f"o{o}", str(s), d, int(q)) for o, s, q in zip(owners, picked, qty, strict=True)
            ]
            n_order += k
            n_lines = len(picked)
        daily.append((d, operating, float(n_lines), float(int(0.8 * n_lines)), 1.0, 0.0))
        d += timedelta(days=1)
    lines = pl.DataFrame(
        rows,
        schema={"order_id": pl.Utf8, "sku": pl.Utf8, "date": pl.Date, "qty_units": pl.Int64},
        orient="row",
    )
    cols = ("date", "is_operating", "lines", "parcels", "pallets_out", "receipts_units")
    series = pl.DataFrame(
        daily,
        schema=dict(zip(cols, (pl.Date, pl.Boolean, *[pl.Float64] * 4), strict=True)),
        orient="row",
    )
    basis = mock_basis().model_copy(update={"overrides": {}})
    dd = mock_design_day().model_copy(update={"stock_units": 300.0})
    scenario = ScenarioDef(id="BASE", name="Baseline", family=family, is_baseline=True)
    return CalibrationInputs(basis, dd, scenario, CATALOG, toy(), series, lines)


def synthetic_actuals(
    base: Baseline,
    truth: dict[str, float],
    months: tuple[str, ...],
    noise: float = 0.02,
    seed: int = 1,
    pfd: float | None = None,
) -> Actuals:
    """Actuals of a site whose multipliers are `truth` (at the basis PF&D unless `pfd`), with
    multiplicative gaussian noise: the predictor itself generates them."""
    b = restrict(base, months)
    pred = predict(b, truth, b.pfd if pfd is None else pfd, tuple(truth))
    rng = np.random.default_rng(seed)
    hours = {g: h * (1 + noise * rng.standard_normal(len(h))) for g, h in pred.items()}
    return Actuals(months, hours, (), None, ())


@pytest.fixture(scope="module")
def inputs() -> CalibrationInputs:
    return site_inputs()


@pytest.fixture(scope="module")
def base(inputs: CalibrationInputs) -> Baseline:
    return baseline_monthly(inputs)


def test_baseline_months_and_groups(base: Baseline) -> None:
    assert base.months[0] == "2025-01" and base.months[-1] == "2026-02" and len(base.months) == 14
    assert base.groups == (
        "receiving",
        "put_away",
        "replenishment",
        "picking",
        "packing",
        "shipping",
        "returns",
        INDIRECT,
    )  # F6c table rows; no decant in the manual family; receipt_check inside receiving
    assert all(h.shape == (14,) and (h > 0).all() for h in base.hours.values())
    assert group_of("packing_ML") == "packing" and group_of("receipt_check") == "receiving"
    assert all(c == 1.0 for c in base.coverage.values())


def test_I74e_coverage_is_the_share_of_the_month_inside_the_calendar_range(
    inputs: CalibrationInputs,
) -> None:
    """The range of the daily series, not its first shipped day, sets the partial months: an
    extract from Jan 2 to Feb 20 covers 30/31 of January and 20/28 of February."""
    keep = pl.col("date").is_between(date(2025, 1, 2), date(2026, 2, 20))
    cut = replace(inputs, daily=inputs.daily.filter(keep), lines=inputs.lines.filter(keep))
    cov = baseline_monthly(cut).coverage
    assert cov["2025-01"] == pytest.approx(30 / 31) and cov["2026-02"] == pytest.approx(20 / 28)
    assert all(cov[m] == 1.0 for m in cov if m not in ("2025-01", "2026-02"))


def test_baseline_sums_equal_the_engine_base_hours(
    inputs: CalibrationInputs, base: Baseline
) -> None:
    """The monthly hours add up to size_labor's `labor.<a>.base_hours` (same daily hours)."""
    inp = world_inputs(
        inputs.basis, inputs.design_day, inputs.scenario, inputs.catalog, inputs.sku, "typ",
        Tracer("BASE"),
    )  # fmt: skip
    days = labor_days(inp, inputs.daily, inputs.lines)
    size_labor(inp, size_throughput(inp, size_storage(inp)), days)
    members = {
        "receiving": ("receiving", "receipt_check"),
        "packing": ("packing_S", "packing_ML"),
        "shipping": ("shipping_parcel", "shipping_pallet"),
    }
    for g, h in base.hours.items():
        want = sum(inp.tracer.get(f"BASE.labor.{a}.base_hours").value for a in members.get(g, (g,)))
        assert h.sum() == pytest.approx(want, rel=1e-12), g
    # orders per month: every order counts on its first date (I1)
    assert base.orders.sum() == pytest.approx(inputs.lines["order_id"].n_unique())


def test_closed_form_predictor_equals_an_engine_rerun(
    inputs: CalibrationInputs, base: Baseline
) -> None:
    """hours(θ) = B / m × (1 + pfd) / (1 + pfd0), indirect = share / m × Σ direct: the engine run
    with every standard × m, the indirect share / m and the PF&D changed gives the same hours."""
    m = {**KNOWN, "picking": 1.35, "packing": 0.7, "indirect": 0.9}
    pfd = 0.2
    overrides = {t.param: t.typ_prior * m[g] for g, ts in base.targets.items() for t in ts} | {
        SHARE: base.indirect_share / m[INDIRECT]
    }
    ops = inputs.basis.operations.model_copy(update={"pfd_allowance": pfd})
    changed = CalibrationInputs(
        inputs.basis.model_copy(update={"operations": ops}),
        inputs.design_day,
        inputs.scenario.model_copy(update={"overrides": overrides}),
        inputs.catalog, inputs.sku, inputs.daily, inputs.lines,
    )  # fmt: skip
    rerun = baseline_monthly(changed)
    got = predict(base, m, pfd, base.groups)
    for g in base.groups:
        assert got[g] == pytest.approx(rerun.hours[g], rel=1e-9), g


def test_indirect_is_the_share_of_the_compared_direct_hours(base: Baseline) -> None:
    """I38: indirect = 0.12 × Σ direct, so the baseline obeys it, and `predict` takes the share of
    the direct groups it is given only (like with like)."""
    direct = [g for g in base.groups if g != INDIRECT]
    total = sum(base.hours[g] for g in direct)
    assert base.indirect_share == 0.12
    assert base.hours[INDIRECT] == pytest.approx(0.12 * total, rel=1e-12)
    ones = dict.fromkeys(base.groups, 1.0)
    some = predict(base, ones, base.pfd, ("picking", "packing", INDIRECT))
    assert some[INDIRECT] == pytest.approx(
        0.12 * (base.hours["picking"] + base.hours["packing"]), rel=1e-12
    )


def test_prior_sigma_is_half_the_catalog_range_relative_to_typ(base: Baseline) -> None:
    """σ = (max − min) / (2 typ), averaged over the standards of the activity: receiving 10-18 /
    14 and 30-60 / 45 pallets and lines per hour; picking 50-95 / 70 and 25-50 / 35; indirect has
    no range (a constant): half the multiplier bounds."""
    assert base.sigma["put_away"] == pytest.approx((16 - 10) / (2 * 13))
    assert base.sigma["receiving"] == pytest.approx(((18 - 10) / 28 + (60 - 30) / 90) / 2)
    assert base.sigma["picking"] == pytest.approx(((95 - 50) / 140 + (50 - 25) / 70) / 2)
    assert base.sigma["packing"] == pytest.approx(((70 - 40) / 110 + (32 - 18) / 50) / 2)
    assert base.sigma[INDIRECT] == pytest.approx(0.75)
    assert base.pfd == 0.12 and base.eta == 0.85
    assert {t.param for t in base.targets["picking"]} == {
        "manual_p2p.pick_rate_shelving_lines_h",
        "manual_p2p.pick_rate_pallet_lines_h",
    }
    assert {t.param: t.typ_prior for t in base.targets["shipping"]} == {
        "labor.shipping_parcel": 110.0,
        "labor.shipping_pallet": 14.0,
    }


def test_cube_family_has_decant_and_its_own_rates() -> None:
    cube = baseline_monthly(site_inputs("cube_asrs", n_months=3, orders_per_day=40))
    assert "decant" in cube.groups
    assert {t.param for t in cube.targets["decant"]} == {"cube_asrs.decant_cases_per_h"}
    assert "cube_asrs.port_rate_lines_h" in {t.param for t in cube.targets["picking"]}


def test_restrict_keeps_the_asked_months(base: Baseline) -> None:
    r = restrict(base, ("2025-03", "2025-11"))
    assert r.months == ("2025-03", "2025-11")
    assert r.hours["picking"] == pytest.approx(base.hours["picking"][[2, 10]])
    assert r.orders == pytest.approx(base.orders[[2, 10]])

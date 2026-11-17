"""F7 fix round 1: the client-current baseline with the spec's coarse labels (Appendix E), FTE hours
on the F6 basis (× utilisation), role-cost fallback on the catalog defaults, boundary validation
(negative inputs, a non-whole equipment life) and the `labor_series` consistency check."""

from __future__ import annotations

import copy
from typing import Any

import pytest
from tests.unit.test_f6_size import ROOT, golden_inputs, sized, with_basis

from whsizing.design import load_basis
from whsizing.errors import ConfigError
from whsizing.finance import compute_finance
from whsizing.schemas import DesignBasis, FinancialResult, ScenarioDef

COST = {"operator": 25.5, "forklift_driver": 27.8, "team_leader": 33.0}
ROLE_OF = {  # coarse label → cost key (primary role of the label's catalog activities)
    "picking": "operator",
    "packing": "operator",
    "receiving": "forklift_driver",
    "shipping": "operator",
    "indirect": "team_leader",
}


def client_fin(basis: DesignBasis, sid: str = "S2") -> FinancialResult:
    g = golden_inputs()
    result, tracer = sized(sid, basis=basis)
    return compute_finance(result, basis, g.catalog, None, daily=g.daily, tracer=tracer)


def with_baseline(**baseline: Any) -> DesignBasis:
    g = golden_inputs()
    return g.basis.model_copy(update={"baseline": g.basis.baseline.model_copy(update=baseline)})


def test_client_baseline_accepts_the_spec_example_labels() -> None:
    """Appendix E / basis/example_basis.yaml: `actual_fte: {picking, packing, receiving, shipping,
    indirect}` are not catalog activity ids; each takes the cost of its primary role."""
    example = load_basis(ROOT / "basis" / "example_basis.yaml")
    fte = example.baseline.actual_fte
    assert fte is not None and set(fte) == set(ROLE_OF)
    basis = with_baseline(actual_fte=fte)
    fin = client_fin(basis)
    assert fin.npv_vs_baseline is not None
    ops = basis.operations
    hours = {a: n * ops.annual_paid_hours_per_fte * ops.utilisation for a, n in fte.items()}
    base_year = sum(h * COST[ROLE_OF[a]] for a, h in hours.items())
    for t in range(1, 6):
        row = fin.opex_by_year[t - 1]
        labor = base_year * 1.04**t * 1.025 ** (t - 1)
        expected = labor + row["consumables"] + row["rent"] - sum(row.values())
        assert fin.delta_cash_flows_typ[t] == pytest.approx(expected, rel=1e-12)


def test_client_baseline_unknown_label_is_still_an_error() -> None:
    with pytest.raises(ConfigError, match=r"unknown activities \['sorting'\]"):
        client_fin(with_baseline(actual_fte={"picking": 2.0, "sorting": 1.0}))


def test_client_baseline_fte_hours_are_on_the_f6_basis() -> None:
    """A client operation staffed exactly like S0 (FTE_a = S0's base-year hours_a / (paid ×
    utilisation), Appendix B core_fte) has the labor cost of S0: the cash flows differ only by
    S0's temp hours (counted twice by I33, the baseline has none) and the maintenance, energy and
    software the baseline does not model. With paid
    hours instead (no × utilisation) the baseline labor would be 1/0.85 − 1 = 18 % dearer."""
    g = golden_inputs()
    s0, tracer = sized("S0")
    ops, gr = g.basis.operations, g.basis.projection.growth_rate
    fte = {
        a.activity: a.annual_hours[0].typ
        / (1 + gr)
        / (ops.annual_paid_hours_per_fte * ops.utilisation)
        for a in s0.labor.activities
    }
    basis = with_baseline(actual_fte=fte, actual_hours_month=None)
    fin = compute_finance(s0, basis, g.catalog, None, daily=g.daily, tracer=tracer)
    fb = basis.finance
    for t in range(1, 6):
        temp = s0.labor.temp_hours[t - 1].typ * fb.labor_cost_eur_h["operator"]
        temp *= (1 + fb.temp_premium) * (1 + fb.wage_inflation) ** (t - 1)
        row = fin.opex_by_year[t - 1]  # the baseline models no maintenance, energy, software
        existing = sum(row[k] for k in ("maintenance", "energy", "software", "renewal"))
        assert fin.delta_cash_flows_typ[t] == pytest.approx(-(temp + existing), rel=1e-9), t
    assert any("utilisation" in n for n in fin.notes)


@pytest.mark.parametrize(
    "baseline",
    [{"actual_fte": {"picking": -5.0}}, {"actual_hours_month": {"picking": [100.0, -1.0]}}],
)
def test_client_baseline_negative_inputs_are_rejected(baseline: dict[str, Any]) -> None:
    with pytest.raises(ConfigError, match="negative"):
        client_fin(with_baseline(**baseline))


def test_partial_labor_costs_fall_back_on_the_catalog_default_roles() -> None:
    """Appendix D `default_roles_cost_eur_h` {operator 26, forklift_driver 28, team_leader 34} is
    "replaced by client values": a role the client leaves out takes the default."""
    g = golden_inputs()
    assert g.catalog.finance.default_roles_cost_eur_h == {
        "operator": 26,
        "forklift_driver": 28,
        "team_leader": 34,
    }
    partial = with_basis(finance={"labor_cost_eur_h": {"operator": 25.0}})
    full = with_basis(
        finance={
            "labor_cost_eur_h": {"operator": 25.0, "forklift_driver": 28.0, "team_leader": 34.0}
        }
    )
    assert client_fin(partial, "S0") == client_fin(full, "S0")
    result, tracer = sized("S0", basis=partial)
    compute_finance(result, partial, g.catalog, None, daily=g.daily, tracer=tracer)
    refs = tracer.get("S0.opex.y1.labor", "typ").inputs  # each cost names its source
    assert refs["cost_operator"] == "data:basis.finance.labor_cost_eur_h.operator"
    assert (
        refs["cost_forklift_driver"]
        == "data:catalog.finance.default_roles_cost_eur_h.forklift_driver"
    )
    assert client_fin(partial, "S0") != client_fin(with_basis(), "S0")  # the client's 25.0 is used


def test_a_role_without_client_value_or_default_is_an_error() -> None:
    g = golden_inputs()
    catalog = copy.deepcopy(g.catalog)
    catalog.finance.default_roles_cost_eur_h.pop("team_leader")
    s0, tracer = sized("S0")
    basis = with_basis(finance={"labor_cost_eur_h": {"operator": 25.0, "forklift_driver": 28.0}})
    with pytest.raises(ConfigError, match="team_leader"):
        compute_finance(s0, basis, catalog, None, daily=g.daily, tracer=tracer)


def test_negative_labor_cost_is_rejected() -> None:
    with pytest.raises(ConfigError, match="negative"):
        client_fin(with_basis(finance={"labor_cost_eur_h": {**COST, "operator": -25.5}}), "S0")


@pytest.mark.parametrize("life", [2.5, 4.9, 0.0, -1.0])
def test_unmatchable_equipment_life_is_an_error(life: float) -> None:
    g = golden_inputs()
    scenario = ScenarioDef(
        id="S0",
        name="manual",
        family="manual_p2p",
        overrides={"manual_p2p.equipment_life_years": life},
    )
    result, tracer = sized(scenario)
    with pytest.raises(ConfigError, match="equipment_life_years"):
        compute_finance(result, g.basis, g.catalog, None, daily=g.daily, tracer=tracer)


def test_a_labor_series_other_than_the_results_is_rejected() -> None:
    """The hours come from the F6 trace of `result`; a different LaborResult would change
    nothing, so it is refused instead of ignored."""
    g = golden_inputs()
    s0, tracer = sized("S0")
    same = compute_finance(s0, g.basis, g.catalog, None, s0.labor, daily=g.daily,
                           tracer=copy.deepcopy(tracer))  # fmt: skip
    assert same.capex_total.typ > 0
    other = s0.labor.model_copy(update={"activities": s0.labor.activities[:-1]})
    with pytest.raises(ConfigError, match="labor_series"):
        compute_finance(s0, g.basis, g.catalog, None, other, daily=g.daily, tracer=tracer)

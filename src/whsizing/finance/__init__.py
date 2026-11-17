"""F7 finance module: capex, opex, TCO, NPV, IRR, payback, cost per line, in the three worlds.

Final signature (F8 calls it once per scenario, baseline scenario first or last, after
`size_scenario` and before `write_scenario`)::

    fin = compute_finance(
        result,                    # ScenarioResult of the scenario (status computed)
        basis, catalog,            # DesignBasis, Catalog (same objects as for size_scenario)
        baseline,                  # ScenarioResult of the baseline scenario, or None
        labor_series=None,         # LaborResult; default result.labor (activities and roles)
        *,
        daily,                     # F3 ProfileTables.daily (annual orders and lines, I4, I35, I36)
        tracer,                    # the scenario's Tracer from size_scenario (all worlds, I62)
        baseline_tracer=None,      # Tracer of the baseline scenario; required with a baseline
        client_baseline=True,      # False: baseline=None means no baseline at all
    ) -> FinancialResult
    write_finance(fin, project_dir)          # scenarios/<id>/finance.json, deterministic JSON

Deviation from the spec signature `compute_finance(result, basis, catalog, baseline,
labor_series)`: `daily` (annual orders and lines) and `tracer` (the F6 quantities of the three
worlds) are extra keyword arguments, `baseline_tracer` and `client_baseline` serve the baseline.
The hours of each world come from the F6 trace nodes `<sid>.labor.<activity>.annual_hours.y<t>`
and `labor.temp_hours.y<t>`, so `labor_series` is only checked: any LaborResult other than
`result.labor` raises ConfigError instead of being silently ignored.

Labor cost per role: the client's `basis.finance.labor_cost_eur_h`, role by role, else the catalog
`default_roles_cost_eur_h` (Appendix D); negative costs and a role key that is not a catalog role
(a typo) raise ConfigError. `wms_adaptation_default_eur` stays
unused (I29: controls = `manual_p2p.wms_adaptation_fixed_eur`).

Baseline (I42): `baseline` = a computed scenario (golden: S0 for S2): its capex and opex are
costed in the same world as the scenario. `baseline=None`: the client's current operation if
`basis.baseline.actual_hours_month` or `actual_fte` is given (capex 0, labor from those actuals,
see `baseline.CLIENT_NOTE`): FTE × annual_paid_hours_per_fte × utilisation (the F6 core_fte
convention, so a client staffed like the scenario has the same labor cost), keys = catalog
activities or the coarse labels of the spec's example (picking, packing, receiving, shipping,
indirect: `baseline.COARSE_ROLE`); negative or unknown values raise. Else NPV / IRR / payback are
None and the notes say why. The baseline scenario itself is computed with `baseline=None,
client_baseline=False` (no NPV against itself).

Renewal (I35): `equipment_life_years` <= 0, or fractional and within the horizon, raises (it would
never match a year t).

An automated scenario with no eligible line (I48) is costed with the manual formulas (WMS
adaptation, manual shares, software and maintenance, overflow 0) and says so in `notes`.

Trace: every quantity is recorded in `tracer` (scope = scenario id, all three worlds; IRR and
payback in the typical world only) with ids equal to the golden keys: `<sid>.capex.<item>`,
`<sid>.opex.y<t>.<item>`, `<sid>.finance.{tco,cost_per_line,annual_lines_y1,npv,irr,
payback_years,delta_cf.y<t>}`, plus `finance.cash_flow.y<t>`, `finance.annual_orders.y<t>`,
`capex.overflow.{storage,equipment}`, `opex.{maintenance,rent_year,energy_kwh_year}` and
`finance.baseline.{capex,opex.y<t>}`. Calling it twice on one tracer with other settings makes
`Tracer.record` raise: use one tracer (or a deepcopy) per variant. **Export the trace after
finance**: `compute_finance`, then `write_finance` and `write_scenario(result, tracer, dir)`.

FinancialResult conventions: `capex` / `opex_by_year` hold the items without `total` (the sum of
a year's dict is opex_t); `cash_flows_typ` = [−capex, −opex_1..T]; `delta_cash_flows_typ` = Δcf
vs the baseline ([] without one). Ranges: lo = min over the worlds, hi = max (ADR-002).
IRR and payback are typ-world values (I73 h): the schema gives them no Range.
"""

from whsizing.finance.compute import compute_finance, write_finance
from whsizing.finance.metrics import annuity_factor, cost_per_line, irr, npv, payback, tco

__all__ = [
    "annuity_factor",
    "compute_finance",
    "cost_per_line",
    "irr",
    "npv",
    "payback",
    "tco",
    "write_finance",
]

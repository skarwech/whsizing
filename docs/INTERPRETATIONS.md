# Interpretations register

Where `description.md` is ambiguous or silent, the rule below is the one the golden oracle
(`tests/golden/oracle.py`, `demand.py`, `build_golden.py`) uses, and the one the engine follows.
To change an entry, contest it (pull request on this file + rebuilt golden case:
`uv run python -m tests.golden.build_golden`); do not diverge silently.

Conventions: `lines*`, `orders*`, `units*`, `parcels*`, `pallets_out*` are design-day values after
growth (F4 step 5); `gf = (1 + g)^T`; `n_op` = observed operating days; "period" = the whole
loaded history. Keys are those of `tests/golden/golden_values.json`. The oracle computes the
typical world only.

## Register

**I1 — Which lines, which date.** Shipped lines = `line_status ∈ {shipped, null}` and
`qty_units > 0`; cancelled and returned lines are excluded. Every line of an order takes the
order's first `order_ts` (F3 edge case "multi-day orders"), converted to `basis.timezone`; local
date and local hour come from that timestamp. Keys: `daily.*`, `profile.n_*`, `design_day.*`.

**I2 — Operating days and calendar.** Calendar = every date from the first to the last local
date with a shipped line. A date is operating iff `lines_d ≥ max(1, 0.10 × median(lines_d > 0))`.
The holiday clause ("unless it is a French public holiday with no volume") adds nothing: a date
with no volume already fails the threshold. Keys: `profile.operating_threshold`,
`profile.operating_days`.

**I3 — Statistics.** All percentiles use `numpy.percentile(x, q)` (linear interpolation) over
operating days. `CV = numpy.std(x, ddof=0) / mean(x)` (population std). EIQ distributions are
over all shipped orders (per order) or all shipped lines (`units_per_line`), not per day.
Keys: `daily.<m>.<stat>`, `eiq.*`.

**I4 — Annual quantities from a short series.** Any annual total built from the daily series
is `Σ_{operating days d} x_d × operating_days_per_year / n_op`. With 31 days of history:
`× 252 / 26`. Applies to annual hours, temp hours, annual orders (consumables) and annual lines
(cost per line). Keys: `S*.labor.*.annual_hours.y<t>`, `S*.labor.temp_hours.y<t>`,
`S*.opex.y<t>.consumables`, `S*.finance.annual_lines_y1`.

**I5 — Trailing window shorter than the history asked.** When history < `trailing_months`,
candidates = all operating days (`F_SHORT_HISTORY`, severity info as in the F6 flag table, when < 60 days). `lines_by_sku`
(eligibility, ABC, zone splits) = shipped lines over the same whole history.
Keys: `design_day.*`, `eligibility.*`, `abc.*`.

**I6 — ABC by lines.** SKUs sorted by lines descending, ties by units descending, `avg_stock`
descending, unit cube descending, weight descending and only then `sku` ascending (the
anonymised id depends on the salt: with the salt-independent attributes first, the classes, and so
the sizing, no longer move with the salt; only SKUs identical in every attribute are ordered by
the hashed id, and they are interchangeable). A SKU's class
uses the cumulative line share *before* adding it: `A if cum < 0.80, B if cum < 0.95, else C`
(so the SKU that crosses 80 % is A and `A.line_share ≥ 0.80`, T3.2). SKUs with zero lines are C.
`sku_share` denominator = all SKUs of the SKU master plus the orphan SKUs (I10).
Keys: `abc.lines.*`.

**I7 — Ties.** Reference day: the operating day with `|lines_d − P_lines|` minimal; on a tie the
earliest date. Design weekday: highest mean lines over operating days; on a tie the lowest
weekday index (0 = Monday). Keys: `design_day.reference_date`, `design_day.design_weekday`.

**I8 — Pallets per pallet order.** A pallet order (F3 step 8) ships exactly 1 pallet
(`pallets_out_d = number of pallet orders`) and 0 parcels. Parcel orders ship
`max(1, ceil(weight / parcel_max_weight_kg))` parcels. Keys: `daily.pallets_out.*`,
`design_day.pallets_out`, `shipment.*`.

**I9 — Return lines.** Workload of the returns activity, design day and every day:
`return_lines = flows.returns_rate × lines` (`design_day.return_lines = returns_rate × lines*`).
The returned lines found in the data (`profile.n_return_lines`) are informational only (they lag
the shipments and are incomplete in a short history). Keys: `design_day.return_lines`,
`S*.labor.returns.*`, `S*.area.returns`.

**I10 — Eligibility inputs and missing SKU data.** F5 step 2 for cube_asrs: `hazmat` SKUs are
excluded (`excludes_hazmat: true`) and `temperature_class` must be ambient or chilled; a missing
`hazmat` column or a null value → not hazmat; a missing `temperature_class` column or a null
value → ambient. These exclusions apply first, also to SKUs without dims. F5 steps 2-3 use
Kleene logic, as the engine's `eligible_mask`: the **known** dims, sorted descending, are
compared with the largest limits (a missing dim sorts as the smallest) and the known weight
with the weight limit (`max_weight_kg`, and also `extra_max_weight_kg` when set); any known
violation → **ineligible**, whatever the flag. Otherwise a SKU with any of `length_mm`,
`width_mm`, `height_mm`, `weight_kg` null (`has_dims = false`) is **ineligible** unless the
scenario sets `assume_eligible_if_missing_dims: true`; then it is eligible "by assumption" and
its lines are reported as `assumed_share_lines` (F_ELIG_ASSUMED, I46). Example: length null and
weight 40 kg → ineligible even with the flag. `use_catalog_limits: false` is not supported (the
oracle raises). F6a `fits_shelf` tests the dims only (`l, w, h` all known and sorted ≤
`shelf_item_max_mm`; a missing weight does not matter); without a dim a SKU does not verifiably
fit a shelf bin: `fits_shelf = false` → manual class `pallet_rack` (F6a rule "not
fits_shelf_bin → pallet_rack"). Unit cube = `l × w × h / 1e9` (§4.1 "derived", as F2 derives
it), else the given `unit_cube_m3` when a dim is missing, else 0; a line whose SKU has no known
cube or weight contributes 0 to order/daily cube and weight. **Orphan SKUs** (shipped SKU absent
from the SKU master, F2 R2 "kept; has_dims=false", and inventory-only SKUs, I50) are kept as SKU
rows without master data
(`has_dims = false`, unit cube 0, `upp` 400, `upc` 1, manual class `pallet_rack`, no stock unless
an inventory row exists) and are **never eligible**, also with `assume_eligible_if_missing_dims`
(nothing is known about them, hazmat and temperature included; engine `eligibility_shares`:
"orphan SKUs included with mask False"). They count in every denominator and in ABC (I6).
Shares (F5 step 4): `share_lines = Σ lines of eligible SKUs / Σ shipped lines` (orphan lines
included); `share_stock_cube = Σ_eligible avg_stock × unit_cube / Σ avg_stock × unit_cube` (mean
snapshot stock, not design stock; identical ratio since design stock is proportional), **0 when
the total stock cube is 0** (no inventory, or no SKU in stock with a known cube), as the engine's
share helper;
`share_skus = n eligible / n SKUs` with `n SKUs` = SKU master (inactive SKUs included) + orphan
SKUs (`n_skus_total`).
Keys: `eligibility.cube_asrs.*` (family, default `EligibilityCfg`), `S2.eligibility.*` (I44).

**I11 — Pick faces.** In the manual family and in the overflow zone, every SKU of class A or B
(I6) stored in `pallet_rack` adds 1 position on top of the reserve:
`positions = Σ pallets_i / fill_pallet + n_AB_pallet_rack_SKUs`. `pallets_i = ceil(s_i / upp_i)`
counts the whole design stock (the pick face is not subtracted from the reserve).
Keys: `S*.storage[.overflow].pallet_rack.{pallets,pick_faces,positions}`.

**I12 — Δstock in derived inbound.** With fewer than 3 inventory snapshots (inventory growth
n/a, F3 step 5), `Δstock_per_year = 0`, so `units_in = mean units out/day × gf`. With 3 or more
snapshots the oracle raises `NotImplementedError` (the OLS Δstock is not computed; the golden
case has one snapshot) instead of returning a silent 0.
Key: `inbound.units_per_day`.

**I13 — Derived inbound per SKU.** `units_in_i = units_in × U_i / Σ U` with `U_i` = shipped units
of SKU i over the period. `pallets_in_i = units_in_i / units_per_pallet_i` (fractional, no ceil;
`units_per_pallet` falls back to 400). Receipt lines: `receipt_lines = Σ_i pallets_in_i × k_i`,
`k_i = 1.0` if `units_in_i ≥ units_per_pallet_i` (at least a full pallet a day) else `4`
(mixed pallet). `cases_in_i = units_in_i / units_per_case_i`. `trucks = pallets_in /
pallets_per_truck`. Null case data uses fallbacks, never a division by zero:
`units_per_pallet` = `units_per_pallet`, else `units_per_case × cases_per_pallet` (§4.1
"derived"), else `default_units_per_pallet` 400 (Appendix D); `units_per_case` (no spec
fallback) = `units_per_case`, else `units_per_pallet / cases_per_pallet`, else 1 (each unit is
decanted as one case: the largest decant workload). SKU sheet columns `upp`, `upc`.
Keys: `inbound.*`.

**I14 — Design stock per SKU.** `s_i = avg_stock_i × peak_stock_factor × gf` (fractional
units, no rounding), `sc_i = s_i × unit_cube_i`. SKUs with `s_i = 0` get no storage position (they
are counted in no class). Every SKU still gets a manual class (`manual_class(fits_shelf, sc_i)`),
used only to route its picking lines (I17). Keys: `design_day.stock_*`, `S*.storage.*`.

**I15 — Design orders by packing class.** `orders_S = orders* × share_S`,
`orders_ML = orders* × (1 − share_S)`, `share_S` = share of 1-line orders over the period.
Packing_S standard applies to S, packing_ML to M and L. Keys: `design_day.orders_S`,
`design_day.orders_ML`, `S*.labor.packing_*`.

**I16 — λ_sla.** `lines_same_day = service.same_day_share × lines*`. `sla_window_hours` =
`service.sla_window_hours` when it is given (it must be > 0, else the oracle raises); when it is
null, `carrier_departure_time − cutoff_time` in hours, modulo 24 h (crossing midnight allowed:
22:00 → 02:00 = 4 h). **Equal times give 24 h**: the departure is the next day's at the same
time (the modulo rule, never a zero window or a division by zero). `λ = max(peak_hour_lines /
η_flow, lines_same_day / sla_window_hours)`. The same window sets the queue threshold
`t = sla_window_hours × 0.5` (I45). Keys: `S*.throughput.lambda*`.

**I17 — Zone split of lines.** Each SKU's lines go to its zone: `cube_bin` when the scenario is
cube_asrs and the SKU is eligible, else its manual class (`shelving` or `pallet_rack`, I14).
Zone line share = period lines of the zone's SKUs / period lines. Design lines per zone =
`lines* × share`; peak flow per manual zone = `λ × share` (equals `λ_o ×` overflow share in S2).
`pickers_peak = Σ_zone ceil(λ_zone / (pick_rate_zone × η_pick))` (ceil per zone, then sum);
`carts = pickers_peak`. Daily workloads (annual hours) use the actual daily lines per zone. S0 (manual family) has
`share_lines_eligible = 1`: `S0.throughput.lambda_e = λ`, `S0.throughput.lambda_o = 0`.
Keys: `S*.throughput.lambda.<zone>`, `S*.equipment.pickers.*`, `S*.labor.picking.<zone>.*`.

**I18 — Forklift peak-hour moves.** `moves_peak_h = pallets_in × inbound_peak_factor ×
peak_hour_share_inbound (0.2) + (pallets_out* + replen_moves*) × peak_hour_share`, where
`peak_hour_share` = max hourly line share of the design weekday. `forklifts = ceil(moves_peak_h /
forklift_moves_h)`. In S2 forklifts serve all inbound pallets (dock → decant) plus the overflow
replenishment; they are costed in the overflow capex item (I30). Keys:
`S*.equipment.forklift_moves_peak_h`, `S*.equipment.forklifts`.

**I19 — Shifts and roster.** The golden basis has `shifts_per_day: 1`; the oracle sizes one
shift only (it raises for more). With one shift every hour of the day falls into that shift, so
per activity `heads_shift_a = max(1, hours_a / (hours_per_shift × utilisation))` if
`hours_a > 0`, else 0 ("floor 1 per staffed activity"; no ceil), and
`roster = Σ_a heads_shift_a × (1 + absenteeism)`. Indirect is a staffed activity. Design-day
`heads_a = hours_a / (paid_hours_per_person_day × utilisation)` (different divisor).
Multi-shift splitting (intraday profile with 1 h lag, 06:00-14:00 inbound window) is not covered
by the golden case. Keys: `S*.labor.*.roster`, `S*.labor.*.heads`.

**I20 — Utilisation and bottleneck.** At typ, `utilisation = load / (count × capacity)`:
pickers `Σ_zone λ_zone / (rate_zone × η_pick) / pickers`; forklifts `moves_peak_h /
(forklifts × forklift_moves_h)`; ports `(λ_e / (port_rate × oee) + decant_port_load_peak_h) /
ports` (I23); cube robots
`bin_pres_h × dig_factor / (robots × robot_bins_h × availability)`. Resources with count 0 have
utilisation 0. Bottleneck = highest utilisation (first of pickers, forklifts, ports, robots on a
tie). Keys: `S*.utilisation.*`, `S*.bottleneck`.

**I21 — Replenishment.** Literal reading of "units_picked_A/B": `replen_moves* = units* ×
(period units of A/B SKUs in manual zones / period units) / replen_units_per_move`, all A/B SKUs
of the manual classes (shelving included), not only pick-face SKUs. In S2 only the overflow
(non-eligible) A/B SKUs count. Daily: `units_AB_manual_d / replen_units_per_move`.
Keys: `S*.labor.replenishment.*`.

**I22 — Daily inbound workload.** Derived inbound is a daily mean: for annual and temp hours,
each operating day carries the same ungrown inbound workload `inbound_x / gf`
(`x ∈ {pallets, receipt_lines, cases}`). Design-day inbound workloads are the Inbound values
themselves, **without** `inbound_peak_factor` (the factor applies only where F6b/F6d write it:
staging, forklift moves, docks).

**I23 — Decant (cube): at the ports, in the inbound peak hour.** F6b: "decant_station_hours =
cases_in / decant_cases_per_h → adds to ports or dedicated decant stations [P]"; the default is
**decant at the ports** (labor table: put-away cube "decant at port"), no dedicated station.
`cases_in` = `Σ_{i eligible in the scenario} cases_in_i` (overflow SKUs are not decanted).
`decant_station_hours = cases_in / cube_asrs.decant_cases_per_h` (port-hours per day, no PF&D,
no `oee`: the decant standard is the port's decant rate). Decant runs in the receiving window,
so its peak-hour load follows the inbound peak-hour convention of F6b / I18 / I28:
`decant_port_load_peak_h = decant_station_hours × inbound_peak_factor ×
peak_hour_share_inbound (0.2)`, conservatively coincident with the outbound peak hour.
`ports = ceil(λ_e / (port_rate × oee) + decant_port_load_peak_h)`. Labor: activity `decant`
on the same `cases_in`, standard `decant_cases_per_h`, role operator, hours with PF&D (I38).
Put-away covers all `pallets_in`. Keys: `S2.equipment.decant_station_hours`,
`S2.equipment.decant_port_load_peak_h`, `S2.equipment.ports`, `S2.utilisation.ports`,
`S2.labor.decant.*`.

**I24 — Pack stations.** `peak_hour_orders = orders* × peak_hour_share`;
`pack_rate = 1 / (s_S / packing_S + (1 − s_S) / packing_ML)` (order-weighted harmonic mean,
`s_S = orders_S / orders*`); `oee = 0.85` (no spec value; same as `engine.pack_station_oee` in
`catalog/engine_defaults.yaml`); `pack_stations = ceil(peak_hour_orders / (pack_rate × oee))`.
Keys: `S*.area.{peak_hour_orders,pack_rate,pack_stations,packing}`.

**I25 — Core heads and temp hours.** `hours_d` = total daily hours (all activities, indirect
included) on each operating day, base year (no growth). Core capacity = `P50(hours_d)`
(`np.percentile`, unrounded heads: `core_heads_day = P50 / (paid_hours × utilisation)`).
`temp_hours_t = Σ_d max(0, hours_d − P50) × 252 / n_op × (1 + g)^t` (capacity grows with demand).
Keys: `S*.labor.p50_day_hours`, `S*.labor.core_heads_day`, `S*.labor.temp_hours.y<t>`.

**I26 — Area constants across families.** `m2_per_pack_station` = manual_p2p value (12) for every
scenario; robot parking = `cube_asrs.m2_per_robot_parking` for every scenario with robots (a scenario without robots reads no parking Param, I47) (catalog 0.2.0 Param, typ 2.0 = the
F6d line 995 value);
`equipment = robots × 2.0 + maintenance_fixed (40)` for every scenario (S0: 40);
`ports = ports × cube_asrs.m2_per_port`. Keys: `S*.area.{packing,equipment,ports}`.

**I27 — Circulation and amenities.** `circulation = 0.25 × Σ all zones except storage`
(amenities included). Amenities are inside the footprint (no `F_AMENITIES_EXTERNAL`).
`total = Σ zones + circulation`. Keys: `S*.area.*`.

**I28 — Trucks in the peak hour.** `trucks_in_peak_h = trucks_per_day × inbound_peak_factor ×
peak_hour_share_inbound (0.2)`; `trucks_out_peak_h = (pallets_out* + parcels* /
parcels_per_pallet_equiv) / pallets_per_truck × peak_hour_share`. Docks per App. B (ceil).
Keys: `S*.docks.*`.

**I29 — S0 capex items.** storage = `pallet positions × per_pallet_position_eur + shelving bins
× per_shelf_bin_eur`; equipment = `carts × per_cart_eur + forklifts × per_forklift_eur`;
controls = `manual_p2p.wms_adaptation_fixed_eur` (50 000, not `wms_adaptation_default_eur`);
building works = `area.total × building_works_per_m2_eur` ("zones changed" = every zone of the
area budget); overflow = 0.

**I30 — S2 capex items.** storage = `bins_total × per_bin_eur + A_grid ×
grid_structure_per_m2_eur`; equipment = `robots × per_robot_eur + ports × per_port_eur`;
controls = `controls_fixed_eur`; building works = `area.total × manual_p2p.building_works_per_m2_eur
+ A_grid × cube_asrs.floor_prep_per_m2_eur` (F7 "+ floor preparation × A_grid"; the manual
"zones changed × €/m²" term of I29 is kept; floor prep is catalog 0.2.0, min 10 / typ 20 / max 40
eur/m², no spec value, analog of `amr_gtp.floor_prep_per_m2_eur`; a degenerate scenario, I48, has
A_grid = 0 and pays no floor prep); overflow =
overflow pallet positions × 90 + overflow shelving bins × 12 + carts × 1 500 + forklifts × 35 000
(manual unit costs, no shares inside the item).

**I31 — Shares.** `integration_commissioning = (integration_share + commissioning_share) of the
scenario family × equipment item` (overflow excluded). `contingency = contingency_share × Σ of
all other items` (storage, equipment, controls, building works, overflow, integration).

**I32 — Energy.** `kWh = robots × kwh_per_robot_year + ports (stations) × 1 500 + forklifts ×
manual_p2p.kwh_per_forklift_year + fixed 20 000`; `1 500 kWh/station/year` has no spec value
(same as `finance.kwh_per_station_year` in the catalog). `energy_t = kWh × price ×
(1 + energy_inflation)^(t−1)`.

**I33 — Labor cost (literal, flagged).** As written in F7:
`labor_t = [Σ_a annual_hours_a,t × cost(role_a) × (1 + shift_premium) + temp_hours_t ×
cost_operator × (1 + temp_premium)] × (1 + wage_inflation)^(t−1)`. Temp hours are part of the
annual hours, so this counts them twice; kept literal for the expert to decide (review #1).
Roles: receiving, put_away, replenishment, shipping_pallet → forklift_driver; indirect →
team_leader; all others → operator.

**I34 — Maintenance.** `maintenance_t = maintenance_share × equipment item` (storage, controls and
works excluded), constant over years; S2 adds `manual_p2p.maintenance_share × (overflow carts +
forklifts)`.

**I35 — Other opex.** software, maintenance and rent are flat (no inflation); rent footprint =
`area.total × rent_eur_m2_year`; consumables = `annual orders_t × packaging_eur_per_order`,
`annual orders_t = Σ_d orders_d × 252 / n_op × (1 + g)^t`; renewal = `renewal_share × equipment
item` in year `equipment_life_years` only (none within T = 5).

**I36 — Annual lines for cost per line.** `annual_lines_1 = Σ_d lines_d × 252 / n_op × (1 + g)`.

**I37 — IRR.** `numpy_financial.irr(Δcf)` only when Δcf (zeros ignored) has exactly one sign
change; otherwise `None` (all positive, all negative, or several changes). `None` also when irr
returns NaN.

**I38 — Labor productivities.** Picking hours use the pick rate alone
(`lines_zone / pick_rate_zone × (1 + pfd)`); `η_pick` only enters `pickers_peak`. Port picking
uses `port_rate_lines_h` without `oee` (oee only enters `ports`). Indirect =
`0.12 × Σ direct hours` (direct hours already include PF&D; no second PF&D), role team_leader,
daily indirect = 0.12 × daily direct. Activities follow Appendix D (receiving on pallets_in +
receipt_check on receipt_lines; packing_S / packing_ML; shipping_parcel / shipping_pallet).

**I39 — Rounding.** Nothing is rounded unless the spec writes ceil/floor: positions, bins_total
(with 1/4 mixed bins and the empty-bin reserve), areas, workloads, hours and heads stay
fractional; levels are integers ≥ 1; equipment counts are ceils. A storage class, picking zone or
activity that exists for the family is emitted even when its count is 0 (e.g. an overflow
class without SKUs, or `shipping_pallet` when no order is a pallet order); its levels are still
computed.

**I40 — F_HEIGHT_LIMIT.** Raised for a pallet_rack or cube_bin class whose
`floor(usable height / pitch) < max_levels` (the building, not the catalog, limits levels).
Shelving is capped by ergonomics, never flagged. Keys: `S*.flags`.

**I41 — Horizons and growth exponents.** Design growth uses `projection.horizon_years`
(`gf = (1 + g)^T`); finance years 1..T use `finance.horizon_years`; year t of labor and orders
uses `(1 + g)^t` with t starting at 1 (year 1 is already one year of growth).

**I42 — Baseline.** When `scenarios.baseline` is a scenario id (golden: S0), the baseline capex
is that scenario's computed capex (not 0): `Δcf_0 = −(capex_S2 − capex_S0)`,
`Δcf_t = opex_S0,t − opex_S2,t`, NPV with `Δcf_0` undiscounted.

**I43 — Overflow zone and mixed bins.** In S2 every non-eligible SKU with `s_i > 0` goes through
the manual class rule and the manual formulas (pallet rack incl. pick faces I11, shelving), keys
`S2.storage.overflow.<class>.*`; their area is part of `S2.storage.total_area_m2`. Mixed-bin test
uses the design stock cube: `bins_i = 1/4` if `sc_i < 0.2 × bin_net_cube_m3` (0.011 m³).

**I44 — Scenario eligibility.** `eligibility.cube_asrs.*` are the family's shares under the
default `EligibilityCfg()` (catalog limits only; what T5.3 recomputes). A cube scenario uses its
own `ScenarioDef.eligibility` (golden S2: `extra_max_weight_kg: 2.0`), reported as
`S2.eligibility.<EligibilityResult field>`; that mask drives λ_e (`share_lines`), the zone of
every SKU (SKU sheet column `zone_S2`), the overflow zone, the decant cases and the eligible
replenishment exclusion. Keys: `S2.eligibility.*`.

**I45 — Queue check (F6e).** Two pools, `t = sla_window_hours × 0.5` (I16); `λ_s` = arrival rate
in the SLA window, taken like λ (I16) as the max of the peak-hour rate and the SLA-window rate,
for both pools. Pack stations: `c = pack_stations`, `λ_s = max(peak_hour_orders, same_day_share
× orders* / sla_window_hours)` (I24; the SLA term binds on the golden case), `μ = pack_rate ×
0.85`. Ports (cube only, when `ports > 0`): `c = ports`, `μ = port_rate × oee`, `λ_s = λ_e +
decant_port_load_peak_h × μ` (decant in line-equivalents, I23), so `a = λ_s / μ` equals the
port load used for sizing. `a = λ_s / μ`; when `a < c`: `P_wait = erlang_c(c, a)`,
`W_q = P_wait / (cμ − λ_s)`, `P(W > t) = P_wait × exp(−(cμ − λ_s) t)`, `c_min = None`; when
`a ≥ c`: `F_UNSTABLE:<pool>`, `P_wait`, `W_q`, `P(W > t)` = None, `c_min = ceil(a) + 1`.
`F_SLA_RISK:<pool>` when `P(W > t) > 0.05`. Field names follow `QueueResource`.
Keys: `S*.queue.<packing|ports>.*`.

**I46 — Flags (F6 table).** `S*.flags` lists the raised flags in F6-table order, a value after
`:` where the spec attaches one: `F_NO_FIT` (area.total > building.area_m2), `F_HEIGHT_LIMIT:
<class>` (I40), `F_ELIG_LOW` (scenario `share_lines < 0.5`), `F_ELIG_ASSUMED:<assumed share of
lines, 6 decimals>` (I10), `F_SCALE_LOW` (cube, `lines* < min_scale_lines_day`),
`F_ROBOT_DENSITY` (cube, `robots / A_grid > cube_asrs.max_robots_per_m2`),
`F_DOCK_SHORTFALL` (`docks.in > dock_doors_in` or `docks.out > dock_doors_out`),
`F_UNSTABLE:<pool>` / `F_SLA_RISK:<pool>` (I45), then the design-day flags of `design_day.flags`
(`F_PERCENTILE_CLIPPED` when `design_percentile > 100`, the percentile then being clipped to
100, i.e. the max; `F_SHORT_HISTORY` when fewer than 60 operating days; `F_RATIO_DRIFT:<m>`),
then `F_LOW_CONFIDENCE:<n>` (I47). **`F_ROBOT_DENSITY`** for cube_asrs: the F5 family table
gives "max robots per m² of grid [P]" without a value; catalog 0.2.0 sets
`cube_asrs.max_robots_per_m2` = 0.05 (analog of the amr_gtp scalar, C.2 l.1661, no spec origin).
The density is over the grid, `S2.equipment.robots_per_grid_m2 = robots / A_grid` (the F6b
amr_gtp line divides by A_storage; for the cube the family table says "of grid"), 0 when A_grid
= 0. On the golden case S2 has ≈ 0.47 robots/m² and raises the flag. The open [EXPERT] ruling is
on the 0.05 value, not on the flag. `F_AMENITIES_EXTERNAL` is never raised (amenities inside,
I27).
F_RATIO_DRIFT, F_SHORT_HISTORY and F_PERCENTILE_CLIPPED are design-day flags, copied into each
scenario. T6.x do not compare flag strings. Key: `S*.flags`.

**I47 — F_LOW_CONFIDENCE count.** Number of distinct catalog Param blocks (`catalog/` YAML, all
confidence L) the scenario's formulas read, scalar `[P]` constants excluded. This is what the
engine counts once F6/F7 read the catalog; it replaces G1b's "ranged Params of the spec" rule,
which left out the catalog-only analogs. manual_p2p (19: densities, fills, pick rates, η_pick,
forklift moves, replen units, pack-station m², the six capex Params, maintenance share, kWh per
forklift, software); cube_asrs (all 21 of catalog 0.2.0: the 18 of the F5 schema plus
`max_robots_per_m2` (I46), `m2_per_robot_parking` (I26) and `floor_prep_per_m2_eur` (I30)) plus
the 17 manual Params of the overflow zone (all but `wms_adaptation_fixed_eur` and
`software_eur_year`, I30, I35); 9 labor standards; `finance.packaging_eur_per_order`;
`engine.pack_station_oee` (pack stations, I24, every scenario); `finance.kwh_per_station_year`
(I32, families with stations or ports only, so not S0). S0 = 19 + 9 + 1 + 1 = 30,
S2 = 21 + 17 + 9 + 1 + 1 + 1 = 50. An amr_gtp scenario has no registered figure (the golden case has
none): the count is by Params read, which gives 49 on ecom_mid (19 amr_gtp + `cube_asrs.m2_per_robot_parking` I26 + 17
overflow manual + 9 labor + packaging + pack OEE + kWh per station). The catalog holds 72 Param blocks in all (manual_p2p 19,
amr_gtp 20, cube_asrs 21, labor 9, finance 2, engine 1), the TODO count the F5 loader logs. The
Params are named by their catalog `id` (`manual_p2p.pallet_rack_fill_factor`, `labor.receiving`,
`finance.packaging_eur_per_order`, `engine.pack_station_oee`); S0 and S2 together read every
non-amr_gtp id. Keys: `S*.low_confidence_params`, the `F_LOW_CONFIDENCE:<n>` flag.

**I48 — Zero eligible lines (F6 edge case).** When a cube scenario's eligibility gives
`share_lines = 0`, it "degenerates to manual with the automation capex at zero": every SKU takes
its manual class (also eligible SKUs without lines), so `λ_e = 0`, ports = robots = 0 and the
cube_bin class has 0 bins; capex and opex are those of the manual family on the scenario's
manual zones (I29, I32-I35: `wms_adaptation_fixed_eur`, manual shares, manual software and
maintenance, overflow item 0), i.e. the scenario costs what the manual baseline costs. The
`S2.eligibility.*` keys, F_ELIG_LOW, F_SCALE_LOW and the F_LOW_CONFIDENCE count stay those of
the cube scenario. Whether the degenerate scenario should carry the manual WMS adaptation and
software is to confirm with the [EXPERT].

**I49 — Per-SKU average stock (F3 step 5).** `avg_stock_i = Σ qty_units of SKU i over all
snapshots / number of snapshots` (distinct `snapshot_date`); a SKU absent from a snapshot counts
0 in it (not the mean of the snapshots where it appears). Several rows of one SKU in one
snapshot are summed. No inventory → 0 for every SKU. Keys: `stock.*`, `design_day.stock_*`,
`eligibility.*.share_stock_cube`, every storage key.

**I50 — Inventory-only SKUs and dead stock.** A SKU in the inventory, absent from the SKU master
and never shipped is an orphan (I10): a SKU row without master data (`has_dims = false`, unit cube
0, `upp` 400, manual class `pallet_rack`), never eligible. It counts in the stock statistics
(`stock.n_skus_in_stock`, `stock.avg_units`; its cube is 0), in every SKU count (`n_skus_total`,
`share_skus`, ABC `sku_share`, class C: no lines) and in dead stock, and its design stock takes
pallet-rack positions. Dead stock (F3 step 5) = stock in the **last** snapshot > 0 (`last_stock`,
summed over the SKU's rows of the latest `snapshot_date`; a SKU stocked only in older snapshots
has `avg_stock > 0` but is no longer in stock, so not dead) and zero shipped lines with a local
date after `period_end − dead_stock_days` (180 `[P]`): a line dated exactly `period_end − 180`
is outside the window. SKUs sheet columns `last_stock`, `dead_stock`. Golden keys
`stock.dead_stock_skus`, `stock.dead_stock_cube_m3` (degenerate on tiny_golden: see the golden
case notes).
Keys: `stock.*`, `abc.lines.*`, `eligibility.*`, `S*.storage.*`.

**I51 — Lines without a time (F3 step 7).** A line has no time component when its local
timestamp (the order's first `order_ts` in `basis.timezone`, I1) is 00:00:00. When fewer than
20 % of the shipped lines (whole history) have no time, those lines are left out of the
intraday shares (numerator and denominator); they still count in every daily total. Above 20 %
(the spec's "more than 20 %", strict: exactly 20 % keeps the measured shares) the shares are the
default profile of `ProfileCfg.default_intraday` (no spec value: `[P]` flat 08:00-17:00, 1/9 per
hour) for every weekday, and the intraday profile is flagged L
(`DemandProfile.intraday_confidence`, no golden key). At 20 % or less, a design weekday without
any timed line also takes the default profile (the shares are undefined), confidence unchanged:
the L flag is the spec's 20 % rule only. Keys: `design_day.intraday_share.*`, `design_day.hourly_lines.*`,
`design_day.peak_hour_*`.

**I52 — Trend CAGR and confidence (F3 step 6).** Mean daily lines per calendar month over
operating days only (a month without operating day gives no point); `slope` = OLS slope
(`numpy.polyfit`, degree 1) of `log(mean)` on the calendar month index; `trend_cagr =
exp(12 × slope) − 1`, None with fewer than 2 months. Means, not monthly totals, so partial
boundary months do not bias it. Confidence on calendar months from the first to the last date of
the calendar (I2), both included: whole calendar months + leftover days / 30.4375
(`relativedelta(last + 1 day, first)`), so 2023-01-01..2024-12-31 is 24.0 and
2022-01-01..2024-12-31 is 36.0, leap day or not; L if < 24, M if 24-36, H if > 36. tiny_golden
(31 days, one calendar month): trend_cagr None, confidence L. Golden keys
`seasonality.trend_cagr`, `seasonality.trend_confidence` (degenerate on tiny_golden: see the
golden case notes).

**I53 — R13 outlier threshold (F2).** Outlier when lines per order or units per line > `median +
10 × max(MAD, 1)`. MAD is floored at 1 unit: with MAD = 0 (most orders of 1 line, most lines of 1
unit) the verbatim `median + 10 × MAD` flags every multi-unit line. `[EXPERT]` to confirm. No
golden key (F2).

**I54 — Decimal sniff (F2 sniff step 4).** Per file, the ≥ 80 % share of
`^\d{1,3}(\.\d{3})*,\d+$` matches is computed over the sampled numeric values that contain a
separator (`.` or `,`); values without one say nothing about the decimal mark. Below 80 % →
decimal dot. An explicit `decimal` in `mapping/<dataset>.yaml` overrides the sniff. No golden key
(F2). **Amendment (W3, `[VERIFY]`).** Pure thousands shapes, `^[1-9]\d{0,2}([.,]\d{3})+$` (`1.200`,
`1,000`, `12,500`; a leading `0` group such as `0.125` is never grouping and stays decimal
evidence), are ambiguous (FR thousands, US thousands, or a 3-decimal value) and are left
out of the share, as are cells in a date shape (`%d.%m.%Y`, `%d/%m/%Y`, ...). Besides the verbatim
regex, two shapes count as decimal-comma evidence because neither can be US grouping: an ungrouped
comma decimal with 4 or more digits before the comma (`^\d{4,},\d+$`, e.g. `1037,5`, the usual FR
Excel CSV export) and a comma decimal grouped by a space, U+00A0 or U+202F
(`^\d{1,3}(<space|U+00A0|U+202F>\d{3})+,\d+$`, e.g. `1 200,5`). Tie-break: when no
separator-bearing value is left (integer-only files such as stock counts), the file's field
delimiter decides: `;` → decimal comma (FR Excel export), any other delimiter → decimal dot.

**I55 — Design-day window (F4 step 1).** "`projection.trailing_months`; use 24 months when
available". When the basis file sets `projection.trailing_months` (the field is in the model's
`model_fields_set`), that value is used as given. When it is left at its default, the window is
24 months if the history covers at least 24 months (calendar days / 30.4375 ≥ 23.9, the I52
threshold), else the schema default (12) and I5 applies to a shorter history. The warning "< 12"
fires when the window actually used covers less than 12 months of history, measured with the I52
calendar-months convention (whole calendar months + leftover days / 30.4375), so a 365-day
history counts as 12.0 and does not warn. Golden: `golden_basis.yaml` sets `trailing_months: 12` explicitly and tiny_golden has
31 days, so no golden value changes.

**I56 — Receipts inbound mode (F4).** `pallets_in`, `receipt_lines`, `units_in` = `P_p` of the
daily receipts series over the candidate days, × `gf` (F4 step 5 "multiply all"); days with an
unknown pallet count are left out of the pallets percentile only. `Inbound.peak_factor` =
`flows.inbound_peak_factor` when the basis sets it, else **1.0**: the spec's "outbound
peak-to-average" fallback is listed under the derived mode only, and in receipts mode `P_p` is
already a design-day value, so F6 (I18, I28 "× inbound_peak_factor") must not apply a second
peak. Derived mode is unchanged (spec text). Golden uses derived mode: no value changes.

**I57 — F_RATIO_DRIFT with P_m = 0 (F4 step 4).** `|m* − P_m| / P_m` is undefined at `P_m = 0`.
When `P_m = 0` and `m* > 0`, `F_RATIO_DRIFT:<m>` is raised (the drift is unbounded; `Flag.value`
None). When both are 0 there is no drift and no flag. No golden value changes (P95).

**I58 — The per-SKU frame shared by F4 and F6 (`sku: pl.DataFrame`).** F8 builds it once per run
and passes the same frame to `select_design_day(..., sku=...)` (F4 derived inbound) and to
`size_scenario(..., sku=..., ...)` (F6). It is the F3 SKU table `ProfileTables.skus` (`sku`,
`length_mm`, `width_mm`, `height_mm`, `weight_kg`, `unit_cube_m3`, `has_dims`, `orphan`, `lines`,
`units`, `avg_stock`, `last_stock`, `stock_cube_m3`, ABC class) left-joined on `sku` with the
canonical `sku_master` columns F3 does not keep: `units_per_pallet`, `units_per_case`,
`cases_per_pallet`, `hazmat`, `temperature_class` (absent columns become null; a null `hazmat`
is not hazmat and a null `temperature_class` is ambient, as in F5 `eligible_mask`). The engine
owns the builder function (`whsizing.engine`, `sku_frame(tables, sku_master)`), which extends
F4's `with_pack_data`; F4 accepts the extra columns. Eligibility (F5) must be evaluated on this
frame, never on `ProfileTables.skus` alone (it lacks `hazmat` and `temperature_class`).

**I59 — F_DEFAULT_UPP (F4 derived inbound, "fallback default [P] 400 units per pallet,
flagged").** The spec names no code; `F_DEFAULT_UPP`, severity info, is raised when at least one
SKU with inbound units has `units_per_case × cases_per_pallet` null (F2 `canonical.derive` then
filled `units_per_pallet` with the default; shipped orphan SKUs count). `Flag.value` = share of design inbound units on
the default. Position in the I46 order: after the design-day flags, before `F_LOW_CONFIDENCE`.
Not raised on the golden case.

**I60 — Basis values F4 and F6 divide by or raise to a power.** `check_basis` rejects with
`ConfigError` (naming the field) any NaN or infinite float in `operations`, `service`,
`projection`, `flows`, `building` and `finance`, and: `projection.peak_stock_factor ≤ 0`,
`flows.inbound_peak_factor ≤ 0` when set, `projection.growth_rate ≤ −1`,
`operations.utilisation` or `flows.dock_utilisation` outside (0, 1], `operations.absenteeism` or
`operations.pfd_allowance` outside [0, 1), `flows.returns_rate` or `service.same_day_share`
outside [0, 1], `operations.shifts_per_day < 1`, and `operations.hours_per_shift`,
`operations.paid_hours_per_person_day`, `operations.annual_paid_hours_per_fte`,
`flows.truck_dwell_hours`, `building.area_m2`, `building.clear_height_m` ≤ 0. Client inputs
never reach the engine as NaN or ±inf.

**I61 — Extra engine inputs (F4/F6 signatures).** `select_design_day(profile, basis, daily, *,
sku, catalog)` and `derive_inbound(profile, basis, daily, sku, *, catalog)` require
`catalog=load_catalog(Project.catalog)` (`ConfigError` when None; nothing is read from the
working directory). `size_scenario(profile, basis, design_day, scenario, catalog, sku, daily,
tracer, *, lines)` takes the F3 shipped lines `ProfileTables.lines` (`order_id`, `sku`, `date`,
`qty_units`, ...) as a keyword-only argument: the daily workloads per zone (I17), the daily
packing split (I66) and the manual A/B units per day (I21) cannot be computed from `daily`
alone. F8 passes the same `ProfileTables` frames to F4 and F6.

**I62 — Booleans, flags and bottleneck come from the typ world.** `AreaResult.fit`
(schema: "total.typ ≤ building area"), `deficit_m2`, docks, ICPE label, `QueueResult` pools and
every F6 flag (`F_NO_FIT`, `F_HEIGHT_LIMIT`, `F_DOCK_SHORTFALL`, `F_SLA_RISK`, `F_UNSTABLE`,
`F_SCALE_LOW`, `F_ROBOT_DENSITY`) and the bottleneck (I20) are evaluated in the typ world; the lo
and hi worlds appear only in the `Range` values (a lo-world total above the building area is
visible as `area.total.hi` > area, not as a flag). All three worlds are traced in full (this
supersedes the "lo/hi trace leaf results only" line of ADR-002: IC2 needs complete trees per
world).

**I63 — Engine conventions (F6a/F6b).** (1) Design stock per SKU `s_i = avg_stock_i ×
design_day.stock_units / Σ avg_stock` (= I14, and carries the `stock_growth_rate` override).
(2) manual_p2p: eligibility mask all true (`share_lines = 1`, `λ_e = λ`). (3) amr_gtp
`F_ROBOT_DENSITY` = robots / pod_bin area (the robot zone; manual overflow excluded), node
`S*.equipment.robots_per_storage_m2`; cube per I46. (4) `F_SCALE_LOW` for every family whose
catalog has `<family>.min_scale_lines_day` (cube 1500, amr 800, manual 0 → never), the F6
table's "family's minimum scale". (5) `F_HEIGHT_LIMIT:<class>` for every emitted pallet_rack or
cube_bin class capped by the building, an overflow class with 0 SKUs included (I39, I40).
(6) Shelving bins use `storage.shelf_bin_net_cube_m3` (the spec's name in both formulas).
(7) `height_utilisation` = max over classes with positions > 0 of used height / clear height
(rack and shelving: levels × pitch; cube: levels × level_height + grid_overhead); it may exceed 1
when levels are forced to 1 (`F_HEIGHT_LIMIT`). (8) Utilisation = load before ceil / count for
every resource (I20); AMR station load has no decant term (I23 is cube-only). (9) Replenishment
(I21) counts A/B SKUs stored in a manual zone (in a cube or AMR scenario, the overflow only).
(10) Equipment keys: `pickers.shelving`, `pickers.pallet_rack`, `pickers_peak`, `carts`,
`forklifts`; cube adds `ports`, `robots`; amr adds `gtp_stations`, `robots`. (11) Levels =
floor with a 1e-9 tolerance (a whole-pitch clear height is not lost to float error); counts use
plain ceil. (12) Robot parking reads `cube_asrs.m2_per_robot_parking` for every scenario with robots (I26,
binding; same values as the family copies in catalog 0.2.0).

**I64 — Labor inbound workloads in receipts mode (F6c).** Daily inbound workloads are the day's
`receipts_pallets` and `receipts_lines`; a day with an unknown pallet count takes
`receipts_units_d × pallets*/units_in*`; decant cases `= cases_in* × receipts_units_d /
units_in*` (the daily series has no per-SKU case mix). When `units_in* = 0`, the two ratios
come from the whole-history receipt totals and the derived-mode cases per unit, never silently
0. Receipts booked on non-operating days are not counted in annual inbound hours (I4).
`[EXPERT]`: with lumpy receipts I25 puts most inbound hours above the P50 day, so temp hours
dominate (b2b S1 typ: 9903 of 14519 h in receipts mode vs 717 of 14489 h derived); literal spec
kept, flagged for review before F7 prices temp hours.

**I65 — Multi-shift split (F6c, `shifts_per_day > 1`).** Shift 1 starts at the inbound window
start (06:00 `[P]`), shifts run back to back for `hours_per_shift`; workload hours falling
outside every shift go to shift 1; returns count as an inbound activity; the 1 h outbound lag
splits fractional hours exactly; window edges at hour resolution. The floor of 1 head per staffed
activity (I19) applies per shift (`[EXPERT]`: about +4 heads on ecom_mid S0 with 2 × 7 h).

**I66 — Daily packing split (I15 for every day).** `orders_S_d` = actual one-line orders on day
`d`, `orders_ML_d = orders_d − orders_S_d` (the design day keeps I15's `orders* × share_S`).
The alternative `orders_d × share_S` misses `p50_day_hours` by 0.9 % and `temp_hours` by 2.2 % on
the golden case.

**I67 — Ingestion sniff details (F2 steps 1, 3, 4).** Step 1: a BOM-less UTF-16/32 file is
recognised from its NUL bytes in the first 4 KB, before charset_normalizer: ≥ 50 % NUL at the
high-byte offsets and < 10 % at the low-byte offsets give the width and byte order (Latin text;
Greek, Cyrillic and CJK are left to charset_normalizer). Step 3: a date-shaped cell (`%d.%m.%Y`,
`%d/%m/%Y`, `%d-%m-%Y`, ISO, optional time) is a value, not a header label, so a date-range
preamble is not taken as the header; when no row of the first 50 qualifies, the verbatim rule
decides (pivoted headers with month columns). Step 4 (I54 tie-break): when the field delimiter
decided the decimal mark, the DQ report carries a warning naming the file, the mark chosen, up to
5 raw → parsed examples of the ambiguous values and the `decimal:` mapping override, because a
`;` file of dot 3-decimal values (`1.250` kg) is then read × 1000. Details: (a) the warning
fires only when a mapped numeric column holds, in the rows the mapping keeps (site filters
applied), a value of the thousands-only shape `^[1-9]\d{0,2}([.,]\d{3})+$` (sign allowed); an
integer-only file gets no note, because the mark changes nothing; (b) when any file of a dataset
got its mark from the tie-break, the auto-saved `mapping/<dataset>.yaml` keeps `decimal: null`,
so each ingest warns again until the user sets `decimal:` (a departure from F2 mapping step 7,
"persist with the sniff results"); (c) up to 5 distinct examples, taken in turn from each mapped
numeric column, each named by its column and shown as raw → parsed exactly as that column's
parser reads it (`parse_int` for integer targets, so the note never shows a value the canonical
table does not hold); the note says "no number in the first 2000 data rows", not "in the file".
`[VERIFY]`: in a `;` file whose other columns show comma decimals, a dot 3-decimal weight
(`1.250`) is read × 1000 with no DQ signal; to confirm with the spec owner.

**I68 — T6.5 and pickers.** "More lines → FTE, stations and area non-decreasing" is a statement
about demand at constant stock (the golden case and T6.5 hold stock constant). When stock is
scaled with demand, `pickers_peak` can fall: the larger design stock moves a SKU from shelving to
pallet_rack (class rule, F6a) and the per-zone ceil of I17 then collapses (1 + 1 → 0 + 1) while
picking hours grow. This is spec-literal and kept; the property test covers pickers, carts and
forklifts at constant stock and every other equipment count at scaled stock.

**I69 — `F_UNSTABLE:packing` on realistic profiles (`[EXPERT]`).** Pack stations are sized on the
peak-hour orders (F6d, I24) while the queue check takes the SLA-window rate when it is higher
(F6e, I45); with a short SLA window and a high same-day share the check reports the stations as
unstable (`a ≥ c`, `c_min = ceil(a) + 1`). This is the check doing its job (the spec has no
feedback loop from F6e into F6d): no automatic resize. `c_min` tells the reader how many pack
stations the SLA window needs. To review with the expert: whether F6d should size on the same
`λ_s` as the check.

**I70 — Design-day flag severities.** `F_SHORT_HISTORY`, `F_RATIO_DRIFT:<m>` and
`F_PERCENTILE_CLIPPED` are `info` in the F6 flag table, in `design_day.json` (F4) and in
`result.json` (F6) alike.

**I71 — Receipts mode needs receipts in the history.** `flows.inbound_mode: receipts` with no
receipts table, or with receipts none of which falls inside the shipped-date window, is a
`ConfigError` (F4) naming the mode and the receipts date range, never an all-zero inbound. F3
treats a receipts table with no row in the window as absent (null `receipts_*` columns). The same
`ConfigError` (R3 fix round 1) when receipts exist inside that window but none on a candidate day
of the design-day window (all before the trailing window, or all on non-operating days): the
message gives the receipts range and the candidate days. A percentile of sparse receipts (some
candidate days, few) stays a percentile: P95 of one receipt day in 26 is 0, as the spec's
percentile rule gives.

**I72 — A missing required column in a canonical table.** `WhsizingError` (exit 1), message
`canonical <table>: cannot find column "<col>" (required by §4.1)`, whichever layer raises it (F2
`validate`; F3 `load_canonical` adds `(in <canonical dir>)`). §2.7 reserves `DataQualityError`
(exit 3) for the blocking R-rules; a column absent from a canonical table that F2 wrote is an
integrity failure of the pipeline, not a client-data defect (an unmapped required column at
ingest is a `MappingError`, exit 2). Several missing columns repeat the clause once per column, in schema order, joined by `; `. A
canonical parquet that cannot be read (truncated, corrupt) and a table name outside the four
canonical tables are `WhsizingError` too (exit 1), never a raw polars or `KeyError`.

**I73 — F7 contract and conventions (W4).** (a) Signature: `compute_finance(result, basis,
catalog, baseline, labor_series, *, daily, tracer, baseline_tracer=None, client_baseline=True)`
(`client_baseline=True` costs a `baseline=None` run against `basis.baseline`, `False` means no baseline at all):
`daily` gives the annual orders and lines (I4, I35, I36); `tracer` gives the F6 per-world
quantities (I62); `baseline_tracer` is required with a scenario baseline; `labor_series` must
equal `result.labor` (`ConfigError` otherwise, the per-world hours come from the F6 trace). The
finance nodes are written into the scenario's tracer, so a second call on the same tracer raises:
F8 deep-copies the pre-finance tracer per variant (sensitivity runs) and calls `compute_finance`
before `write_scenario`. (b) Client-current baseline (`scenarios.baseline = client_current`, no
computed baseline scenario): capex 0 (sunk); labor from `basis.baseline`: `actual_fte ×
annual_paid_hours_per_fte × utilisation` (F6 `core_fte` convention) or `actual_hours_month`
annualised × 12 / months, grown at `(1+g)^t`, wage inflation `(t−1)`, shift premium; coarse
labels `picking`/`packing`/`shipping` → operator, `receiving` → forklift_driver, `indirect` →
team_leader (primary role), catalog activity ids use their own role; consumables and rent are the
scenario's (they cancel); maintenance, energy and software of the existing equipment are not
modelled (0), so NPV versus client current is biased towards the current operation and
`FinancialResult.notes` says so; when a label has both FTE and monthly hours, hours win (noted).
(c) Role costs: the client's `labor_cost_eur_h` per role, else `catalog default_roles_cost_eur_h`;
`wms_adaptation_default_eur` is unused (I29). (d) amr_gtp capex `[EXPERT]` (no golden): storage =
`pods × per_pod_eur`; equipment = `robots × per_robot + stations × per_station + robots ×
charging_per_robot_eur` (0 placeholder); building works = `area.total × manual building works +
A_storage × amr_gtp.floor_prep_per_m2_eur` with `A_storage = storage.pod_bin.area_m2` (the same
A_storage as the F_ROBOT_DENSITY of I63 (3)); renewal applies to the family equipment item only
(the overflow carts and forklifts never renew). (e) `equipment_life_years` must be a whole number
≥ 1 when it falls within the horizon, else `ConfigError`. (f) Rent modes: `footprint` =
`area.total × rent`, `full_building` = `building.area × rent` for every scenario (cancels in the
deltas), `none` = 0. (g) Forklift energy (I32) is part of the energy kWh of every scenario with
forklifts. (h) IRR and payback are typ-world values (no `Range` in the schema); NPV, TCO, capex,
opex and cost per line are Ranges over the three worlds, the baseline evaluated in the same world
as the scenario. (i) I47 vs I48: a degenerate cube scenario reads two manual Params in F7
(`wms_adaptation_fixed_eur`, `software_eur_year`) that the I47 count excludes; the
`F_LOW_CONFIDENCE` count of `result.json` stays that of the cube scenario (50), part of the I48
`[EXPERT]` ruling.

**I74 — F11 calibration conventions (W4).** (a) One multiplier per row of the F6c table:
receiving (+ receipt_check), put_away, decant, replenishment, picking, packing (S + ML), shipping
(parcel + pallet), returns, indirect. (b) Hours are linear in 1 / productivity and in (1 + PF&D)
(I38): the engine runs once and θ is evaluated in closed form; η does not enter the monthly hours
(it stays at its prior); PF&D is confounded with the multipliers, so the identified (effective)
multiplier is `m × (1 + pfd_basis) / (1 + pfd)`, the quantity tested within 5 % (T11.1).
(c) The data term of the objective is divided by (0.3 % of the mean point)², so the prior is a
tie-breaker; `soft_l1` scale `F_SCALE` = 2 such units. (d) Peak month = month of the highest total
actual hours; the hold-out is the last `holdout_months` months, shifted to start at the peak
month (flag `W_HOLDOUT_SHIFTED`) when it is not in them. (e) A month is partial
(`W_PARTIAL_MONTH`, left out of the fit, the hold-out and the acceptance) only when the calendar
range of the daily series covers fewer than 90 % `[P]` of its days (an extract that starts or ends
mid-month); a month whose first or last day merely had no shipment is complete (I2: the calendar
runs from the first to the last local date, every date included). (f) A calendar month with no
actuals for any label: `W_MISSING_MONTH`. Two map keys equal after case and space folding must
map to the same target (`ConfigError`). (g) Peak lines/h error = design peak-hour lines / (growth
factor × η_fit) against the observed peak; η stays at its prior, so it does not depend on the
actuals (disclosed in the note). (h) Model activities without actuals are not compared and not in
the indirect base; headcount-only rows use `annual_paid_hours_per_fte / 12` hours per head and
month; `temp_hours` is informational. (i) An activity the client declares as client-specific is
reported (`F_CLIENT_ACTIVITY`), not fed into the catalog or sizing; an undeclared client activity
is a `ConfigError`. (j) Flag codes: `F_CALIB_ERROR`, `W_HOLDOUT_SHIFTED`, `W_PARTIAL_MONTH`,
`W_MISSING_MONTH`, `W_UNMAPPED_ACTIVITY`, `W_NO_ACTUALS`, `W_SHORT_HISTORY`, `F_CLIENT_ACTIVITY`,
`I_HEADCOUNT_ONLY`, `I_TEMPS_COMBINED`. (k) Catalog update: `typ` changes only within the current
`[min, max]`, confidence M and `validated_by` only with a reviewer name, a CHANGELOG line; always
on a copy of the catalog in tests.

**I75 — F8a runner conventions (W5).** (a) Run folder = `<created_at UTC YYYY-MM-DDTHH-MM-SS>_<first
6 hex of manifest_hash>`, created with mkdir, never overwritten (on a name clash `created_at`
moves by 1 microsecond). (b) `manifest_hash` excludes `run_id`, `mapping_hashes`, `timings` and
the `inputs/project.yaml` copy, so the suffix equals the hash of the written `manifest.json`;
`project_hash` (sha256 of the normalised project model) is part of the hashed content and is
checked by `rerun` (an edited `inputs/project.yaml` is a `ConfigError`). (c) Canonical reuse key =
`ingest_key`: file and mapping hashes, each dataset's `InputSpec` incl. sheet, sha256(salt), units
per pallet, engine version and git sha, stored in `canonical/.ingest_key`; `find_canonical` picks
the newest matching run and reuse is opt-in (`reuse_canonical=`; F10 `run-all` passes it).
(d) Salt = `project.salt_file`, else `$WHSIZING_SALT`, else `ConfigError` (exit 2, before any
folder is made); never written into the run; `rerun` needs none. (e) `engine_version` =
`<package version>+<git describe --always --dirty>`, `git_sha` = `rev-parse HEAD`, both
`unknown` without git or a commit. (f) A scenario raising `SizingInfeasibleError` becomes a
`not_computed` stub (status, reason); `ranking_payback` leaves out scenarios without a payback;
strict mode raises exit 4 after everything is written when a scenario is not computed or none
fits. (g) `comparison.baseline_id` = `scenarios.baseline` (`client_current` or a scenario id);
`is_baseline` must agree with `baseline:` (`ConfigError` otherwise). (h) A failed run logs
`run_failed` with the traceback to `logs/run.log` and keeps the manifest of its last finished
stage. (i) A path containing glob characters (`[`, `]`, `*`, `?`) is a normal path everywhere
(ingest inputs, canonical and profile parquet, run folders, report and calibration inputs; one
helper, `read_parquet_file` in `io/readers.py`, reads a parquet file by literal path through an
open handle). A wildcard pattern in `inputs.files` that must also
contain a literal glob character in another path component has to escape it (`[[]`): a known limit. (j) A scenario override must be
finite and `> 0` unless the catalog range of that Param includes 0 (`ConfigError` naming the id),
so a zero divisor never reaches the engine; a catalog constant the engine divides by (listed in
`catalog.paramset.DIVISOR_CONSTANTS`, e.g. `engine.eta_flow`, `area.parcels_per_pallet_equiv`,
`storage.skus_per_mixed_bin`) must also be `> 0`; no range check against `[min, max]` (sensitivity
runs leave it). (k) `options.worlds: typ` is accepted and ignored with a warning (the three worlds are
always computed); `--worlds` is a CLI display choice (F10).

**I76 — F8b sensitivity conventions (W5, `[EXPERT]` for the parameter definitions).** The public
functions take the run's `RunContext`, not a `Project`. Parameters: `labor_cost` (every role of
`basis.finance.labor_cost_eur_h`), `picking_productivity` (the catalog picking standards),
`growth_rate` (absolute ± δ × typ), `equipment_capex` (the equipment item's unit costs of the
family: robots, ports, stations, carts, forklifts; pods (`per_pod_eur`, the S1 storage item),
storage, controls and building works unchanged), `design_percentile` (90 / 95 / 98), `fill_factor` (pallet, shelf, bin fills) and
`oee`. `TornadoBar.low_input` / `high_input` carry the unit of their parameter (multiplier,
absolute rate, percentile, fill share). The break-even solves `payback(k) = target` for the labor
cost multiplier `k ∈ [0.3, 3]` with `scipy.optimize.brentq`; an unreached payback is mapped to the
horizon plus the remaining shortfall at the horizon end (monotone in k) and the root is
re-verified at k* within 1e-3. A scenario variant that raises `SizingInfeasibleError` is left out
of the tornado with a log warning. Bracket and parameter definitions to confirm with the expert.

**I77 — Receipts-mode flags (R4).** `F_INBOUND_SPARSE` (warning, value = receipt days among the
candidate days) when receipts exist but the percentile of the daily units or pallets is 0;
`F_RECEIPTS_NO_PALLETS` (warning, value = receipt days) when the pallet count is unknown on every
receipt day. I46 order: the design-day flags, then `F_INBOUND_SPARSE`, `F_RECEIPTS_NO_PALLETS`,
`F_DEFAULT_UPP`, then `F_LOW_CONFIDENCE`. `result.json` carries the design-day flags with the
severity F4 gave them (info for the three of I70, warning for these two). The flag fires only
when the percentile is exactly 0: two or three receipt days among 26 give a small non-zero
inbound without a flag (consistent with I71). A calendar month covered 90 to 100 % by the daily
series is complete for F11 (I74 e) and used without a flag.

**I78 — F10 CLI conventions.** (a) Staged flow (`ingest` → `profile` → `size`): the run folder
is made by the first `ingest`, before any manifest exists, so its suffix is the first 6 hex of the
sha256 of the dataset name and the input file hashes, not of the manifest (§2.4 and I75 a hold for
`run-all` and `rerun`). `manifest.run_id` is that folder name and the folder is never renamed, so
the path `ingest` printed stays valid for every later command. (b) Runs are immutable (§2.4):
`ingest --run` accepts only a folder `ingest` or `run-all` made (all §2.4 subfolders) that has no
`manifest.json` and no `design/design_day.json`; `profile` and `size` refuse a run with
`design/`; `compare`, `report` and `calibrate` need a sized run. A failed new `ingest` (exit 2 or
3) removes its folder when it wrote nothing but `logs/run.log`; exit 1 keeps it (traceback in
run.log) and so does a blocking DQ issue (its `dq/` explains it). (c) `size` writes
`canonical/.ingest_key` and `.sha256.json` like the F8a runner, with the key computed from the
data hashes and an empty salt and `inputs = {}`: `rerun` replays a staged run (no salt, no data
files read), `run-all` never reuses its canonical tables (the key matches no project's).
(d) `ingest` is timed in `logs/run.log` (`stage_done`); `size` puts it into `manifest.timings`.
(e) `run-all` takes the options of the commands it runs: `--strict`, `--worlds`,
`--sensitivity/--no-sensitivity`, `--delta` (validated, exit 2), `--lang`, `--formats`,
`--salt-file`, `--basis`, `--scenarios`, `--catalog` (these replace the project's, and the copies in
the run say so) and `--non-interactive` (accepted, `run-all` never asks). `--keep-descriptions` is
an option of `ingest` and of `run-all` (`ProjectOptions.keep_descriptions`, false by default; the
`ingest_key` and the `project_hash` carry it only when true, so earlier runs stay valid). A project without
`inputs.order_lines` is exit 2 before any folder is made. (f) `basis init` refuses to overwrite its
`--out` (exit 2): a hand-edited basis.yaml is never lost. (g) Output: the run folder is the last
line a command prints on stdout (`run-all` and `rerun` too; a failed report stage of `run-all`
prints `run folder: ...` on stderr). FTE in the comparison table has one decimal (a site of 1 FTE
has a lo-hi range of 0.7-1.4). The exit-5 message lists `IC<n> location: message`, 20 at most.

**I79 — F9a report conventions (W6).** (a) IC7 treats a cell marked `signed` (NPV, deltas, own and
cumulative cash flows, sensitivity deltas) as signed by nature; a cell shown as euros counts as
euros. (b) Block diagram: `Building` has no width, so the envelope is a square of side
`sqrt(area)`; docks always on the south wall; remaining zones strip-packed under the storage
rectangle, overflow hatched below the envelope with the deficit printed; 1 m = 2 px and the legend
column sets the picture height for a short envelope (F9c scales the SVG up on the A4 page).
(c) Opex by year is shown in the typical world only (`FinancialResult.opex_by_year` has no lo/hi);
the year-1 total and the capex items carry lo/typ/hi. (d) The Summary `n_warnings` cell cites
`<sid>.report.n_warnings` (typ world, scope = scenario id, count of flags with severity ≠ info), a
node the report records in memory and writes in the exported `report/trace.jsonl` (skipped when
F6/F8 record it). (e) Cash flow: cumulative = Σ Δ cash flows (IC6); the baseline scenario has no
delta and no cumulative column; the chart plots the cumulative delta against the baseline as the
zero line, and the caption says 'its own flows' when no delta column is drawn (no baseline, or the
baseline alone). (f) IC1 covers the numeric cells in the scenario columns of summary, scenarios,
fte and capex_opex; the dataset DQ score in the Summary study block is an untraced dataset
metric. (g) Payback 'not reached' is a text cell; the ranking-by-payback row is omitted when
nothing is ranked. (h) `FinancialResult.notes`, design-basis notes and DQ rule messages are shown
in the language the pipeline wrote them (English). (i) `report.export_trace(data, path)` writes
`report/trace.jsonl` with every id the report cites; the report builders call it.

**I80 — `--strict` and required inputs (§2.7 exit 4).** Required inputs, from the spec's
"minimum to start" (Appendix A): order lines, a SKU master with dimensions and weight, a stock
snapshot, and the site facts (basis). In strict mode `SizingInfeasibleError` (exit 4) is raised
(a) before ingest when the project has no `sku_master` or no `inventory` input, (b) after sizing
when an automated scenario has `F_ELIG_ASSUMED` (eligibility assumed for SKUs without
dimensions), in addition to the not-computed and no-fit cases of I75 (f); implemented by
`io.ingest.check_required_inputs` (before ingest) and the runner's strict check (after sizing).
Outside strict mode the
run continues with the flags and warnings.

**I81 — F9c PDF conventions.** (a) Every number of the PDF is a `Cell` of the F9a report model
printed by `render_cell`; the one derived figure is the overflow share of section 4 (1 − the
eligible share of lines). (b) The trace index of Appendix C is depth 1: for each computed
scenario, the Summary numbers (typical world) with trace id, formula and direct inputs. `param:`
inputs print the value used (more than 8 of them: their count, values in Appendix A),
`data:basis.*` the basis value, other `data:` inputs are dataset leaves (id only). Values have two
decimals (four below 1), a whole number none, so the printed inputs add up to the printed total;
a node deeper than the Summary (e.g. a parameter chain) is read in `report/trace.jsonl`, not in
the PDF. The three done-when numbers (total area, design-day heads, TCO) are reproducible from
the PDF alone. (c) Page budget (spec: 12-18): the report is typeset loosely and, when that gives
more than 18 pages, again with `.compact` (smaller tables and charts) and `.compact2` (tighter
spacing, six scenarios per stacked table); the loosest that fits is kept (3 example scenarios: 17
pages; 4: 17 in English, 18 in French; 5: 19 / 20). Legibility is never bought with pages: the
block diagrams (one per row, labels 7.1 pt at the page width after R7) and Appendix C (5.8 pt and
up, the page a reader reproduces the numbers from) keep their sizes at every level, so a study of
more scenarios is longer than 18 pages (6: 21 in both languages; 7 and 8 are proven at chart
level only, the executive summary then spills onto page 3): the tightest is written and
`report_over_page_budget` is logged; the budget is not a limit on the study. (d) A table with more scenarios than fit on the page width is cut into several, by scenario
(3 per table for ranges written inline and for the cash flow, 4 stacked), the label column
repeating. (e) Section 8 is a bordered box kept on one page; the percentile sweep is shown as
its table, no chart. (f) The cover has no running header; the footer reads run id and engine
version in the language of the report. (g) The French PDF and workbook carry the translated formulas block and say the flag codes of
the generated limitations through their i18n messages; only the free texts the pipeline wrote
(F4 notes, DQ messages, F7 notes) are shown as written, in English (I79 h). (h) The tornado is one
stacked figure, one panel per scenario with a shared x axis, its height growing with the number of
scenarios (readable up to 8; R7 replaced the earlier figures of at most 3 scenarios).

**I82 — F9b Excel conventions.** (a) The sheet `Capex / Opex` is written `Capex - Opex`: Excel
forbids `/` (every character of `[]:*?/\` becomes `-`, 31 characters at most); the title cell A1
keeps the i18n text. (b) The workbook is value-only (the live-formula stretch is not built); no
formula cell exists and a text starting with `=` stays a string. (c) Every cell with a trace id
(the four IC1 tables and the cash flow) carries a comment with the id, the world, the node label,
formula and inputs, and its value equals the node's value; a lo or hi cell cites the world whose
node holds the value (`Cell.world`), so a `Low` cell can read "hi world" (pessimistic and
optimistic worlds are not the same as min and max, I62). (d) The fit flag stays numeric 1 / 0
with a yes/no number format. (e) A scenario not computed is a grey merged region holding the
reason. (f) Summary writes its comparison block first, so the frozen header is the comparison
header. (g) `build_excel` runs `assert_integrity` first, builds the workbook in memory, checks the
Excel strings for untranslated sentinels (IC8), and only then writes `report/trace.jsonl` and the
xlsx. (h) The demand charts sit below the tables of `Demand profile`; the other charts are not in
the workbook. (i) A number above 9.99e307 is refused with `ReportIntegrityError`. (j) Thousands
and decimal separators follow the viewer's Excel locale; only dates follow the report language.

**I83 — R1 lower date bound (§4.1 `order_ts` "within [period − 1 d, today]").** The spec's
"period" has no definition in the data model. Registered: the period is the history proper, and a
date is implausibly early when it lies before a gap in the earliest dates. Among the earliest
`max(3, 5 %)` `[P]` distinct local order dates, the last gap of more than 90 days `[P]` separates
junk dates (1970-01-01 from an epoch default, 1900-01-01, a typo year) from the rest; the dates
before that gap are implausible, the bound is recomputed on the dates it keeps until stable (a pile
of junk dates larger than the cap is shed in turns), and it works on distinct dates, not lines (a
default-epoch export puts many lines on one junk date). Lines before the bound are R1 hits,
dropped and counted like an unreadable or a future date (severity by the R1 share rule: blocking
above 1 % of lines, else warning); R9, R10, R12 and the calendar are computed on the kept lines, so
one stray 1970-01-01 line cannot defeat the history gate (the 31-day tiny_golden plus one such
line still exits 3 through R9). A clean dataset is unaffected: a real start without a gap of more
than 90 days in its earliest dates is never cut, nor a slow launch ramp. Known limits (ponytail:
the upgrade is a per-client `history_start` input): a junk cluster above 5 % of the distinct dates
that is also isolated by more than 90 days looks like a real earlier period and stays (R9 and R12
show it); a real early block of up to 5 % of the distinct dates before a closure of more than 90
days (a season) is dropped, and R1 blocks when it exceeds 1 % of the lines; a stray date within 90
days before the first real date is kept and stretches the history (R9's message and R12 show it).

**I84 — Documented signature deviations (final audit).** `write_canonical(frames, out_dir,
manifest, timezone)` takes the manifest the caller built (the spec's two-argument form does not
say where the manifest comes from); `eligibility_shares(mask, lines_by_sku, stock_by_sku, *, family,
low_share, assumed)` and `breakeven(ctx, target_payback, scenario_id)` gained the arguments their
callers need (`breakeven` needs `scenario_id` when a run has 2 or more automated scenarios);
`build_profile` returns the profile and writes nothing (`write_profile` writes the artifacts and
`daily_series_path` names a file that exists after it); `finance/compute.py` and
`schemas/trace.py` hold what the spec layout calls `finance/build.py` and `engine/trace.py`;
`data/synth/generator.py` is a shim over `whsizing.synth`. T10.1's happy path runs on a generated
243-day site, not on tiny_golden: the spec contradicts itself (tiny_golden has 31 days, R9 makes
a history under 3 months blocking), so tiny_golden is the exit-3 fixture of T10.3.

**I85 — Plausibility guards on data-derived quantities.** (a) Derived inbound (I12) that comes out
negative (an extreme destock in the inventory history) is a `DataQualityError` (exit 3) naming the
delta-stock term, never a negative design value. (b) A sized equipment count above
`engine.max_equipment_count` `[P]` (100 000, catalog `engine_defaults.yaml`, a scalar constant so
the I47 counts stay) raises `SizingInfeasibleError` (exit 4) naming the resource and the value, so
a unit or outlier problem (R13 lists quantities such as 1e12 and keeps them) stops with a message
instead of running for minutes in the Erlang-C loop; `erlang_c` itself rejects `c` above that bound.

**I86 — `calibrate` (final audit).** The CLI parses `--actuals` and `--activity-map` first and
copies them into `calibration/` only when the calibration succeeded; a re-calibration refuses to
overwrite an existing `calibration/` (runs are immutable, §2.4) unless `--force` is given, and
`--observed-peak-lines-h` passes the client's observed peak to `calibrate` (the peak lines/h half
of the T11.4 error).

**I87 — Units at the parameter layer (pint, principle 3).** `whsizing.units` holds one pint
registry with the project's countable units defined (`eur`, `kEUR`, `lines`, `orders`, `pallets`,
`bins`, `pods`, `robots`, `ports`, `stations`, `cases`, `parcels`, `units`, `heads`, ...); a
`Param.unit` that pint cannot parse in that registry (other than `-`) is rejected by the catalog
loader and the `Param` model (`ConfigError` naming the id and the unit). The engine still works
in SI floats; pint is used at load time only.

**I88 — Annex A shows the value each scenario used.** The assumptions table keeps one row per
`Param` with the base value, and a scenario that overrides it adds a row/column `<scenario>:
<value>` (origin `override`); the PDF Annex A prints it (the xlsx already did), so a reader can
recompute any scenario from the annex. A test pins every Annex A value to the `params_snapshot` of
the scenario it is quoted for.

**I89 — C1 in the staged CLI.** Spec C1 asks for a `RunManifest` at the end of every stage. The
staged flow (`ingest` → `profile` → `size`) writes `manifest.json` at `size` (I78 a, b) because
the file is the marker that no further dataset may be ingested; this deviates from C1 for the
intermediate stages (their state is in `dq/`, `canonical/`, `profile/` and `logs/run.log`).
`run-all` and `rerun` follow C1.

**I90 — Failure handling and hygiene added by the final audit.** (a) A run that fails after its
folder exists (any `WhsizingError`, an unexpected exception, `KeyboardInterrupt`) writes
`<run>/logs/FAILED` (one JSON line `{error_type, reason}`, no data) besides `run_failed` in
`logs/run.log`; `app/state.py` neither lists nor opens such a run. The CLI turns SIGTERM into the
same path and exits 143 (128 + 15, added to the §2.7 table). A run that completed but is
infeasible (exit 4, below) is complete and stays listed. (b) `[VERIFY]` §2.7 reserves exit 4 for `--strict`;
registered extension: a run in which NO scenario is computed also raises `SizingInfeasibleError`
(exit 4) after everything is written, without `--strict` (an all-not-computed report is never
presented as a result); a partial failure stays a not-computed row with exit 0. (c) `calibrate`
stages its outputs in `<run>/.calibration-<hex>` and swaps the folder by renaming the old one aside
(restored when the swap fails), so a failed calibration leaves the earlier one untouched; a
non-finite or non-positive `--observed-peak-lines-h` is a `ConfigError`. (d) Anonymisation salt: a
salt file readable by group or world logs `salt_file_permissions`, a salt shorter than
`SALT_MIN_CHARS` = 16 logs `salt_too_short`; neither refuses the run and the salt is never
printed. (e) A column header repeated with different values logs a DQ note (file, column, the
ignored copy); identical repeated columns stay silent. (f) A control character in a client,
site or scenario name is stripped or escaped before it reaches the PDF running header (a form
feed or carriage return used to drop it from every page). (g) The C5 profile, sensitivity and
report budget tests carry the `bench` marker, so `just bench` and the CI bench job measure all
five C5 rows (they no longer run in `just test`).

## Golden case notes

- F3 decisions I49-I52 change no existing golden value: tiny_golden has one inventory snapshot,
  no inventory-only SKU, no line at local midnight, no dead stock and one calendar month.
  G1d (2026-11-08) adds four keys, compared by T3.1 (`tests/golden/test_f3_golden.py`):
  `stock.dead_stock_skus` = 0, `stock.dead_stock_cube_m3` = 0.0 (Σ over dead SKUs of
  `last_stock × unit_cube_m3`, the last-snapshot stock of I50, as the engine),
  `seasonality.trend_cagr` = null (one calendar month, I52) and `seasonality.trend_confidence` =
  "L". These golden values are degenerate, so the rules are pinned on modified copies of the data:
  oracle to register by `tests/golden/test_g1_sync.py` (dead stock 1 and 2 SKUs, trend on a
  synthetic 24-month series), engine to oracle by
  `test_T3_1_dead_stock_equals_the_oracle_on_a_copy_with_dead_stock` (every F3 key, 2 dead SKUs)
  and `test_T3_1_trend_equals_the_oracle_on_a_two_month_copy` (defined trend_cagr).
- I55-I57 and I59 change no golden value (G1d rebuild: only the four keys above were added):
  `golden_basis.yaml` sets `trailing_months: 12` and has 31 days (I55, I5), `inbound_mode:
  derived` (I56), every `design_day.p.*` > 0 (I57) and the SKU master has full pack data (I59).
  The oracle raises both flags (G1d fix round 1; `design_day.flags` is now written after the
  inbound rows, value unchanged): `F_RATIO_DRIFT:<m>` at `P_m = 0 < m*` and `F_DEFAULT_UPP`
  (code only, after the design-day flags, also in `S*.flags` before `F_LOW_CONFIDENCE`), pinned
  oracle = register = engine on modified data by `tests/golden/test_g1_register.py`.
- Basis: `tests/golden/golden_basis.yaml` (one shift, 7.5 h shift vs 7.0 paid hours, 8.5 m clear
  height, 410 m²: S0 fits at ≈ 399 m², S2 does not at ≈ 421 m², both margins ≈ 2.7 % > 0.5 %),
  scenarios `tests/golden/golden_scenarios.yaml`.
- Shipment thresholds are deliberately low (12 kg / 0.1 m³ / 5 kg instead of 300 kg / 0.6 m³ /
  30 kg): no tiny_golden order exceeds 21.6 kg, so the defaults leave pallets_out, multi-parcel
  orders and shipping_pallet at zero. Now 39 pallet orders (25 by weight only, 14 by cube only),
  2-parcel and 3-parcel orders, `F_RATIO_DRIFT:pallets_out` on the design day.
- S2 sets `extra_max_weight_kg: 2.0` (I44) so the overflow zone has a shelving class (every SKU
  outside the cube dims envelope is also outside the shelf envelope): 86 of 100 SKUs eligible
  for S2, 91 for the family default.
- tiny_golden has full dims coverage and no hazmat / temperature column: the I10 and I13
  branches are exercised by `tests/golden/test_g1_remediation.py` on a defect copy of the data.
- At ≈ 140 design lines/day most equipment counts are 1 or 2; engine golden tests (T6.1-T6.3,
  T7.1) are discriminating on the continuous values (positions, areas, hours, costs).
- S2 never pays back on this dataset (F_SCALE_LOW): `S2.finance.irr` and
  `S2.finance.payback_years` are `null`.
- The S0 roster is ≈ 11.7 heads for ≈ 7.9 design-day hours (S2: ≈ 12.7 for ≈ 6.3) because of
  the floor of 1 head per staffed activity (I19); the amenities it drives are what pushes S2
  over the building area (`F_NO_FIT`). This is spec-literal, not a data bug.
- Workbook comments: every value cell of the stage sheets carries its formula comment; in the
  SKUs and DailySeries sheets (one row per SKU / date) the **column header** carries the formula
  of every cell of its column, the data cells carry none (a comment per cell would add ≈ 3 000
  identical notes). Cells hold values, not live Excel formulas (the oracle is the Python code).
- `golden_case.xlsx` stores numbers with 16 significant digits; compare engine outputs with the
  T1.5 tolerance (0.5 %), not equality. Regenerate with `uv run python -m tests.golden.build_golden`.
- Engine-side T1.5: each stage compares itself with `golden_values.json` in its own golden test:
  T3.1 `tests/golden/test_f3_golden.py`, T4.1 `test_f4_golden.py`, T6.1 `test_f6_storage_golden.py`
  (`S*.storage|throughput|equipment|utilisation|eligibility|bottleneck`), T6.2
  `test_f6_labor_golden.py` (`S*.labor`), T6.3 `test_f6_area_golden.py` (`S*.area|docks|queue`).
  `tests/golden/test_g1_engine_parity.py` (no `whsizing` import) checks that these tests exist, are
  not skipped and that their `KEYS` patterns select every such key; `S*.flags` and
  `S*.low_confidence_params` are compared by no T6 test (I46). G1f (2026-11-09): T7.1
  `test_f7_golden.py` (`S*.capex|opex|finance`, 111 keys) is a fourth row of the same check, with
  the same disabling mutants and a narrowed-`KEYS` mutant; the "F7 not built" skip is gone.
- G1e (2026-11-09): the oracle's levels use I63 (11), floor with a 1e-9 tolerance, in both
  `levels` and the I40 `F_HEIGHT_LIMIT` test, and its shelving bins read
  `storage.shelf_bin_net_cube_m3` (I63 (6); the oracle's stray `manual_p2p.shelf_bin_net_cube_m3`,
  same 0.040, is gone from the Inputs sheet). Rebuild: `golden_values.json` byte-identical (8.5 m
  is no whole-pitch height); `golden_case.xlsx` loses that one Inputs row only. Pinned at 7.8 m
  (cube grid exactly 20 × 0.33 m, 19.999999999999996 in floats): 20 levels, no
  `F_HEIGHT_LIMIT:cube_bin`, oracle = engine on every storage key
  (`tests/golden/test_g1_oracle.py`, `test_g1_register.py`).
- I61-I67 against the oracle (G1e): I62 holds by construction (the oracle computes the typ world
  only). I63 (2), (4), (5), (8), (10)-(12) and I26 match the oracle (robot parking =
  `cube_asrs.m2_per_robot_parking` × robots + 40 in S0 and S2; S0 has 0 robots, so it reads no
  robot Param and I47 counts none: S0 = 30). I66 matches (`orders_S_d` =
  actual one-line orders per day); its "0.9 % / 2.2 %" are the S0 figures, S2 misses
  `p50_day_hours` by 1.05 % and `temp_hours` by 3.9 % with the `orders_d × share_S` alternative.
  Not discriminated by the golden case: I63 (1)'s `stock_growth_rate` override (the oracle reads
  no overrides; the golden basis has none, so `s_i` = I14), I63 (7) `height_utilisation` (no
  golden key), I63 (9) "stored" (no A/B SKU has `s_i = 0`), I64 (derived inbound), I65 (one
  shift), I61 and I67 (engine signatures, F2 ingestion), and the amr_gtp parts of I63 (3)
  (`F_ROBOT_DENSITY` over the pod_bin area) and (12) (no amr_gtp scenario). I63 (12) for
  amr_gtp is pinned on an inline S1 by `test_T1_5_amr_robot_parking_reads_the_cube_param`
  (`test_g1_register.py`); F6z fixed the engine to read `cube_asrs.m2_per_robot_parking`, so the
  strict xfail was removed and the test passes (docs/audit/F6d.md finding 2, closed).
- Engine-parity "not skipped" (G1e fix round 1): an F6 golden file counts as no test when it
  contains any skip / skipif / xfail / importorskip or a module `pytestmark`.
- I29-I37, I41, I42 and I48 against the oracle and F7 (G1f, 2026-11-09, after the F7 audit record
  `docs/audit/F7.md`): oracle = register = engine on every point. The register formulas, written
  a third time from this file and the catalog YAML alone, reproduce all 111 golden
  `S0|S2.capex|opex|finance` keys at 1e-9 (`tests/golden/test_g1_finance_register.py`), and T7.1
  holds the engine to the same keys at 0.5 %. I37 / I42 metrics (NPV with Δcf_0 undiscounted, IRR
  only with exactly one sign change, zeros ignored, payback interpolated and 0 when the capex
  delta is ≤ 0) are equal between `oracle.py` and `whsizing.finance` on eight flow sets. I48 holds
  on a degenerate copy (S2 with `extra_max_weight_kg` ≈ 0): oracle and F7 agree on all 60 S2
  capex / opex / finance keys, `capex.overflow` = 0, `capex.controls` = 50 000 (WMS adaptation,
  not `controls_fixed_eur`), no floor prep, and S2 costs what S0 costs (NPV 0). Roles of I33
  equal `catalog/labor_standards.yaml` (receiving, put_away, replenishment, shipping_pallet →
  forklift_driver; indirect → team_leader).
- What the register leaves unsaid, which oracle and F7 do (G1f; none changes a golden number).
  I35 states the `footprint` rent only: F7 and the oracle also price `full_building` (building
  area × rent, equal across scenarios) and `none` (0), as the spec does (T7.4). I35's renewal
  applies to the family `equipment` item only (overflow carts and forklifts never renew); F7
  raises `ConfigError` for `equipment_life_years` ≤ 0 or fractional inside the horizon, the oracle
  would never renew. I32 adds `forklifts × kwh_per_forklift_year` to the spec's energy formula
  (robots, stations, fixed): spec text is silent on forklifts, register, oracle and F7 agree. I42
  covers a scenario baseline only; F7 also costs the client's current operation
  (`baseline=None`: capex 0, labor from `basis.baseline` as FTE × `annual_paid_hours_per_fte` ×
  `utilisation` or actual hours, grown at g, plus the scenario's own consumables and rent; the
  oracle has no counterpart). amr_gtp capex (pods × `per_pod_eur`; equipment = robots × (robot +
  charging) + stations × `per_station_eur`; floor prep × pod storage area) and the
  `compute_finance` signature extras (`daily`, `tracer`, `baseline_tracer`, `client_baseline`) are
  registered in I73 (a) and (d); no golden scenario covers amr_gtp.
- Tension between I47 and I48: I47 counts "the Param blocks the scenario's formulas read", I48
  says the F_LOW_CONFIDENCE count of a degenerate cube scenario stays the cube's (50 on the golden
  copy; oracle and F6 agree). F7 prices that scenario with the manual formulas, so it reads
  `manual_p2p.wms_adaptation_fixed_eur` and `manual_p2p.software_eur_year`, which the cube count
  excludes, and does not read the cube's `controls_fixed_eur`, `software_eur_year` and the other
  cube capex Params. The count is by family, not by Params read, in this one case.
- I6 amended (G1g, 2026-11-09): the oracle ranks SKUs by lines, units, avg_stock, unit cube, weight
  (all descending, unknown weight = 0, I10), then sku ascending (`demand.ABC_ORDER`); it used
  lines then sku before, so the hashed id (salt) decided ties. Rebuild: 55 of the 741 golden
  values change, none added or removed. Cause: 12 SKUs tie at 5 lines across the B / C boundary
  (the first 5 of them are B). Old order, by sku: B = 73da1141072c60b3, 1853b525133fdf6b,
  08d40036a7a6742f (5-6 units), 2a7d19452a07904d (9) and 7b8801b209320951 (8); new order, by
  units: 87f4f13fa5f648b9, d924c41697680c3b, a11dc9f9aae82c3b (8 units each) enter B in their
  place, those three go to C.
  Same number of A / B SKUs, so no `abc.*`, `storage`, `area` or `capex` key moves; what moves is
  the replenishment workload of the B SKUs: S0 `labor.replenishment.*` (+0.31 %), `labor.indirect.*`,
  `labor.total.*`, `core_fte`, `temp_hours`, `p50_day_hours`, `equipment.forklift_moves_peak_h`,
  `utilisation.forklifts`, `opex.y1..y5.labor|total`, `finance.tco`, `finance.cost_per_line`, and
  S2 `finance.delta_cf.y1..y5` and `npv` through the S0 baseline (I42). Largest relative change
  0.314 %, inside the T1.5 tolerance. Only the units rung decides a golden tie (stock, cube and
  weight never do on tiny_golden): the four lower rungs, the identical-SKU pair and the null weight
  are pinned on a modified copy by `tests/golden/test_g1_abc_tiebreak.py`, which also relabels
  every sku id (another salt): all 741 values stay equal, while the old order moves 135 of them
  (55 to 137 across salts), `S0.storage.pallet_rack.pick_faces` 16 → 17 included; `S0.labor.annual_hours.y1..y5`
  and `S0.labor.core_heads_day` move with the replenishment workload like the keys above.
- Engine and I6 (F3f, 2026-11-09): `whsizing.profile.abc.classify` follows the amended chain
  (`lines, units, avg_stock, unit_cube_m3, weight_kg` descending, then `sku`), so the engine and the
  oracle agree at 1e-9 (the two strict xfails of G1g are gone). Known limit: the engine ranks a null
  weight after 0.0 while the oracle fills it with 0.0 (I10), so two SKUs tied on the five
  attributes, one of them with an unknown weight, can get a different per-SKU label (class sizes
  and shares are equal); SKUs tied on the five attributes but different in another one (hazmat,
  dims, temperature class, pack data, last stock) still fall to the hashed id when a class boundary
  falls between them.
- I75-I77 against the oracle (G1g): none changes a golden value. I75 (runner) and I76 (sensitivity)
  have no oracle counterpart. I77's two flags exist in receipts mode only; the golden basis is
  derived (I56) and the oracle now raises `NotImplementedError` for any other `inbound_mode`
  instead of computing derived silently (`test_T1_5_receipts_mode_is_not_silently_derived_in_the_oracle`).
  The I77 flag order (design-day flags, receipts flags, `F_DEFAULT_UPP`, `F_LOW_CONFIDENCE`) agrees
  with `build_golden.flags()` for the flags the oracle can raise. No contradiction with I42, I46,
  I56, I57, I59, I70 or I71. Left unsaid: when the pallet count is unknown on every receipt day
  the pallets percentile has no value (I56), so I77 does not say whether `F_INBOUND_SPARSE` also
  fires next to `F_RECEIPTS_NO_PALLETS`. F4 settled it: `design/inbound.py::_receipt_flags` leaves
  the pallets branch of `F_INBOUND_SPARSE` out in that case (its zero pallets are not also called
  sparse), the units branch is unaffected. The oracle has no receipts mode, so no golden value
  depends on it.

## Open expert rulings

Every `[EXPERT]` / `[VERIFY]` marker of the register, once, by entry (checked by
`tests/golden/test_g1_expert_rulings.py`: a marked entry missing here, or an entry listed twice,
fails). Nothing below changes a golden value unless said.

- **I33** (named in review #1, no marker): labor cost counts the temp hours twice, literal F7
  (on top of the annual hours); the expert decides. Golden S0 and S2 hold the literal value.
- **I46** `[EXPERT]`: the value of `cube_asrs.max_robots_per_m2` (0.05, no spec value), not the
  `F_ROBOT_DENSITY` flag; S2 raises it at ≈ 0.47 robots/m².
- **I48** `[EXPERT]`: whether a degenerate cube scenario (zero eligible lines) carries the manual
  WMS adaptation and manual software; to settle together with the I47 count (see above).
- **I53** `[EXPERT]`: R13 outlier threshold `median + 10 × max(MAD, 1)`, the MAD floor of 1 unit.
- **I54** `[VERIFY]`: amendment W3 to the decimal sniff (thousands shapes left out of the 80 %
  share, decimal-comma evidence beyond the verbatim regex, delimiter tie-break).
- **I64** `[EXPERT]`: with lumpy receipts, receipts-mode inbound hours sit above the P50 day and
  temp hours dominate (b2b S1 typ 9903 of 14519 h); literal spec kept, review before F7 prices
  temp hours (F7 now does, I33).
- **I65** `[EXPERT]`: the floor of 1 head per staffed activity applies per shift (about +4 heads on
  ecom_mid S0 with 2 × 7 h).
- **I67** `[VERIFY]`: in a `;` file with comma decimals elsewhere, a dot 3-decimal weight
  (`1.250`) is read × 1000 with no DQ signal; confirm with the spec owner.
- **I69** `[EXPERT]`: whether F6d should size the pack stations on the same `λ_s` as the F6e queue
  check, instead of reporting `F_UNSTABLE:packing` with `c_min`.

- **I76** `[EXPERT]`: the F8b parameter definitions (equipment_capex, picking_productivity) and the
  break-even bracket `[0.3, 3]`.
- **I90** `[VERIFY]`: exit 4 also without `--strict` when no scenario is computed (a deviation
  from the literal "only in --strict" of §2.7, added so that an all-not-computed report is never
  presented as a result); revert to exit 0 with a not-computed report if the spec owner prefers.
- **I73** `[EXPERT]`: the amr_gtp capex formulas and the `A_storage` choice for its floor
  preparation (no golden); the client-current baseline (labor only, biased towards the current
  operation).

# Assumptions

Generated from `catalog/` (C4) by `uv run python -m whsizing.catalog.assumptions`; do not edit by hand.
Every value is a placeholder `[P]` until the `[EXPERT]` validates it (`validated_by`).

Catalog version: `manual_p2p=0.1.0 amr_gtp=0.2.0 cube_asrs=0.2.0 sha256:452f630fe98a`. 72 ranged parameters: 72 with source TODO, 72 with confidence L.
The pessimistic world takes each parameter at its pessimistic end (ADR-002).

## Ranged parameters

| id | unit | min | typ | max | pessimistic end | source | confidence | validated by | date | note |
|---|---|---:|---:|---:|---|---|---|---|---|---|
| amr_gtp.bins_per_pod | - | 40 | 60 | 90 | min | TODO | L |  | 2026-11-01 |  |
| amr_gtp.charging_per_robot_eur | eur | 0 | 0 | 0 | max | TODO | L |  | 2026-11-01 | no spec value; 0 = included in per_robot_eur |
| amr_gtp.decant_cases_per_h | cases/h | 50 | 80 | 110 | min | TODO | L |  | 2026-11-01 |  |
| amr_gtp.fill_factor | - | 0.7 | 0.8 | 0.88 | min | TODO | L |  | 2026-11-01 |  |
| amr_gtp.fleet_software_fixed_eur | eur | 80000 | 150000 | 300000 | max | TODO | L |  | 2026-11-01 |  |
| amr_gtp.floor_prep_per_m2_eur | eur/m2 | 10 | 20 | 40 | max | TODO | L |  | 2026-11-01 |  |
| amr_gtp.kwh_per_robot_year | kWh | 1000 | 1500 | 2200 | max | TODO | L |  | 2026-11-01 |  |
| amr_gtp.lines_per_pod_visit | - | 1.2 | 1.8 | 2.5 | min | TODO | L |  | 2026-11-01 |  |
| amr_gtp.m2_per_robot_parking | m2 | 1.5 | 2 | 2.5 | max | TODO | L |  | 2026-11-01 |  |
| amr_gtp.m2_per_station | m2 | 12 | 16 | 20 | max | TODO | L |  | 2026-11-01 |  |
| amr_gtp.maintenance_share_of_equipment_capex | - | 0.04 | 0.06 | 0.08 | max | TODO | L |  | 2026-11-01 |  |
| amr_gtp.oee | - | 0.75 | 0.85 | 0.9 | min | TODO | L |  | 2026-11-01 |  |
| amr_gtp.per_pod_eur | eur | 600 | 900 | 1400 | max | TODO | L |  | 2026-11-01 |  |
| amr_gtp.per_robot_eur | eur | 20000 | 30000 | 45000 | max | TODO | L |  | 2026-11-01 |  |
| amr_gtp.per_station_eur | eur | 25000 | 40000 | 60000 | max | TODO | L |  | 2026-11-01 |  |
| amr_gtp.pod_footprint_m2 | m2 | 2 | 2.6 | 3.2 | max | TODO | L |  | 2026-11-01 |  |
| amr_gtp.robot_availability | - | 0.88 | 0.94 | 0.97 | min | TODO | L |  | 2026-11-01 |  |
| amr_gtp.robot_pod_moves_h | moves/h | 8 | 12 | 16 | min | TODO | L |  | 2026-11-01 |  |
| amr_gtp.software_eur_year | eur | 20000 | 40000 | 80000 | max | TODO | L |  | 2026-11-01 |  |
| amr_gtp.station_rate_lines_h | lines/h | 150 | 250 | 350 | min | TODO | L |  | 2026-11-01 |  |
| cube_asrs.bins_per_m2_per_level | 1/m2 | 2.6 | 3 | 3.4 | min | TODO | L |  | 2026-11-01 |  |
| cube_asrs.controls_fixed_eur | eur | 100000 | 150000 | 250000 | max | TODO | L |  | 2026-11-01 |  |
| cube_asrs.decant_cases_per_h | cases/h | 60 | 90 | 120 | min | TODO | L |  | 2026-11-01 |  |
| cube_asrs.dig_factor | - | 1.3 | 1.6 | 2 | max | TODO | L |  | 2026-11-01 |  |
| cube_asrs.fill_factor | - | 0.8 | 0.88 | 0.92 | min | TODO | L |  | 2026-11-01 |  |
| cube_asrs.floor_prep_per_m2_eur | eur/m2 | 10 | 20 | 40 | max | TODO | L |  | 2026-11-01 | no spec value; analog of amr_gtp.floor_prep_per_m2_eur |
| cube_asrs.grid_structure_per_m2_eur | eur/m2 | 400 | 650 | 900 | max | TODO | L |  | 2026-11-01 |  |
| cube_asrs.kwh_per_robot_year | kWh | 800 | 1200 | 1800 | max | TODO | L |  | 2026-11-01 |  |
| cube_asrs.lines_per_bin_presentation | - | 1 | 1.3 | 1.8 | min | TODO | L |  | 2026-11-01 |  |
| cube_asrs.m2_per_port | m2 | 15 | 20 | 25 | max | TODO | L |  | 2026-11-01 |  |
| cube_asrs.m2_per_robot_parking | m2 | 1.5 | 2 | 2.5 | max | TODO | L |  | 2026-11-01 | typ from F6d; range analog of amr_gtp.m2_per_robot_parking |
| cube_asrs.maintenance_share_of_equipment_capex | - | 0.03 | 0.05 | 0.07 | max | TODO | L |  | 2026-11-01 |  |
| cube_asrs.max_robots_per_m2 | robots/m2 | 0.05 | 0.05 | 0.05 | min | TODO | L |  | 2026-11-01 | no spec value; analog of amr_gtp.max_robots_per_m2 |
| cube_asrs.oee | - | 0.75 | 0.85 | 0.9 | min | TODO | L |  | 2026-11-01 |  |
| cube_asrs.per_bin_eur | eur | 25 | 40 | 60 | max | TODO | L |  | 2026-11-01 |  |
| cube_asrs.per_port_eur | eur | 40000 | 60000 | 90000 | max | TODO | L |  | 2026-11-01 |  |
| cube_asrs.per_robot_eur | eur | 25000 | 35000 | 50000 | max | TODO | L |  | 2026-11-01 |  |
| cube_asrs.port_rate_lines_h | lines/h | 250 | 350 | 450 | min | TODO | L |  | 2026-11-01 |  |
| cube_asrs.robot_availability | - | 0.9 | 0.95 | 0.98 | min | TODO | L |  | 2026-11-01 |  |
| cube_asrs.robot_bins_per_h | bins/h | 15 | 22 | 30 | min | TODO | L |  | 2026-11-01 |  |
| cube_asrs.software_eur_year | eur | 20000 | 40000 | 80000 | max | TODO | L |  | 2026-11-01 |  |
| engine.pack_station_oee | - | 0.75 | 0.85 | 0.9 | min | TODO | L |  | 2026-11-01 | no spec value; analog of amr_gtp.oee |
| finance.kwh_per_station_year | kWh | 1000 | 1500 | 2200 | max | TODO | L |  | 2026-11-01 | no spec value; analog of amr_gtp.kwh_per_robot_year |
| finance.packaging_eur_per_order | eur | 0.6 | 0.9 | 1.3 | max | TODO | L |  | 2026-11-01 |  |
| labor.packing_ML | orders/h | 18 | 25 | 32 | min | TODO | L |  | 2026-11-01 |  |
| labor.packing_S | orders/h | 40 | 55 | 70 | min | TODO | L |  | 2026-11-01 |  |
| labor.put_away | pallets/h | 10 | 13 | 16 | min | TODO | L |  | 2026-11-01 |  |
| labor.receipt_check | lines/h | 30 | 45 | 60 | min | TODO | L |  | 2026-11-01 |  |
| labor.receiving | pallets/h | 10 | 14 | 18 | min | TODO | L |  | 2026-11-01 |  |
| labor.replenishment | moves/h | 10 | 14 | 18 | min | TODO | L |  | 2026-11-01 |  |
| labor.returns | lines/h | 15 | 22 | 30 | min | TODO | L |  | 2026-11-01 |  |
| labor.shipping_pallet | pallets/h | 10 | 14 | 18 | min | TODO | L |  | 2026-11-01 |  |
| labor.shipping_parcel | parcels/h | 80 | 110 | 140 | min | TODO | L |  | 2026-11-01 |  |
| manual_p2p.building_works_per_m2_eur | eur/m2 | 30 | 60 | 120 | max | TODO | L |  | 2026-11-01 |  |
| manual_p2p.eta_pick | - | 0.75 | 0.85 | 0.92 | min | TODO | L |  | 2026-11-01 |  |
| manual_p2p.forklift_moves_h | moves/h | 12 | 16 | 22 | min | TODO | L |  | 2026-11-01 |  |
| manual_p2p.kwh_per_forklift_year | kWh | 3000 | 4500 | 6000 | max | TODO | L |  | 2026-11-01 |  |
| manual_p2p.m2_per_pack_station | m2 | 10 | 12 | 15 | max | TODO | L |  | 2026-11-01 |  |
| manual_p2p.maintenance_share_of_equipment_capex | - | 0.02 | 0.04 | 0.06 | max | TODO | L |  | 2026-11-01 |  |
| manual_p2p.pallet_rack_fill_factor | - | 0.8 | 0.85 | 0.9 | min | TODO | L |  | 2026-11-01 |  |
| manual_p2p.pallet_rack_positions_per_m2_per_level | 1/m2 | 0.3 | 0.38 | 0.45 | min | TODO | L |  | 2026-11-01 |  |
| manual_p2p.per_cart_eur | eur | 800 | 1500 | 3000 | max | TODO | L |  | 2026-11-01 |  |
| manual_p2p.per_forklift_eur | eur | 25000 | 35000 | 50000 | max | TODO | L |  | 2026-11-01 |  |
| manual_p2p.per_pallet_position_eur | eur | 60 | 90 | 140 | max | TODO | L |  | 2026-11-01 |  |
| manual_p2p.per_shelf_bin_eur | eur | 8 | 12 | 18 | max | TODO | L |  | 2026-11-01 |  |
| manual_p2p.pick_rate_pallet_lines_h | lines/h | 25 | 35 | 50 | min | TODO | L |  | 2026-11-01 |  |
| manual_p2p.pick_rate_shelving_lines_h | lines/h | 50 | 70 | 95 | min | TODO | L |  | 2026-11-01 |  |
| manual_p2p.replen_units_per_move | units | 40 | 80 | 150 | min | TODO | L |  | 2026-11-01 |  |
| manual_p2p.shelving_bins_per_m2_per_level | 1/m2 | 6 | 8 | 10 | min | TODO | L |  | 2026-11-01 |  |
| manual_p2p.shelving_fill_factor | - | 0.7 | 0.8 | 0.9 | min | TODO | L |  | 2026-11-01 |  |
| manual_p2p.software_eur_year | eur | 5000 | 15000 | 40000 | max | TODO | L |  | 2026-11-01 |  |
| manual_p2p.wms_adaptation_fixed_eur | eur | 20000 | 50000 | 120000 | max | TODO | L |  | 2026-11-01 |  |

## Structural constants

| id | value |
|---|---:|
| amr_gtp.charging_reserve | 0.15 |
| amr_gtp.commissioning_share | 0.05 |
| amr_gtp.contingency_share | 0.1 |
| amr_gtp.empty_bin_reserve | 0.05 |
| amr_gtp.equipment_life_years | 8 |
| amr_gtp.integration_share | 0.1 |
| amr_gtp.max_robots_per_m2 | 0.05 |
| amr_gtp.max_weight_kg | 20 |
| amr_gtp.min_scale_lines_day | 800 |
| amr_gtp.pod_bin_net_cube_m3 | 0.03 |
| amr_gtp.renewal_share | 0.6 |
| area.amenities_fixed_m2 | 150 |
| area.circulation_share | 0.25 |
| area.m2_per_head_amenities | 4 |
| area.m2_per_pallet_staged | 1.5 |
| area.m2_per_return_line_day | 0.05 |
| area.maintenance_fixed_m2 | 40 |
| area.parcels_per_pallet_equiv | 40 |
| area.peak_hour_share_inbound | 0.2 |
| area.receiving_window_hours | 8 |
| area.returns_fixed_m2 | 30 |
| area.staging_days | 1 |
| cube_asrs.bin_net_cube_m3 | 0.055 |
| cube_asrs.commissioning_share | 0.05 |
| cube_asrs.contingency_share | 0.1 |
| cube_asrs.empty_bin_reserve | 0.05 |
| cube_asrs.equipment_life_years | 12 |
| cube_asrs.grid_overhead_m | 1.2 |
| cube_asrs.integration_share | 0.1 |
| cube_asrs.level_height_mm | 330 |
| cube_asrs.max_levels | 20 |
| cube_asrs.max_weight_kg | 25 |
| cube_asrs.min_scale_lines_day | 1500 |
| cube_asrs.renewal_share | 0.6 |
| cube_asrs.service_aisle_share | 0.08 |
| engine.core_day_percentile | 50 |
| engine.elig_low_line_share | 0.5 |
| engine.eta_flow | 0.85 |
| engine.max_equipment_count | 100000 |
| engine.receipt_lines_per_pallet_full | 1 |
| engine.receipt_lines_per_pallet_mixed | 4 |
| engine.sla_risk_max_probability | 0.05 |
| engine.sla_wait_threshold_share | 0.5 |
| finance.default_roles_cost_eur_h_forklift_driver | 28 |
| finance.default_roles_cost_eur_h_operator | 26 |
| finance.default_roles_cost_eur_h_team_leader | 34 |
| finance.fixed_energy_kwh_year | 20000 |
| finance.wms_adaptation_default_eur | 30000 |
| labor.indirect_share_of_direct_hours | 0.12 |
| labor.outbound_lag_hours | 1 |
| manual_p2p.commissioning_share | 0.02 |
| manual_p2p.contingency_share | 0.1 |
| manual_p2p.equipment_life_years | 10 |
| manual_p2p.integration_share | 0.05 |
| manual_p2p.max_weight_kg | 1000 |
| manual_p2p.min_scale_lines_day | 0 |
| manual_p2p.pallet_rack_beam_pitch_mm | 150 |
| manual_p2p.pallet_rack_max_levels | 6 |
| manual_p2p.pallet_rack_pallet_load_height_mm | 1400 |
| manual_p2p.pallet_rack_top_clearance_m | 0.6 |
| manual_p2p.pick_face_policy_faces_per_sku | 1 |
| manual_p2p.renewal_share | 0.5 |
| manual_p2p.shelving_bin_net_cube_m3 | 0.04 |
| manual_p2p.shelving_bin_pitch_mm | 400 |
| manual_p2p.shelving_ergonomic_max_levels | 5 |
| manual_p2p.shelving_shelf_max_height_m | 2.1 |
| storage.default_units_per_pallet | 400 |
| storage.max_bins_per_sku_shelf | 6 |
| storage.mixed_bin_threshold_share | 0.2 |
| storage.pallet_threshold_m3 | 0.6 |
| storage.shelf_bin_net_cube_m3 | 0.04 |
| storage.skus_per_mixed_bin | 4 |

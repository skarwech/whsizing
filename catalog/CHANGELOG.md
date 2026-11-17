# Catalog changelog

One entry per change (F5 governance): date, files, parameter ids, old → new, reason, reviewer.

## engine_defaults — 2026-11-10

- `engine.max_equipment_count` (new scalar constant, 100000, `[P]`, I85 b): a plausibility bound on any
  sized equipment count (pickers, forklifts, carts, stations, ports, robots, pack stations, pods). A
  count above it stops the run with `SizingInfeasibleError` (exit 4) naming the resource and the value,
  so a unit or outlier problem does not run for minutes. A scalar, not a Param block: the I47
  low-confidence counts are unchanged. No spec value. Reviewer: none.

## amr_gtp 0.2.0, cube_asrs 0.2.0 — 2026-11-08

Parameters F6/F7 consume that had no catalog entry (W1 F5 audit, finding 4). All are new
`[P]` placeholders with `source: TODO` and `confidence: L`. None of them has a spec value. Not
yet reviewed by the `[EXPERT]` (reviewer: none).

- `cube_asrs.floor_prep_per_m2_eur` (new, eur/m2, 10 / 20 / 40, pessimistic max). It is used by
  F7 building works, "+ floor preparation × A_grid" (description.md l.1091). The values are the
  analog of `amr_gtp.floor_prep_per_m2_eur` (C.2 l.1670). Before this change, F7 had no
  parameter here, so the golden interpretation I30 takes cube floor prep = 0.
- `cube_asrs.max_robots_per_m2` (new, robots/m2, 0.05 / 0.05 / 0.05, pessimistic min). It is the
  F5 family table's "max robots per m² of grid [P]" (l.847). The value is the analog of the
  `amr_gtp.max_robots_per_m2` scalar 0.05 (C.2 l.1661). The range is degenerate because the
  analog has no range.
- `cube_asrs.m2_per_robot_parking` (new, m2, 1.5 / 2.0 / 2.5, pessimistic max). It is used by
  F6d equipment area, "robots × m2_per_robot_parking (2.0)" (l.995). typ 2.0 comes from F6d.
  The range is the analog of `amr_gtp.m2_per_robot_parking` (C.2 l.1664).
- `amr_gtp.charging_per_robot_eur` (new, eur, 0 / 0 / 0, pessimistic max). It is the F7 S1
  equipment item "+ charging" (l.1089). The spec gives no value and no analog. 0 means charging
  is taken as included in `per_robot_eur`. F7 multiplies it by the robot count.
- kWh per station per year is not added per family. F7's energy formula (l.1104) has a single
  `stations × kWh_per_station_year` term, and `finance.kwh_per_station_year` already covers it.
- The loader now enforces a per-family schema. Each family file must hold exactly its own
  family's keys (`FAMILY_KEYS` in `src/whsizing/catalog/models.py`).

## 0.1.0 — 2026-11-08

- Initial catalog v0 from the spec: `families/manual_p2p.yaml` (Appendix C.1), `amr_gtp.yaml`
  (C.2), `cube_asrs.yaml` (F5 schema), `labor_standards.yaml`, `finance_defaults.yaml`,
  `storage_classes.yaml`, `area_factors.yaml`, `icpe_1510.yaml` (Appendix D). Values verbatim;
  every range has `source: TODO`, `confidence: L`. Not yet reviewed by the `[EXPERT]`.
- `engine_defaults.yaml`: `[P]` constants the spec states outside Appendix C/D (η_flow,
  receipt lines per pallet, P50 core day, SLA thresholds, F_ELIG_LOW share).
- No spec value, analog placeholders to be set by the `[EXPERT]`: `engine.pack_station_oee`
  (analog of `amr_gtp.oee`), `finance.kwh_per_station_year` (analog of
  `amr_gtp.kwh_per_robot_year`).

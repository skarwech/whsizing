# tiny_golden — golden case dataset (F1)

Canonical synthetic dataset behind the golden spreadsheet (T1.5) and the golden tests of F3–F7.
Generated deterministically, no defects. Do not edit by hand.

## Regenerate

From the repository root:

```bash
uv run python data/synth/generator.py data/synth/profiles/tiny_golden.yaml --out tests/golden/tiny_golden --seed 42
```

`tests/unit/test_f1_generator.py::test_tiny_golden_dataset_matches_profile_and_seed` fails if the
generator or the profile no longer reproduce these files. Changing either one invalidates the
golden spreadsheet: regenerate, then have the spreadsheet re-checked.

Last regenerated in F1 fix round 1 (returns delay window, receipts carry-over), before the
T1.5 spreadsheet existed.

## Files

| File | Content |
|---|---|
| `order_lines.parquet` | canonical §4.1 order lines, `order_ts` in UTC (Paris wall time at generation) |
| `sku_master.parquet` | 100 SKUs, full dims / weight / `units_per_case` / `cases_per_pallet` coverage |
| `inventory.parquet` | one month-end snapshot (2025-03-31) for every SKU |
| `receipts.parquet` | weekly (Monday) replenishment receipts |
| `csv_en/*.csv`, `csv_fr/*.csv` | the same data as client-like CSV extracts (F2 mapping fixture; 31 days trips R9 "history < 3 months", so T1.4 re-ingests a 4-month ecom_mid instead) |

## Contents (seed 42)

- Period: 2025-03-01 → 2025-03-31 (Paris local dates), no French public holiday, no orders on Sundays.
- 984 orders (expected Σλ_d ≈ 991), 1,954 lines: 1,881 shipped, 28 cancelled, 45 returns
  (negative quantities, own order ids, `line_status = returned`, 3-20 days after shipping,
  never on a Sunday).
- 100 SKUs, 90 ordered (10 inactive), 8 categories.
- Engine coverage: 9 SKUs outside the cube_asrs envelope (sorted dims > [600, 400, 300] mm);
  by snapshot stock cube (qty × unit cube), 5 SKUs ≥ 0.6 m³ (pallet_rack), 7 between 0.24 and
  0.6 m³, 78 non-zero ≤ 0.24 m³ (shelving range), 10 with zero stock.
- 233 receipt lines on 40 receipts; receipts carry the case-rounding surplus over, so received
  units ≈ shipped units (ratio 1.045 over the month).

Profile tuning against the `[P]` defaults (`sigma_log_mm` 0.7, `days_of_cover` 60,
`orders_per_day_mean` 46) is explained at the top of `data/synth/profiles/tiny_golden.yaml`.

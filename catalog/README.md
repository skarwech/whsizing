# Automation catalog (F5)

Neutral, traceable equipment data. No brand names, quotes or client data; ranges come from public
documentation and expert judgment only. Every value is a placeholder `[P]` until the `[EXPERT]`
validates it (then `source`, `confidence`, `validated_by` and `date` are updated and
`CHANGELOG.md` gets an entry).

| File | Content | Id prefix |
|---|---|---|
| `families/<family>.yaml` | one automation family (Appendix C, F5 schema) | `<family>.` |
| `labor_standards.yaml` | activities, drivers, standards, roles (Appendix D) | `labor.` |
| `finance_defaults.yaml` | packaging, energy, default role costs (Appendix D) | `finance.` |
| `storage_classes.yaml` | storage class assignment (Appendix D) | `storage.` |
| `area_factors.yaml` | area budget factors (Appendix D) | `area.` |
| `icpe_1510.yaml` | ICPE regimes, informational `[VERIFY]` (Appendix D) | — |
| `engine_defaults.yaml` | `[P]` constants of F4/F6 with no other home | `engine.` |

`load_catalog("catalog")` validates everything; `docs/assumptions.md` is generated from it
(`uv run python -m whsizing.catalog.assumptions`).

## Parameter ids

Every numeric value has an id, used by overrides (`basis.overrides`, `scenario.overrides`), the
trace (`param:<id>`) and the run's `params_snapshot`:

- `<prefix>.<path>`, where `<path>` is the YAML key path joined with `_`, after dropping
  1. the top-level section of a family file (`constraints`, `storage`, `throughput`, `area`,
     `capex`, `opex`, `life`) and of `labor_standards.yaml` (`activities`, `profiles`);
  2. a trailing `standard` (labor activities).
- Examples: `throughput.port_rate_lines_h` in `cube_asrs.yaml` → `cube_asrs.port_rate_lines_h`;
  `storage.pallet_rack.positions_per_m2_per_level` in `manual_p2p.yaml` →
  `manual_p2p.pallet_rack_positions_per_m2_per_level`; `activities.receiving.standard` →
  `labor.receiving`; `default_roles_cost_eur_h.operator` → `finance.default_roles_cost_eur_h_operator`.
- Ids are unique across the catalog. A block's explicit `id`, when given, must equal this id.
- `basis.overrides` may also hold the basis-level keys in `BASIS_KEYS`
  (`src/whsizing/catalog/paramset.py`). Today that is only `stock_growth_rate` (F4 step 7).
  These keys are not catalog parameters: read them with `ParamSet.basis_value(key, default)`.
  Any other unknown id is rejected.

## Ranged values (Param blocks)

A ranged value is a full block, never the `R(...)` shorthand of the spec:

```yaml
port_rate_lines_h: {id: cube_asrs.port_rate_lines_h, unit: "lines/h", min: 250, typ: 350, max: 450, source: TODO, confidence: L, pessimistic_end: min, date: 2026-11}
```

`unit`, `min`, `typ`, `max`, `source`, `confidence` and `date` are required; `min ≤ typ ≤ max`.
`pessimistic_end` is the bound used in the pessimistic world (ADR-002). When it is absent, the
loader infers it from the unit's tokens, not from substrings (§2.5.1). The rules apply in this
order:

1. An `eur` token or `€` in the unit, or a `kWh` token → `max`. Costs and energy, so `eur/m2`
   and `eur/h` are costs (`europallets/h` is not).
2. A rate per hour (`x/h`) or a density per m² (`x/m2`) → `min`.
3. The word `fill`, `availability` or `oee` in the unit or in the parameter name → `min`.
4. The unit exactly `h` (a duration), the unit `m2 per …` or a name with `m2_per` (area per
   unit) that is not a density (`…_per_m2_…`) → `max`.

If no rule matches, the value must be written, or the file is rejected. Examples of such units:
`pallets/shift`, `units/month`, `lines/day`, `share`, `hours`, `-`. An explicit value that
contradicts the inference is loaded with a warning.

Scalars are structural constants (dims, levels, shares); they are the same in every world.

## Loader rules

Rejected (`ConfigError`, exit 2, naming file and key): missing `unit`/`source`/`confidence`,
missing `pessimistic_end` that cannot be inferred, `min > typ` (or `typ > max`), unknown keys,
a family file that lacks one of its family's parameters or holds another family's key (the exact
key set of each family's sections is `FAMILY_KEYS` in `src/whsizing/catalog/models.py`),
duplicate YAML keys, duplicate ids or family ids, a non-semver family `version`, the `R(...)`
shorthand, unknown or missing catalog files, a non-finite number (`.nan`, `.inf`, `"nan"`)
anywhere, a file that is not UTF-8, and a `max_robots_per_m2` of the wrong shape (a number in
`amr_gtp`, a Param block in `cube_asrs`). Warned: `source: TODO` (counted in
`Catalog.todo_count`).

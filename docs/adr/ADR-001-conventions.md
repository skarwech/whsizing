# ADR-001 — Conventions

Status: accepted (D1). Source: spec §3.5.

## Decision

- **Units:** mm, kg, m, m², m³, hours. Currency EUR excluding VAT.
- **Timestamps:** tz-aware (`Europe/Paris`), stored as UTC in Parquet with the zone in metadata.
  The Pandera frames (`whsizing.schemas.frames`) reject naive timestamps instead of coercing them
  to UTC: localise in ingestion, then validate.
- **IDs** are strings; hashed IDs are 16 hex characters.
- **Rounding** only at presentation. The engine keeps floats; counts are `ceil`ed where stated.
  Contract counts are floats unless the spec says `int`.
- **Randomness:** every random process takes an explicit `seed`; default seed 42 in tests.
- **YAML:** keys are `snake_case`; parameter ids are `<family>.<name>` or `<file>.<name>`
  (e.g. `labor.pick_rate_manual_lines_h`). Loaded with `yaml.safe_load`; every model forbids
  unknown keys (`StrictModel`, `extra="forbid"`) and errors become `ConfigError` (exit 2).
- **YAML times are quoted:** `cutoff_time: "15:00"`. YAML 1.1 reads an unquoted `15:00` as the
  base-60 integer 900; `Service` rejects integers rather than silently reading 00:15.
- **Paths in project.yaml** resolve relative to the YAML file (`ResolvedPath`), `~` is expanded.
- **Contracts** live in `whsizing.schemas` and are frozen: changes are additive only
  (new optional field or new model).

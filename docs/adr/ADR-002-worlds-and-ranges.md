# ADR-002 — Worlds and ranges

Status: accepted (D1). Source: spec §2.5.1.

## Decision

- Each `Param` declares `pessimistic_end` (`min` or `max`). Loader inference rule: units containing
  `/h`, `/m2`, `fill`, `availability`, `OEE` → `min`; units containing `eur`, `h` (durations),
  `m2 per` → `max`; anything else must be explicit, otherwise the loader rejects the file.
- The engine evaluates every output three times: the **pessimistic world** (all parameters at their
  pessimistic end), the **typical world** (all at `typ`) and the **optimistic world**.
- `Range.lo` / `Range.hi` are the sorted extremes; `Range.typ` is always the typical world.
  `Range` enforces `lo ≤ typ ≤ hi`.
- Ranges bound the result; they are **not** statistical intervals (Monte Carlo is backlog).
- Trace: all three worlds are traced in full (register I62, which supersedes the spec 2.6 'lo/hi
  worlds trace only leaf results': IC2 needs a complete tree per world). The `Tracer` keys nodes by
  `(id, world)`.

## Consequences

Ranges can be wide; the report always prints them with the confidence note and never labels a
scenario "recommended" (F8).

## World names (added before W1)

The `World` literal is `lo | typ | hi` and names the **world**, not the value: `lo` = pessimistic world
(every parameter at its `pessimistic_end`), `typ` = typical world, `hi` = optimistic world (every
parameter at the other bound). A result's `Range` is then built as `lo=min(values over the 3 worlds)`,
`typ=typical value`, `hi=max(...)`, because a pessimistic world gives a *higher* cost but a *lower* rate.

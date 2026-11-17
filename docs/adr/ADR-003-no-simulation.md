# ADR-003 — No simulation in the POC

Status: accepted (D1). Source: spec §1.3, §10.

## Decision

The POC sizes analytically (closed-form formulas, Erlang-C queue check). Discrete-event simulation
(SimPy) and Monte Carlo are out of scope and stay in the backlog.

## Rationale

- Fast: three scenarios × three worlds in < 10 s (C5).
- Glass-box: every number traces to a formula and a `Param` (F6f); a simulation is harder to audit.
- Uncertainty is shown with lo/typ/hi worlds (ADR-002) instead of sampled distributions.

## Consequences

Dynamic effects (congestion, wave interactions) are approximated by flow efficiency and the queue
check; the report's limitations box says so.

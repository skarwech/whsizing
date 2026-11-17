"""F11 step 8: `calibration_note.md` from the two reports (no clock: same reports, same text)."""

from __future__ import annotations

from whsizing.calibration.models import ActivityMetrics, FitReport, HoldoutReport, ThetaRow


def _pct(x: float | None) -> str:
    return "n/a" if x is None else f"{x:.1f} %"


def _theta_table(rows: list[ThetaRow]) -> list[str]:
    out = [
        "| Parameter | Prior | σ | Bounds | Fitted | Effective | Identified |",
        "|---|---|---|---|---|---|---|",
    ]
    for t in rows:
        eff = "" if t.effective is None else f"{t.effective:.3f}"
        out.append(
            f"| {t.name} | {t.prior:.3f} | {t.sigma:.3f} | {t.lo:g} to {t.hi:g} | "
            f"{t.fitted:.3f} | {eff} | {'yes' if t.identified else 'no'} |"
        )
    return out


def _metric_row(name: str, m: ActivityMetrics) -> str:
    return f"| {name} | {_pct(m.mape)} | {_pct(m.bias)} |"


def render_note(fit: FitReport, hold: HoldoutReport, site: str) -> str:
    """The calibration note: method, period, multipliers, hold-out errors, caveats."""
    months = sorted({*fit.months_fit, *fit.months_holdout})
    status = "ACCEPTED" if hold.accepted else "NOT ACCEPTED"
    lines = [
        f"# Calibration note: {site}",
        "",
        f"Calibrated on {fit.sites} site(s). Baseline scenario `{fit.scenario}` "
        f"(family `{fit.family}`), labor only. Acceptance: {status} "
        f"(hold-out MAPE on total hours {_pct(hold.total.mape)} and peak-month error "
        f"{hold.peak_month_error_pct:+.1f} %, target ≤ {hold.threshold_pct:.0f} % [P]).",
        "",
        "## Method",
        "",
        "Monthly hours per activity are predicted from the daily series with the catalog values "
        "(F6c, typ world). A productivity multiplier m per activity (bounds 0.5 to 2.0), the flow "
        "efficiency η (0.6 to 1.0) and PF&D (0.05 to 0.25) are fitted with "
        "`scipy.optimize.least_squares` (soft_l1, bounds) on "
        "Σ w_i (pred_i − actual_i)² + λ Σ ((θ_j − prior_j) / σ_j)², w_i proportional to the actual "
        "hours, λ = 1, priors = catalog typ with σ = half the catalog range. The fit uses the "
        "fit months only; the hold-out months are never used to fit.",
        "",
        "## Data",
        "",
        f"- Period: {months[0]} to {months[-1]} ({len(months)} months).",
        f"- Fit months ({len(fit.months_fit)}): {', '.join(fit.months_fit)}.",
        f"- Hold-out months ({len(fit.months_holdout)}): {', '.join(fit.months_holdout)}.",
        f"- Peak month: {fit.peak_month} ({fit.peak_definition}).",
        f"- Points in the fit: {fit.n_points}.",
    ]
    if fit.excluded_activities:
        skipped = ", ".join(fit.excluded_activities)
        lines.append(f"- Model activities without actuals (not compared): {skipped}.")
    for c in fit.client_activities:
        lines.append(
            f"- Client-specific activity `{c.name}` (not in the model): "
            f"{c.hours_per_order:.4f} h per order, fitted on the fit months."
        )
    lines += ["", "## Fitted parameters", "", *_theta_table(fit.theta), ""]
    lines += [
        "`Effective` = the multiplier at the basis PF&D (m × (1 + pfd_basis) / (1 + pfd)): the "
        "only combination the hours identify, and the one the catalog update uses.",
        "",
        "## Hold-out errors",
        "",
        "| Activity | MAPE | Bias |",
        "|---|---|---|",
        *(_metric_row(n, m) for n, m in hold.per_activity.items()),
        _metric_row("**total**", hold.total),
        "",
        f"- Peak month {hold.peak_month}: error {hold.peak_month_error_pct:+.1f} % "
        f"({'in' if hold.peak_in_holdout else 'NOT in'} the hold-out).",
    ]
    if hold.peak_lines_h_observed is not None:
        lines.append(
            f"- Peak lines/h: predicted {hold.peak_lines_h_pred:.0f}, observed "
            f"{hold.peak_lines_h_observed:.0f}, error {_pct(hold.peak_lines_h_error_pct)}."
        )
    else:
        lines.append(
            f"- Peak lines/h: predicted {hold.peak_lines_h_pred:.0f}; no observed peak given."
        )
    lines.append("- Per-activity errors are reported, not gated.")
    flags = [*fit.flags, *hold.flags]
    if flags:
        lines += ["", "## Flags and warnings", ""]
        lines += [f"- `{f.code}` ({f.severity}): {f.message}" for f in flags]
    lines += ["", "## Caveats", "", *_caveats(fit)]
    return "\n".join(lines) + "\n"


def _caveats(fit: FitReport) -> list[str]:
    out = [
        f"- Calibrated on {fit.sites} site(s): a single site can over-fit; the priors and bounds "
        "limit it. Catalog confidence is raised to M at most, after expert review.",
        "- η does not enter the monthly hours (it sets the pickers and the peak flow only): it "
        "stays at its prior.",
        "- Peak lines/h = design peak-hour lines / (growth factor × η): η stays at its prior, so "
        "this error compares the design day with the observed peak and does not move with the fit.",
        "- PF&D and the multipliers are confounded in the hours: the prior fixes the split, the "
        "effective multipliers are the identified values.",
        "- The model predicts the hours the workload needs; actuals include absence, idle time, "
        "overtime and unmodelled tasks, which the multipliers absorb.",
    ]
    if any(f.code == "I_TEMPS_COMBINED" for f in fit.flags):
        out.append(
            "- Temps are not separated in the actuals: hours are combined (core, temp, "
            "overtime); the model's temp hours are not back-tested."
        )
    return out

"""F2 DQ report: score [P], band, coverage metrics, JSON + readable HTML (Jinja2)."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, date, datetime, time
from pathlib import Path

import jinja2
import polars as pl

from whsizing.io.rules import history_months, local_dates
from whsizing.schemas.ingest import Band, DQReport, RuleResult
from whsizing.schemas.manifest import DatasetIngest

BLOCKING_POINTS, BLOCKING_CAP = 25, 50  # [P]
WARNING_POINTS, WARNING_CAP = 5, 25  # [P]
DIMS_POINTS = 20  # [P]
SHORT_HISTORY_POINTS = 10  # [P]
BAND_USABLE, BAND_CAVEATS = 80, 60  # [P]
HOUR_KNOWN_MIN_SHARE = 0.5  # F2 choice: below, order times are treated as absent
TEMPLATES = Path(__file__).with_name("templates")
DQ_JSON = "dq_report.json"

# Plain-language title and action per rule, for the non-technical reader.
RULE_TEXT: dict[str, tuple[str, str]] = {
    "REQ": ("Required values present", "Rows missing a required value are removed."),
    "R1": (
        "Order dates readable, not in the future and not implausibly early",
        "Lines without a usable date, or dated implausibly early, are removed.",
    ),
    "R2": ("Ordered products exist in the product list", "Kept, but without dimensions."),
    "R3": ("No zero quantities", "Lines with quantity 0 are removed."),
    "R4": ("Negative quantities", "Treated as returns."),
    "R5": ("No duplicated rows", "Exact duplicates are removed."),
    "R6": ("One line per product per order", "Repeated lines are added together."),
    "R7": ("Dimensions and weight known", "Counted; affects which equipment each product fits."),
    "R8": ("Dimensions and weight plausible", "Implausible values are cleared."),
    "R9": ("At least 3 months of orders", "Below this, the study cannot proceed."),
    "R10": ("At least 12 months of orders", "Seasonality is flagged as low confidence."),
    "R11": ("Quantities in units, not cases", "Please confirm the unit of the quantities."),
    "R12": ("Orders on every working day", "Days without orders: please review the calendar."),
    "R13": ("Unusually large orders or lines", "Listed for review; never removed."),
    "R14": ("Recent stock snapshot", "Old or missing stock: stock figures flagged low confidence."),
}
BAND_TEXT: dict[str, str] = {
    "usable": "The data can be used for the study as it is.",
    "usable with caveats": "The data can be used; the points below limit the confidence.",
    "remediation needed": "The data needs fixing before the study can be trusted.",
}


def band(score: float) -> Band:
    if score >= BAND_USABLE:
        return "usable"
    return "usable with caveats" if score >= BAND_CAVEATS else "remediation needed"


def dq_score(
    n_blocking: int, n_warnings: int, dims_coverage_lines: float, short_history: bool
) -> tuple[float, dict[str, float]]:
    """100 − 25·blocking (cap 50) − 5·warnings (cap 25) − 20·(1 − coverage) − 10·[< 12 months]."""
    parts = {
        "blocking": -min(BLOCKING_POINTS * n_blocking, BLOCKING_CAP),
        "warnings": -min(WARNING_POINTS * n_warnings, WARNING_CAP),
        "dims_coverage": -DIMS_POINTS * (1 - dims_coverage_lines),
        "short_history": -SHORT_HISTORY_POINTS * short_history,
    }
    return round(min(100.0, max(0.0, 100 + sum(parts.values()))), 2), parts


def coverage(frames: dict[str, pl.DataFrame], tz: str) -> dict[str, float]:
    """dims_coverage_lines (SKU share without order lines), order_ts_with_time_share,
    history_months, units_per_pallet_default_share."""
    lines, master = frames.get("order_lines"), frames.get("sku_master")
    cov: dict[str, float] = {"dims_coverage_lines": 0.0}
    if lines is not None and lines.height and "has_dims" in lines.columns:
        cov["dims_coverage_lines"] = float(lines["has_dims"].mean() or 0.0)  # pyright: ignore[reportArgumentType]
    elif master is not None and master.height:
        dims = ("length_mm", "width_mm", "height_mm", "weight_kg")
        cov["dims_coverage_lines"] = float(
            master.select(pl.all_horizontal(pl.col(dims).is_not_null()).mean()).item()
        )
    if lines is not None and lines.height:
        local = lines["order_ts"].dt.convert_time_zone(tz)
        cov["order_ts_with_time_share"] = float((local.dt.time() != time(0)).mean())  # pyright: ignore[reportArgumentType]
        d = local_dates(lines, tz)
        first, last = d.min(), d.max()
        if isinstance(first, date) and isinstance(last, date):
            cov["history_months"] = history_months(first, last)
    if master is not None and master.height:
        defaulted = pl.col("units_per_case").is_null() | pl.col("cases_per_pallet").is_null()
        cov["units_per_pallet_default_share"] = float(master.select(defaulted.mean()).item())
    return {k: round(v, 6) for k, v in cov.items()}


def build_dq_report(
    rules: list[RuleResult],
    frames: dict[str, pl.DataFrame],
    notes: Sequence[str] = (),
    timezone: str = "Europe/Paris",
) -> DQReport:
    cov = coverage(frames, timezone)
    r10 = next((r for r in rules if r.rule == "R10"), None)
    short = r10 is None or r10.severity != "ok"  # no order lines → history unknown → short
    n_blocking = sum(r.severity == "blocking" for r in rules)
    n_warnings = sum(r.severity == "warning" for r in rules)
    score, parts = dq_score(n_blocking, n_warnings, cov["dims_coverage_lines"], short)
    all_notes = list(notes)
    if cov.get("order_ts_with_time_share", 1.0) < HOUR_KNOWN_MIN_SHARE:
        all_notes.append(
            "Order lines carry a date but no time: the hour is unknown, so the intraday "
            "profile is flagged low confidence (L)."
        )
    return DQReport(
        created_at=datetime.now(UTC),
        score=score,
        band=band(score),
        score_breakdown={k: float(v) for k, v in parts.items()},
        coverage=cov,
        rules=rules,
        notes=all_notes,
        rows={name: df.height for name, df in frames.items()},
    )


def render_html(report: DQReport, datasets: Sequence[DatasetIngest] = ()) -> str:
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(TEMPLATES),
        autoescape=True,
        undefined=jinja2.StrictUndefined,
    )
    return env.get_template("dq_report.html.j2").render(
        report=report,
        datasets=datasets,
        rule_text=RULE_TEXT,
        band_text=BAND_TEXT[report.band],
        flagged=[r for r in report.rules if r.severity in ("blocking", "warning")],
    )


def write_dq_report(
    report: DQReport, out_dir: Path, datasets: Sequence[DatasetIngest] = ()
) -> tuple[Path, Path]:
    """`<out_dir>/dq/dq_report.json` and `.html`."""
    dq_dir = Path(out_dir) / "dq"
    dq_dir.mkdir(parents=True, exist_ok=True)
    json_path, html_path = dq_dir / DQ_JSON, dq_dir / "dq_report.html"
    json_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    html_path.write_text(render_html(report, datasets), encoding="utf-8")
    return json_path, html_path

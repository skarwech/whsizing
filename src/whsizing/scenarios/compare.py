"""F8 comparison table: one row per scenario, rankings at typ, TCO overlap note.

No automatic "recommended" label: the rankings are read at typical values and the note says
which scenarios cannot be told apart once their lo-hi TCO ranges are taken into account.
"""

from __future__ import annotations

from collections.abc import Mapping
from itertools import combinations

from whsizing.errors import WhsizingError
from whsizing.schemas import (
    AreaResult,
    Comparison,
    ComparisonRow,
    EligibilityResult,
    FinancialResult,
    LaborResult,
    QueueResult,
    Range,
    ScenarioDef,
    ScenarioResult,
    StorageResult,
)

RANKING_NOTE = "Ranking at typical values"
LOW_CONFIDENCE = "F_LOW_CONFIDENCE"  # flag code, with a `:<n>` suffix (I46)
EQUIPMENT_KEYS = ("pickers_peak", "gtp_stations", "ports", "robots")  # the row's headcounts


def tco_overlaps(tco: Mapping[str, Range]) -> list[tuple[str, str]]:
    """Pairs (a, b), a before b in `tco`'s order, whose [lo, hi] intervals intersect (closed
    intervals, so touching ranges overlap). Symmetric by construction; never (a, a)."""
    return [
        (a, b)
        for (a, ra), (b, rb) in combinations(tco.items(), 2)
        if ra.lo <= rb.hi and rb.lo <= ra.hi
    ]


def overlap_note(overlaps: list[tuple[str, str]]) -> str:
    """'Ranking at typical values', plus '; ranges overlap for scenarios X and Y' (pairs joined
    by '; ') only when some TCO ranges overlap (T8.6). F9 localises it from `overlaps`."""
    if not overlaps:
        return RANKING_NOTE
    pairs = "; ".join(f"{a} and {b}" for a, b in overlaps)
    return f"{RANKING_NOTE}; ranges overlap for scenarios {pairs}"


def compare(
    results: Mapping[str, ScenarioResult],
    finances: Mapping[str, FinancialResult],
    baseline_id: str | None = None,
) -> Comparison:
    """One row per entry of `results`, in its order (T8.2): a computed scenario needs its
    FinancialResult in `finances`, a not-computed one becomes a row with status "not_computed"
    and its reason. `ranking_tco` / `ranking_payback` sort the computed rows ascending at typ;
    a scenario without a payback (the baseline, or not reached within the horizon) is left out of
    `ranking_payback`. `baseline_id` is kept as given ("client_current" or a scenario id)."""
    rows = [_row(r, finances.get(sid)) for sid, r in results.items()]
    tco = {r.scenario_id: r.tco for r in rows if r.tco is not None}
    payback = {r.scenario_id: r.payback_years for r in rows if r.payback_years is not None}
    overlaps = tco_overlaps(tco)
    return Comparison(
        baseline_id=baseline_id,
        rows=rows,
        ranking_tco=sorted(tco, key=lambda sid: tco[sid].typ),
        ranking_payback=sorted(payback, key=lambda sid: payback[sid]),
        overlaps=overlaps,
        confidence_note=overlap_note(overlaps),
    )


def _row(r: ScenarioResult, fin: FinancialResult | None) -> ComparisonRow:
    s = r.scenario
    if r.status == "not_computed":
        return ComparisonRow(
            scenario_id=s.id,
            name=s.name,
            family=s.family,
            status="not_computed",
            status_reason=r.status_reason,
        )
    if fin is None:
        raise WhsizingError(f"compare: scenario {s.id} is computed but has no FinancialResult")
    return ComparisonRow(
        scenario_id=s.id,
        name=s.name,
        family=s.family,
        eligible_line_share=r.eligibility.share_lines,
        storage_area_m2=r.storage.total_area_m2,
        total_area_m2=r.area.total_m2,
        fit=r.area.fit,
        equipment={k: r.equipment[k] for k in EQUIPMENT_KEYS if k in r.equipment},
        fte_design_day=r.labor.total_heads,
        core_fte_year1=r.labor.core_fte[0],
        roster=r.labor.roster,
        capex=fin.capex_total,
        opex_year1=fin.opex_year1,
        tco=fin.tco,
        npv_vs_baseline=fin.npv_vs_baseline,
        payback_years=fin.payback_years,
        cost_per_line=fin.cost_per_line,
        n_warnings=sum(f.severity != "info" for f in r.flags),
        n_low_confidence_params=sum(
            int(f.value or 0) for f in r.flags if f.code.split(":")[0] == LOW_CONFIDENCE
        ),
    )


def not_computed_result(scenario: ScenarioDef, reason: str, building_m2: float) -> ScenarioResult:
    """Placeholder result of a scenario that raised SizingInfeasibleError (non-strict mode):
    status "not_computed" with `reason`, every quantity zero, no flags, `fit` False."""
    zero = Range(lo=0, typ=0, hi=0, unit="-")
    m2 = Range(lo=0, typ=0, hi=0, unit="m2")
    return ScenarioResult(
        scenario=scenario,
        eligibility=EligibilityResult(
            family=scenario.family,
            share_lines=0.0,
            share_stock_cube=0.0,
            share_skus=0.0,
            n_skus_eligible=0,
            n_skus_total=0,
        ),
        storage=StorageResult(classes=[], total_area_m2=m2, height_utilisation=0.0),
        equipment={},
        bottleneck="",
        labor=LaborResult(
            activities=[],
            total_hours=zero,
            total_heads=zero,
            roster=zero,
            annual_hours=[],
            core_fte=[],
            temp_hours=[],
            shifts=[],
        ),
        area=AreaResult(
            zones={},
            total_m2=m2,
            building_m2=building_m2,
            fit=False,
            utilisation=zero,
            deficit_m2=m2,
            docks_in_required=0.0,
            docks_out_required=0.0,
            icpe_volume_m3=0.0,
            icpe_regime=None,
        ),
        queue=QueueResult(resources=[]),
        flags=[],
        trace_path=f"scenarios/{scenario.id}/trace.jsonl",
        status="not_computed",
        status_reason=reason,
    )

"""F8a properties of the comparison: the TCO overlap relation is symmetric and irreflexive, the
note appears iff some ranges overlap (T8.6), every scenario is ranked and listed once (T8.2)."""

from __future__ import annotations

from itertools import combinations

from hypothesis import given
from hypothesis import strategies as st
from tests.fixtures import mock_financial, mock_result

from whsizing.scenarios import compare, overlap_note, tco_overlaps
from whsizing.schemas import Range

edge = st.floats(min_value=-1e9, max_value=1e9, allow_nan=False, allow_infinity=False)


@st.composite
def ranges(draw: st.DrawFn) -> dict[str, Range]:
    triples = draw(st.lists(st.tuples(edge, edge, edge), min_size=0, max_size=8))
    out: dict[str, Range] = {}
    for i, t in enumerate(triples):
        lo, typ, hi = sorted(t)
        out[f"S{i}"] = Range(lo=lo, typ=typ, hi=hi, unit="eur")
    return out


def intersect(a: Range, b: Range) -> bool:
    return max(a.lo, b.lo) <= min(a.hi, b.hi)


@given(ranges())
def test_T8_6_overlap_pairs_are_exactly_the_intersecting_distinct_pairs(
    tco: dict[str, Range],
) -> None:
    pairs = tco_overlaps(tco)
    expected = {frozenset(p) for p in combinations(tco, 2) if intersect(tco[p[0]], tco[p[1]])}
    assert {frozenset(p) for p in pairs} == expected
    assert len(pairs) == len(expected)  # each pair once
    assert all(a != b for a, b in pairs)  # never a scenario with itself


@given(ranges())
def test_T8_6_overlap_relation_is_symmetric_whatever_the_order(tco: dict[str, Range]) -> None:
    forward = {frozenset(p) for p in tco_overlaps(tco)}
    backward = {frozenset(p) for p in tco_overlaps(dict(reversed(tco.items())))}
    assert forward == backward


@given(ranges())
def test_T8_6_note_appears_iff_overlaps_and_never_pairs_a_scenario_with_itself(
    tco: dict[str, Range],
) -> None:
    pairs = tco_overlaps(tco)
    note = overlap_note(pairs)
    assert note.startswith("Ranking at typical values")
    assert ("ranges overlap for scenarios" in note) == bool(pairs)
    clauses = note.partition("ranges overlap for scenarios ")[2]
    listed = [c.split(" and ") for c in clauses.split("; ")] if pairs else []
    assert listed == [list(p) for p in pairs]
    assert all(a != b for a, b in listed)


@given(ranges())
def test_T8_2_every_scenario_once_ranked_by_typ_and_consistent_with_the_overlaps(
    tco: dict[str, Range],
) -> None:
    result, fin = mock_result(), mock_financial()
    results = {
        sid: result.model_copy(update={"scenario": result.scenario.model_copy(update={"id": sid})})
        for sid in tco
    }
    finances = {
        sid: fin.model_copy(update={"scenario_id": sid, "tco": r, "payback_years": None})
        for sid, r in tco.items()
    }
    cmp = compare(results, finances)
    assert [r.scenario_id for r in cmp.rows] == list(tco)
    assert sorted(cmp.ranking_tco) == sorted(tco)
    assert [tco[s].typ for s in cmp.ranking_tco] == sorted(r.typ for r in tco.values())
    assert cmp.ranking_payback == []
    assert cmp.overlaps == tco_overlaps(tco) and cmp.confidence_note == overlap_note(cmp.overlaps)

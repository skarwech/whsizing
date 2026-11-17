"""T9.5 prerequisite: the FR and EN formatters round-trip (format, then parse) for random
values, and the FR and EN report tables hold identical raw numbers that render to identical
numbers once parsed back."""

from __future__ import annotations

from datetime import date

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from tests.unit.test_f9_tables_support import private_run, report_data

from whsizing.report import iter_cells, render_cell
from whsizing.report.i18n import NNBSP, Lang, fmt_date, fmt_general, fmt_number, fmt_pct
from whsizing.schemas import Cell
from whsizing.schemas.run import RunOutput

SEPARATORS = {"fr": (NNBSP, ","), "en": (",", ".")}
values = st.floats(min_value=-1e9, max_value=1e9, allow_nan=False, allow_infinity=False)
langs = st.sampled_from(["fr", "en"])


def parse_number(text: str, lang: Lang) -> float:
    thousands, decimal = SEPARATORS[lang]
    assert "\0" not in text
    return float(text.replace(thousands, "").replace(decimal, "."))


def parse_cell(cell: Cell, text: str, lang: Lang) -> float:
    if cell.fmt == "pct":
        return parse_number(text.removesuffix("%").strip(" " + NNBSP), lang) / 100
    if cell.fmt == "bool":
        return float(text in ("Oui", "Yes"))
    return parse_number(text, lang)


@settings(max_examples=300, deadline=None)
@given(v=values, d=st.integers(0, 4), lang=langs)
def test_T9_5_prep_number_format_round_trips(v: float, d: int, lang: Lang) -> None:
    text = fmt_number(v, lang, d)
    back = parse_number(text, lang)
    assert abs(back - v) <= 0.5 * 10**-d + 1e-9 * abs(v)  # within the rounding of the format
    assert fmt_number(back, lang, d) == text  # and formatting the parsed value changes nothing


@settings(max_examples=300, deadline=None)
@given(v=values, d=st.integers(0, 4))
def test_T9_5_prep_fr_and_en_print_the_same_number(v: float, d: int) -> None:
    assert parse_number(fmt_number(v, "fr", d), "fr") == parse_number(fmt_number(v, "en", d), "en")


@settings(max_examples=200, deadline=None)
@given(v=st.floats(min_value=-50, max_value=50, allow_nan=False), lang=langs)
def test_T9_5_prep_percent_format_round_trips(v: float, lang: Lang) -> None:
    text = fmt_pct(v, lang, 1)
    assert text.endswith("%")
    back = parse_cell(Cell(value=v, fmt="pct"), text, lang)
    assert abs(back - v) <= 0.0005 + 1e-9


@settings(max_examples=200, deadline=None)
@given(v=st.floats(min_value=-1e7, max_value=1e7, allow_nan=False), lang=langs)
def test_T9_5_prep_general_format_keeps_six_significant_digits(v: float, lang: Lang) -> None:
    back = parse_number(fmt_general(v, lang), lang)
    assert abs(back - v) <= max(abs(v) * 1e-5, 1e-10) if v else back == 0


@settings(max_examples=200, deadline=None)
@given(d=st.dates(min_value=date(1990, 1, 1), max_value=date(2100, 12, 31)))
def test_T9_5_prep_dates_round_trip_in_both_languages(d: date) -> None:
    fr, en = fmt_date(d, "fr"), fmt_date(d, "en")
    day, month, year = fr.split("/")
    assert date(int(year), int(month), int(day)) == d == date.fromisoformat(en)
    assert fmt_date(en, "fr") == fr  # an ISO string formats like the date


@pytest.fixture(scope="module")
def run(tmp_path_factory: pytest.TempPathFactory) -> RunOutput:
    return private_run(tmp_path_factory, "f9a_formats")


def test_T9_5_prep_fr_and_en_tables_hold_identical_raw_numbers(run: RunOutput) -> None:
    fr, en = report_data(run, "fr"), report_data(run, "en")
    assert fr.lang == "fr" and en.lang == "en"
    # labels are i18n keys, so the two models are the same object graph: only rendering differs
    assert fr.tables == en.tables
    cells = [(w, c) for w, c in iter_cells(fr.tables) if isinstance(c.value, float)]
    assert len(cells) > 2000


def test_T9_5_prep_numbers_render_to_the_same_values_in_fr_and_en(run: RunOutput) -> None:
    data = report_data(run, "en")
    checked = 0
    for where, cell in iter_cells(data.tables):
        if not isinstance(cell.value, float) or cell.fmt in ("key", "text", "date"):
            continue
        fr = parse_cell(cell, render_cell(cell, "fr"), "fr")
        en = parse_cell(cell, render_cell(cell, "en"), "en")
        assert fr == pytest.approx(en, rel=1e-9, abs=1e-12), (where, cell)
        assert en == pytest.approx(
            cell.value, rel=1e-5, abs=0.51 if cell.fmt in ("int", "eur") else 0.051
        )
        checked += 1
    assert checked > 1500


def test_T9_5_prep_fr_text_uses_the_french_separators(run: RunOutput) -> None:
    data = report_data(run, "fr")
    cells = [c for _, c in iter_cells(data.tables) if c.fmt in ("int", "eur", "dec1")]
    fr = [render_cell(c, "fr") for c in cells]
    en = [render_cell(c, "en") for c in cells]
    assert any(NNBSP in t for t in fr)  # thousands
    assert any("," in t and "." not in t for t in fr)  # decimal comma, never a point
    assert not any("," in t and NNBSP in t for t in fr + en)  # the two never mix
    assert any("," in t and NNBSP not in t for t in en)  # EN: comma thousands

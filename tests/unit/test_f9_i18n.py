"""F9a i18n: the two YAML files hold the same keys and placeholders, `t` never raises and returns
the sentinel for a missing key, the number and date formats of FR and EN, every flag code of
the engine has a message, and every key the report tables use exists in both languages."""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

import pytest
import yaml
from tests.unit.test_f9_tables_support import private_run, report_data

from whsizing.report import iter_cells, render_cell, t, used_keys
from whsizing.report.i18n import (
    I18N_DIR,
    LANGS,
    NNBSP,
    flag_text,
    fmt_date,
    fmt_general,
    fmt_number,
    fmt_pct,
    has_key,
    texts,
)
from whsizing.schemas import Cell

SRC = Path(__file__).resolve().parents[2] / "src" / "whsizing"
PLACEHOLDER = re.compile(r"\{(\w+)\}")
FLAG_CODE = re.compile(r"\"(F_[A-Z_]+)")
NOT_REPORTED = {"F_CALIB_ERROR", "F_CLIENT_ACTIVITY"}  # F11 calibration flags: not in the report


def test_T9_5_i18n_files_hold_the_same_keys() -> None:
    fr, en = texts("fr"), texts("en")
    assert len(en) > 300
    assert set(fr) == set(en), sorted(set(fr) ^ set(en))
    raw = {lang: yaml.safe_load((I18N_DIR / f"{lang}.yaml").read_text("utf-8")) for lang in LANGS}
    assert all(isinstance(v, str) and v.strip() for d in raw.values() for v in d.values())


def test_T9_5_i18n_placeholders_match_in_both_languages() -> None:
    fr, en = texts("fr"), texts("en")
    bad = {
        k: (sorted(PLACEHOLDER.findall(fr[k])), sorted(PLACEHOLDER.findall(en[k])))
        for k in en
        if k != "methodology.formulas"
        and sorted(PLACEHOLDER.findall(fr[k])) != sorted(PLACEHOLDER.findall(en[k]))
    }
    assert bad == {}


def test_T9_5_missing_key_gives_the_sentinel_and_never_raises() -> None:
    assert t("no.such.key", "fr") == "{{ missing:no.such.key }}"
    assert t("no.such.key", "en", n=3) == "{{ missing:no.such.key }}"
    assert not has_key("no.such.key", "en")
    # a text whose placeholder is not given is as good as missing; extra arguments are ignored
    assert t("row.year", "en") == "{{ missing:row.year }}"
    assert t("row.year", "en", n=3) == "Year 3"
    assert t("row.year", "fr", n=3, extra="x") == "Année 3"
    # the formulas hold literal braces: with no arguments the text is returned as it is
    assert "{a,t}" in t("methodology.formulas", "en")


def test_T9_5_fr_number_format_uses_narrow_no_break_space_and_comma() -> None:
    assert fmt_number(1234567.891, "fr", 2) == f"1{NNBSP}234{NNBSP}567,89"
    assert fmt_number(1234567.891, "fr", 2).count(" ") == 2
    assert fmt_number(-0.4, "fr", 0) == "0"  # never "-0"
    assert fmt_number(999.5, "fr", 0) == "1 000" or fmt_number(999.5, "fr", 0) == "1000"
    assert fmt_pct(0.1234, "fr") == f"12,3{NNBSP}%"
    assert fmt_general(0.0525, "fr") == "0,0525"
    assert fmt_general(1607, "fr") == f"1{NNBSP}607"


def test_T9_5_en_number_format_uses_comma_thousands_and_point() -> None:
    assert fmt_number(1234567.891, "en", 2) == "1,234,567.89"
    assert fmt_number(-1234.5, "en", 1) == "-1,234.5"
    assert fmt_pct(0.1234, "en") == "12.3 %"
    assert fmt_general(0.0525, "en") == "0.0525"
    assert fmt_general(1e-7, "en") == "0.0000001"


def test_T9_5_dates_are_dd_mm_yyyy_in_fr_and_iso_in_en() -> None:
    assert fmt_date(date(2026, 11, 9), "fr") == "09/11/2026"
    assert fmt_date("2026-11-09", "fr") == "09/11/2026"
    assert fmt_date(date(2026, 11, 9), "en") == "2026-11-09"


def test_T9_5_render_cell_formats_by_fmt() -> None:
    n = 1234.5678
    assert render_cell(Cell(value=n, fmt="int"), "en") == "1,235"
    assert render_cell(Cell(value=n, fmt="dec1"), "fr") == f"1{NNBSP}234,6"
    assert render_cell(Cell(value=0.5, fmt="pct"), "en") == "50.0 %"
    assert render_cell(Cell(value=1.0, fmt="bool"), "fr") == "Oui"
    assert render_cell(Cell(value=0.0, fmt="bool"), "en") == "No"
    assert render_cell(Cell(value="2026-01-31", fmt="date"), "fr") == "31/01/2026"
    assert render_cell(Cell(value="row.year", fmt="key", args={"n": 3.0}), "fr") == "Année 3"
    assert render_cell(Cell(value="row.year", fmt="key"), "fr") == "{{ missing:row.year }}"
    assert render_cell(Cell(), "fr") == ""


def test_T9_5_every_flag_code_of_the_engine_has_a_message_in_both_languages() -> None:
    codes: set[str] = set()
    for sub in ("engine", "design", "catalog", "finance", "scenarios", "schemas", "io"):
        for path in (SRC / sub).rglob("*.py"):
            codes |= set(FLAG_CODE.findall(path.read_text(encoding="utf-8")))
    codes |= {"F_AMENITIES_EXTERNAL"}  # the schema names it, the engine never raises it (I27)
    codes -= NOT_REPORTED
    assert {"F_NO_FIT", "F_UNSTABLE", "F_RATIO_DRIFT", "F_DEFAULT_UPP", "F_LOW_CONFIDENCE"} <= codes
    missing = [(c, lang) for c in sorted(codes) for lang in LANGS if not has_key(f"flag.{c}", lang)]
    assert missing == []


@pytest.fixture(scope="module")
def run(tmp_path_factory: pytest.TempPathFactory):
    return private_run(tmp_path_factory, "f9a_i18n")


def test_T9_5_every_key_the_tables_use_exists_in_both_languages(run) -> None:
    data = report_data(run)
    keys = used_keys(data.tables)
    assert len(keys) > 250
    for lang in LANGS:
        assert [k for k in keys if not has_key(k, lang)] == []
        rendered = [render_cell(c, lang) for _, c in iter_cells(data.tables) if c.fmt == "key"]
        assert not any("{{ missing" in r for r in rendered)


def test_T9_5_an_unsupported_language_is_a_config_error_not_a_file_error() -> None:
    from whsizing.errors import ConfigError

    with pytest.raises(ConfigError, match="unsupported language 'de'"):
        t("row.fit", "de")  # pyright: ignore[reportArgumentType]
    with pytest.raises(ConfigError):
        texts("de")  # pyright: ignore[reportArgumentType]


# ------------------------------------------------------------------ R7: flags and formulas
FLAG_CODE_TEXT = re.compile(r"\bF_[A-Z_]+")


def raised_flags(data, sid: str) -> list[str]:
    return [f.code for f in data.run.results[sid].flags if f.severity != "info"]


@pytest.mark.parametrize("lang", LANGS)
def test_R7_3_flag_codes_of_the_generated_limitations_are_said_as_their_messages(run, lang) -> None:
    data = report_data(run, lang)
    rows = {r.key: r.label for b in data.tables["methodology"].blocks for r in b.rows}
    checked = 0
    for sid in data.run.results:
        codes = raised_flags(data, sid)
        if not codes:
            continue
        text = render_cell(rows[f"limit.gen.flags.{sid}"], lang)
        assert not FLAG_CODE_TEXT.search(text), text  # no raw code, in French or in English
        assert "{{ missing" not in text
        for code in codes:
            assert flag_text(code, lang) in text, (code, text)
        checked += 1
    assert checked >= 2  # the example scenarios raise flags: the test is not vacuous


def test_R7_3_a_flag_message_carries_its_detail_and_drops_a_numeric_tail() -> None:
    assert flag_text("F_UNSTABLE:packing", "en") == t("flag.F_UNSTABLE", "en", detail="packing")
    assert "(packing)" in flag_text("F_UNSTABLE:packing", "en")
    assert "(packing)" in flag_text("F_UNSTABLE:packing", "fr")
    assert flag_text("F_LOW_CONFIDENCE:3", "fr") == t("flag.F_LOW_CONFIDENCE", "fr")  # a value
    assert flag_text("F_NO_FIT", "en") != flag_text("F_NO_FIT", "fr")
    assert flag_text("F_NOT_A_FLAG", "fr").startswith("{{ missing:")  # IC8 sees it


def test_R7_3_the_limitation_table_keeps_the_codes_so_both_languages_hold_the_same_cells(
    run,
) -> None:
    en, fr = report_data(run, "en"), report_data(run, "fr")
    assert en.tables["methodology"] == fr.tables["methodology"]  # T9.5: labels are keys


def test_R7_3_the_french_formulas_are_a_translation_line_for_line() -> None:
    en, fr = texts("en")["methodology.formulas"], texts("fr")["methodology.formulas"]
    assert fr != en
    assert len(fr.splitlines()) == len(en.splitlines())  # the Excel sheet writes one row per line
    for symbol in ("Σ", "ceil(", "floor(", "max(", "exp(", "λ", "η_flow", "{a,t}", "Δcf_t"):
        assert fr.count(symbol) == en.count(symbol), symbol  # the mathematics is the same
    headings = lambda text: [ln for ln in text.splitlines() if ln.startswith("#")]  # noqa: E731
    assert len(headings(fr)) == len(headings(en)) == 8
    assert all(f != e for f, e in zip(headings(fr), headings(en), strict=True) if "(F7)" not in f)
    # prose that was English in the French text: words of the English text only
    for word in (
        "operating day",
        "trailing window",
        "building works",
        "hold-out",
        "Erlang-B recursion",
    ):
        assert word in en and word not in fr, word
    for word in ("jour ouvré", "fenêtre glissante", "travaux du bâtiment", "validation"):
        assert word in fr, word

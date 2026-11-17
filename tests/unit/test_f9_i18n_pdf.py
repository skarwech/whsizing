"""F9c i18n: every text key the PDF templates and generated text ask for exists in both
languages (IC8 only finds a missing key once a report is rendered), and the PDF texts have the
same placeholders in FR and EN."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from whsizing.report.i18n import LANGS, PLACEHOLDER, has_key, texts

REPORT = Path(__file__).resolve().parents[2] / "src" / "whsizing" / "report"
KEY = re.compile(r"""\bt\(\s*["']([a-z0-9_.]+)["']""")
FSTRING_KEY = re.compile(r"""\bt\(\s*f["']([a-z0-9_.]+)\{""")


def literal_keys() -> dict[str, set[str]]:
    """file → the i18n keys written as literals in `t("...")` calls of the PDF code, templates."""
    files = [REPORT / "pdf.py", REPORT / "pdf_text.py", REPORT / "pdf_view.py"]
    files += sorted((REPORT / "templates").rglob("*.j2"))
    return {
        f.name: set(KEY.findall(f.read_text(encoding="utf-8")))
        for f in files
        if f.name != "stub.html.j2"
    }


def test_F9c_i18n_every_key_of_the_pdf_exists_in_both_languages() -> None:
    found = literal_keys()
    assert sum(len(v) for v in found.values()) > 25  # the scan finds the calls
    missing = {
        (name, key, lang)
        for name, keys in found.items()
        for key in keys
        for lang in LANGS
        if not has_key(key, lang)
    }
    assert missing == set()


def test_F9c_i18n_the_pdf_section_titles_and_family_texts_exist() -> None:
    from whsizing.report.pdf import SECTIONS

    for lang in LANGS:
        for _, key, _ in SECTIONS:
            assert has_key(key, lang), key
        for family in ("manual_p2p", "amr_gtp", "cube_asrs"):
            assert has_key(f"family.{family}.name", lang) and has_key(
                f"family.{family}.description", lang
            )


@pytest.mark.parametrize("prefix", ["pdf.", "msg."])
def test_F9c_i18n_pdf_texts_have_the_same_placeholders_in_both_languages(prefix: str) -> None:
    fr, en = texts("fr"), texts("en")
    keys = [k for k in en if k.startswith(prefix)]
    assert keys
    for k in keys:
        assert sorted(PLACEHOLDER.findall(fr[k])) == sorted(PLACEHOLDER.findall(en[k])), k

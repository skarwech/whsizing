"""F10b app: static properties (T10.4). The app makes no network call and sends no telemetry,
the Streamlit config says so, the justfile starts the app, and every text the app asks for exists
in French and English (the banner comes from the report package's i18n)."""

from __future__ import annotations

import ast
import re
import tomllib
from pathlib import Path

import pytest

from whsizing.app import strings
from whsizing.app.strings import SECTIONS, UI, tr
from whsizing.report import LANGS, t
from whsizing.report.i18n import MISSING_PREFIX

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "src" / "whsizing" / "app"
SOURCES = sorted(APP.rglob("*.py"))
NETWORK_MODULES = {
    "requests", "urllib", "urllib3", "http", "httpx", "aiohttp", "socket", "ssl", "ftplib",
    "smtplib", "telnetlib", "websocket", "websockets", "xmlrpc", "webbrowser",
}  # fmt: skip


def imported_modules(path: Path) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            found |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found.add(node.module.split(".")[0])
    return found


def test_T10_4_app_has_the_home_page_and_six_numbered_pages() -> None:
    assert (APP / "Home.py").is_file()
    pages = sorted(p.name for p in (APP / "pages").glob("*.py"))
    assert [p.split("_")[0] for p in pages] == ["1", "2", "3", "4", "5", "6"]
    assert "6_Results.py" in pages


def test_T10_4_app_sources_import_no_network_module() -> None:
    assert SOURCES  # the walk found the package
    for path in SOURCES:
        bad = imported_modules(path) & NETWORK_MODULES
        assert not bad, f"{path.relative_to(ROOT)} imports {sorted(bad)}"


def test_T10_4_app_sources_open_no_url_and_call_no_remote_api() -> None:
    for path in SOURCES:
        text = path.read_text(encoding="utf-8")
        assert not re.search(r"https?://", text), f"{path.name}: a URL in the source"
        assert "urlopen" not in text and "requests." not in text


def test_T10_4_streamlit_config_turns_telemetry_off_and_allows_1_gb_uploads() -> None:
    config = tomllib.loads((ROOT / ".streamlit" / "config.toml").read_text(encoding="utf-8"))
    assert config["browser"]["gatherUsageStats"] is False
    assert config["server"]["maxUploadSize"] == 1024
    assert config["server"]["address"] == "127.0.0.1"  # no authentication: loopback only


def test_T10_4_justfile_has_an_app_recipe_that_starts_the_home_page() -> None:
    lines = (ROOT / "justfile").read_text(encoding="utf-8").splitlines()
    assert "app:" in lines
    assert "    uv run streamlit run src/whsizing/app/Home.py --server.address 127.0.0.1" in lines


def test_T10_4_app_imports_no_numeric_library_for_its_own_computations() -> None:
    """No business logic in the UI: what the pages show comes from library calls (report tables,
    cached loaders, CLI commands), so no page or helper needs numpy or scipy."""
    for path in SOURCES:
        assert not imported_modules(path) & {"scipy", "numpy_financial", "numpy"}, path.name


def used_keys() -> set[str]:
    keys: set[str] = set()
    for path in SOURCES:
        text = path.read_text(encoding="utf-8")
        keys |= set(re.findall(r"""\btr\(\s*f?["']([\w.]+)["']""", text))
        keys |= set(re.findall(r"""setup\(\s*["']([\w.]+)["']""", text))
    keys |= {f"dd.{n}" for n in ("lines", "orders", "units", "cube_m3", "peak_hour_lines")}
    keys |= {f"dd.{n}" for n in ("parcels", "pallets_out", "stock_cube_m3")}
    keys |= set(strings_used_by_name())
    return {k for k in keys if "{" not in k and k != "leaf_"}  # "leaf_" + kind: listed apart


def strings_used_by_name() -> list[str]:
    """Keys passed as variables: the mapping headers and the drill-down leaf kinds."""
    from whsizing.app.ingest_ui import MAP_HEADERS

    return [*MAP_HEADERS, "leaf_param", "leaf_dataset", "leaf_unresolved", "leaf_cycle"]


def test_T10_4_every_text_the_app_asks_for_is_defined_in_both_languages() -> None:
    missing = sorted(used_keys() - set(UI))
    assert missing == []
    for key, (french, english) in UI.items():
        assert french.strip() and english.strip(), key
        # the same placeholders in both languages
        assert set(re.findall(r"\{(\w+)", french)) == set(re.findall(r"\{(\w+)", english)), key
    for group, (french, english) in SECTIONS.items():
        assert french and english, group


def test_T10_4_tr_fills_placeholders_and_switches_language() -> None:
    assert tr("upload.add_to_run", "en", run="R1") == "Add to run R1"
    assert tr("upload.add_to_run", "fr", run="R1") == "Ajouter au run R1"
    assert tr("home.title", "fr") != tr("home.title", "en")
    assert strings.section_title("operations", "fr") == "Exploitation"
    assert strings.section_title("unknown", "en") == "unknown"
    with pytest.raises(KeyError):
        tr("no.such.key", "en")


@pytest.mark.parametrize("lang", LANGS)
def test_T10_4_banner_text_comes_from_the_report_i18n(lang: str) -> None:
    text = t("banner.indicative", lang)  # type: ignore[arg-type]
    assert MISSING_PREFIX not in text and len(text) > 20
    assert t("banner.indicative", "fr") != t("banner.indicative", "en")

"""F10b app: static properties (T10.4). The app makes no network call and sends no telemetry,
the Streamlit config says so, the justfile starts the app, and every text the app asks for exists
in French and English (the banner comes from the report package's i18n)."""

from __future__ import annotations

import ast
import re
import shutil
import subprocess
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


def test_T10_4_streamlit_config_turns_telemetry_off_and_only_the_full_app_allows_1_gb_uploads() -> (
    None
):
    """Streamlit serves its upload route whether or not a page has an uploader, and keeps what a
    client sends in memory: the shared config (read by the hosted demo, which takes no upload)
    sets the cap to 0, which refuses every non-empty body (a cap of 1 kept 300 requests of 0.9 MB,
    +283 MB; an empty upload sent in chunks is still recorded, about 4 KB each),
    and `just app` (the full app, spec: 1024 MB) raises it."""
    config = tomllib.loads((ROOT / ".streamlit" / "config.toml").read_text(encoding="utf-8"))
    assert config["browser"]["gatherUsageStats"] is False
    assert config["server"]["maxUploadSize"] == 0
    justfile = (ROOT / "justfile").read_text(encoding="utf-8")
    app_recipe = next(ln for ln in justfile.splitlines() if "streamlit run src/whsizing" in ln)
    assert "--server.maxUploadSize 1024" in app_recipe


def test_T10_4_loopback_is_enforced_by_the_commands_and_the_app_not_by_the_shared_config() -> None:
    """`.streamlit/config.toml` is read by every way of serving the app, the platform that hosts
    the public demo included, which must reach it: no `address` there. The full app has no
    authentication, so `just app` binds loopback and the app refuses any other address."""
    config = tomllib.loads((ROOT / ".streamlit" / "config.toml").read_text(encoding="utf-8"))
    assert "address" not in config["server"]
    justfile = (ROOT / "justfile").read_text(encoding="utf-8")
    assert "streamlit run src/whsizing/app/Home.py --server.address 127.0.0.1" in justfile
    assert "streamlit run streamlit_app.py --server.address 127.0.0.1" in justfile


def test_T10_4_justfile_has_an_app_recipe_that_starts_the_home_page() -> None:
    lines = (ROOT / "justfile").read_text(encoding="utf-8").splitlines()
    assert "app:" in lines
    assert any(
        ln.startswith(
            "    uv run streamlit run src/whsizing/app/Home.py --server.address 127.0.0.1"
        )
        for ln in lines
    )


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


# ------------------------------------------------------------------------- hosted demo files
def test_T10_4_packages_txt_lists_the_debian_packages_weasyprint_needs() -> None:
    """Streamlit Community Cloud installs `packages.txt` with apt before the app starts, on Debian
    11 ("bullseye", the package list its documentation points to). An unknown name aborts the
    whole apt step and the deployment, so each line must be a package that exists there, and the
    Pango packages WeasyPrint needs must be there, or the PDF report cannot be built on the host.
    `libharfbuzz-subset0` is the one the WeasyPrint documentation also lists: it does not exist on
    Debian 11 (it appears with Debian 12) and WeasyPrint 70 loads that library only if present
    (`allow_fail=True`, a DeprecationWarning otherwise: fontTools subsets the fonts). The image
    and the CI runner, newer systems, install it."""
    lines = (ROOT / "packages.txt").read_text(encoding="utf-8").split()
    assert lines and len(set(lines)) == len(lines)
    assert all(re.fullmatch(r"[a-z0-9][a-z0-9+.-]+", name) for name in lines), lines
    assert {"libpango-1.0-0", "libpangoft2-1.0-0"} <= set(lines)
    assert "libharfbuzz-subset0" not in lines  # not in Debian 11: it would break the first deploy
    assert any(name.startswith("fonts-") for name in lines)  # a PDF needs at least one font
    assert "tzdata" in lines  # ingestion checks the site's time zone with `ZoneInfo`
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    shared = {"libpango-1.0-0", "libpangoft2-1.0-0", "fonts-liberation"}
    assert all(name in dockerfile.split() for name in shared)  # the image installs them as well


def test_T10_4_the_ci_installs_the_pango_and_font_packages_the_delivered_app_has() -> None:
    """The report CSS asks for Liberation Sans first: a runner without it would render the PDFs
    (and test them) with the DejaVu fallback, which is not what the image and the host deliver."""
    steps = [
        line
        for line in (ROOT / ".github" / "workflows" / "ci.yml").read_text("utf-8").splitlines()
        if "apt-get install" in line
    ]
    assert len(steps) == 2  # the test job and the bench job
    needed = {"libpango-1.0-0", "libpangoft2-1.0-0", "libharfbuzz-subset0", "fonts-liberation"}
    for step in steps:
        assert needed <= set(step.split()), step


def test_T10_4_streamlit_is_a_default_dependency_group_of_the_lock_the_host_reads() -> None:
    """Community Cloud reads `uv.lock` first: a plain `uv sync` has to install Streamlit, so it is
    in a default dependency group (the optional extra is for pip)."""
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert "streamlit" in project["dependency-groups"]["app"]
    assert "app" in project["tool"]["uv"]["default-groups"]
    assert "streamlit" in project["project"]["optional-dependencies"]["ui"]
    lock = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))
    ours = next(p for p in lock["package"] if p["name"] == project["project"]["name"])
    assert {"name": "streamlit"} in ours["dev-dependencies"]["app"]  # the group, not the extra


@pytest.mark.skipif(shutil.which("uv") is None, reason="uv not installed")
def test_T10_4_uv_lock_is_current() -> None:
    """The host installs exactly what the lock says: a lock that no longer matches
    `pyproject.toml` would be re-resolved there, or refused."""
    done = subprocess.run(
        ["uv", "lock", "--check"], cwd=ROOT, capture_output=True, text=True, timeout=300
    )
    assert done.returncode == 0, done.stdout[-1500:] + done.stderr[-1500:]

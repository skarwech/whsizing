"""F10b public demo: what a visitor may size, and what the server tells them (no Streamlit).

An anonymous visitor shares one process, and the commands run one at a time and cannot be
interrupted: plain widgets must not be able to ask the engine for minutes of work or gigabytes.
`whsizing.app.demo_limits` bounds the inputs that did (measured in the security review of the demo:
a 320-year horizon, 30 scenarios, a lifted `engine.max_equipment_count`, overrides far outside the
catalog). The AppTest side is in tests/e2e/test_f10_app_demo.py.
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import yaml

from whsizing.app import calls, demo, demo_limits, loaders
from whsizing.app.calls import BUSY_CODE, CliError
from whsizing.app.demo_limits import MAX_HORIZON_YEARS, MAX_SCENARIOS, limit_problems, scrub
from whsizing.app.strings import UI, tr
from whsizing.catalog import Catalog, load_catalog

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def catalog() -> Catalog:
    return load_catalog(ROOT / "catalog")


@pytest.fixture
def public(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(demo.DEMO_ENV, "1")


def keys(problems: list[demo_limits.Problem]) -> list[str]:
    return [key for key, _ in problems]


# ------------------------------------------------------------------------------ the limits
def test_the_demos_own_basis_and_scenarios_are_within_every_limit(
    public: None, catalog: Catalog
) -> None:
    basis = yaml.safe_load((ROOT / demo.BASIS).read_text(encoding="utf-8"))
    scenarios = yaml.safe_load((ROOT / demo.SCENARIOS).read_text(encoding="utf-8"))
    assert limit_problems(basis, scenarios, catalog) == []


def test_the_full_app_has_no_limits(monkeypatch: pytest.MonkeyPatch, catalog: Catalog) -> None:
    monkeypatch.delenv(demo.DEMO_ENV, raising=False)
    absurd = {
        "projection": {"horizon_years": 1000},
        "finance": {"horizon_years": 1000},
        "overrides": {"engine.max_equipment_count": 10**12, "labor.packing_S": 0.000055},
    }
    many = {"scenarios": [{"id": f"S{i}", "family": "manual_p2p"} for i in range(30)]}
    assert limit_problems(absurd, many, catalog) == []


@pytest.mark.parametrize("section", ["projection", "finance"])
def test_a_horizon_over_the_limit_is_refused_at_the_limit_it_is_not(
    public: None, catalog: Catalog, section: str
) -> None:
    at_limit = {section: {"horizon_years": MAX_HORIZON_YEARS}}
    assert limit_problems(at_limit, {}, catalog) == []
    over = {section: {"horizon_years": MAX_HORIZON_YEARS + 1}}
    assert limit_problems(over, {}, catalog) == [
        ("demo.limit.horizon", {"name": f"{section}.horizon_years", "max": MAX_HORIZON_YEARS})
    ]


def test_scenarios_over_the_limit_are_refused(public: None, catalog: Catalog) -> None:
    def cards(n: int) -> dict[str, Any]:
        return {"scenarios": [{"id": f"S{i}", "family": "manual_p2p"} for i in range(n)]}

    assert limit_problems({}, cards(MAX_SCENARIOS), catalog) == []
    assert limit_problems({}, cards(MAX_SCENARIOS + 1), catalog) == [
        ("demo.limit.scenarios", {"max": MAX_SCENARIOS})
    ]


def test_a_constant_cannot_be_overridden_least_of_all_the_guard_against_endless_queues(
    public: None, catalog: Catalog
) -> None:
    """`engine.max_equipment_count` stops a queue model that needs millions of stations; lifted, a
    visitor made the engine loop for a quarter of an hour on 2.8 million packing stations."""
    assert "engine.max_equipment_count" in catalog.constants
    basis = {"overrides": {"engine.max_equipment_count": 10**12}}
    assert limit_problems(basis, {}, catalog) == [
        ("demo.limit.constant", {"id": "engine.max_equipment_count"})
    ]


def test_a_parameter_stays_inside_the_catalog_range_in_the_basis_and_in_a_scenario(
    public: None, catalog: Catalog
) -> None:
    param = catalog.params["labor.packing_S"]  # 40..70 orders/h in the catalog
    inside = {"overrides": {"labor.packing_S": param.typ}}
    assert limit_problems(inside, {}, catalog) == []
    edges = {"overrides": {"labor.packing_S": param.min}}
    assert limit_problems(edges, {}, catalog) == []  # the bounds themselves are the catalog's
    for value in (0.000055, param.min - 1, param.max + 1):  # the first: the visitor's 1000x
        basis = {"overrides": {"labor.packing_S": value}}
        scenarios = {"scenarios": [{"id": "S0", "overrides": {"labor.packing_S": value}}]}
        wanted = [("demo.limit.range", {"id": "labor.packing_S", "lo": param.min, "hi": param.max})]
        assert limit_problems(basis, {}, catalog) == wanted
        assert limit_problems({}, scenarios, catalog) == wanted
        assert limit_problems(basis, scenarios, catalog) == wanted  # reported once, not twice


@pytest.mark.parametrize("text", ["0.000055", " 0.000055 ", "5.5e-5", "1e-5", "-1", "nan", "inf"])
def test_a_number_typed_as_text_is_checked_like_a_number(
    public: None, catalog: Catalog, text: str
) -> None:
    """pydantic reads `overrides: dict[str, float]` from text too ("1e-5" is text for PyYAML), so
    a quoted number must not slip past the range of the catalog."""
    param = catalog.params["labor.packing_S"]
    wanted = [("demo.limit.range", {"id": "labor.packing_S", "lo": param.min, "hi": param.max})]
    basis = {"overrides": {"labor.packing_S": text}}
    scenarios = {"scenarios": [{"id": "S0", "overrides": {"labor.packing_S": text}}]}
    assert limit_problems(basis, {}, catalog) == wanted
    assert limit_problems({}, scenarios, catalog) == wanted


@pytest.mark.parametrize("text", ["55", " 55 ", "5.5e1", "4e1"])  # the last is the lower bound
def test_a_number_typed_as_text_inside_the_range_is_allowed(
    public: None, catalog: Catalog, text: str
) -> None:
    overrides = {"labor.packing_S": text}
    scenarios = {"scenarios": [{"id": "S0", "overrides": overrides}]}
    assert limit_problems({"overrides": overrides}, scenarios, catalog) == []


@pytest.mark.parametrize(("text", "refused"), [("21", True), ("1e3", True), ("20", False)])
def test_a_horizon_typed_as_text_is_checked_like_a_number(
    public: None, catalog: Catalog, text: str, refused: bool
) -> None:
    basis = {"projection": {"horizon_years": text}, "finance": {"horizon_years": text}}
    assert keys(limit_problems(basis, {}, catalog)) == (
        ["demo.limit.horizon"] * 2 if refused else []
    )


def test_what_the_library_reports_itself_is_left_to_it(public: None, catalog: Catalog) -> None:
    """An unknown parameter id and a basis-level key are the library's to judge (ConfigError with
    a hint), and values that are no numbers are the schema's: the demo only adds its limits."""
    junk: dict[str, Any] = {
        "projection": {"horizon_years": "many"},
        "finance": {"horizon_years": True},
        "overrides": {"no.such.param": 5.0, "stock_growth_rate": 99.0, "labor.packing_S": "fast"},
    }
    assert limit_problems(junk, {"scenarios": "none", "baseline": None}, catalog) == []
    assert (
        limit_problems({"projection": 3, "overrides": [1]}, {"scenarios": [7, None]}, catalog) == []
    )


def test_every_limit_has_its_text_in_both_languages(public: None, catalog: Catalog) -> None:
    basis = {
        "projection": {"horizon_years": 99},
        "overrides": {"engine.max_equipment_count": 1, "labor.packing_S": 1.0},
    }
    problems = limit_problems(basis, {"scenarios": [{"id": f"S{i}"} for i in range(9)]}, catalog)
    assert sorted(keys(problems)) == [
        "demo.limit.constant",
        "demo.limit.horizon",
        "demo.limit.range",
        "demo.limit.scenarios",
    ]
    for key, values in problems:
        assert key in UI
        for lang in ("fr", "en"):
            text = tr(key, lang, **values)  # type: ignore[arg-type]  # every placeholder is given
            assert text.startswith("Démo publique" if lang == "fr" else "Public demo")
            assert "{" not in text


# --------------------------------------------------------------------- what the server tells
def test_the_folders_of_the_server_are_hidden_in_the_public_demo_only(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    runs = tmp_path / "var" / "runs"
    work = tmp_path / "var" / "work"
    runs.mkdir(parents=True)
    work.mkdir()
    monkeypatch.setenv("WHSIZING_RUNS", str(runs))
    monkeypatch.setenv(demo.WORK_ENV, str(work))
    message = f"{runs}/2026-11-17T10-00-00_abc: no scenario computed; data in {work}/data-1/csv_en"
    monkeypatch.delenv(demo.DEMO_ENV, raising=False)
    assert scrub(message) == message  # the full app shows the user their own paths
    monkeypatch.setenv(demo.DEMO_ENV, "1")
    hidden = scrub(message)
    assert (
        hidden
        == "<runs>/2026-11-17T10-00-00_abc: no scenario computed; data in <work>/data-1/csv_en"
    )
    assert str(tmp_path) not in hidden


def test_the_resolved_spelling_of_a_folder_is_hidden_too(
    public: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The commands print `run.resolve()`: on macOS `/var/...` is `/private/var/...`."""
    real = tmp_path / "real" / "runs"
    real.mkdir(parents=True)
    link = tmp_path / "link"
    link.symlink_to(tmp_path / "real")
    monkeypatch.setenv("WHSIZING_RUNS", str(link / "runs"))  # given through a symlink
    assert scrub(f"{real.resolve()}/x") == "<runs>/x"
    assert scrub(f"{link}/runs/x") == "<runs>/x"


def test_a_relative_folder_name_is_hidden_through_its_resolved_path_not_as_a_word(
    public: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """WHSIZING_RUNS=runs must not turn "runs are immutable" into "<runs> are immutable": the
    commands print the resolved folder, which is what is replaced."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("WHSIZING_RUNS", "runs")
    (tmp_path / "runs").mkdir()
    assert scrub("already sized and runs are immutable") == "already sized and runs are immutable"
    assert scrub(f"{(tmp_path / 'runs').resolve()}/x: not sized") == "<runs>/x: not sized"


def test_a_short_folder_name_is_never_replaced_it_would_garble_the_text(
    public: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("WHSIZING_RUNS", "/")
    monkeypatch.setenv(demo.WORK_ENV, "/a")
    assert scrub("exit 4: /a/b and /x/y") == "exit 4: /a/b and /x/y"


# ------------------------------------------------------------- a command that waits too long
def test_a_command_behind_a_long_one_gives_up_with_a_busy_error_and_the_next_one_runs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Streamlit cannot interrupt a command, so without a time limit one visitor's long command
    would hang every other visitor for as long."""
    monkeypatch.setattr(calls, "WAIT_S", 0.2)
    started, release = threading.Event(), threading.Event()

    def long_command() -> None:
        started.set()
        release.wait(5)

    holder = threading.Thread(target=lambda: calls.call(long_command))
    holder.start()
    try:
        assert started.wait(5)
        began = time.perf_counter()
        with pytest.raises(CliError) as busy:
            calls.call(lambda: None)
        assert busy.value.code == BUSY_CODE
        assert 0.15 < time.perf_counter() - began < 3  # it waited, then gave up
    finally:
        release.set()
        holder.join()
    assert calls.call(lambda: None).stdout == ""  # and the lock was not left taken


def test_the_busy_message_exists_in_both_languages() -> None:
    assert "{" not in tr("demo.busy", "fr") and "{" not in tr("demo.busy", "en")
    assert tr("demo.busy", "fr") != tr("demo.busy", "en")


# ----------------------------------------------------------- heavy computations, two at a time
def test_heavy_page_computations_run_two_at_a_time_not_all_at_once(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Every slider position of page 4 is a cache miss computed in the visitor's own thread: eight
    visitors took the demo to 2.8 GB. The loaders take a turn (`loaders.HEAVY_AT_ONCE`)."""
    inside = peak = 0
    guard = threading.Lock()

    def slow_tables(*args: object, **kwargs: object) -> SimpleNamespace:
        nonlocal inside, peak
        with guard:
            inside += 1
            peak = max(peak, inside)
        time.sleep(0.15)
        with guard:
            inside -= 1
        return SimpleNamespace(daily="daily")

    basis = yaml.safe_load((ROOT / demo.BASIS).read_text(encoding="utf-8"))
    monkeypatch.setattr(loaders, "build_tables", slow_tables)
    monkeypatch.setattr(loaders, "profile_from_tables", lambda *a, **k: "profile")
    monkeypatch.setattr(loaders, "sku_frame", lambda *a, **k: "sku")
    monkeypatch.setattr(loaders, "load_catalog", lambda *a, **k: "catalog")
    monkeypatch.setattr(loaders, "select_design_day", lambda *a, **k: "design day")
    loaders.design_preview.clear()
    results: list[object] = []

    def visitor(horizon: int) -> None:  # a distinct basis each: no cache hit to share
        nested = {**basis, "projection": {**basis["projection"], "horizon_years": horizon}}
        results.append(
            loaders.design_preview(str(tmp_path), "k", json.dumps(nested), "catalog", "k")
        )

    threads = [threading.Thread(target=visitor, args=(n,)) for n in range(1, 9)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    loaders.design_preview.clear()
    assert results == ["design day"] * 8
    assert 1 <= peak <= loaders.HEAVY_AT_ONCE  # eight at once without the turns

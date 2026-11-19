"""F10b public demo: what a visitor may size, and what the server tells them (no Streamlit).

An anonymous visitor shares one process, and the commands run one at a time and cannot be
interrupted: plain widgets must not be able to ask the engine for minutes of work or gigabytes.
`whsizing.app.demo_limits` bounds the inputs that did (found in the security reviews of the demo:
a 320-year finance horizon, 30 scenarios, 300 shifts per day, a lifted `engine.max_equipment_count`,
overrides far outside the catalog). The AppTest side is in tests/e2e/test_f10_app_demo.py.
"""

from __future__ import annotations

import json
import sys
import tempfile
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import yaml

from whsizing.app import calls, demo, demo_limits, loaders
from whsizing.app.calls import BUSY_CODE, CliError
from whsizing.app.demo_limits import (
    MAX_HORIZON_YEARS,
    MAX_SCENARIOS,
    MAX_SHIFTS,
    MAX_TEXT_CHARS,
    MAX_YAML_CHARS,
    limit_problems,
    parse_yaml,
    scrub,
    yaml_too_long,
)
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
    """`engine.max_equipment_count` stops a queue model that needs millions of stations (a packing
    rate far below the catalog's asks for 1.3 to 2.8 million); lifted, a security review saw the
    engine run for minutes on such an input, which a later audit could not reproduce (10 s)."""
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
    for value in (0.000055, param.min - 1, param.max + 1):  # the first: a million times too low
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


def test_the_catalog_maximum_is_allowed_and_a_hair_above_it_is_not(
    public: None, catalog: Catalog
) -> None:
    param = catalog.params["labor.packing_S"]
    assert limit_problems({"overrides": {"labor.packing_S": param.max}}, {}, catalog) == []
    assert keys(
        limit_problems({"overrides": {"labor.packing_S": param.max + 0.001}}, {}, catalog)
    ) == ["demo.limit.range"]


def test_a_bool_override_is_read_like_the_library_reads_it(public: None, catalog: Catalog) -> None:
    """ScenarioSet reads `true` as 1.0, which is outside the range of a packing rate: the limit
    must see the number the library will use, not skip a value that is no `int | float`."""
    param = catalog.params["labor.packing_S"]
    scenarios = {"scenarios": [{"id": "S0", "overrides": {"labor.packing_S": True}}]}
    assert limit_problems({}, scenarios, catalog) == [
        ("demo.limit.range", {"id": "labor.packing_S", "lo": param.min, "hi": param.max})
    ]


@pytest.mark.parametrize(("text", "refused"), [("21", True), ("1e3", True), ("20", False)])
def test_a_horizon_typed_as_text_is_checked_like_a_number(
    public: None, catalog: Catalog, text: str, refused: bool
) -> None:
    basis = {"projection": {"horizon_years": text}, "finance": {"horizon_years": text}}
    assert keys(limit_problems(basis, {}, catalog)) == (
        ["demo.limit.horizon"] * 2 if refused else []
    )


@pytest.mark.parametrize(("shifts", "refused"), [(MAX_SHIFTS, False), (MAX_SHIFTS + 1, True)])
@pytest.mark.parametrize("as_text", [False, True])
def test_shifts_per_day_stop_at_the_limit_whatever_their_hours(
    public: None, catalog: Catalog, shifts: int, refused: bool, as_text: bool
) -> None:
    """300 shifts of a few minutes (the sum of the hours stays under 24) took 34 s and 2.1 GB: the
    loops of the engine go over the shifts, and the library only asks for at least one."""
    value: int | str = str(shifts) if as_text else shifts
    basis = {"operations": {"shifts_per_day": value, "hours_per_shift": 0.01}}
    assert limit_problems(basis, {}, catalog) == (
        [("demo.limit.maximum", {"name": "operations.shifts_per_day", "max": MAX_SHIFTS})]
        if refused
        else []
    )


def test_a_text_over_the_limit_is_refused_wherever_it_sits(public: None, catalog: Catalog) -> None:
    """A name reaches the PDF (25 s per MB under the lock), the messages and the drafts."""
    long = "x" * (MAX_TEXT_CHARS + 1)
    assert limit_problems({"client": "x" * MAX_TEXT_CHARS}, {}, catalog) == []  # the limit is ok
    assert limit_problems({"client": long}, {}, catalog) == [
        ("demo.limit.text", {"name": "basis.client", "max": MAX_TEXT_CHARS})
    ]
    cards = {"scenarios": [{"id": "S0"}, {"id": "S1", "name": long}]}
    assert limit_problems({}, cards, catalog) == [
        ("demo.limit.text", {"name": "scenarios[1].name", "max": MAX_TEXT_CHARS})
    ]
    nested = {"overrides": {long: 1.0}, "building": {"notes": [{"deep": long}]}}
    names = [values["name"] for _, values in limit_problems(nested, {}, catalog)]
    assert names == ["basis.overrides.xxxxxxxxxxxxxxxxxxxx...", "basis.building.notes[0].deep"]


def test_long_texts_are_listed_a_few_at_a_time_and_cards_over_the_count_are_not_walked(
    public: None, catalog: Catalog
) -> None:
    long = "x" * (MAX_TEXT_CHARS + 1)
    many = {f"field{i}": long for i in range(20)}
    texts = [p for p in limit_problems(many, {}, catalog) if p[0] == "demo.limit.text"]
    assert len(texts) == 3  # not one message per text
    cards = [{"id": f"S{i}", "name": long if i == MAX_SCENARIOS + 2 else "s"} for i in range(9)]
    problems = limit_problems({}, {"scenarios": cards}, catalog)  # the long name is on card 8 of 9
    assert keys(problems) == ["demo.limit.scenarios"]  # refused by its count: the rest is not read
    first = [{"id": f"S{i}", "name": long if i == 0 else "s"} for i in range(9)]
    assert keys(limit_problems({}, {"scenarios": first}, catalog)) == [  # while one that is read
        "demo.limit.scenarios",
        "demo.limit.text",
    ]  # is reported


def test_the_demo_reads_yaml_without_aliases_the_full_app_with_them(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A few anchors multiply a small paste into millions of values: 200 KB took 7 s and 2.5 GB at
    every rerun. Inside the size limit the multiplication is still there, so the demo refuses it."""
    text = "a: &a [1, 2]\nb: *a\n"
    monkeypatch.delenv(demo.DEMO_ENV, raising=False)
    assert parse_yaml(text) == {"a": [1, 2], "b": [1, 2]}  # the full app: the user's machine
    monkeypatch.setenv(demo.DEMO_ENV, "1")
    with pytest.raises(yaml.YAMLError, match="alias"):
        parse_yaml(text)
    bomb = "a: &a [" + "1," * 2000 + "1]\n" + "".join(f"k{i}: *a\n" for i in range(600))
    assert not yaml_too_long(bomb)  # it fits the size limit...
    with pytest.raises(yaml.YAMLError, match="alias"):
        parse_yaml(bomb)  # ...and is refused at its first alias
    assert parse_yaml("a: [1, 2]\nb: {c: 3}\n") == {"a": [1, 2], "b": {"c": 3}}  # as before
    assert parse_yaml("") is None


def test_the_pointer_to_a_folder_of_the_server_is_dropped_from_a_message(
    public: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """'no scenario computed: not computed: S0 (see <runs>/2026-.../)': a folder a visitor cannot
    open, which the library names as the place to look."""
    runs = tmp_path / "runs"
    runs.mkdir()
    monkeypatch.setenv("WHSIZING_RUNS", str(runs))
    message = f"no scenario computed: not computed: S0 (see {runs}/2026-11-17T10-00-00_ab); S0: bad"
    assert scrub(message) == "no scenario computed: not computed: S0; S0: bad"


def test_a_yaml_box_over_the_limit_is_refused_in_the_demo_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """It is parsed again on every rerun, in the visitor's own thread and outside the locks."""
    monkeypatch.delenv(demo.DEMO_ENV, raising=False)
    assert not yaml_too_long("x" * (10 * MAX_YAML_CHARS))  # the full app has no limit
    monkeypatch.setenv(demo.DEMO_ENV, "1")
    assert not yaml_too_long("x" * MAX_YAML_CHARS) and yaml_too_long("x" * (MAX_YAML_CHARS + 1))


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
        "client": "x" * (MAX_TEXT_CHARS + 1),
        "operations": {"shifts_per_day": 99},
        "projection": {"horizon_years": 99},
        "overrides": {"engine.max_equipment_count": 1, "labor.packing_S": 1.0},
    }
    problems = limit_problems(basis, {"scenarios": [{"id": f"S{i}"} for i in range(9)]}, catalog)
    assert sorted(keys(problems)) == [
        "demo.limit.constant",
        "demo.limit.horizon",
        "demo.limit.maximum",
        "demo.limit.range",
        "demo.limit.scenarios",
        "demo.limit.text",
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


def test_the_app_and_the_temporary_folders_are_hidden_too(
    public: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    app = tmp_path / "srv" / "app"
    scratch = tmp_path / "srv" / "scratch"
    app.mkdir(parents=True)
    scratch.mkdir()
    monkeypatch.chdir(app)
    monkeypatch.setattr(tempfile, "tempdir", str(scratch))
    text = f"{app}/catalog/x.yaml, {scratch}/whsizing-abc/data.csv"
    assert scrub(text) == "<app>/catalog/x.yaml, <tmp>/whsizing-abc/data.csv"


def test_the_home_and_the_python_folders_are_hidden_too(
    public: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A message that names a file of the interpreter or of the account running the server
    (a library error about one of its own files) tells a visitor where the server keeps them."""
    home = tmp_path / "home" / "adminuser"
    prefix = tmp_path / "opt" / "venv"
    home.mkdir(parents=True)
    prefix.mkdir(parents=True)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    monkeypatch.setattr(sys, "prefix", str(prefix))
    text = f"{home}/.cache/x, {prefix}/lib/python3.12/site-packages/polars/io.py"
    assert scrub(text) == "<home>/.cache/x, <python>/lib/python3.12/site-packages/polars/io.py"
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: (_ for _ in ()).throw(RuntimeError)))
    assert scrub("no home to find") == "no home to find"  # and a missing home is not an error


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


def test_exclusive_keeps_the_lock_across_the_calls_so_nothing_slips_between_them() -> None:
    """`compare` after `size`: the lock is not a queue, so a command waiting for it could take it
    between the two and the second would then wait behind it (and give up)."""
    order: list[str] = []
    other_ran = threading.Event()

    def other() -> None:
        calls.call(lambda: order.append("other"))
        other_ran.set()

    waiter = threading.Thread(target=other)
    with calls.exclusive():
        calls.call(lambda: order.append("first"))  # the lock is re-entrant: no wait, no deadlock
        waiter.start()
        assert not other_ran.wait(0.3)  # it waits for the whole block, not for the first command
        calls.call(lambda: order.append("second"))
    waiter.join(5)
    assert order == ["first", "second", "other"]


def test_exclusive_gives_up_with_a_busy_error_when_the_lock_stays_taken_and_leaves_it_free(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(calls, "WAIT_S", 0.2)
    taken, release = threading.Event(), threading.Event()

    def holder() -> None:
        with calls.exclusive():
            taken.set()
            release.wait(5)

    thread = threading.Thread(target=holder)
    thread.start()
    try:
        assert taken.wait(5)
        with pytest.raises(CliError) as busy, calls.exclusive():
            pass
        assert busy.value.code == BUSY_CODE
    finally:
        release.set()
        thread.join()
    with calls.exclusive():  # not left taken by the one that gave up
        assert calls.call(lambda: None).stdout == ""


def test_the_demos_own_lock_gives_up_busy_too_and_nothing_is_built_meanwhile(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The first visitor's build holds the demo's lock for its whole length: the ones behind it get
    the busy message after `calls.WAIT_S`, not an unbounded wait (and then a second one)."""
    monkeypatch.setattr(calls, "WAIT_S", 0.2)
    monkeypatch.setenv(demo.SALT_ENV, "set")  # `ensure_salt` then changes nothing
    taken, release = threading.Event(), threading.Event()

    def holder() -> None:
        with demo._held():  # pyright: ignore[reportPrivateUsage]
            taken.set()
            release.wait(5)

    thread = threading.Thread(target=holder)
    thread.start()
    try:
        assert taken.wait(5)
        for visit in (demo.ensure_salt, lambda: demo.shared_run(tmp_path, ROOT / "catalog")):
            began = time.perf_counter()
            with pytest.raises(CliError) as busy:
                visit()
            assert busy.value.code == BUSY_CODE and 0.15 < time.perf_counter() - began < 3
        assert list(tmp_path.iterdir()) == []  # the shared build did not start
    finally:
        release.set()
        thread.join()
    demo.ensure_salt()  # the lock was not left taken


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

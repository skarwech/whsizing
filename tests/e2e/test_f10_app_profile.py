"""F10b pages 1 and 3 on a small synthetic site (T10.4, R7.5): the unit hints and the suggested
columns of the mapping, the raw upload that does not outlive the script run, and page 3 profiling
a run once, again only when the tables or the profile configuration change, and showing an error
(not a traceback) for a damaged table."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import yaml
from streamlit.testing.v1 import AppTest
from tests.e2e.test_f10_app_support import (
    APP,
    TIMEOUT,
    ingest_run,
    raw_copies,
    render,
    salted,
    synthetic_csv_dir,
    texts,
    upload_page,
)

from whsizing.app.strings import tr
from whsizing.report import fmt_pct


@pytest.fixture(scope="session", autouse=True)
def salt_env() -> Iterator[None]:
    yield from salted()


@pytest.fixture(scope="session")
def csv_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return synthetic_csv_dir(tmp_path_factory)


# --------------------------------------------------------------------- page 1: mapping and hints
def test_T10_4_unit_hints_are_confirmed_on_the_page_and_recorded_in_the_mapping(
    csv_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import polars as pl

    monkeypatch.setenv("WHSIZING_RUNS", str(tmp_path / "runs"))
    master = pl.read_csv(csv_dir / "sku_master.csv")
    scaled = tmp_path / "sku_cm_g.csv"  # dimensions in cm, weights in g (all 600 g)
    master.with_columns(pl.col("Length", "Width", "Height") / 10, Weight=pl.lit(600.0)).write_csv(
        scaled
    )
    up = upload_page("sku_master", scaled)
    key = "map.sku_master.sku_cm_g.csv"
    assert up.checkbox(key=f"{key}.dims").value and up.checkbox(key=f"{key}.weight").value
    up.checkbox(key=f"{key}.weight").uncheck().run()  # keep the weights as they are (kg)
    up.button[-1].click().run()
    assert not up.exception and not up.error, texts(up, "error")
    run = Path(up.session_state["run_dir"])
    saved = yaml.safe_load((run / "inputs" / "mapping" / "sku_master.yaml").read_text("utf-8"))
    assert saved["unit_hints"] == {"dims": "cm", "weight": "kg"}  # the answers, recorded
    canonical = pl.read_parquet(run / "canonical" / "sku_master.parquet").sort("sku")
    expected = master.select("Length").to_series().sort()
    assert sorted(canonical["length_mm"].round(1).to_list()) == pytest.approx(
        sorted(expected.round(1).to_list()), abs=0.11
    )  # cm converted back to mm, as the library does
    assert canonical["weight_kg"].min() == pytest.approx(600.0)  # declined: not divided


def test_T10_4_a_suggested_column_is_used_only_when_the_accept_toggle_is_on(
    csv_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("WHSIZING_RUNS", str(tmp_path / "runs"))
    text = (csv_dir / "order_lines.csv").read_text(encoding="utf-8").split("\n", 1)
    fuzzy = tmp_path / "fuzzy.csv"  # 'Ord Nbr' is close to 'order number', not an exact synonym
    fuzzy.write_text("Ord Nbr,Order Date,SKU,Quantity,Channel,Line Status\n" + text[1], "utf-8")
    up = upload_page("order_lines", fuzzy)
    toggle = "map.order_lines.fuzzy.csv.order_id.ok"
    assert not up.toggle(key=toggle).value  # needs a confirmation, like the CLI's question
    assert any("order_id" in e and "not mapped" in e for e in texts(up, "error"))
    assert not [b for b in up.button if b.label == tr("upload.run", "en")]  # nothing to run yet
    up.toggle(key=toggle).set_value(True).run()
    assert not up.error, texts(up, "error")
    up.button[-1].click().run()
    assert any("quality score" in s for s in texts(up, "success")), texts(up, "error")


# ------------------------------------------------------------------------- the profile of page 3
def test_T10_4_page_1_the_raw_upload_is_deleted_when_the_script_run_ends(
    csv_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The page sniffs and maps the uploaded file (it was on disk during the run), and nothing
    of it is left afterwards, ingest or not."""
    monkeypatch.setenv("WHSIZING_RUNS", str(tmp_path))
    up = AppTest.from_file(str(APP / "pages/1_Upload.py"), default_timeout=TIMEOUT)
    up.session_state["lang"] = "en"
    up.run()
    blob = (csv_dir / "sku_master.csv").read_bytes()
    up.file_uploader(key="up.sku_master").upload("sku_master.csv", blob, "text/csv").run()
    assert not up.exception and not up.error, texts(up, "error")
    assert up.selectbox(key="map.sku_master.sku_master.csv.sku.col").value  # mapped from the file
    assert raw_copies(tmp_path) == []


@pytest.mark.slow
def test_T10_4_page_3_reprofiles_when_a_dataset_is_ingested_after_the_profile_was_made(
    csv_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("WHSIZING_RUNS", str(tmp_path))
    run = ingest_run(csv_dir, tmp_path, ("order_lines",))
    dims = lambda at: next(m.value for m in at.metric if m.label == tr("profile.dims", "en"))  # noqa: E731
    before = render("pages/3_Demand_profile.py", run, "en")
    assert not before.exception and dims(before) == fmt_pct(0.0, "en")
    ingest_run(csv_dir, tmp_path, ("sku_master",), run=run)  # dimensions arrive later
    after = render("pages/3_Demand_profile.py", run, "en")
    assert not after.exception
    stored = json.loads((run / "profile" / "demand_profile.json").read_text("utf-8"))
    assert stored["dims_coverage_lines"] > 0.5  # page 3 profiled the run again
    assert dims(after) == fmt_pct(stored["dims_coverage_lines"], "en") != dims(before)


@pytest.mark.slow
def test_R7_5_page_3_profiles_once_and_again_only_when_the_tables_or_the_cfg_change(
    csv_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`profile` writes canonical/daily_series.parquet after demand_profile.json: with file times
    the profile was always older than a table, and page 3 profiled again on every script run (a
    visit, a language toggle), 1.4-1.6 s each, rewriting the profile, the series, the charts."""
    from whsizing.app import calls
    from whsizing.cli.data import profile_cmd

    monkeypatch.setenv("WHSIZING_RUNS", str(tmp_path))
    profiled: list[dict[str, Any]] = []
    real_call = calls.call

    def counting(command: Any, **kwargs: Any) -> Any:
        if command is profile_cmd:
            profiled.append(kwargs)
        return real_call(command, **kwargs)

    monkeypatch.setattr(calls, "call", counting)
    run = ingest_run(csv_dir, tmp_path, ("order_lines",))
    stamp = lambda: [  # noqa: E731
        (run / rel).stat().st_mtime_ns
        for rel in ("profile/demand_profile.json", "canonical/daily_series.parquet")
    ]
    first = render("pages/3_Demand_profile.py", run, "en")
    assert not first.exception and len(profiled) == 1
    written = stamp()
    for lang in ("en", "fr", "en"):  # visits and language toggles of a profiled run
        again = render("pages/3_Demand_profile.py", run, lang)
        assert not again.exception
    assert len(profiled) == 1 and stamp() == written  # nothing profiled, nothing rewritten
    # another profile configuration: the page profiles again, with that configuration
    cfg = run / "inputs" / "profile_cfg.yaml"
    cfg.write_text("abc_thresholds: [0.6, 0.9]\n", encoding="utf-8")
    assert not render("pages/3_Demand_profile.py", run, "en").exception
    assert len(profiled) == 2 and profiled[1]["cfg"] == cfg
    stored = json.loads((run / "profile" / "demand_profile.json").read_text("utf-8"))
    assert stored["abc"]["thresholds"] == [0.6, 0.9]
    assert not render("pages/3_Demand_profile.py", run, "fr").exception
    assert len(profiled) == 2  # and it is current again
    # new tables: again
    ingest_run(csv_dir, tmp_path, ("sku_master",), run=run)
    assert not render("pages/3_Demand_profile.py", run, "en").exception
    assert len(profiled) == 3
    assert not render("pages/3_Demand_profile.py", run, "en").exception
    assert len(profiled) == 3


@pytest.mark.slow
@pytest.mark.parametrize("damage", ["garbage", "removed"])
def test_R7_5_page_3_a_damaged_or_removed_table_of_a_profiled_run_is_an_error_not_a_traceback(
    damage: str, csv_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`profile_stale` hashes the canonical tables, which raises for one it cannot read: page 3
    runs it outside any try, so the run (profiled, tables damaged afterwards) was a traceback."""
    monkeypatch.setenv("WHSIZING_RUNS", str(tmp_path))
    run = ingest_run(csv_dir, tmp_path, ("order_lines",))
    first = render("pages/3_Demand_profile.py", run, "en")
    assert not first.exception and not first.error
    table = run / "canonical" / "order_lines.parquet"
    if damage == "garbage":
        table.write_bytes(b"{")
    else:
        table.unlink()
    at = render("pages/3_Demand_profile.py", run, "en")
    assert not at.exception, [str(e.value)[:200] for e in at.exception]
    assert any(e.startswith("exit ") for e in texts(at, "error")), texts(at, "error")

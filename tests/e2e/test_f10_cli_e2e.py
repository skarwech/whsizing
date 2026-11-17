"""F10a CLI end to end on a small synthetic site (F1 generator, 243 days from 2025-01-01, 120 SKUs,
≈ 14 000 order lines: 8 complete months, no blocking R-rule): the staged flow `ingest → profile →
size → compare → report → calibrate` (T10.1), `run-all` and its canonical reuse (T10.2, wall time
printed), `rerun`, and the exit codes 1, 4 and 5 of §2.7 that need a run folder (T10.3).

`whsizing.report` (F9) is built apart from the CLI: its three functions are monkeypatched here, the
command is tested for what it calls and what it exits with."""

from __future__ import annotations

import json
import re
import shutil
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any, NamedTuple

import polars as pl
import pytest
import yaml
from tests.unit.test_f11_pipeline import write_actuals
from typer.testing import CliRunner, Result

import whsizing.cli.data as cli_data
import whsizing.report as report_api
from whsizing.calibration import baseline_monthly, inputs_from_run
from whsizing.catalog import load_catalog
from whsizing.cli import app
from whsizing.design import load_basis
from whsizing.errors import ReportIntegrityError
from whsizing.scenarios.manifest import manifest_hash, read_manifest
from whsizing.schemas import IntegrityIssue
from whsizing.schemas.run import RunOutput
from whsizing.synth import synthesize

ROOT = Path(__file__).resolve().parents[2]
DATASETS = ("sku_master", "inventory", "receipts", "order_lines")  # sku_master first (F2 checks)
SCENARIOS = ("S0", "S1", "S2")
RUN_NAME = re.compile(r"\d{4}-\d\d-\d\dT\d\d-\d\d-\d\d_[0-9a-f]{6}")
SALT = "f10-e2e-salt"
NOTICE = "indicative study"
SMALL_PROFILE = """\
name: small_cli
n_skus: 120
start_date: 2025-01-01
n_days: 243
orders_per_day_mean: 40
promos: []
"""
runner = CliRunner()


def cli(*args: object) -> Result:
    return runner.invoke(app, [str(a) for a in args])


def run_path(res: Result) -> Path:
    """The run folder is the last line a command prints on stdout."""
    return Path(res.stdout.strip().splitlines()[-1])


def copy_run(src: Path, parent: Path) -> Path:
    dst = parent / src.name
    shutil.copytree(src, dst)
    return dst


def size_args(run: Path, basis: Path = ROOT / "basis" / "example_basis.yaml") -> list[object]:
    return [
        "size", run, "--basis", basis, "--scenarios", ROOT / "scenarios" / "example_scenarios.yaml",
        "--catalog", ROOT / "catalog",
    ]  # fmt: skip


class Sized(NamedTuple):
    run: Path
    result: Result


@pytest.fixture(scope="module", autouse=True)
def salt_env() -> Iterator[None]:
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("WHSIZING_SALT", SALT)
        yield


class ReportCalls:
    """Records what the CLI asks of `whsizing.report` (F9); the files it 'builds' are 1 byte."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str | None]] = []
        self.runs: list[RunOutput] = []

    def build(self, kind: str) -> Any:
        def fn(run: RunOutput, lang: str) -> Path:
            self.calls.append((kind, lang))
            self.runs.append(run)
            path = run.run_dir / "report" / f"report_{lang}.{kind}"
            path.write_bytes(b"x")
            return path

        return fn

    def check(self, run: RunOutput) -> list[str]:
        self.calls.append(("check", None))
        return []


@pytest.fixture(scope="module")
def fake_report() -> Iterator[ReportCalls]:
    rec = ReportCalls()
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(report_api, "check_integrity", rec.check, raising=False)
        mp.setattr(report_api, "build_excel", rec.build("xlsx"), raising=False)
        mp.setattr(report_api, "build_pdf", rec.build("pdf"), raising=False)
        yield rec


@pytest.fixture(scope="module")
def data(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("f10_data")
    (root / "small.yaml").write_text(SMALL_PROFILE, encoding="utf-8")
    synthesize(root / "small.yaml", root / "out", seed=42)
    return root / "out" / "csv_en"


@pytest.fixture(scope="module")
def ingested(data: Path, tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Four `whsizing ingest` calls into one run folder, as a consultant would."""
    out_dir = tmp_path_factory.mktemp("f10_runs")
    first = cli("ingest", data / "sku_master.csv", "--dataset", "sku_master", "--non-interactive",
                "--out-dir", out_dir)  # fmt: skip
    assert first.exit_code == 0, first.output
    run = run_path(first)
    for ds in DATASETS[1:]:
        res = cli("ingest", data / f"{ds}.csv", "--dataset", ds, "--non-interactive", "--run", run)
        assert res.exit_code == 0, res.output
        assert run_path(res) == run
    return run


@pytest.fixture(scope="module")
def sized(ingested: Path, tmp_path_factory: pytest.TempPathFactory) -> Sized:
    """`profile --cfg` then `size` on a copy of the ingested run."""
    work = tmp_path_factory.mktemp("f10_sized")
    run = copy_run(ingested, work)
    cfg = work / "profile_cfg.yaml"
    cfg.write_text("abc_thresholds: [0.7, 0.9]\n", encoding="utf-8")
    prof = cli("profile", run, "--cfg", cfg)
    assert prof.exit_code == 0, prof.output
    res = cli(*size_args(run))
    assert res.exit_code == 0, res.output
    return Sized(run, res)


@pytest.fixture(scope="module")
def project_yaml(data: Path, tmp_path_factory: pytest.TempPathFactory) -> Path:
    return write_project(data, tmp_path_factory.mktemp("f10_project"))


def write_project(data: Path, folder: Path) -> Path:
    """project.yaml on the generated CSVs, with its own out_dir (absolute paths)."""
    text = {
        "name": "small_cli",
        "language": ["fr", "en"],
        "out_dir": str(folder / "runs"),
        "catalog": str(ROOT / "catalog"),
        "inputs": {ds: {"files": [str(data / f"{ds}.csv")]} for ds in DATASETS},
        "basis": str(ROOT / "basis" / "example_basis.yaml"),
        "scenarios": str(ROOT / "scenarios" / "example_scenarios.yaml"),
        "options": {"worlds": "all", "sensitivity": False, "delta": 0.2, "strict": False},
    }
    path = folder / "project.yaml"
    path.write_text(yaml.safe_dump(text), encoding="utf-8")
    return path


# ------------------------------------------------------------------------------ T10.1 staged flow
def test_T10_1_ingest_makes_a_run_folder_without_the_salt(ingested: Path) -> None:
    assert RUN_NAME.fullmatch(ingested.name)
    for ds in DATASETS:
        assert (ingested / "canonical" / f"{ds}.parquet").is_file()
        assert (ingested / "inputs" / "mapping" / f"{ds}.yaml").is_file()
    assert (ingested / "dq" / "dq_report.html").is_file()
    assert not (ingested / "mapping").exists()  # moved under inputs/ like the F8 runner does
    log = ingested / "logs" / "run.log"
    assert log.read_text(encoding="utf-8").count('"ingest_done"') == len(DATASETS)
    leaked = [p for p in ingested.rglob("*") if p.is_file() and SALT.encode() in p.read_bytes()]
    assert leaked == []  # the salt never reaches the run folder (I75 d)


def test_T10_1_ingest_with_a_salt_file_gives_the_same_ids(
    data: Path, ingested: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    salt_file = tmp_path / "salt.txt"
    salt_file.write_text(SALT + "\n", encoding="utf-8")  # same salt, now from a file
    monkeypatch.delenv("WHSIZING_SALT")
    res = cli("ingest", data / "sku_master.csv", "--dataset", "sku_master", "--non-interactive",
              "--salt-file", salt_file, "--out-dir", tmp_path / "runs")  # fmt: skip
    assert res.exit_code == 0, res.output
    other = run_path(res)
    assert (other / "canonical" / "sku_master.parquet").read_bytes() == (
        ingested / "canonical" / "sku_master.parquet"
    ).read_bytes()


def test_T10_1_ingest_asks_about_a_close_header_unless_non_interactive(
    data: Path, tmp_path: Path
) -> None:
    text = (data / "order_lines.csv").read_text(encoding="utf-8").split("\n", 1)
    fuzzy = tmp_path / "fuzzy.csv"  # 'Ord Nbr' is close to 'order number', not an exact synonym
    fuzzy.write_text("Ord Nbr,Order Date,SKU,Quantity,Channel,Line Status\n" + text[1], "utf-8")
    args = ["ingest", fuzzy, "--dataset", "order_lines", "--out-dir", tmp_path / "runs"]
    refused = cli(*args, "--non-interactive")
    assert refused.exit_code == 2 and "needs confirmation" in refused.stderr
    asked = runner.invoke(app, [str(a) for a in args], input="y\n" * 10)
    assert asked.exit_code == 0, asked.output
    assert "Use column 'Ord Nbr' as order_id?" in asked.stdout
    saved = run_path(asked) / "inputs" / "mapping" / "order_lines.yaml"
    assert "Ord Nbr" in json.dumps(yaml.safe_load(saved.read_text(encoding="utf-8")))  # recorded
    again = cli(*args, "--non-interactive", "--mapping", saved)  # the saved decision is enough
    assert again.exit_code == 0, again.output


def test_T10_1_ingest_into_a_run_keeps_the_mappings_of_the_earlier_datasets(
    data: Path, tmp_path: Path
) -> None:
    """order_lines first, then sku_master: F2 reads mapping/ of the run for the earlier dataset
    (timezone, merge setting), so the command puts inputs/mapping/ back there while it runs."""
    first = cli("ingest", data / "order_lines.csv", "--dataset", "order_lines",
                "--non-interactive", "--out-dir", tmp_path / "runs")  # fmt: skip
    assert first.exit_code == 0, first.output
    run = run_path(first)
    second = cli("ingest", data / "sku_master.csv", "--dataset", "sku_master", "--non-interactive",
                 "--run", run)  # fmt: skip
    assert second.exit_code == 0, second.output
    assert sorted(p.name for p in (run / "inputs" / "mapping").iterdir()) == [
        "order_lines.yaml", "sku_master.yaml",
    ]  # fmt: skip
    assert not (run / "mapping").exists()


def test_T10_1_ingest_keep_descriptions_is_accepted(data: Path, tmp_path: Path) -> None:
    res = cli("ingest", data / "sku_master.csv", "--dataset", "sku_master", "--non-interactive",
              "--keep-descriptions", "--out-dir", tmp_path / "runs")  # fmt: skip
    assert res.exit_code == 0, res.output


def test_T10_1_profile_cfg_is_kept_and_size_uses_it(sized: Sized) -> None:
    run = sized.run
    assert (run / "profile" / "demand_profile.json").is_file()
    assert (run / "canonical" / "daily_series.parquet").is_file()
    project = yaml.safe_load((run / "inputs" / "project.yaml").read_text(encoding="utf-8"))
    assert project["profile_cfg"]["abc_thresholds"] == [0.7, 0.9]


def test_T10_1_size_writes_design_scenarios_manifest_and_the_notice(sized: Sized) -> None:
    run, res = sized
    assert (run / "design" / "design_day.json").is_file()
    for sid in SCENARIOS:
        for name in ("result.json", "finance.json", "trace.jsonl"):
            assert (run / "scenarios" / sid / name).is_file(), (sid, name)
    manifest = json.loads((run / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["run_id"] == run.name
    assert {"ingest", "inputs", "profile", "design", "scenarios"} <= set(manifest["timings"])
    assert manifest["timings"]["ingest"] > 0  # from logs/run.log: another process ran it
    assert set(manifest["mapping_hashes"]) == set(DATASETS)
    assert sum(k.endswith(".csv") for k in manifest["inputs"]) == len(DATASETS)  # data hashes
    assert {"inputs/basis.yaml", "inputs/scenarios.yaml", "inputs/project.yaml"} <= set(
        manifest["inputs"]
    )
    assert NOTICE in res.stdout.lower()
    assert all(sid in res.stdout for sid in SCENARIOS)
    assert res.stdout.strip().splitlines()[-1] == str(run)
    assert re.search(r"\d\.\d \[\d\.\d-\d\.\d\]", res.stdout)  # FTE keeps a decimal


def test_T10_1_ingest_never_changes_a_sized_run(sized: Sized, data: Path, tmp_path: Path) -> None:
    """Runs are immutable (§2.4): ingest into a sized run, or into a folder that is no run, is
    refused (exit 2) and writes nothing."""
    run = copy_run(sized.run, tmp_path / "runs")
    files = {p: p.read_bytes() for p in run.rglob("*") if p.is_file()}
    args = ["ingest", data / "receipts.csv", "--dataset", "receipts", "--non-interactive"]
    res = cli(*args, "--run", run)
    assert res.exit_code == 2 and "immutable" in res.stderr
    assert {p: p.read_bytes() for p in run.rglob("*") if p.is_file()} == files
    empty = tmp_path / "not_a_run"
    empty.mkdir()
    res = cli(*args, "--run", empty)
    assert res.exit_code == 2 and "not a run folder" in res.stderr
    assert list(empty.iterdir()) == []


def test_T10_1_ingest_refuses_a_run_that_has_a_manifest_but_no_design(
    ingested: Path, data: Path, tmp_path: Path
) -> None:
    run = copy_run(ingested, tmp_path)  # `size` died after it wrote manifest.json
    (run / "manifest.json").write_text("{}", encoding="utf-8")
    res = cli("ingest", data / "receipts.csv", "--dataset", "receipts", "--run", run,
              "--non-interactive")  # fmt: skip
    assert res.exit_code == 2 and "immutable" in res.stderr


def test_T10_1_size_refuses_a_run_that_is_already_sized(sized: Sized, tmp_path: Path) -> None:
    again = cli(*size_args(copy_run(sized.run, tmp_path)))
    assert again.exit_code == 2 and "already sized" in again.stderr


def test_T10_1_size_worlds_typ_prints_typical_values_only(
    sized: Sized, ingested: Path, tmp_path: Path
) -> None:
    range_cell = re.compile(r"\d \[[\d,]+-[\d,]+\]")
    assert range_cell.search(sized.result.stdout)  # default: typ [lo-hi]
    res = cli(*size_args(copy_run(ingested, tmp_path)), "--worlds", "typ")
    assert res.exit_code == 0, res.output
    assert "S0" in res.stdout and range_cell.search(res.stdout) is None


@pytest.mark.slow
def test_T10_1_compare_with_and_without_sensitivity(sized: Sized, tmp_path: Path) -> None:
    run = copy_run(sized.run, tmp_path)
    res = cli("compare", run, "--delta", "0.1")
    assert res.exit_code == 0, res.output
    cmp = json.loads((run / "comparison" / "comparison.json").read_text(encoding="utf-8"))
    assert [r["scenario_id"] for r in cmp["rows"]] == list(SCENARIOS)
    sens = json.loads((run / "comparison" / "sensitivity.json").read_text(encoding="utf-8"))
    assert sens["delta"] == 0.1 and sens["tornado"]
    manifest = json.loads((run / "manifest.json").read_text(encoding="utf-8"))
    assert {"comparison", "sensitivity", "scenarios"} <= set(manifest["timings"])
    assert NOTICE in res.stdout.lower()
    res = cli("compare", run, "--no-sensitivity")
    assert res.exit_code == 0, res.output
    assert (run / "comparison" / "comparison.json").is_file()
    assert not (run / "comparison" / "sensitivity.json").exists()  # no stale sensitivity


def test_T10_1_compare_before_size_is_a_config_error(ingested: Path, tmp_path: Path) -> None:
    res = cli("compare", copy_run(ingested, tmp_path))
    assert res.exit_code == 2
    assert "not sized yet" in res.stderr and "whsizing size" in res.stderr


@pytest.fixture(scope="module")
def compared(sized: Sized, tmp_path_factory: pytest.TempPathFactory) -> Path:
    run = copy_run(sized.run, tmp_path_factory.mktemp("f10_compared"))
    res = cli("compare", run, "--no-sensitivity")
    assert res.exit_code == 0, res.output
    return run


def test_T10_1_report_calls_f9_in_order_for_each_language_and_format(
    compared: Path, fake_report: ReportCalls
) -> None:
    fake_report.calls.clear()
    res = cli("report", compared, "--lang", "both", "--formats", "both")
    assert res.exit_code == 0, res.output
    assert fake_report.calls == [
        ("check", None), ("xlsx", "fr"), ("pdf", "fr"), ("xlsx", "en"), ("pdf", "en"),
    ]  # fmt: skip
    out = fake_report.runs[-1]
    assert out.run_dir == compared and list(out.results) == list(SCENARIOS)
    assert out.manifest.run_id == compared.name and out.comparison.baseline_id == "client_current"
    assert [Path(p).name for p in res.stdout.splitlines() if p.endswith((".xlsx", ".pdf"))] == [
        "report_fr.xlsx", "report_fr.pdf", "report_en.xlsx", "report_en.pdf",
    ]  # fmt: skip
    assert NOTICE in res.stdout.lower()
    fake_report.calls.clear()
    assert cli("report", compared, "--lang", "en", "--formats", "pdf").exit_code == 0
    assert fake_report.calls == [("check", None), ("pdf", "en")]
    fake_report.calls.clear()
    assert cli("report", compared).exit_code == 0  # project language, both formats
    assert fake_report.calls == [("check", None), ("xlsx", "fr"), ("pdf", "fr")]


def test_T10_1_report_without_the_f9_builders_says_so_and_exits_1(
    compared: Path, fake_report: ReportCalls, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The F9 builders are built apart from the CLI: while one is missing the command exits 1 with
    a message that names it (not a raw AttributeError), after the integrity check passed."""
    monkeypatch.delattr(report_api, "build_excel", raising=False)
    fake_report.calls.clear()
    res = cli("report", compared, "--lang", "en", "--formats", "xlsx")
    assert res.exit_code == 1, res.output
    assert "whsizing.report.build_excel is not available" in res.stderr
    assert "AttributeError" not in res.stderr
    assert fake_report.calls == [("check", None)]


@pytest.mark.slow
def test_T10_1_calibrate_happy_path(sized: Sized, tmp_path: Path) -> None:
    run = copy_run(sized.run, tmp_path)
    basis = load_basis(run / "inputs" / "basis.yaml")
    catalog = load_catalog(run / "inputs" / "catalog")
    base = baseline_monthly(inputs_from_run(run, basis, catalog))
    months = tuple(f"2025-{m:02d}" for m in range(1, 9))
    assert set(months) <= set(base.months)
    actuals, activity_map = write_actuals(tmp_path, base, months)
    res = cli("calibrate", run, "--actuals", actuals, "--activity-map", activity_map,
              "--holdout-months", 3)  # fmt: skip
    assert res.exit_code == 0, res.output
    out = run / "calibration"
    for name in ("fit.json", "holdout.json", "calibration_note.md", "actuals.csv",
                 "activity_map.yaml"):  # fmt: skip
        assert (out / name).is_file(), name
    fit = json.loads((out / "fit.json").read_text(encoding="utf-8"))
    assert len(fit["months_holdout"]) == 3 and len(fit["months_fit"]) == 5
    assert "hold-out MAPE" in res.stdout and NOTICE in res.stdout.lower()
    missing = cli("calibrate", run, "--actuals", tmp_path / "nope.csv", "--activity-map",
                  activity_map)  # fmt: skip
    assert missing.exit_code == 2


# ---------------------------------------------------------------------- T10.1 / T10.2 run-all
@pytest.fixture(scope="module")
def all_run(project_yaml: Path, fake_report: ReportCalls) -> tuple[Path, Result, float]:
    fake_report.calls.clear()
    t0 = time.perf_counter()
    res = cli("run-all", project_yaml)
    return run_path(res), res, time.perf_counter() - t0


@pytest.mark.slow
def test_T10_1_run_all_happy_path_and_wall_time(
    all_run: tuple[Path, Result, float],
    fake_report: ReportCalls,
    capsys: pytest.CaptureFixture[str],
) -> None:
    run, res, seconds = all_run
    assert res.exit_code == 0, res.output
    assert RUN_NAME.fullmatch(run.name)
    assert run.name.endswith("_" + manifest_hash(read_manifest(run))[:6])  # §2.4, I75 b
    for sid in SCENARIOS:
        assert (run / "scenarios" / sid / "finance.json").is_file()
    assert (run / "comparison" / "comparison.json").is_file()
    assert not (run / "comparison" / "sensitivity.json").exists()  # options.sensitivity: false
    assert ("check", None) in fake_report.calls
    assert [c for c in fake_report.calls if c[0] != "check"] == [
        ("xlsx", "fr"), ("pdf", "fr"), ("xlsx", "en"), ("pdf", "en"),
    ]  # fmt: skip
    manifest = json.loads((run / "manifest.json").read_text(encoding="utf-8"))
    assert {"ingest", "scenarios", "comparison", "report"} <= set(manifest["timings"])
    assert NOTICE in res.stdout.lower()
    assert "canonical reused" not in res.stderr  # the first run ingests
    with capsys.disabled():
        print(f"\nF10a run-all happy path (small synthetic site, report stubbed): {seconds:.1f} s")


@pytest.mark.slow
def test_T10_1_rerun_gives_a_new_run_with_the_same_results(
    all_run: tuple[Path, Result, float],
) -> None:
    run = all_run[0]
    res = cli("rerun", run)
    assert res.exit_code == 0, res.output
    new = run_path(res)
    assert new != run and new.parent == run.parent and RUN_NAME.fullmatch(new.name)
    for sid in SCENARIOS:
        for name in ("result.json", "finance.json"):
            assert (new / "scenarios" / sid / name).read_bytes() == (
                run / "scenarios" / sid / name
            ).read_bytes()
    assert NOTICE in res.stdout.lower()


@pytest.mark.slow
def test_T10_1_compare_rebuilds_the_comparison_and_sensitivity_of_a_run_all_folder(
    data: Path, tmp_path: Path, fake_report: ReportCalls
) -> None:
    """The stage command re-reads result.json, finance.json and trace.jsonl: what it writes must
    equal what the runner computed in memory."""
    project = write_project(data, tmp_path)
    text = yaml.safe_load(project.read_text(encoding="utf-8"))
    text["options"]["sensitivity"] = True
    project.write_text(yaml.safe_dump(text), encoding="utf-8")
    res = cli("run-all", project)
    assert res.exit_code == 0, res.output
    run = copy_run(run_path(res), tmp_path / "copy")
    before = {
        n: (run / "comparison" / n).read_bytes() for n in ("comparison.json", "sensitivity.json")
    }
    again = cli("compare", run)  # project options: delta 0.2
    assert again.exit_code == 0, again.output
    for name, content in before.items():
        assert (run / "comparison" / name).read_bytes() == content, name


def test_T10_1_rerun_of_a_staged_run_gives_the_same_results(sized: Sized, tmp_path: Path) -> None:
    """C1: the staged flow leaves what `rerun` needs (canonical/.ingest_key, .sha256.json, the
    copies in inputs/); the data files and the salt are not read again."""
    run = copy_run(sized.run, tmp_path / "runs")
    res = cli("rerun", run)
    assert res.exit_code == 0, res.output
    new = run_path(res)
    assert new != run and new.parent == run.parent and RUN_NAME.fullmatch(new.name)
    for sid in SCENARIOS:
        for name in ("result.json", "finance.json"):
            assert (new / "scenarios" / sid / name).read_bytes() == (
                run / "scenarios" / sid / name
            ).read_bytes(), (sid, name)
    again = cli("rerun", new)  # and the replay of a replay
    assert again.exit_code == 0, again.output


def test_T10_1_rerun_prints_the_comparison_with_the_worlds_option_of_the_run(
    ingested: Path, tmp_path: Path
) -> None:
    """The replayed run keeps its `options.worlds`: `size --worlds typ`, then `rerun` shows typ
    only, like `size` did (a run with the default shows `typ [lo-hi]`)."""
    range_cell = re.compile(r"\d \[[\d,]+-[\d,]+\]")
    run = copy_run(ingested, tmp_path / "runs")
    sized_typ = cli(*size_args(run), "--worlds", "typ")
    assert sized_typ.exit_code == 0, sized_typ.output
    assert range_cell.search(sized_typ.stdout) is None
    res = cli("rerun", run, "--out-dir", tmp_path / "again")
    assert res.exit_code == 0, res.output
    assert "S0" in res.stdout and range_cell.search(res.stdout) is None


def test_T10_1_rerun_of_a_staged_run_refuses_changed_canonical_tables(
    sized: Sized, tmp_path: Path
) -> None:
    run = copy_run(sized.run, tmp_path / "runs")
    path = run / "canonical" / "sku_master.parquet"
    path.write_bytes(path.read_bytes() + b"x")
    res = cli("rerun", run)
    assert res.exit_code == 2 and "changed" in res.stderr


@pytest.mark.slow
def test_T10_1_run_all_options_override_the_project(
    data: Path, tmp_path: Path, fake_report: ReportCalls
) -> None:
    project = write_project(data, tmp_path)  # sensitivity false, worlds all, delta 0.2
    basis = tmp_path / "my_basis.yaml"  # not the project's: an edited copy
    basis.write_text(
        (ROOT / "basis" / "example_basis.yaml").read_text(encoding="utf-8") + "\n# edited\n",
        "utf-8",
    )
    res = cli("run-all", project, "--sensitivity", "--delta", "0.3", "--worlds", "typ",
              "--basis", basis, "--non-interactive")  # fmt: skip
    assert res.exit_code == 0, res.output
    run = run_path(res)
    sens = json.loads((run / "comparison" / "sensitivity.json").read_text(encoding="utf-8"))
    assert sens["delta"] == 0.3
    assert re.search(r"\d \[[\d,]+-[\d,]+\]", res.stdout) is None  # typ only
    assert (run / "inputs" / "basis.yaml").read_bytes() == basis.read_bytes()
    kept = yaml.safe_load((run / "inputs" / "project.yaml").read_text(encoding="utf-8"))
    assert kept["options"] == {
        "worlds": "typ", "sensitivity": True, "delta": 0.3, "strict": False,
        "keep_descriptions": False,
    }  # fmt: skip
    text = yaml.safe_load(project.read_text(encoding="utf-8"))
    text["options"]["sensitivity"] = True
    project.write_text(yaml.safe_dump(text), encoding="utf-8")
    off = cli("run-all", project, "--no-sensitivity")
    assert off.exit_code == 0, off.output
    assert not (run_path(off) / "comparison" / "sensitivity.json").exists()
    gone = cli("run-all", project, "--scenarios", tmp_path / "gone.yaml")
    assert gone.exit_code == 2 and "gone.yaml" in gone.stderr


@pytest.mark.slow
def test_T10_2_run_all_reuses_canonical_when_hashes_match(
    data: Path, tmp_path: Path, fake_report: ReportCalls
) -> None:
    own = tmp_path / "data"
    shutil.copytree(data, own)
    project = write_project(own, tmp_path)
    first = cli("run-all", project)
    assert first.exit_code == 0, first.output
    assert "canonical reused" not in first.stderr
    run1 = run_path(first)

    second = cli("run-all", project)  # same bytes: reused
    assert second.exit_code == 0, second.output
    run2 = run_path(second)
    assert run2 != run1
    assert "canonical reused" in second.stderr
    assert "canonical reused" in (run2 / "logs" / "run.log").read_text(encoding="utf-8")
    assert (run2 / "canonical" / "order_lines.parquet").read_bytes() == (
        run1 / "canonical" / "order_lines.parquet"
    ).read_bytes()

    lines = own / "order_lines.csv"
    raw = lines.read_bytes()
    assert b",1," in raw
    lines.write_bytes(raw.replace(b",1,", b",2,", 1))  # one byte of one input changes
    third = cli("run-all", project)
    assert third.exit_code == 0, third.output
    run3 = run_path(third)
    assert "canonical reused" not in third.stderr
    assert "canonical reused" not in (run3 / "logs" / "run.log").read_text(encoding="utf-8")
    assert (run3 / "canonical" / "order_lines.parquet").read_bytes() != (
        run2 / "canonical" / "order_lines.parquet"
    ).read_bytes()


# ------------------------------------------------------------------------------ T10.3 exit codes
def test_T10_3_exit_4_strict_with_a_building_that_fits_nothing(
    ingested: Path, tmp_path: Path
) -> None:
    basis = tmp_path / "basis_small.yaml"
    text = (ROOT / "basis" / "example_basis.yaml").read_text(encoding="utf-8")
    assert "area_m2: 12000" in text
    basis.write_text(text.replace("area_m2: 12000", "area_m2: 50"), encoding="utf-8")
    ok = cli(*size_args(copy_run(ingested, tmp_path / "a"), basis))  # no --strict: a success
    assert ok.exit_code == 0, ok.output
    assert "NO" in ok.stdout  # the fit column says so
    run = copy_run(ingested, tmp_path / "b")
    res = cli(*size_args(run, basis), "--strict")
    assert res.exit_code == 4, res.output
    assert "strict" in res.stderr and "Traceback" not in res.output
    assert (run / "scenarios" / "S0" / "result.json").is_file()  # all written, then the exit


def ingest_all(data: Path, out_dir: Path) -> Path:
    """The staged ingest of the four datasets of `data` into one new run folder."""
    first = cli("ingest", data / "sku_master.csv", "--dataset", "sku_master", "--non-interactive",
                "--out-dir", out_dir)  # fmt: skip
    assert first.exit_code == 0, first.output
    run = run_path(first)
    for ds in DATASETS[1:]:
        res = cli("ingest", data / f"{ds}.csv", "--dataset", ds, "--non-interactive", "--run", run)
        assert res.exit_code == 0, res.output
    return run


@pytest.mark.parametrize("missing", ["sku_master", "inventory"])
def test_R6_6_exit_4_run_all_strict_without_a_required_input(
    missing: str, data: Path, tmp_path: Path, fake_report: ReportCalls
) -> None:
    """I80 (a): refused before ingest, no run folder; the same project without --strict runs."""
    project = write_project(data, tmp_path)
    text = yaml.safe_load(project.read_text(encoding="utf-8"))
    del text["inputs"][missing]
    project.write_text(yaml.safe_dump(text), encoding="utf-8")
    fake_report.calls.clear()
    res = cli("run-all", project, "--strict")
    assert res.exit_code == 4, res.output
    assert "required input" in res.stderr and missing in res.stderr
    assert "Traceback" not in res.output and fake_report.calls == []
    assert not (tmp_path / "runs").exists()
    assert cli("run-all", project).exit_code == 0  # not strict: the run goes on


def test_R6_6_exit_4_size_strict_without_a_required_input_leaves_the_run_sizeable(
    data: Path, tmp_path: Path
) -> None:
    """Same rule in the staged flow: only order_lines was ingested, `size --strict` is exit 4 before
    anything is written, so the run can still be sized without --strict."""
    res = cli("ingest", data / "order_lines.csv", "--dataset", "order_lines", "--non-interactive",
              "--out-dir", tmp_path / "runs")  # fmt: skip
    assert res.exit_code == 0, res.output
    run = run_path(res)
    strict = cli(*size_args(run), "--strict")
    assert strict.exit_code == 4, strict.output
    assert "required input" in strict.stderr and "sku_master, inventory" in strict.stderr
    assert (
        not (run / "manifest.json").exists() and not (run / "design" / "design_day.json").exists()
    )
    assert cli(*size_args(run)).exit_code == 0  # not sealed: still sized as before


def test_R6_6_exit_4_size_strict_when_an_automated_scenario_assumes_eligibility(
    data: Path, tmp_path: Path
) -> None:
    """I80 (b): SKUs without a length, scenarios that assume they fit: F_ELIG_ASSUMED in S2."""
    site = tmp_path / "site"
    shutil.copytree(data, site)
    sku = pl.read_csv(site / "sku_master.csv")
    blank = pl.int_range(pl.len()) % 10 == 0  # every tenth SKU has no length
    sku.with_columns(Length=pl.when(blank).then(None).otherwise(pl.col("Length"))).write_csv(
        site / "sku_master.csv"
    )
    text = (ROOT / "scenarios" / "example_scenarios.yaml").read_text(encoding="utf-8")
    flag = "eligibility: {assume_eligible_if_missing_dims: %s}"
    scenarios = tmp_path / "assume.yaml"
    scenarios.write_text(text.replace(flag % "false", flag % "true"), encoding="utf-8")
    run = ingest_all(site, tmp_path / "runs")
    args = ["size", run, "--basis", ROOT / "basis" / "example_basis.yaml", "--scenarios", scenarios,
            "--catalog", ROOT / "catalog"]  # fmt: skip
    strict = cli(*args, "--strict")
    assert strict.exit_code == 4, strict.output
    assert "F_ELIG_ASSUMED in S2" in strict.stderr and "Traceback" not in strict.output
    assert (run / "scenarios" / "S2" / "result.json").is_file()  # all written, then the exit 4


def site_with_descriptions(data: Path, folder: Path) -> Path:
    """A copy of the generated site whose SKU master also has a free-text Description column."""
    shutil.copytree(data, folder)
    sku = pl.read_csv(folder / "sku_master.csv")
    sku.with_columns(Description=pl.lit("item ") + pl.col("SKU")).write_csv(
        folder / "sku_master.csv"
    )
    return folder


def test_R6_5_ingest_keep_descriptions_keeps_the_description_column(
    data: Path, tmp_path: Path
) -> None:
    """F10a open issue 9: the flag was only tested for exit 0."""
    site = site_with_descriptions(data, tmp_path / "site")
    for flag, kept in ((["--keep-descriptions"], True), ([], False)):
        res = cli("ingest", site / "sku_master.csv", "--dataset", "sku_master", "--non-interactive",
                  *flag, "--out-dir", tmp_path / f"runs{kept}")  # fmt: skip
        assert res.exit_code == 0, res.output
        columns = pl.read_parquet(run_path(res) / "canonical" / "sku_master.parquet").columns
        assert ("description" in columns) is kept


def test_R6_5_run_all_keep_descriptions_keeps_the_description_column(
    data: Path, tmp_path: Path, fake_report: ReportCalls
) -> None:
    """I78 (e): `run-all --keep-descriptions` reaches the runner's ingest (was: not an option)."""
    project = write_project(site_with_descriptions(data, tmp_path / "site"), tmp_path)
    kept = cli("run-all", project, "--keep-descriptions")
    assert kept.exit_code == 0, kept.output
    run = run_path(kept)
    assert "description" in pl.read_parquet(run / "canonical" / "sku_master.parquet").columns
    copy = yaml.safe_load((run / "inputs" / "project.yaml").read_text(encoding="utf-8"))
    assert copy["options"]["keep_descriptions"] is True
    dropped = cli("run-all", project)  # the default: free text is dropped (no reuse of `kept`)
    assert dropped.exit_code == 0, dropped.output
    plain = pl.read_parquet(run_path(dropped) / "canonical" / "sku_master.parquet").columns
    assert "description" not in plain


def test_T10_3_exit_3_run_all_on_tiny_golden_is_blocked_by_r9(
    tmp_path: Path, fake_report: ReportCalls
) -> None:
    project = write_project(ROOT / "tests" / "golden" / "tiny_golden" / "csv_en", tmp_path)
    fake_report.calls.clear()
    res = cli("run-all", project)
    assert res.exit_code == 3, res.output
    assert "R9" in res.stderr and "Traceback" not in res.output  # not even the runner's record
    assert fake_report.calls == []
    (run,) = (tmp_path / "runs").iterdir()
    log = (run / "logs" / "run.log").read_text(encoding="utf-8")
    assert '"run_failed"' in log and "Traceback (most recent call last)" in log  # kept in the file
    debug = cli("--debug", "run-all", project)
    assert debug.exit_code == 3 and "Traceback" in debug.stderr


def test_T10_3_exit_4_run_all_strict_with_a_building_that_fits_nothing(
    data: Path, tmp_path: Path, fake_report: ReportCalls
) -> None:
    project = write_project(data, tmp_path)
    text = yaml.safe_load(project.read_text(encoding="utf-8"))
    basis = tmp_path / "basis_small.yaml"
    raw = (ROOT / "basis" / "example_basis.yaml").read_text(encoding="utf-8")
    basis.write_text(raw.replace("area_m2: 12000", "area_m2: 50"), encoding="utf-8")
    text["basis"] = str(basis)
    project.write_text(yaml.safe_dump(text), encoding="utf-8")
    fake_report.calls.clear()
    res = cli("run-all", project, "--strict")
    assert res.exit_code == 4, res.output
    assert "strict" in res.stderr and fake_report.calls == []
    assert cli("run-all", project, "--no-strict").exit_code == 0  # same project, not strict


def issue(n: int) -> IntegrityIssue:
    return IntegrityIssue(
        id="IC1", severity="error", message=f"trace node {n} does not exist", location=f"cell {n}"
    )


def test_T10_3_exit_5_failed_integrity_check_builds_nothing(
    compared: Path, fake_report: ReportCalls, monkeypatch: pytest.MonkeyPatch
) -> None:
    found = [issue(n) for n in range(58)]
    monkeypatch.setattr(report_api, "check_integrity", lambda run: found, raising=False)
    fake_report.calls.clear()
    res = cli("report", compared)
    assert res.exit_code == 5, res.output
    assert "58 integrity check(s) failed" in res.stderr and "Traceback" not in res.output
    assert "  IC1 cell 0: trace node 0 does not exist" in res.stderr  # one line per issue
    assert "cell 19:" in res.stderr and "cell 20:" not in res.stderr  # the first 20 only
    assert "... and 38 more" in res.stderr
    assert max(len(line) for line in res.stderr.splitlines()) < 100  # no pydantic repr
    assert fake_report.calls == []


@pytest.mark.slow
def test_T10_3_exit_5_run_all_says_where_the_complete_run_is(
    project_yaml: Path, fake_report: ReportCalls, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(report_api, "check_integrity", lambda run: [issue(1)], raising=False)
    res = cli("run-all", project_yaml)
    assert res.exit_code == 5, res.output
    folder = re.search(r"run folder: (\S+)", res.stderr)
    assert folder and (Path(folder.group(1)) / "scenarios" / "S0" / "result.json").is_file()


def test_T10_3_exit_5_when_a_builder_raises_the_integrity_error(
    compared: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def build(run: RunOutput, lang: str) -> Path:
        raise ReportIntegrityError("IC8: untranslated key 'x' in the rendered HTML")

    monkeypatch.setattr(report_api, "build_pdf", build, raising=False)
    res = cli("report", compared, "--formats", "pdf")
    assert res.exit_code == 5 and "IC8" in res.stderr


def test_T10_3_exit_1_unexpected_failure_in_a_stage_is_logged_in_the_run(
    ingested: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(*_a: object, **_k: object) -> None:
        raise RuntimeError("stage boom")

    monkeypatch.setattr(cli_data, "build_tables", boom)
    run = copy_run(ingested, tmp_path)
    res = cli("profile", run)
    assert res.exit_code == 1
    assert "error: unexpected RuntimeError: stage boom" in res.stderr
    assert "Traceback" not in res.output  # short message only
    records = [
        json.loads(line)
        for line in (run / "logs" / "run.log").read_text(encoding="utf-8").splitlines()
        if line.startswith("{")
    ]
    failed = [r for r in records if r["event"] == "command_failed"]
    assert len(failed) == 1 and failed[0]["error_type"] == "RuntimeError"
    assert "Traceback (most recent call last)" in failed[0]["traceback"]
    assert "stage boom" in failed[0]["traceback"]
    assert failed[0]["run_id"] == run.name

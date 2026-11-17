"""T0.1: CI is green. GitHub Actions is not available here, so the test checks the workflow
structure (§3.4 stages and order) and runs the lint and typecheck gates locally."""

from __future__ import annotations

import itertools
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
STAGES = ["lint", "typecheck", "test", "docker-build", "docker-smoke", "bench"]
RECIPES = {"lint", "typecheck", "test", "test-fast", "golden-update", "demo", "docker-build",
           "docker-demo", "bench", "docs"}  # fmt: skip


def _run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=600)


def test_T0_1_ci_workflow_has_the_six_stages_in_order() -> None:
    wf = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())
    jobs = wf["jobs"]
    assert list(jobs) == STAGES
    for prev, job in itertools.pairwise(STAGES):
        assert jobs[job]["needs"] == prev, f"{job} must run after {prev}"
    test_steps = " ".join(str(s.get("run", "")) for s in jobs["test"]["steps"])
    assert "--cov" in test_steps and "--fail-under=80" in test_steps
    smoke = " ".join(str(s.get("run", "")) for s in jobs["docker-smoke"]["steps"])
    assert "run-all project/example_project.yaml" in smoke


@pytest.mark.skipif(shutil.which("just") is None, reason="just not installed")
def test_T0_1_justfile_has_every_section_3_2_recipe() -> None:
    out = _run(["just", "--summary"])
    assert out.returncode == 0, out.stderr
    assert set(out.stdout.split()) >= RECIPES


@pytest.mark.slow
@pytest.mark.parametrize(
    "cmd",
    [
        ["uv", "run", "ruff", "check", "src", "tests"],
        ["uv", "run", "ruff", "format", "--check", "src", "tests"],
        ["uv", "run", "pyright"],
    ],
    ids=["ruff-check", "ruff-format", "pyright"],
)
def test_T0_1_lint_and_typecheck_gates_pass(cmd: list[str]) -> None:
    out = _run(cmd)
    assert out.returncode == 0, out.stdout[-3000:] + out.stderr[-3000:]


BENCH_TESTS = {  # the five C5 rows: stage -> test function (R8c, audit L1)
    "ingest + validate": "test_C5_bench_ingest_and_validate_1m_line_csv",
    "profile": "test_T3_8_one_million_lines_profiled_under_60_s",
    "size": "test_T8_5_three_scenarios_times_three_worlds_run_in_under_10_seconds",
    "sensitivity": "test_same_inputs_give_byte_identical_json_and_the_run_time_is_seconds",
    "report": "test_T9_7_the_excel_and_the_pdf_are_built_in_under_60_seconds_together",
}


@pytest.mark.slow
def test_R8c_just_bench_and_the_ci_bench_job_collect_all_five_c5_budgets() -> None:
    """`just bench` and the CI bench job run `pytest -m bench`: each C5 row has a test in it."""
    out = _run([sys.executable, "-m", "pytest", "--collect-only", "-q", "-m", "bench", "tests"])
    assert out.returncode == 0, out.stdout[-2000:] + out.stderr[-2000:]
    collected = {line.partition("::")[2] for line in out.stdout.splitlines() if "::" in line}
    assert set(BENCH_TESTS.values()) <= collected, set(BENCH_TESTS.values()) - collected
    justfile = (ROOT / "justfile").read_text(encoding="utf-8")
    assert "uv run pytest -m bench" in justfile.split("bench:", 1)[1]


def test_R8c_golden_update_regenerates_the_syrupy_snapshots_after_a_confirmation() -> None:
    """It used to run `pytest tests/golden --snapshot-update`, which regenerates nothing."""
    lines = (ROOT / "justfile").read_text(encoding="utf-8").splitlines()
    at = lines.index("golden-update:")
    assert lines[at - 1].startswith("[confirm(")  # the prompt stays
    assert lines[at + 1].strip() == "uv run pytest tests/e2e/test_snapshots.py --snapshot-update"
    note = "\n".join(lines[:at])
    assert "tests.golden.build_golden" in note and "golden_values.json" in note
    assert (ROOT / "tests/e2e/test_snapshots.py").is_file()
    assert (ROOT / "tests/e2e/__snapshots__/test_snapshots.ambr").stat().st_size > 10_000

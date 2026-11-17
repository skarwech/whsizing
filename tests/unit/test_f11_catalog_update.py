"""F11 step 9: catalog update from a single-site calibration, always on a temp COPY."""

from __future__ import annotations

import hashlib
import shutil
from datetime import date
from pathlib import Path

import pytest
from tests.unit.test_f11_pipeline import write_actuals
from tests.unit.test_f11_predict import site_inputs

from whsizing.calibration import FitReport, baseline_monthly, calibrate, update_catalog
from whsizing.calibration.catalog_update import SHARE_ID
from whsizing.calibration.models import ThetaRow
from whsizing.catalog import load_catalog
from whsizing.errors import ConfigError

ROOT = Path(__file__).resolve().parents[2]
REPO_CATALOG = ROOT / "catalog"
DAY = date(2026, 11, 20)


def digest(folder: Path) -> dict[str, str]:
    return {
        p.relative_to(folder).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(folder.rglob("*"))
        if p.is_file()
    }


@pytest.fixture(scope="module")
def report(tmp_path_factory: pytest.TempPathFactory) -> FitReport:
    inputs = site_inputs()
    folder = tmp_path_factory.mktemp("cal")
    csv_path, map_path = write_actuals(folder, baseline_monthly(inputs), extra=False)
    return calibrate(inputs, csv_path, map_path, folder / "out").fit


@pytest.fixture
def copy(tmp_path: Path) -> Path:
    """A COPY of the catalog; the repo's `catalog/` is never touched."""
    dest = tmp_path / "catalog_copy"
    shutil.copytree(REPO_CATALOG, dest)
    return dest


def only(rep: FitReport, name: str, value: float) -> FitReport:
    """A report that calibrates one activity at `value`."""
    keep: list[ThetaRow] = [t for t in rep.theta if t.name == f"m:{name}"]
    keep = [keep[0].model_copy(update={"effective": value})]
    return rep.model_copy(update={"theta": keep, "targets": {name: rep.targets[name]}})


def test_typ_is_updated_within_range_without_a_reviewer(copy: Path, report: FitReport) -> None:
    before = digest(REPO_CATALOG)
    changes = update_catalog(copy, report, site="Site A", today=DAY)
    assert digest(REPO_CATALOG) == before  # the repo catalog is untouched
    applied = {c.param: c for c in changes if c.applied}
    assert applied["labor.receiving"].old_typ == 14.0
    eff = next(t.effective for t in report.theta if t.name == "m:receiving")
    assert eff is not None
    assert applied["labor.receiving"].new_typ == pytest.approx(14.0 * eff, rel=1e-5)
    cat = load_catalog(copy)  # the copy still validates
    for p, c in applied.items():
        param = cat.params[p]
        assert param.typ == pytest.approx(c.new_typ)
        assert param.min <= param.typ <= param.max
        assert param.confidence == "L" and param.validated_by is None  # no reviewer
    assert cat.params["manual_p2p.forklift_moves_h"].typ == 16  # not a labor standard: untouched
    assert {"manual_p2p.pick_rate_shelving_lines_h", "labor.packing_ML"} <= set(applied)


def test_a_reviewer_sets_confidence_m_and_validated_by(copy: Path, report: FitReport) -> None:
    changes = update_catalog(copy, report, reviewer="J. Martin", site="Site A", today=DAY)
    cat = load_catalog(copy)
    for c in changes:
        if c.applied:
            p = cat.params[c.param]
            assert p.confidence == "M" and p.validated_by == "J. Martin", c.param
    assert cat.params["manual_p2p.forklift_moves_h"].confidence == "L"  # not calibrated


def test_an_existing_validated_by_is_replaced_and_confidence_h_is_kept(
    copy: Path, report: FitReport
) -> None:
    path = copy / "labor_standards.yaml"
    text = path.read_text(encoding="utf-8")
    text = text.replace("id: labor.receiving, unit", "id: labor.receiving, validated_by: Old, unit")
    text = text.replace(
        "typ: 13, max: 16, source: TODO, confidence: L",
        "typ: 13, max: 16, source: TODO, confidence: H",
    )
    path.write_text(text, encoding="utf-8")
    update_catalog(copy, report, reviewer="New Person", today=DAY)
    after = path.read_text(encoding="utf-8")
    line = next(x for x in after.splitlines() if "id: labor.receiving," in x)
    assert line.count("validated_by") == 1 and '"New Person"' in line
    cat = load_catalog(copy)
    assert cat.params["labor.receiving"].validated_by == "New Person"
    assert cat.params["labor.put_away"].confidence == "H"  # never lowered


def test_typ_outside_the_current_range_is_not_updated(copy: Path, report: FitReport) -> None:
    """A single site never widens a range: picking × 1.5 would give 105 and 52.5 lines/h (the
    ranges end at 95 and 50): skipped, with the reason."""
    rep = only(report, "picking", 1.5)
    changes = update_catalog(copy, rep, reviewer="J. Martin", today=DAY)
    assert [c.applied for c in changes] == [False, False]
    assert all("outside the current range" in c.reason for c in changes)
    assert {c.param: c.new_typ for c in changes} == {
        "manual_p2p.pick_rate_shelving_lines_h": 105.0,
        "manual_p2p.pick_rate_pallet_lines_h": 52.5,
    }
    assert digest(copy) == digest(REPO_CATALOG)  # nothing changed, nothing logged


def test_one_param_in_and_one_out_of_range(copy: Path, report: FitReport) -> None:
    """picking × 1.4: shelving 70 → 98 > 95 skipped; pallet 35 → 49 ≤ 50 applied."""
    changes = {c.param: c for c in update_catalog(copy, only(report, "picking", 1.4), today=DAY)}
    assert not changes["manual_p2p.pick_rate_shelving_lines_h"].applied
    assert changes["manual_p2p.pick_rate_pallet_lines_h"].applied
    cat = load_catalog(copy)
    assert cat.params["manual_p2p.pick_rate_shelving_lines_h"].typ == 70
    assert cat.params["manual_p2p.pick_rate_pallet_lines_h"].typ == pytest.approx(49.0)


def test_changelog_gets_one_dated_entry(copy: Path, report: FitReport) -> None:
    old = (copy / "CHANGELOG.md").read_text(encoding="utf-8")
    update_catalog(copy, report, reviewer="J. Martin", site="Site A", today=DAY)
    new = (copy / "CHANGELOG.md").read_text(encoding="utf-8")
    assert new.startswith(old.rstrip())
    entry = new[len(old.rstrip()) :]
    assert "## calibration, 1 site(s) (Site A) — 2026-11-20" in entry
    assert "reviewer: J. Martin" in entry and "`labor.receiving` typ 14 → " in entry
    assert entry.count("## calibration") == 1
    unreviewed = shutil.copytree(REPO_CATALOG, copy.parent / "other")
    update_catalog(unreviewed, report, today=DAY)
    assert "not reviewed" in (unreviewed / "CHANGELOG.md").read_text(encoding="utf-8")


def test_comments_and_layout_survive(copy: Path, report: FitReport) -> None:
    update_catalog(copy, report, today=DAY)
    for name in ("labor_standards.yaml", "families/manual_p2p.yaml"):
        old = (REPO_CATALOG / name).read_text(encoding="utf-8").splitlines()
        new = (copy / name).read_text(encoding="utf-8").splitlines()
        assert len(old) == len(new)
        changed = [i for i, (a, b) in enumerate(zip(old, new, strict=True)) if a != b]
        assert changed and all("typ:" in old[i] for i in changed)
        assert all(
            a.partition("#")[2] == b.partition("#")[2] for a, b in zip(old, new, strict=True)
        )
    assert "# [P] F6c line 968" in (copy / "labor_standards.yaml").read_text(encoding="utf-8")


def test_the_indirect_share_is_reported_not_written(copy: Path, report: FitReport) -> None:
    changes = {c.param: c for c in update_catalog(copy, report, today=DAY)}
    share = changes[SHARE_ID]
    m = next(t.fitted for t in report.theta if t.name == "m:indirect")
    assert not share.applied and share.old_typ == 0.12
    assert share.new_typ == pytest.approx(0.12 / m) and "constant" in share.reason
    text = (copy / "labor_standards.yaml").read_text(encoding="utf-8")
    assert "share_of_direct_hours: 0.12" in text


def test_a_bad_target_restores_the_files_and_a_non_catalog_folder_is_refused(
    copy: Path, report: FitReport, tmp_path: Path
) -> None:
    bad = report.model_copy(update={"targets": {**report.targets, "put_away": [
        report.targets["put_away"][0].model_copy(update={"param": "labor.nope"})
    ]}})  # fmt: skip
    with pytest.raises(ConfigError, match=r"labor\.nope"):
        update_catalog(copy, bad, today=DAY)
    assert digest(copy) == digest(REPO_CATALOG)
    with pytest.raises(ConfigError, match="not a catalog folder"):
        update_catalog(tmp_path, report)


def test_an_unidentified_multiplier_is_not_written(copy: Path, report: FitReport) -> None:
    theta = [
        t.model_copy(update={"identified": False}) if t.name == "m:picking" else t
        for t in report.theta
    ]
    changes = update_catalog(copy, report.model_copy(update={"theta": theta}), today=DAY)
    assert not any("pick_rate" in c.param for c in changes)

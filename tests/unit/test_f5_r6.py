"""R6 remediation of the F5 finding: `validate_catalog` reports every file error of a catalog
folder, where `load_catalog` stops at the first (`whsizing validate-catalog`, F10)."""

from __future__ import annotations

from pathlib import Path

import pytest
from tests.unit.test_f5_loader import BAD, BAD_CASES, CATALOG, _overlay  # pyright: ignore[reportPrivateUsage]

from whsizing.catalog import load_catalog
from whsizing.catalog.loader import validate_catalog
from whsizing.errors import ConfigError


def test_R6_3_the_shipped_catalog_has_no_error() -> None:
    assert validate_catalog(CATALOG) == []


@pytest.mark.parametrize("case", sorted(BAD_CASES))
def test_R6_3_validate_catalog_reports_what_load_catalog_raises_on_each_malformed_fixture(
    case: str, tmp_path: Path
) -> None:
    cat = _overlay(tmp_path, BAD / case)
    with pytest.raises(ConfigError) as exc:
        load_catalog(cat)
    assert validate_catalog(cat) == [str(exc.value)]


def test_R6_3_every_broken_file_is_reported_not_only_the_first(tmp_path: Path) -> None:
    """Two family files and a supporting file are broken: load_catalog names `amr_gtp` only."""
    cat = _overlay(tmp_path, {})
    for rel in ("families/amr_gtp.yaml", "families/cube_asrs.yaml", "area_factors.yaml"):
        path = cat / rel
        path.write_text(path.read_text(encoding="utf-8") + "\nsurprise_key: 1\n", encoding="utf-8")
    with pytest.raises(ConfigError) as exc:
        load_catalog(cat)
    assert "amr_gtp.yaml" in str(exc.value) and "cube_asrs.yaml" not in str(exc.value)
    errors = validate_catalog(cat)
    assert len(errors) == 3
    for name, error in zip(
        ["amr_gtp.yaml", "cube_asrs.yaml", "area_factors.yaml"], errors, strict=True
    ):
        assert name in error and "surprise_key" in error and "unknown key" in error


def test_R6_3_structural_and_file_errors_come_together(tmp_path: Path) -> None:
    cat = _overlay(tmp_path, {"extra.yaml": "a: 1\n"})
    (cat / "icpe_1510.yaml").unlink()
    path = cat / "finance_defaults.yaml"
    path.write_text(path.read_text(encoding="utf-8") + "\nsurprise_key: 1\n", encoding="utf-8")
    errors = validate_catalog(cat)
    assert len(errors) == 2
    assert "unknown catalog file(s) ['extra.yaml']" in errors[0] and "icpe_1510.yaml" in errors[0]
    assert "finance_defaults.yaml" in errors[1] and "surprise_key" in errors[1]


def test_R6_3_a_missing_catalog_folder_is_one_error(tmp_path: Path) -> None:
    (error,) = validate_catalog(tmp_path / "nowhere")
    assert "nowhere" in error and "catalog folder not found" in error

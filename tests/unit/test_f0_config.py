"""F0 config loaders: ConfigError (exit 2) on unknown keys, readable messages, path resolution."""

from __future__ import annotations

from pathlib import Path

import pytest
from tests.fixtures import FIXTURES, mock_basis

from whsizing.config import load_project, load_yaml_model
from whsizing.errors import ConfigError
from whsizing.schemas import DesignBasis, ScenarioSet

CFG = FIXTURES / "config"


def test_valid_basis_yaml_loads_and_matches_mock() -> None:
    assert load_yaml_model(CFG / "basis_valid.yaml", DesignBasis).model_dump(
        exclude={"baseline": {"actual_hours_month", "equipment"}}
    ) == mock_basis().model_dump(exclude={"baseline": {"actual_hours_month", "equipment"}})


def test_basis_unknown_key_raises_config_error_exit_2() -> None:
    with pytest.raises(ConfigError) as exc:
        load_yaml_model(CFG / "basis_unknown_key.yaml", DesignBasis)
    assert exc.value.exit_code == 2
    msg = str(exc.value)
    assert "basis_unknown_key.yaml" in msg
    assert "building.roof_colour: unknown key" in msg


def test_unquoted_time_is_rejected_not_read_as_900() -> None:
    with pytest.raises(ConfigError, match=r"service\.cutoff_time: .*quoted"):
        load_yaml_model(CFG / "basis_unquoted_time.yaml", DesignBasis)


@pytest.mark.parametrize(
    ("text", "match"),
    [("a: [unclosed", "invalid YAML"), ("- 1\n- 2\n", "mapping"), ("", "mapping")],
)
def test_malformed_yaml_raises_config_error(tmp_path: Path, text: str, match: str) -> None:
    p = tmp_path / "bad.yaml"
    p.write_text(text)
    with pytest.raises(ConfigError, match=match):
        load_yaml_model(p, DesignBasis)


def test_missing_file_raises_config_error(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="cannot read"):
        load_yaml_model(tmp_path / "absent.yaml", DesignBasis)


def test_load_project_resolves_paths_relative_to_yaml() -> None:
    project = load_project(CFG / "project_example.yaml")
    base = CFG.resolve()
    assert project.basis == base / "basis/client_x.yaml"
    assert project.out_dir == base / "runs"
    assert project.salt_file == Path.home() / ".whsizing/salt_client_x"
    ol = project.inputs["order_lines"]
    assert ol is not None and ol.files[0] == base / "data/ventes_2025.csv"
    inv = project.inputs["inventory"]
    assert inv is not None and inv.files[0].name == "stock_*.csv"  # globs kept for the reader
    assert project.inputs["receipts"] is None
    assert project.profile_cfg.dead_stock_days == 180
    assert project.options.worlds == "all"


def test_scenarios_example_loads_and_duplicate_id_is_config_error(tmp_path: Path) -> None:
    ok = load_yaml_model(CFG / "scenarios_example.yaml", ScenarioSet)
    assert [s.id for s in ok.scenarios] == ["S0", "S1", "S2"]
    dup = tmp_path / "dup.yaml"
    dup.write_text((CFG / "scenarios_example.yaml").read_text().replace("id: S1", "id: S0"))
    with pytest.raises(ConfigError, match="duplicate scenario id"):
        load_yaml_model(dup, ScenarioSet)

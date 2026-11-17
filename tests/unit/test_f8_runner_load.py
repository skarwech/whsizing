"""F8a scenarios.yaml loading: T8.1 (duplicate id), the id guard, the Appendix E examples."""

from __future__ import annotations

from pathlib import Path

import pytest

from whsizing.config import load_project
from whsizing.errors import ConfigError
from whsizing.scenarios import load_scenarios

ROOT = Path(__file__).resolve().parents[2]


def write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "scenarios.yaml"
    path.write_text(text, encoding="utf-8")
    return path


def test_T8_1_duplicate_scenario_id_is_a_config_error(tmp_path: Path) -> None:
    path = write(
        tmp_path,
        """
scenarios:
  - {id: S0, name: "Manual", family: manual_p2p}
  - {id: S1, name: "AMR", family: amr_gtp}
  - {id: S0, name: "Manual again", family: manual_p2p}
baseline: client_current
""",
    )
    with pytest.raises(ConfigError, match=r"duplicate scenario id.*S0"):
        load_scenarios(path)


@pytest.mark.parametrize(
    "bad_id", ["../etc", "S 1", "S/1", "é", "x" * 65, "client_current"], ids=repr
)
def test_T8_1_id_guard_rejects_ids_that_cannot_name_a_folder(tmp_path: Path, bad_id: str) -> None:
    path = write(tmp_path, f'scenarios:\n  - {{id: "{bad_id}", name: "x", family: manual_p2p}}\n')
    with pytest.raises(ConfigError, match=r"scenario id|reserved"):
        load_scenarios(path)


@pytest.mark.parametrize(("first", "second"), [("a", "A"), ("S0", "s0"), ("Ab_1", "aB_1")])
def test_ids_that_differ_only_by_case_are_refused(tmp_path: Path, first: str, second: str) -> None:
    """`a` and `A` are one folder `scenarios/<id>/` on macOS and Windows: the second scenario
    would overwrite the first one's result.json, finance.json and trace.jsonl."""
    rows = "".join(f'  - {{id: "{i}", name: "n", family: manual_p2p}}\n' for i in (first, second))
    with pytest.raises(ConfigError, match=rf"'{first}' and '{second}' differ only by case"):
        load_scenarios(write(tmp_path, f"scenarios:\n{rows}"))


def test_id_guard_accepts_64_characters_dash_and_underscore(tmp_path: Path) -> None:
    ids = ["A-1_b", "x" * 64]
    rows = "".join(f'  - {{id: "{i}", name: "n", family: manual_p2p}}\n' for i in ids)
    loaded = load_scenarios(write(tmp_path, f"scenarios:\n{rows}"))
    assert [s.id for s in loaded.scenarios] == ids
    assert loaded.baseline == "client_current"


def test_unknown_baseline_empty_list_and_unknown_key_are_config_errors(tmp_path: Path) -> None:
    one = '  - {id: S0, name: "n", family: manual_p2p}\n'
    for text in (
        f"scenarios:\n{one}baseline: S9\n",
        "scenarios: []\n",
        f"scenarios:\n{one}extra: 1\n",
        "scenarios:\n  - {id: S0, name: n, family: warp_drive}\n",
    ):
        with pytest.raises(ConfigError):
            load_scenarios(write(tmp_path, text))


def test_is_baseline_must_agree_with_the_baseline_key(tmp_path: Path) -> None:
    """`baseline:` decides; an is_baseline scenario it does not name is a conflict, not ignored."""

    def text(is_baseline: str, baseline: str) -> str:
        return (
            f'scenarios:\n  - {{id: S0, name: "n", family: manual_p2p, '
            f'is_baseline: {is_baseline}}}\n  - {{id: S1, name: "m", family: amr_gtp}}\n'
            f"baseline: {baseline}\n"
        )

    assert load_scenarios(write(tmp_path, text("true", "S0"))).baseline == "S0"
    assert load_scenarios(write(tmp_path, text("false", "S1"))).baseline == "S1"
    for baseline in ("client_current", "S1"):  # S0 says it is the baseline, the file says not
        with pytest.raises(ConfigError, match=r"S0.*is_baseline: true.*baseline: S0"):
            load_scenarios(write(tmp_path, text("true", baseline)))


def test_example_scenarios_and_project_load() -> None:
    scenarios = load_scenarios(ROOT / "scenarios" / "example_scenarios.yaml")
    assert [(s.id, s.family) for s in scenarios.scenarios] == [
        ("S0", "manual_p2p"),
        ("S1", "amr_gtp"),
        ("S2", "cube_asrs"),
    ]
    assert scenarios.baseline == "client_current"
    assert scenarios.scenarios[1].overrides == {"amr_gtp.station_rate_lines_h": 230}
    project = load_project(ROOT / "project" / "example_project.yaml")
    assert project.basis.name == "example_basis.yaml"
    assert project.scenarios.name == "example_scenarios.yaml"
    assert {ds: len(spec.files) for ds, spec in project.inputs.items() if spec} == dict.fromkeys(
        ("order_lines", "sku_master", "inventory", "receipts"), 1
    )
    assert all("data/generated/ecom_mid" in str(s.files[0]) for s in project.inputs.values() if s)

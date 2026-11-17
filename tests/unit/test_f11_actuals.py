"""F11 step 1: actuals.csv + activity_map.yaml -> monthly hours per target activity (T11.2)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from whsizing.calibration.actuals import Actuals, load_actuals, read_actuals
from whsizing.errors import ConfigError, DataQualityError

GROUPS = (
    "receiving",
    "put_away",
    "replenishment",
    "picking",
    "packing",
    "shipping",
    "returns",
    "indirect",
)
HEAD = "month,activity_client,hours,headcount,temp_hours\n"
MAP = """activities:
  Picking: picking
  "Packing  Station": packing
  Supervision: indirect
"""


def put(tmp_path: Path, name: str, text: str) -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def csv_rows(*rows: tuple[str, str, str, str, str]) -> str:
    return HEAD + "".join(",".join(r) + "\n" for r in rows)


def load(tmp_path: Path, csv_text: str, amap: str = MAP, paid: float | None = None) -> Actuals:
    return load_actuals(
        put(tmp_path, "actuals.csv", csv_text), put(tmp_path, "map.yaml", amap), GROUPS, paid
    )


def codes(a) -> list[str]:
    return [f.code for f in a.flags]


def test_T11_2_unmapped_activity_goes_to_indirect_with_a_warning(tmp_path: Path) -> None:
    """A client label absent from the map: its hours join `indirect` (with the labels mapped to
    it) and a warning names the label and the hours moved; mapped activities are untouched."""
    rows = [
        ("2025-01", "Picking", "1000", "", ""),
        ("2025-02", "Picking", "1100", "", ""),
        ("2025-01", "Supervision", "100", "", ""),
        ("2025-02", "Supervision", "110", "", ""),
        ("2025-01", "Cleaning", "30", "", ""),
        ("2025-02", "Cleaning", "40", "", ""),
    ]
    a = load(tmp_path, csv_rows(*rows))
    assert a.months == ("2025-01", "2025-02")
    assert a.hours["indirect"].tolist() == [130.0, 150.0]  # supervision + cleaning
    assert a.hours["picking"].tolist() == [1000.0, 1100.0]
    warn = next(f for f in a.flags if f.code == "W_UNMAPPED_ACTIVITY:Cleaning")
    assert warn.severity == "warning" and warn.value == 70.0
    assert "Cleaning" in warn.message and "indirect" in warn.message
    assert not any(c.startswith("W_UNMAPPED_ACTIVITY:Picking") for c in codes(a))


def test_many_labels_map_to_one_activity_and_labels_match_loosely(tmp_path: Path) -> None:
    amap = MAP + "  Prep: picking\n"
    rows = [
        ("2025-01", " picking ", "600", "", ""),
        ("2025-01", "PREP", "400", "", ""),
        ("2025-01", "packing station", "50", "", ""),
    ]
    a = load(tmp_path, csv_rows(*rows), amap)
    assert a.hours["picking"].tolist() == [1000.0]
    assert a.hours["packing"].tolist() == [50.0]
    assert "indirect" not in a.hours and not any(c.startswith("W_UNMAPPED") for c in codes(a))


def test_headcount_only_rows_become_hours_with_the_paid_hours_per_month(tmp_path: Path) -> None:
    rows = [("2025-01", "Picking", "", "10", ""), ("2025-02", "Picking", "500", "", "")]
    a = load(tmp_path, csv_rows(*rows), paid=1607 / 12)
    assert a.hours["picking"].tolist() == pytest.approx([10 * 1607 / 12, 500.0])
    assert "I_HEADCOUNT_ONLY:picking" in codes(a)
    with pytest.raises(ConfigError, match="paid hours per month"):
        load(tmp_path, csv_rows(*rows))


def test_temps_not_separated_is_noted_and_separated_temps_give_the_share(tmp_path: Path) -> None:
    plain = load(tmp_path, csv_rows(("2025-01", "Picking", "100", "", "")))
    assert plain.temp_share is None and "I_TEMPS_COMBINED" in codes(plain)
    rows = [("2025-01", "Picking", "100", "", "20"), ("2025-01", "Supervision", "100", "", "0")]
    split = load(tmp_path, csv_rows(*rows))
    assert split.temp_share == pytest.approx(0.1) and "I_TEMPS_COMBINED" not in codes(split)


def test_client_specific_activity_must_be_declared_and_is_flagged(tmp_path: Path) -> None:
    rows = [("2025-01", "Picking", "100", "", ""), ("2025-01", "Kitting", "40", "", "")]
    declared = MAP + "  Kitting: kitting\nclient_activities: [kitting]\n"
    a = load(tmp_path, csv_rows(*rows), declared)
    assert a.client_activities == ("kitting",) and a.hours["kitting"].tolist() == [40.0]
    assert "F_CLIENT_ACTIVITY:kitting" in codes(a)
    with pytest.raises(ConfigError, match="kitting") as e:
        load(tmp_path, csv_rows(*rows), MAP + "  Kitting: kitting\n")
    assert "client_activities" in str(e.value)


def test_a_typo_in_the_map_target_suggests_the_model_activity(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="receiving"):
        load(tmp_path, csv_rows(("2025-01", "Dock", "5", "", "")), MAP + "  Dock: recieving\n")


def test_an_activity_the_family_lacks_is_an_error(tmp_path: Path) -> None:
    """decant is not an activity of the manual family (GROUPS): map it elsewhere or declare it."""
    with pytest.raises(ConfigError, match="decant"):
        load(tmp_path, csv_rows(("2025-01", "Dock", "5", "", "")), MAP + "  Dock: decant\n")


def test_semicolon_file_with_decimal_commas(tmp_path: Path) -> None:
    text = "month;activity_client;hours\n2025-01;Picking;1234,5\n2025-02;Picking;1000\n"
    rows, _ = read_actuals(put(tmp_path, "a.csv", text))
    assert [r.hours for r in rows] == [1234.5, 1000.0]


@pytest.mark.parametrize(
    ("text", "match"),
    [
        ("", "needs columns"),
        ("month,activity_client\n2025-01,Picking\n", "needs columns"),
        ("month,hours\n2025-01,5\n", "needs columns"),
        ("month,activity_client,hours\n", "no data row"),
        ("month,activity_client,hours\n2025/01,Picking,5\n", "line 2"),
        ("month,activity_client,hours\n2025-13,Picking,5\n", "line 2"),
        ("month,activity_client,hours\n2025-01,Picking,abc\n", "not a number"),
        ("month,activity_client,hours\n2025-01,Picking,-5\n", "greater than or equal to 0"),
        ("month,activity_client,hours\n2025-01,Picking,nan\n", "line 2"),
        ("month,activity_client,hours,site\n2025-01,Picking,5,x\n", "site"),
        ("month,activity_client,hours\n2025-01,Picking,5,9\n", "more cells"),
        ("month,activity_client,hours,headcount\n2025-01,Picking,,\n", "neither hours nor"),
        ("month,activity_client,hours\n2025-01,Picking,5\n2025-01,picking,6\n", "twice"),
        ("month,activity_client,hours,temp_hours\n2025-01,Picking,5,9\n", "temp_hours exceeds"),
        (
            "month,activity_client,hours\n2025-01,Picking,5\n2025-02,Picking,5\n2025-01,Pack,1\n",
            "no row for",
        ),
    ],
)
def test_malformed_actuals_raise_data_quality_errors(tmp_path: Path, text: str, match: str) -> None:
    with pytest.raises(DataQualityError, match=match):
        load(tmp_path, text, MAP + "  Pack: packing\n")


@pytest.mark.parametrize(
    "amap",
    [
        "activities: {Picking: picking}\nunknown: 1\n",
        "client_activities: [kitting]\n",
        "activities: {Picking: picking}\nclient_activities: [Kitting-X]\n",
        "activities: {Picking: picking}\nclient_activities: [picking]\n",
        "activities: {Picking: ''}\n",
        "- not a mapping\n",
    ],
)
def test_malformed_activity_maps_raise_config_errors(tmp_path: Path, amap: str) -> None:
    with pytest.raises(ConfigError):
        load(tmp_path, csv_rows(("2025-01", "Picking", "5", "", "")), amap)


def test_a_missing_file_is_a_clear_error(tmp_path: Path) -> None:
    with pytest.raises(DataQualityError, match="cannot read"):
        read_actuals(tmp_path / "absent.csv")
    with pytest.raises(ConfigError, match="cannot read"):
        load_actuals(put(tmp_path, "a.csv", HEAD), tmp_path / "absent.yaml", GROUPS)


def test_hours_arrays_are_float_and_sorted_by_month(tmp_path: Path) -> None:
    rows = [("2025-03", "Picking", "3", "", ""), ("2025-01", "Picking", "1", "", "")]
    a = load(tmp_path, csv_rows(*rows))
    assert a.months == ("2025-01", "2025-03")
    assert a.hours["picking"].dtype == np.float64 and a.hours["picking"].tolist() == [1.0, 3.0]


def test_a_month_absent_for_every_label_is_flagged(tmp_path: Path) -> None:
    months = ("2024-11", "2025-01", "2025-02", "2025-05")  # 2024-12, 2025-03 and 2025-04 absent
    a = load(tmp_path, csv_rows(*[(m, "Picking", "100", "", "") for m in months]))
    missing = [c for c in codes(a) if c.startswith("W_MISSING_MONTH")]
    assert missing == [f"W_MISSING_MONTH:{m}" for m in ("2024-12", "2025-03", "2025-04")]
    full = load(tmp_path, csv_rows(*[(m, "Picking", "1", "", "") for m in months[1:3]]))
    assert not [c for c in codes(full) if c.startswith("W_MISSING_MONTH")]


def test_map_keys_equal_after_normalisation_must_agree(tmp_path: Path) -> None:
    rows = csv_rows(("2025-01", "Picking", "100", "", ""))
    with pytest.raises(ConfigError, match="same label") as e:
        load(tmp_path, rows, MAP + "  PICKING: packing\n")
    assert "'picking'" in str(e.value) and "'packing'" in str(e.value)
    ok = load(tmp_path, rows, MAP + "  PICKING: picking\n")  # same target: harmless
    assert ok.hours["picking"].tolist() == [100.0]

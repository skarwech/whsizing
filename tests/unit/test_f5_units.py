"""I87 / L6: units are checked at the parameter layer with pint (spec principle 3, section 3.1).

`whsizing.units` holds the one registry; `Param.unit` must be `-` or a unit of it, and the catalog
loader turns a bad unit into a ConfigError that names the file, the key, the id and the unit.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import pytest
import yaml
from pydantic import ValidationError

from whsizing.catalog import load_catalog
from whsizing.catalog.loader import validate_catalog
from whsizing.errors import ConfigError
from whsizing.schemas import Param
from whsizing.units import is_unit, registry

ROOT = Path(__file__).resolve().parents[2]
CATALOG = ROOT / "catalog"
PARAM = {"min": 1.0, "typ": 2.0, "max": 3.0, "source": "TODO", "confidence": "L", "date": "2026-11"}


def yaml_units(node: Any) -> list[str]:
    """Every `unit:` value of a parsed catalog file (a Param block has `unit` and `typ`)."""
    if isinstance(node, dict):
        own = [node["unit"]] if "unit" in node and "typ" in node else []
        return own + [u for v in node.values() for u in yaml_units(v)]
    if isinstance(node, list):
        return [u for v in node for u in yaml_units(v)]
    return []


def test_I87_every_unit_written_in_the_catalog_files_parses() -> None:
    units = [
        u
        for f in sorted(CATALOG.rglob("*.yaml"))
        for u in yaml_units(yaml.safe_load(f.read_text(encoding="utf-8")))
    ]
    assert len(units) >= 72  # every Param block of the shipped catalog was looked at
    assert {u for u in units if not is_unit(u)} == set()
    assert {"eur/m2", "lines/h", "1/m2", "robots/m2", "m2", "kWh", "eur", "units", "-"} <= set(
        units
    )


def test_I87_every_loaded_param_has_a_pint_unit() -> None:
    catalog = load_catalog(CATALOG)
    assert len(catalog.params) == 72
    bad = {pid: p.unit for pid, p in catalog.params.items() if not is_unit(p.unit)}
    assert bad == {}


@pytest.mark.parametrize(
    "unit",
    [
        "eur/m2", "lines/h", "kEUR", "1/m2", "units", "pallets/shift", "units/month", "-", "h",
        "m3", "eur/m3", "pallets/m3", "FTE", "FTE/shift", "FTEs", "fte",
    ],
)  # fmt: skip
def test_I87_spec_and_project_units_parse(unit: str) -> None:
    assert is_unit(unit)


@pytest.mark.parametrize("unit", ["banana/h", "", "  ", "3 lines", "lines/", "(", "lines/banana"])
def test_I87_unknown_or_malformed_units_are_rejected(unit: str) -> None:
    assert not is_unit(unit)


def test_I87_countable_units_are_dimensions_of_their_own() -> None:
    ureg = registry()
    assert ureg.get_dimensionality("lines/h") != ureg.get_dimensionality("orders/h")
    assert ureg.get_dimensionality("eur/m2") != ureg.get_dimensionality("1/m2")
    assert ureg.get_dimensionality("m2") == ureg.get_dimensionality("meter ** 2")
    assert ureg.Quantity(1, "kEUR").to("eur").magnitude == pytest.approx(1000.0)
    assert ureg.Quantity(1, "lines/h").to("lines/min").magnitude == pytest.approx(1 / 60)


def test_I87_param_rejects_a_bad_unit_and_names_id_and_unit() -> None:
    with pytest.raises(ValidationError, match=r"x\.rate: unit 'banana/h' is not a pint unit"):
        Param(id="x.rate", unit="banana/h", pessimistic_end="min", **PARAM)  # type: ignore[arg-type]
    ok = Param(id="x.rate", unit="lines/h", pessimistic_end="min", **PARAM)  # type: ignore[arg-type]
    assert ok.unit == "lines/h"


def overlay(tmp_path: Path, relpath: str, old: str, new: str) -> Path:
    """The shipped catalog copied to tmp_path with `old` replaced by `new` in one file."""
    dest = tmp_path / "catalog"
    shutil.copytree(CATALOG, dest)
    text = (dest / relpath).read_text(encoding="utf-8")
    assert old in text
    (dest / relpath).write_text(text.replace(old, new, 1), encoding="utf-8")
    return dest


def test_I87_loader_rejects_a_bad_unit_with_the_id_and_the_unit(tmp_path: Path) -> None:
    text = (CATALOG / "finance_defaults.yaml").read_text(encoding="utf-8")
    assert "packaging_eur_per_order" in text
    bad = overlay(tmp_path, "finance_defaults.yaml", 'unit: "eur"', 'unit: "banana/h"')
    with pytest.raises(ConfigError) as err:
        load_catalog(bad)
    message = str(err.value)
    assert "finance_defaults.yaml" in message and "banana/h" in message
    assert "finance.packaging_eur_per_order" in message
    errors = validate_catalog(bad)  # `catalog validate` reports it too
    assert len(errors) == 1 and "banana/h" in errors[0]


def test_R8c_m3_and_FTE_are_aliases_of_meter_cubed_and_fte() -> None:
    """`m3` was rejected although `m2` was not, and `FTE` (the spelling of comparison.json) although
    `fte` was: a catalog author writing either got 'not a pint unit'."""
    ureg = registry()
    assert ureg.get_dimensionality("m3") == ureg.get_dimensionality("meter ** 3")
    assert ureg.Quantity(2, "m3").to("liter").magnitude == pytest.approx(2000.0)
    assert ureg.get_dimensionality("FTE") == ureg.get_dimensionality("fte")
    assert ureg.Quantity(3, "FTE").to("fte").magnitude == pytest.approx(3.0)
    assert ureg.get_dimensionality("FTE") != ureg.get_dimensionality("pallet")


@pytest.mark.parametrize("bad", ["lines/0", "1/0", "m ** m", "banana/h", "", "   ", "2 m"])
def test_T5_6_is_unit_rejects_malformed_expressions_without_raising(bad: str) -> None:
    """Final audit (R8c open medium): `lines/0` (ZeroDivisionError) and `m ** m` (TypeError) used to
    escape `is_unit` and crash `validate-catalog` with exit 1; they are bad units, not crashes."""
    assert is_unit(bad) is False

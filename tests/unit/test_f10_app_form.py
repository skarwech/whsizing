"""F10b basis form and scenario cards (T10.4): the form is generated from the `DesignBasis`
schema, defaults are marked, and the values validate with the library's own checks."""

from __future__ import annotations

from datetime import time
from pathlib import Path
from typing import Any

import yaml

from whsizing.app import basis_form, scenario_cards
from whsizing.app.strings import tr
from whsizing.catalog import load_catalog
from whsizing.design import load_basis
from whsizing.design.basis import EXAMPLES, UNSET_IN_TEMPLATE
from whsizing.design.validate import leaf_fields
from whsizing.schemas import DesignBasis

ROOT = Path(__file__).resolve().parents[2]
EXAMPLE_BASIS = ROOT / "basis" / "example_basis.yaml"


def test_T10_4_form_has_one_leaf_per_schema_field() -> None:
    schema_paths = [path for path, _, _ in leaf_fields(load_basis(EXAMPLE_BASIS))]
    assert [leaf.path for leaf in basis_form.leaves()] == schema_paths


def test_T10_4_required_fields_are_client_values_and_the_others_have_defaults() -> None:
    by_path = {leaf.path: leaf for leaf in basis_form.leaves()}
    required = {p for p, leaf in by_path.items() if leaf.required}
    assert {"client", "site", "building.area_m2", "service.cutoff_time"} <= required
    assert "operations.utilisation" not in required
    assert by_path["operations.utilisation"].default == 0.85
    assert by_path["projection.design_percentile"].default == 95.0


def test_T10_4_widget_kinds_follow_the_annotations() -> None:
    kinds = {leaf.path: basis_form.kind_of(leaf.annotation) for leaf in basis_form.leaves()}
    assert kinds["operations.shifts_per_day"] == ("int", False)
    assert kinds["operations.utilisation"] == ("float", False)
    assert kinds["service.cutoff_time"] == ("time", False)
    assert kinds["flows.inbound_mode"] == ("choice", False)
    assert kinds["building.sprinklered"] == ("bool", True)  # bool | None
    assert kinds["flows.inbound_peak_factor"] == ("float", True)
    assert kinds["finance.labor_cost_eur_h"] == ("mapping", False)
    assert kinds["baseline.actual_fte"] == ("mapping", True)  # dict | None


def test_T10_4_initial_values_are_a_valid_basis_with_the_template_examples() -> None:
    flat = basis_form.initial_values(None)
    assert flat["client"] == EXAMPLES["client"]
    assert flat["service.cutoff_time"] == "15:00"
    for path in UNSET_IN_TEMPLATE:  # trailing_months stays derived (I55)
        assert flat[path] is None
    basis, problems = basis_form.validate(basis_form.nest(flat))
    assert problems == [] and isinstance(basis, DesignBasis)
    assert "trailing_months" not in basis.projection.model_fields_set


def test_T10_4_nest_and_flatten_round_trip_the_basis_yaml() -> None:
    saved: dict[str, Any] = yaml.safe_load(EXAMPLE_BASIS.read_text(encoding="utf-8"))
    flat = basis_form.flatten(saved)
    assert "finance.labor_cost_eur_h" in flat and isinstance(flat["finance.labor_cost_eur_h"], dict)
    assert basis_form.nest(flat) == saved
    values = basis_form.initial_values(saved)
    assert values["building.area_m2"] == saved["building"]["area_m2"]  # saved wins over examples
    assert basis_form.validate(basis_form.nest(values))[0] is not None


def test_T10_4_nest_leaves_out_unset_values_so_the_schema_default_applies() -> None:
    nested = basis_form.nest({"operations.utilisation": None, "overrides": {}, "client": "X"})
    assert nested == {"client": "X"}


def test_T10_4_validate_reports_schema_and_library_errors() -> None:
    nested = basis_form.nest(basis_form.initial_values(None))
    nested["service"]["cutoff_time"] = 900  # unquoted 15:00 read by YAML as an int
    basis, problems = basis_form.validate(nested)
    assert basis is None and any("cutoff_time" in p for p in problems)
    nested = basis_form.nest(basis_form.initial_values(None))
    nested["operations"]["utilisation"] = 1.5  # check_basis: in (0, 1]
    basis, problems = basis_form.validate(nested)
    assert basis is None and "operations.utilisation" in problems[0]
    assert basis_form.validate({})[0] is None  # required fields missing


def test_T10_4_validate_checks_the_overrides_against_the_catalog_when_given_one() -> None:
    catalog = load_catalog(ROOT / "catalog")
    nested = basis_form.nest(basis_form.initial_values(None))
    nested["overrides"] = {"nope.param": 3}
    assert basis_form.validate(nested)[0] is not None  # without a catalog: nothing to check against
    basis, problems = basis_form.validate(nested, catalog)
    assert basis is None and "unknown parameter id 'nope.param'" in problems[0]
    nested["overrides"] = {"manual_p2p.pick_rate_shelving_lines_h": 60}
    assert basis_form.validate(nested, catalog)[0] is not None


def test_T10_4_default_times_are_written_as_quoted_hh_mm() -> None:
    assert basis_form.initial_values(None)["service.carrier_departure_time"] == "18:30"
    assert basis_form._plain(time(15, 0)) == "15:00"  # pyright: ignore[reportPrivateUsage]


# ---------------------------------------------------------------------------------- scenarios
def test_T10_4_initial_scenarios_come_from_the_example_file_and_validate() -> None:
    data = scenario_cards.initial_scenarios(None)
    scenario_set, problems = scenario_cards.validate(data)
    assert problems == [] and scenario_set is not None
    assert {s.family for s in scenario_set.scenarios} >= {"manual_p2p", "amr_gtp"}
    saved = {"scenarios": [], "baseline": "client_current"}
    assert scenario_cards.initial_scenarios(saved) is saved


def test_T10_4_added_scenarios_get_unique_ids_and_duplicates_are_reported() -> None:
    data = scenario_cards.initial_scenarios(None)
    more = scenario_cards.with_added(scenario_cards.with_added(data))
    ids = [s["id"] for s in more["scenarios"]]
    assert len(ids) == len(set(ids)) == len(data["scenarios"]) + 2
    clash = {**data, "scenarios": [*data["scenarios"], dict(data["scenarios"][0])]}
    assert scenario_cards.validate(clash)[0] is None


def test_T10_4_an_empty_scenario_list_is_not_valid_to_size() -> None:
    data = {**scenario_cards.initial_scenarios(None), "scenarios": []}
    scenario_set, problems = scenario_cards.validate(data, "en")
    assert scenario_set is None and problems == [tr("scn.none", "en")]
    assert scenario_cards.validate(data, "fr")[1] == [tr("scn.none", "fr")]


def test_T10_4_override_choices_are_the_family_params_within_catalog_bounds() -> None:
    catalog = load_catalog(ROOT / "catalog")
    choices = scenario_cards.override_choices(
        catalog, "amr_gtp", {"cube_asrs.port_rate_lines_h": 1}
    )
    assert "amr_gtp.station_rate_lines_h" in choices
    assert "cube_asrs.port_rate_lines_h" in choices  # already overridden: kept, never lost
    assert any(c.startswith("labor.") for c in choices)  # shared parameters
    assert not any(c.startswith("manual_p2p.") for c in choices)
    param = catalog.params["amr_gtp.station_rate_lines_h"]
    assert param.min < param.typ < param.max  # the slider bounds are the catalog's

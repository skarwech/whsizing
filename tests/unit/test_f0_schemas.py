"""F0 contracts: T0.3 JSON round-trip of every schema, T0.4 Param ordering, strictness, frames."""

from __future__ import annotations

import inspect
from datetime import UTC, date, datetime

import pandera.errors
import polars as pl
import pytest
from pydantic import BaseModel, ValidationError
from tests.fixtures import mock_param, mock_result, rng, schema_examples

import whsizing.schemas as schemas
from whsizing.schemas import (
    DailySeries,
    Inventory,
    OrderLines,
    Param,
    ProfileCfg,
    Range,
    Receipts,
    ScenarioResult,
    ScenarioSet,
    SkuMaster,
    StrictModel,
)


def _exported_models() -> set[type[BaseModel]]:
    return {
        obj
        for _, obj in inspect.getmembers(schemas, inspect.isclass)
        if issubclass(obj, BaseModel) and obj is not StrictModel
    }


def test_T0_3_every_exported_model_has_an_example() -> None:
    exported = _exported_models()
    examples = schema_examples()
    assert len(exported) >= 50
    assert set(examples) == exported, (
        f"missing examples: {sorted(m.__name__ for m in exported - set(examples))}; "
        f"not exported: {sorted(m.__name__ for m in set(examples) - exported)}"
    )


_MODELS = sorted(_exported_models(), key=lambda m: m.__name__)


@pytest.mark.parametrize("model", _MODELS, ids=[m.__name__ for m in _MODELS])
def test_T0_3_schema_json_round_trip(model: type[BaseModel]) -> None:
    instance = schema_examples()[model]
    restored = model.model_validate_json(instance.model_dump_json())
    assert restored == instance
    assert restored.model_dump_json() == instance.model_dump_json()


def test_T0_4_param_min_greater_than_typ_raises() -> None:
    data = mock_param().model_dump()
    with pytest.raises(ValidationError, match="min ≤ typ ≤ max"):
        Param.model_validate({**data, "min": 400, "typ": 350})
    with pytest.raises(ValidationError, match="min ≤ typ ≤ max"):
        Param.model_validate({**data, "max": 300})
    assert Param.model_validate({**data, "min": 350, "max": 350}).typ == 350  # equality allowed


def test_range_requires_lo_typ_hi_order() -> None:
    with pytest.raises(ValidationError, match="lo ≤ typ ≤ hi"):
        Range(lo=3, typ=2, hi=4, unit="m2")
    assert rng(2, 2, 2, "m2").typ == 2


def test_every_model_forbids_unknown_keys() -> None:
    for model, instance in schema_examples().items():
        data = instance.model_dump(mode="json")
        with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
            model.model_validate({**data, "not_a_field": 1})


def test_param_range_trace_node_are_frozen() -> None:
    p = mock_param()
    with pytest.raises(ValidationError):
        p.typ = 1.0  # type: ignore[misc]
    r = rng(1, 2, 3)
    with pytest.raises(ValidationError):
        r.lo = 0.0  # type: ignore[misc]


def test_scenario_set_rejects_duplicate_ids_and_unknown_baseline() -> None:
    s = mock_result().scenario
    with pytest.raises(ValidationError, match="duplicate scenario id"):
        ScenarioSet(scenarios=[s, s])
    with pytest.raises(ValidationError, match="neither 'client_current'"):
        ScenarioSet(scenarios=[s], baseline="S9")


def test_not_computed_result_needs_a_reason() -> None:
    data = mock_result().model_dump()
    with pytest.raises(ValidationError, match="status_reason"):
        ScenarioResult.model_validate({**data, "status": "not_computed"})


def test_profile_cfg_default_intraday_sums_to_one() -> None:
    assert abs(sum(ProfileCfg().default_intraday) - 1) < 1e-12
    with pytest.raises(ValidationError, match="24 shares"):
        ProfileCfg(default_intraday=[1.0])


def _order_lines(ts: datetime) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "order_id": ["o1", "o1", "o2"],
            "order_ts": [ts, ts, ts],
            "sku": ["a", "b", "a"],
            "qty_units": [1, -2, 3],
            "line_status": pl.Series(["shipped", "returned", "shipped"], dtype=pl.Categorical),
            "source_file": ["f.csv"] * 3,
            "source_row": [2, 3, 4],
        }
    )


def test_order_lines_frame_validates_and_rejects() -> None:
    good = _order_lines(datetime(2026, 1, 5, 9, 30, tzinfo=UTC))
    assert OrderLines.validate(good).height == 3
    naive = _order_lines(datetime(2026, 1, 5, 9, 30))
    with pytest.raises(pandera.errors.SchemaError):
        OrderLines.validate(naive)  # never silently assume UTC
    with pytest.raises(pandera.errors.SchemaError):
        OrderLines.validate(good.with_columns(pl.lit(0).alias("qty_units")))
    bad_status = good.with_columns(
        pl.Series("line_status", ["shipped", "lost", "shipped"], dtype=pl.Categorical)
    )
    with pytest.raises(pandera.errors.SchemaError):
        OrderLines.validate(bad_status)


def test_other_frames_validate_and_reject() -> None:
    sku = pl.DataFrame(
        {
            "sku": ["a", "b"],
            "length_mm": [300.0, None],
            "width_mm": [200.0, None],
            "height_mm": [100.0, None],
            "weight_kg": [1.2, None],
            "units_per_case": [6, None],
        }
    )
    assert SkuMaster.validate(sku).height == 2
    with pytest.raises(pandera.errors.SchemaError):
        SkuMaster.validate(sku.with_columns(pl.Series("sku", ["a", "a"])))  # unique
    with pytest.raises(pandera.errors.SchemaError):
        SkuMaster.validate(sku.with_columns(pl.Series("length_mm", [3500.0, None])))  # < 3000

    inv = pl.DataFrame({"sku": ["a"], "qty_units": [10], "snapshot_date": [date(2026, 10, 31)]})
    assert Inventory.validate(inv).height == 1
    with pytest.raises(pandera.errors.SchemaError):
        Inventory.validate(inv.with_columns(pl.lit(-1).alias("qty_units")))

    rec = pl.DataFrame(
        {
            "receipt_id": ["r1"],
            "receipt_ts": [datetime(2026, 1, 5, tzinfo=UTC)],
            "sku": ["a"],
            "qty_units": [400],
        }
    )
    assert Receipts.validate(rec).height == 1

    daily = pl.DataFrame(
        {
            "date": [date(2026, 1, 5)],
            "weekday": [0],
            "is_operating": [True],
            "is_holiday": [False],
            "orders": [800],
            "lines": [2100],
            "units": [2900],
            "cube_m3": [55.0],
            "weight_kg": [9800.0],
            "parcels": [850.0],
            "pallets_out": [12.0],
            "return_lines": [60],
        }
    )
    assert DailySeries.validate(daily).schema["lines"] == pl.Float64
    with pytest.raises(pandera.errors.SchemaError):
        DailySeries.validate(daily.with_columns(pl.lit(7).alias("weekday")))

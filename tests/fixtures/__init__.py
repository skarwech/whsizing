"""Shared test fixtures: `from tests.fixtures import mock_result` (pytest pythonpath = ".")."""

from tests.fixtures.factories import (
    FIXTURES,
    mock_basis,
    mock_comparison,
    mock_design_day,
    mock_financial,
    mock_ingest_manifest,
    mock_manifest,
    mock_param,
    mock_profile,
    mock_project,
    mock_result,
    mock_scenario,
    mock_sensitivity,
    rng,
    schema_examples,
)

__all__ = [
    "FIXTURES",
    "mock_basis",
    "mock_comparison",
    "mock_design_day",
    "mock_financial",
    "mock_ingest_manifest",
    "mock_manifest",
    "mock_param",
    "mock_profile",
    "mock_project",
    "mock_result",
    "mock_scenario",
    "mock_sensitivity",
    "rng",
    "schema_examples",
]

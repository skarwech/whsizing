"""T1.5 engine side: "golden spreadsheet values equal engine outputs within 0.5 %" (F1).

Each engine stage compares itself with golden_values.json in its own golden test: T3.1
tests/golden/test_f3_golden.py, T4.1 test_f4_golden.py, T6.1-T6.3 test_f6_*_golden.py, T7.1
test_f7_golden.py. This file checks, without importing `whsizing` (oracle independence), that the
F6 and F7 golden tests exist, are not skipped and select every S*.<group> golden key of their
stage with their `KEYS` pattern. `S*.flags` and `S*.low_confidence_params` are compared by no T6
or T7 test (I46: "T6.x do not compare flag strings").
"""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
GOLDEN = json.loads((HERE / "golden_values.json").read_text(encoding="utf-8"))
OWNERS = {  # test id → (golden test file, S*.<group> key groups it compares)
    "T6.1": (
        "test_f6_storage_golden.py",
        ("storage", "throughput", "equipment", "utilisation", "eligibility", "bottleneck"),
    ),
    "T6.2": ("test_f6_labor_golden.py", ("labor",)),
    "T6.3": ("test_f6_area_golden.py", ("area", "docks", "queue")),
    "T7.1": ("test_f7_golden.py", ("capex", "opex", "finance")),
}
F7_KEYS = 111  # S0 + S2: 8 capex + 40 opex each, 3 finance (S0) + 12 finance (S2)
NOT_IN_T6 = {"flags", "low_confidence_params"}  # I46
DISABLE = {"skip", "skipif", "xfail", "importorskip"}  # pytest.* / pytest.mark.* / unittest.*


def _scenario_keys(groups: tuple[str, ...]) -> list[str]:
    return [k for k in GOLDEN if re.match(r"S\d+\.", k) and k.split(".")[1] in groups]


def _disabled(tree: ast.Module) -> bool:
    """Any skip / xfail anywhere in the file (decorator, fixture or test body, `from pytest import
    skip`) or a module `pytestmark`: a golden parity file has no business with either."""
    return any(
        (isinstance(n, ast.Attribute) and n.attr in DISABLE)
        or (isinstance(n, ast.alias) and n.name in DISABLE)
        or (isinstance(n, ast.Name) and n.id == "pytestmark")
        for n in ast.walk(tree)
    )


def _keys_pattern_and_tests(source: str, test_id: str) -> tuple[re.Pattern[str], list[str]]:
    """The file's module-level `KEYS = re.compile(<literal>)` and its test functions named
    test_<test_id>_* (T6.1 → test_T6_1_*); none when the file can skip or xfail (`_disabled`)."""
    tree = ast.parse(source)
    pattern = next(
        ast.literal_eval(node.value.args[0])
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "KEYS" for t in node.targets)
        and isinstance(node.value, ast.Call)
    )
    prefix = "test_" + test_id.replace(".", "_") + "_"
    tests = [
        node.name
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name.startswith(prefix)
    ]
    return re.compile(pattern), [] if _disabled(tree) else tests


@pytest.mark.parametrize("test_id", sorted(OWNERS))
def test_T1_5_engine_parity_golden_test_covers_its_keys(test_id: str) -> None:
    """T6.1 storage/throughput/equipment/utilisation/eligibility/bottleneck, T6.2 labor, T6.3
    area/docks/queue, T7.1 capex/opex/finance: the stage's golden test runs and its KEYS selects
    every such golden key of S0 and S2 (the test then requires a trace node per key, 0.5 %)."""
    name, groups = OWNERS[test_id]
    keys = _scenario_keys(groups)
    assert {k.split(".")[1] for k in keys} == set(groups), "a group has no golden key"
    assert {k.split(".")[0] for k in keys} == {"S0", "S2"}
    pattern, tests = _keys_pattern_and_tests((HERE / name).read_text(encoding="utf-8"), test_id)
    assert tests, f"{name}: no test_{test_id.replace('.', '_')}_* function, or the file skips"
    missed = [k for k in keys if not pattern.match(k)]
    assert not missed, f"{name} KEYS misses {missed[:10]}"
    other = [k for k in GOLDEN if pattern.match(k) and k.split(".")[1] not in groups]
    assert not other, f"{name} KEYS also selects {other[:10]}"
    if test_id == "T7.1":  # test_f7_golden.py asserts the same count of keys it compares
        assert len(keys) == F7_KEYS


AREA = "test_f6_area_golden.py"
CMP = "def test_T6_3_area_docks_queue_equal_golden("
MUTANTS = {  # (old, new) applied once to test_f6_area_golden.py
    "module pytestmark": ("HERE = ", 'pytestmark = pytest.mark.skip(reason="x")\nHERE = '),
    "pytest.skip in a fixture": (
        "def run() -> Run:\n",
        'def run() -> Run:\n    pytest.skip("x")\n',
    ),
    "xfail on the comparison test": (CMP, "@pytest.mark.xfail\n" + CMP),
    "skipif on the comparison test": (CMP, "@pytest.mark.skipif(True, reason='x')\n" + CMP),
    "imported skip": ("import pytest\n", "import pytest\nfrom pytest import skip\n"),
}


@pytest.mark.parametrize("mutant", sorted(MUTANTS))
def test_T1_5_engine_parity_rejects_a_disabled_golden_test(mutant: str) -> None:
    """A T6.3 file that can skip or xfail (module, fixture or decorator) counts as no test; the
    unmodified file counts its three test_T6_3_* functions."""
    source = (HERE / AREA).read_text(encoding="utf-8")
    assert len(_keys_pattern_and_tests(source, "T6.3")[1]) == 3
    old, new = MUTANTS[mutant]
    assert source.count(old) == 1, f"mutant anchor {old!r} not unique in {AREA}"
    assert _keys_pattern_and_tests(source.replace(old, new), "T6.3")[1] == []


F7_FILE = "test_f7_golden.py"
F7_CMP = "def test_T7_1_golden_finance_equals_the_spreadsheet("


@pytest.mark.parametrize("mutant", sorted(MUTANTS))
def test_T1_5_engine_parity_rejects_a_disabled_f7_golden_test(mutant: str) -> None:
    """The same disabling mutants on the T7.1 file: it counts its three test_T7_1_* functions
    unmodified and none once it can skip or xfail."""
    source = (HERE / F7_FILE).read_text(encoding="utf-8")
    assert len(_keys_pattern_and_tests(source, "T7.1")[1]) == 3
    old, new = (x.replace(CMP, F7_CMP) for x in MUTANTS[mutant])
    assert source.count(old) == 1, f"mutant anchor {old!r} not unique in {F7_FILE}"
    assert _keys_pattern_and_tests(source.replace(old, new), "T7.1")[1] == []


def test_T1_5_engine_parity_rejects_a_narrowed_f7_keys_pattern() -> None:
    """Dropping `finance` from the T7.1 KEYS leaves every S*.finance.* golden key unselected."""
    source = (HERE / F7_FILE).read_text(encoding="utf-8")
    narrowed = source.replace("(capex|opex|finance)", "(capex|opex)")
    assert narrowed != source
    pattern, tests = _keys_pattern_and_tests(narrowed, "T7.1")
    assert tests
    assert [k for k in _scenario_keys(("finance",)) if not pattern.match(k)]


def test_T1_5_engine_parity_every_scenario_key_has_an_owner() -> None:
    """Every S*.<group> golden key is compared by an F6 or F7 test, or is a flag string (I46). A
    new group fails here until a golden test or this register claims it."""
    groups = {k.split(".")[1] for k in GOLDEN if re.match(r"S\d+\.", k)}
    owned = [g for _, gs in OWNERS.values() for g in gs]
    assert len(owned) == len(set(owned)), "a group has two owners"
    assert groups == set(owned) | NOT_IN_T6
    assert not (set(owned) & NOT_IN_T6)

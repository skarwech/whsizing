"""F6z `size_scenario` on tiny_golden: T6.9 (identical inputs → byte-identical result.json),
T6.11 (every number of result.json has a TraceNode), the F6 edge cases (I48 zero eligible
lines, building below one level, F_NO_FIT), input errors and the part fixes closed by F6z (I64
receipts with units_in* = 0, shift windows, queue NaN, decant_cases_in inputs).

T6.11 mapping, result.json path → trace id `<sid>.<key>`. A Range's typ is the typ-world node,
its lo / hi the min / max of that node over the three worlds; any other number is the typ node.
  eligibility.<f>                                 → eligibility.<f>
  storage.classes[i].<f>                          → storage[.overflow].<class>.<f>
  storage.total_area_m2, storage.height_utilisation → storage.<f>
  equipment.<k>                                   → equipment.<k>
  labor.activities[i].<f>                         → labor.<activity>.<f>
  labor.activities[i].annual_hours[t]             → labor.<activity>.annual_hours.y<t+1>
  labor.total_hours | total_heads | roster        → labor.total.hours | heads | roster
  labor.annual_hours | core_fte | temp_hours [t]  → labor.<f>.y<t+1>
  labor.shifts[i].start_hour | end_hour           → labor.shift<s>.<f>
  labor.shifts[i].hours | heads                   → labor.<activity>.shift<s>.<f>
  area.zones.<z>                                  → area.<z>
  area.total_m2                                   → area.total
  area.docks_in_required | docks_out_required     → docks.in | docks.out
  area.<f> (building_m2, utilisation, deficit_m2, icpe_volume_m3) → area.<f>
  queue.resources[i].<f>                          → queue.<resource>.<f>
  <any>.flags[i].value                            → flags.<code without a numeric :suffix>
Exempt: `scenario.*` (the ScenarioDef echoed back: inputs; its overrides are `param:` leaves)
and `labor.shifts[i].shift` (the row's shift number, a key). Booleans are not JSON numbers
(`area.fit` and `queue...stable` are traced as 1 / 0 all the same).
"""

from __future__ import annotations

import json
import math
import os
import re
import shutil
import subprocess
import sys
from collections.abc import Iterator, Sequence
from functools import cache
from pathlib import Path
from typing import Any, NamedTuple

import polars as pl
import pytest
from tests.unit.test_f6_inputs import build
from tests.unit.test_f6_labor import PFD, frames, labor, value
from tests.unit.test_f6_throughput import toy

from whsizing.catalog import Catalog, load_catalog
from whsizing.config import load_yaml_model
from whsizing.design import load_basis, select_design_day
from whsizing.engine import WORLDS, queue_resource, size_scenario, sku_frame, write_scenario
from whsizing.errors import ConfigError, DataQualityError, WhsizingError
from whsizing.profile import build_tables, profile_from_tables
from whsizing.schemas import (
    DemandProfile,
    DesignBasis,
    DesignDay,
    EligibilityCfg,
    Flag,
    ProfileCfg,
    ScenarioDef,
    ScenarioResult,
    ScenarioSet,
)
from whsizing.schemas.trace import Tracer

ROOT = Path(__file__).resolve().parents[2]
GOLDEN = ROOT / "tests" / "golden"
S1 = ScenarioDef(id="S1", name="AMR goods-to-person", family="amr_gtp")


class Inputs(NamedTuple):
    profile: DemandProfile
    basis: DesignBasis
    design_day: DesignDay
    catalog: Catalog
    sku: pl.DataFrame
    daily: pl.DataFrame
    lines: pl.DataFrame
    scenarios: dict[str, ScenarioDef]  # S0 manual, S1 amr (inline), S2 cube


@cache
def golden_inputs() -> Inputs:
    """tiny_golden through F3 → I58 → F4, the golden scenarios plus an inline AMR S1."""
    basis = load_basis(GOLDEN / "golden_basis.yaml")
    cfg = ProfileCfg()
    t = build_tables(GOLDEN / "tiny_golden", basis, cfg)
    profile = profile_from_tables(t, cfg)
    sku = sku_frame(t, pl.read_parquet(GOLDEN / "tiny_golden" / "sku_master.parquet"))
    catalog = load_catalog(ROOT / "catalog")
    dd = select_design_day(profile, basis, t.daily, sku=sku, catalog=catalog)
    golden = load_yaml_model(GOLDEN / "golden_scenarios.yaml", ScenarioSet).scenarios
    scenarios = {s.id: s for s in sorted([*golden, S1], key=lambda s: s.id)}
    return Inputs(profile, basis, dd, catalog, sku, t.daily, t.lines, scenarios)


def sized(scenario: ScenarioDef | str, **change: Any) -> tuple[ScenarioResult, Tracer]:
    """size_scenario on the golden inputs, any of basis / design_day / sku / daily / lines
    replaced."""
    g = golden_inputs()._replace(**change)
    s = g.scenarios[scenario] if isinstance(scenario, str) else scenario
    tracer = Tracer(s.id)
    result = size_scenario(
        g.profile, g.basis, g.design_day, s, g.catalog, g.sku, g.daily, tracer, lines=g.lines
    )
    return result, tracer


def write_all(out: Path | str, **change: Any) -> dict[str, bytes]:
    """result.json bytes of S0, S1, S2 written by `write_scenario` under `out`."""
    files: dict[str, bytes] = {}
    for sid in golden_inputs().scenarios:
        folder = write_scenario(*sized(sid, **change), out)
        files[sid] = (folder / "result.json").read_bytes()
    return files


def with_basis(**sections: dict[str, Any]) -> DesignBasis:
    """The golden basis with fields of some sections changed."""
    b = golden_inputs().basis
    return b.model_copy(update={k: getattr(b, k).model_copy(update=v) for k, v in sections.items()})


# ---------------------------------------------------------------- T6.9
def test_T6_9_identical_inputs_give_byte_identical_result_json(tmp_path: Path) -> None:
    """Two runs in one process write the same result.json and trace.jsonl bytes, and the
    result names its trace by a path relative to the project (no tmp dir in result.json)."""
    one, two = write_all(tmp_path / "a"), write_all(tmp_path / "b")
    assert one == two
    for sid in one:
        a, b = (tmp_path / d / "scenarios" / sid / "trace.jsonl" for d in "ab")
        assert a.read_bytes() == b.read_bytes()
        assert json.loads(one[sid])["trace_path"] == f"scenarios/{sid}/trace.jsonl"


@pytest.mark.slow
def test_T6_9_a_fresh_process_writes_the_same_result_json(tmp_path: Path) -> None:
    """A new interpreter (another hash seed) writes byte-identical result.json files."""
    script = "import sys; from tests.unit.test_f6_size import write_all; write_all(sys.argv[1])"
    env = {**os.environ, "PYTHONHASHSEED": "4242"}
    subprocess.run(
        [sys.executable, "-c", script, str(tmp_path / "sub")], check=True, cwd=ROOT, env=env
    )
    here = write_all(tmp_path / "here")
    for sid, data in here.items():
        assert (tmp_path / "sub" / "scenarios" / sid / "result.json").read_bytes() == data, sid


@pytest.mark.slow
def test_T6_9_rerun_from_manifest_gives_identical_result_json(
    tmp_path: Path, tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """F8: `rerun` replays a run from its manifest and the copies in `inputs/` (the originals
    are deleted first): a new folder with byte-identical result.json, finance.json, trace.jsonl."""
    from tests.unit.test_f8_runner import small_data, small_project

    from whsizing.scenarios import rerun, run_scenarios

    monkeypatch.setenv("WHSIZING_SALT", "t6-9-salt")  # the run's anonymisation salt (C2)
    src = tmp_path / "src"
    shutil.copytree(small_data(tmp_path_factory), src / "data")
    shutil.copytree(ROOT / "catalog", src / "catalog")
    shutil.copy(ROOT / "basis" / "example_basis.yaml", src / "basis.yaml")
    shutil.copy(ROOT / "scenarios" / "example_scenarios.yaml", src / "scenarios.yaml")
    project = small_project(
        src / "data", tmp_path / "runs",
        catalog=src / "catalog", basis=src / "basis.yaml", scenarios=src / "scenarios.yaml",
    )  # fmt: skip
    first = run_scenarios(project)
    shutil.rmtree(src)
    monkeypatch.delenv("WHSIZING_SALT")  # a rerun reads the run's copies and canonical/ only
    second = rerun(first.run_dir)
    assert second.run_dir != first.run_dir and second.run_dir.parent == first.run_dir.parent
    assert list(first.results) == ["S0", "S1", "S2"]
    for sid in first.results:
        for name in ("result.json", "finance.json", "trace.jsonl"):
            one, two = (r.run_dir / "scenarios" / sid / name for r in (first, second))
            assert one.read_bytes() == two.read_bytes(), (sid, name)
        assert (
            json.loads((second.run_dir / "scenarios" / sid / "result.json").read_text())[
                "trace_path"
            ]
            == f"scenarios/{sid}/trace.jsonl"
        )


# ---------------------------------------------------------------- T6.11
def numbers(node: Any, path: tuple[Any, ...] = ()) -> Iterator[tuple[tuple[Any, ...], Any]]:
    """(path, value) of every number of a result.json tree; a Range comes whole."""
    if isinstance(node, dict) and {"lo", "typ", "hi", "unit"} <= node.keys():
        yield path, node
    elif isinstance(node, dict):
        for k, v in node.items():
            yield from numbers(v, (*path, k))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from numbers(v, (*path, i))
    elif isinstance(node, int | float) and not isinstance(node, bool):
        yield path, node


def trace_key(r: dict[str, Any], path: Sequence[Any]) -> str | None:
    """The module docstring's mapping; None = exempt."""
    head, f = path[0], path[1] if len(path) > 1 else None
    if head == "scenario" or path[-1] == "shift":
        return None
    if path[-1] == "value" and path[-3] == "flags":
        code = _at(r, path[:-1])["code"]
        return "flags." + re.sub(r":[0-9.]+$", "", code)
    if head == "storage" and f == "classes":
        c = r["storage"]["classes"][path[2]]
        zone = "overflow." if c["zone"] == "overflow" else ""
        return f"storage.{zone}{c['storage_class']}.{path[3]}"
    if head == "labor":
        return _labor_key(r, path)
    if head == "area":
        alias = {"total_m2": "area.total", "docks_in_required": "docks.in",
                 "docks_out_required": "docks.out"}  # fmt: skip
        return f"area.{path[2]}" if f == "zones" else alias.get(str(f), f"area.{f}")
    if head == "queue":
        return f"queue.{r['queue']['resources'][path[2]]['resource']}.{path[3]}"
    return ".".join(str(p) for p in path)  # eligibility.*, storage.*, equipment.*


def _labor_key(r: dict[str, Any], path: Sequence[Any]) -> str:
    f = path[1]
    if f == "activities":
        a = r["labor"]["activities"][path[2]]["activity"]
        year = f".y{path[4] + 1}" if path[3] == "annual_hours" else ""
        return f"labor.{a}.{path[3]}{year}"
    if f == "shifts":
        row = r["labor"]["shifts"][path[2]]
        if path[3] in ("start_hour", "end_hour"):
            return f"labor.shift{row['shift']}.{path[3]}"
        return f"labor.{row['activity']}.shift{row['shift']}.{path[3]}"
    if f in ("annual_hours", "core_fte", "temp_hours"):
        return f"labor.{f}.y{path[2] + 1}"
    return {"total_hours": "labor.total.hours", "total_heads": "labor.total.heads",
            "roster": "labor.total.roster"}[f]  # fmt: skip


def _at(tree: Any, path: Sequence[Any]) -> Any:
    for p in path:
        tree = tree[p]
    return tree


def stress() -> tuple[ScenarioDef, dict[str, Any]]:
    """A cube variant raising the rarer flags: F_ELIG_ASSUMED (SKUs without dims assumed
    eligible), F_DOCK_SHORTFALL (no dock door), F_UNSTABLE:packing (0.2 h SLA window)."""
    g = golden_inputs()
    scenario = ScenarioDef(
        id="S9",
        name="stress",
        family="cube_asrs",
        eligibility=EligibilityCfg(assume_eligible_if_missing_dims=True),
    )
    sku = g.sku.with_columns(
        length_mm=pl.when(pl.col("sku").is_in(g.sku["sku"].head(10).implode()))
        .then(None)
        .otherwise(pl.col("length_mm"))
    )
    basis = with_basis(
        building={"dock_doors_in": 0, "dock_doors_out": 0}, service={"sla_window_hours": 0.2}
    )
    return scenario, {"sku": sku, "basis": basis}


def assert_traced(sid: str, folder: Path) -> dict[str, Any]:
    """T6.11 on a written scenario folder: every number of result.json maps to a node of
    trace.jsonl with that value (Range: typ node; lo / hi = min / max over the worlds), only
    `scenario.*` and the shift numbers are exempt, and every node input resolves (a node of the
    same world, `param:` or `data:`). Returns the result.json tree."""
    r = json.loads((folder / "result.json").read_text(encoding="utf-8"))
    tracer = Tracer.load_jsonl(folder / "trace.jsonl")
    nodes = {(n.id, n.world): n.value for n in tracer.nodes}
    checked = 0
    for path, v in numbers(r):
        key = trace_key(r, path)
        if key is None:
            assert path[0] == "scenario" or path[-1] == "shift", path
            continue
        tid = f"{sid}.{key}"
        if isinstance(v, dict):
            worlds = [nodes[(tid, w)] for w in WORLDS]
            assert (v["lo"], v["typ"], v["hi"]) == (min(worlds), nodes[(tid, "typ")], max(worlds))
        else:
            assert nodes[(tid, "typ")] == v, (path, tid)
        checked += 1
    assert checked > 150
    for n in tracer.nodes:
        for ref in n.inputs.values():
            assert ref.startswith(("param:", "data:")) or (ref, n.world) in nodes, (n.id, ref)
    return r


@pytest.mark.parametrize("sid", ["S0", "S1", "S2", "S9"])
def test_T6_11_every_number_in_result_json_has_a_trace_node(sid: str, tmp_path: Path) -> None:
    """`assert_traced` on the golden S0, S2, the inline AMR S1 and the S9 stress variant (whose
    flags carry the values of F_ELIG_ASSUMED, F_DOCK_SHORTFALL and F_UNSTABLE)."""
    scenario, change = stress() if sid == "S9" else (sid, {})
    r = assert_traced(sid, write_scenario(*sized(scenario, **change), tmp_path))
    if sid == "S9":
        codes = [f["code"].split(":")[0] for f in r["flags"]]
        assert {"F_ELIG_ASSUMED", "F_DOCK_SHORTFALL", "F_UNSTABLE"} <= set(codes)


# ---------------------------------------------------------------- F6 edge cases
def test_zero_eligible_lines_degenerate_to_manual() -> None:
    """I48: a cube scenario with no eligible SKU (weight cap 0 kg) sizes every SKU manually:
    no port, robot or cube bin, F_ELIG_LOW, the cube's F_LOW_CONFIDENCE count (50), only the
    packing queue; storage, labor hours and the area budget equal the manual S0's."""
    g = golden_inputs()
    none = g.scenarios["S2"].model_copy(
        update={"id": "S3", "eligibility": EligibilityCfg(extra_max_weight_kg=0.0)}
    )
    r, _ = sized(none)
    s0, _ = sized("S0")
    assert r.eligibility.share_lines == 0.0
    for k in ("ports", "robots"):
        assert (r.equipment[k].lo, r.equipment[k].hi) == (0.0, 0.0)
    cube = next(c for c in r.storage.classes if c.storage_class == "cube_bin")
    assert cube.n_skus == 0 and cube.positions.hi == 0.0
    codes = [f.code for f in r.flags]
    assert "F_ELIG_LOW" in codes and codes[-1] == "F_LOW_CONFIDENCE:50"
    assert [q.resource for q in r.queue.resources] == ["packing"]
    assert r.storage.total_area_m2.typ == pytest.approx(s0.storage.total_area_m2.typ, rel=1e-12)
    assert r.labor.total_hours.typ == pytest.approx(s0.labor.total_hours.typ, rel=1e-12)
    assert r.area.total_m2.typ == pytest.approx(s0.area.total_m2.typ, rel=1e-12)
    assert r.equipment["pickers_peak"] == s0.equipment["pickers_peak"]


def test_design_day_flags_carry_the_f6_table_severity_info() -> None:
    """F6 flags table and I70: F_RATIO_DRIFT, F_PERCENTILE_CLIPPED, F_SHORT_HISTORY are info in
    design_day.json (F4) and in result.json; same codes, order and values."""
    g = golden_inputs()
    clip = Flag(code="F_PERCENTILE_CLIPPED", severity="info", message="clipped to the max")
    dd = g.design_day.model_copy(update={"flags": [clip, *g.design_day.flags]})
    assert {f.code.split(":")[0] for f in dd.flags} == {
        "F_PERCENTILE_CLIPPED", "F_SHORT_HISTORY", "F_RATIO_DRIFT"
    }  # fmt: skip
    assert {f.severity for f in dd.flags} == {"info"}  # I70
    r, _ = sized("S0", design_day=dd)
    copied = [f for f in r.flags if f.code in {d.code for d in dd.flags}]
    key = [(f.code, f.message, f.value) for f in dd.flags]
    assert [(f.code, f.message, f.value) for f in copied] == key
    assert {f.severity for f in copied} == {"info"}


def test_no_low_confidence_param_gives_no_low_confidence_flag() -> None:
    """F6 table: F_LOW_CONFIDENCE only when the result depends on ≥ 1 confidence-L Param; the
    count node is still traced (0)."""
    g = golden_inputs()
    high = {k: p.model_copy(update={"confidence": "H"}) for k, p in g.catalog.params.items()}
    r, tracer = sized("S0", catalog=g.catalog.model_copy(update={"params": high}))
    assert not [f for f in r.flags if f.code.startswith("F_LOW_CONFIDENCE")]
    assert tracer.get("S0.low_confidence_params").value == 0.0
    r, _ = sized("S0")
    assert r.flags[-1].code == "F_LOW_CONFIDENCE:30"


@pytest.mark.parametrize("bad", ["../escaped", "a/b", "", ".", "S 0"])
def test_scenario_id_must_be_one_safe_path_segment(bad: str, tmp_path: Path) -> None:
    """scenarios/<id>/ is built from the id: size_scenario and write_scenario reject an id that
    is not letters, digits, '_' or '-' (ConfigError) and write nothing."""
    g = golden_inputs()
    with pytest.raises(ConfigError, match="scenario id"):
        sized(g.scenarios["S0"].model_copy(update={"id": bad}))
    r, tracer = sized("S0")
    forged = r.model_copy(update={"scenario": r.scenario.model_copy(update={"id": bad})})
    with pytest.raises(ConfigError, match="scenario id"):
        write_scenario(forged, tracer, tmp_path / "project")
    assert not any(tmp_path.rglob("result.json"))


def test_building_below_one_level_gives_one_level_and_height_limit() -> None:
    """F6 edge case: a 1.0 m clear height fits no rack or grid level → levels 1, flagged
    F_HEIGHT_LIMIT:<class> for the pallet rack and the cube grid; the run completes."""
    r, _ = sized("S2", basis=with_basis(building={"clear_height_m": 1.0}))
    levels = {c.storage_class: c.levels for c in r.storage.classes}
    assert levels["pallet_rack"] == levels["cube_bin"] == 1
    codes = [f.code for f in r.flags]
    assert {"F_HEIGHT_LIMIT:cube_bin", "F_HEIGHT_LIMIT:pallet_rack"} <= set(codes)
    assert r.storage.height_utilisation > 1  # levels forced to 1 above the clear height


def test_stock_larger_than_the_building_flags_no_fit_and_continues() -> None:
    """F6 edge case: in a 50 m² building every family gets F_NO_FIT (first flag, I46) with
    the deficit, and a full result."""
    basis = with_basis(building={"area_m2": 50.0})
    for sid in ("S0", "S1", "S2"):
        r, _ = sized(sid, basis=basis)
        assert not r.area.fit and r.flags[0].code == "F_NO_FIT", sid
        assert r.flags[0].value == pytest.approx(r.area.total_m2.typ - 50.0)
        assert r.labor.roster.typ > 0 and r.status == "computed"


@pytest.mark.parametrize(
    ("n", "length", "expected"),
    [
        (3, 6.0, {(1, 6.0, 12.0), (2, 12.0, 18.0), (3, 18.0, 24.0)}),
        (2, 10.0, {(1, 6.0, 16.0), (2, 16.0, 26.0)}),
        (3, 8.0, {(1, 6.0, 14.0), (2, 14.0, 22.0), (3, 22.0, 30.0)}),
    ],
)
def test_shift_end_is_start_plus_length_and_traced(
    n: int, length: float, expected: set[tuple[int, float, float]]
) -> None:
    """Shifts from 06:00, end = start + hours_per_shift: midnight is 24.0 and a shift crossing
    it ends after 24 (26.0 = 02:00 next day), so end − start is the shift length every time;
    each hour is a trace node and the end reads the start."""
    ops = with_basis(operations={"shifts_per_day": n, "hours_per_shift": length})
    r, tracer = sized("S0", basis=ops)
    assert {(s.shift, s.start_hour, s.end_hour) for s in r.labor.shifts} == expected
    assert sum(s.hours for s in r.labor.shifts) == pytest.approx(r.labor.total_hours.typ)
    last = tracer.get(f"S0.labor.shift{n}.end_hour")
    assert last.value == max(e for _, _, e in expected)
    assert last.inputs["start_hour"] == f"S0.labor.shift{n}.start_hour"


def test_decant_cases_in_lists_its_pack_data_and_amr_parks_on_the_cube_param() -> None:
    """F6a open issue: `throughput.decant_cases_in` names the pack columns it divides by;
    I26 / I63 (12): the AMR equipment area reads cube_asrs.m2_per_robot_parking."""
    _, s2 = sized("S2")
    leaves = set(s2.get("S2.throughput.decant_cases_in").inputs.values())
    assert {"data:sku.units_per_case", "data:sku.units_per_pallet",
            "data:sku.cases_per_pallet"} <= leaves  # fmt: skip
    _, s1 = sized("S1")
    park = s1.get("S1.area.equipment").inputs["m2_per_robot_parking"]
    assert park == "param:cube_asrs.m2_per_robot_parking"


# ---------------------------------------------------------------- input errors
def test_bad_daily_or_lines_raise_data_quality_errors() -> None:
    """A repeated date, a null is_operating or a text qty_units → DataQualityError naming it."""
    g = golden_inputs()
    with pytest.raises(DataQualityError, match="repeats date"):
        sized("S0", daily=pl.concat([g.daily, g.daily.head(1)]))
    null_op = g.daily.with_columns(
        is_operating=pl.when(pl.int_range(pl.len()) == 3).then(None).otherwise("is_operating")
    )
    with pytest.raises(DataQualityError, match="null is_operating"):
        sized("S0", daily=null_op)
    with pytest.raises(DataQualityError, match="qty_units must be numeric"):
        sized("S0", lines=g.lines.with_columns(pl.col("qty_units").cast(pl.Utf8)))


def test_inconsistent_inputs_raise_data_quality_errors() -> None:
    """A repeated SKU row (named, not a labor mismatch), a non-positive qty_units, a SKU absent
    from the frame, a shipped date absent from daily, no operating day → DataQualityError."""
    g = golden_inputs()
    first = g.sku["sku"][0]
    with pytest.raises(DataQualityError, match=f"repeats sku.*{first}"):
        sized("S2", sku=pl.concat([g.sku, g.sku.head(1)]))
    with pytest.raises(DataQualityError, match="non-positive qty_units"):
        sized("S0", lines=g.lines.with_columns(qty_units=pl.lit(0) * pl.col("qty_units")))
    with pytest.raises(DataQualityError, match="SKUs missing from the SKU frame"):
        sized("S0", lines=g.lines.with_columns(sku=pl.lit("NOT_A_SKU")))
    with pytest.raises(DataQualityError, match="date absent from the daily series"):
        sized("S0", daily=g.daily.filter(pl.col("date") != g.lines["date"][0]))
    with pytest.raises(DataQualityError, match="no operating day"):
        sized("S0", daily=g.daily.with_columns(is_operating=pl.lit(False)))


@pytest.mark.parametrize(
    ("lam", "mu", "t"),
    [(math.nan, 10.0, 1.0), (math.inf, 10.0, 1.0), (5.0, math.nan, 1.0), (5.0, 10.0, math.inf)],
)
def test_queue_resource_rejects_non_finite_rates(lam: float, mu: float, t: float) -> None:
    with pytest.raises(WhsizingError, match="non-finite"):
        queue_resource("packing", 2, lam, mu, t)


def test_receipts_mode_without_design_receipts_keeps_decant_and_pallets() -> None:
    """I64 on the F6c toy: receipts mode with units_in* = 0. D1 1000 units / 2 pallets, D2 500
    units / unknown pallets, D3 not operating. Pallets per unit from the whole history
    (2 / 1000) → D2 = 1 pallet, receiving 3 / 14 h; decant cases = units × derived cases per
    unit of the eligible SKUs (200 / 2000) = 150 → 150 / 90 h, never 0."""
    ib = build(toy()).design_day.inbound.model_copy(
        update={"mode": "receipts", "units_per_day": 0.0, "pallets_per_day": 0.0}
    )
    daily = frames()[0].with_columns(
        receipts_pallets=pl.Series([2.0, None, 0.0]), receipts_lines=pl.Series([5.0, 30.0, 0.0])
    )
    inp = build(toy(), "cube_asrs", dd={"inbound": ib})
    labor(inp, daily)
    assert value(inp, "labor.receiving.base_hours") == pytest.approx(3 / 14 * PFD, rel=1e-9)
    assert value(inp, "labor.decant.base_hours") == pytest.approx(150 / 90 * PFD, rel=1e-9)
    with pytest.raises(DataQualityError, match="without a pallet count"):
        labor(
            build(toy(), dd={"inbound": ib}),
            daily.with_columns(receipts_pallets=pl.lit(None, pl.Float64)),
        )


def test_labor_days_is_shared_by_the_worlds() -> None:
    """The data-only daily workloads (one frame) feed all three worlds: base hours differ by
    the productivities only (lo ≥ typ ≥ hi)."""
    _, tracer = sized("S2")
    base = [tracer.get("S2.labor.picking.base_hours", w).value for w in WORLDS]
    assert base[0] >= base[1] >= base[2] > 0
    days = {tracer.get("S2.labor.operating_days", w).value for w in WORLDS}
    assert days == {float(golden_inputs().daily["is_operating"].sum())}

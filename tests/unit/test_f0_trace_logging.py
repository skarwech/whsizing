"""F0 Tracer (§2.6) and structlog setup (§2.8)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import structlog

from whsizing.logging import configure_logging, get_logger, stage_timer, timings
from whsizing.schemas import TraceNode, Tracer


def _ports_trace() -> Tracer:
    t = Tracer(scope="S2")
    lam = t.record(
        "S2.throughput.lambda",
        "Peak flow",
        520.0,
        "lines/h",
        "peak_hour_lines / eta_flow",
        {"peak_hour_lines": "global.design.peak_hour_lines", "eta_flow": "param:engine.eta_flow"},
    )
    t.record(
        "global.design.peak_hour_lines",
        "Peak-hour lines",
        442.0,
        "lines/h",
        "max(hourly_lines)",
        {"hourly_lines": "data:daily_series"},
        scope="global",
    )
    lam_e = t.record(
        "S2.throughput.lambda_e",
        "Eligible flow",
        lam * 0.8,
        "lines/h",
        "lambda * share",
        {"lambda": "S2.throughput.lambda", "share": "param:cube_asrs.share"},
    )
    t.record(
        "S2.equipment.ports",
        "Cube ports",
        2.0,
        "-",
        "ceil(lambda_e / (port_rate * oee))",
        {"lambda_e": "S2.throughput.lambda_e", "port_rate": "param:cube_asrs.port_rate_lines_h"},
    )
    t.record("S2.equipment.ports", "Cube ports", 3.0, "-", "ceil(...)", {}, world="hi")
    assert lam_e == pytest.approx(416.0)
    return t


def test_tracer_record_get_and_worlds() -> None:
    t = _ports_trace()
    assert t.get("S2.equipment.ports").value == 2.0
    assert t.get("S2.equipment.ports", "hi").value == 3.0
    assert t.get("global.design.peak_hour_lines").scope == "global"
    assert len(t.nodes) == 5
    with pytest.raises(ValueError, match="recorded twice"):
        t.record("S2.equipment.ports", "Cube ports", 5.0, "-", "x", {})


def test_tracer_jsonl_round_trip(tmp_path: Path) -> None:
    t = _ports_trace()
    p = tmp_path / "trace.jsonl"
    t.export_jsonl(p)
    lines = p.read_text().splitlines()
    assert len(lines) == 5
    assert TraceNode.model_validate_json(lines[0]).id == "S2.throughput.lambda"
    assert Tracer.load_jsonl(p).nodes == t.nodes


def test_tracer_tree_expands_to_param_leaves() -> None:
    tree = _ports_trace().tree("S2.equipment.ports")
    assert tree["value"] == 2.0
    lam_e = tree["inputs"]["lambda_e"]
    assert lam_e["kind"] == "node"
    assert tree["inputs"]["port_rate"] == {
        "id": "param:cube_asrs.port_rate_lines_h",
        "kind": "param",
    }
    lam = lam_e["inputs"]["lambda"]
    assert lam["inputs"]["eta_flow"]["kind"] == "param"
    assert lam["inputs"]["peak_hour_lines"]["inputs"]["hourly_lines"]["kind"] == "unresolved"


def test_tracer_tree_survives_cycles() -> None:
    t = Tracer()
    t.record("a", "A", 1, "-", "b", {"b": "b"})
    t.record("b", "B", 1, "-", "a", {"a": "a"})
    assert t.tree("a")["inputs"]["b"]["inputs"]["a"]["kind"] == "cycle"


def test_logging_json_file_carries_run_stage_scenario_and_timings(tmp_path: Path) -> None:
    log = tmp_path / "logs" / "run.log"
    configure_logging("run-123", log)
    with stage_timer("size"), structlog.contextvars.bound_contextvars(scenario="S1"):
        get_logger("whsizing.engine.size").info("sized", robots=12)
    get_logger().info("done")
    records = [json.loads(line) for line in log.read_text().splitlines()]
    assert [r["event"] for r in records] == ["sized", "stage_done", "done"]
    assert (
        records[0] | {"run_id": "run-123", "stage": "size", "scenario": "S1", "robots": 12}
        == records[0]
    )
    assert records[1]["stage"] == "size" and records[1]["duration_s"] >= 0
    assert records[2]["stage"] is None and records[2]["run_id"] == "run-123"
    assert set(timings()) == {"size"}
    configure_logging("run-456")
    assert timings() == {}

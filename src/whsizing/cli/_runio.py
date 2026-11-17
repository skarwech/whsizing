"""Read the artifacts of a run folder back into library objects (stage commands, F10).

Nothing here sizes anything: results come from `scenarios/<id>/{result,finance}.json` and
`trace.jsonl`, the comparison from `comparison/`, the manifest from `manifest.json`.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ValidationError

from whsizing.errors import ConfigError
from whsizing.scenarios.load import load_scenarios
from whsizing.scenarios.manifest import read_manifest
from whsizing.scenarios.runner import Evaluated
from whsizing.schemas import (
    Comparison,
    FinancialResult,
    ScenarioResult,
    ScenarioSet,
    Sensitivity,
)
from whsizing.schemas.run import RunOutput
from whsizing.schemas.trace import TraceNode, Tracer

SENSITIVITY_FILE = Path("comparison") / "sensitivity.json"
COMPARISON_FILE = Path("comparison") / "comparison.json"


def read_model[M: BaseModel](path: Path, model: type[M], hint: str) -> M:
    """`path` (JSON) validated as `model`; ConfigError names the file and what to run."""
    try:
        return model.model_validate_json(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ConfigError(f"{path}: not found ({hint})") from None
    except OSError as e:
        raise ConfigError(f"{path}: cannot read file ({e.strerror})") from e
    except ValueError as e:
        raise ConfigError(f"{path}: invalid {model.__name__}: {e}") from e


def check_trace(path: Path) -> None:
    """ConfigError (one line: file, line, first problem) when a line of a trace.jsonl is not a
    TraceNode; `Tracer.load_jsonl` alone dumps pydantic's whole report and does not say where."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        raise ConfigError(f"{path}: not found (run `whsizing size`)") from None
    except (OSError, UnicodeDecodeError) as e:
        raise ConfigError(
            f"{path}: cannot read the trace ({getattr(e, 'strerror', None) or e})"
        ) from e
    for n, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            TraceNode.model_validate_json(line)
        except ValidationError as e:
            first = e.errors()[0]
            where = ".".join(str(p) for p in first["loc"])
            problem = f"{where}: {first['msg']}" if where else first["msg"]
            raise ConfigError(f"{path}: line {n}: invalid trace node ({problem})") from None


def check_traces(run: Path) -> None:
    """`check_trace` of the trace.jsonl beside every scenarios/<id>/result.json of `run` (the
    runner writes both, also for a not-computed scenario): a missing one is an error too."""
    for result in sorted((run / "scenarios").glob("*/result.json")):
        check_trace(result.with_name("trace.jsonl"))


def load_results(
    run: Path, scenarios: ScenarioSet
) -> tuple[dict[str, ScenarioResult], dict[str, FinancialResult]]:
    """Results of every scenario of `scenarios` (file order) and finances of the computed ones."""
    results: dict[str, ScenarioResult] = {}
    finances: dict[str, FinancialResult] = {}
    for s in scenarios.scenarios:
        folder = run / "scenarios" / s.id
        results[s.id] = read_model(folder / "result.json", ScenarioResult, "run `whsizing size`")
        if results[s.id].status == "computed":
            finances[s.id] = read_model(
                folder / "finance.json", FinancialResult, "run `whsizing size`"
            )
    return results, finances


def load_evaluated(
    run: Path,
    results: dict[str, ScenarioResult],
    finances: dict[str, FinancialResult],
) -> dict[str, Evaluated]:
    """The computed scenarios as the sensitivity hook wants them: result, finance, trace."""
    check_traces(run)
    return {
        sid: Evaluated(
            results[sid], fin, Tracer.load_jsonl(run / "scenarios" / sid / "trace.jsonl")
        )
        for sid, fin in finances.items()
    }


def load_run(run: Path) -> RunOutput:
    """The `RunOutput` of a sized and compared run (what F9 builds the report from)."""
    scenarios = load_scenarios(run / "inputs" / "scenarios.yaml")
    results, finances = load_results(run, scenarios)
    hint = "run `whsizing compare`"
    sens_path = run / SENSITIVITY_FILE
    return RunOutput(
        run_dir=run,
        manifest=read_manifest(run),
        results=results,
        finances=finances,
        comparison=read_model(run / COMPARISON_FILE, Comparison, hint),
        sensitivity=read_model(sens_path, Sensitivity, hint) if sens_path.is_file() else None,
    )

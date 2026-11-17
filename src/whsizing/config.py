"""YAML → Pydantic loaders. Every model forbids unknown keys; errors become ConfigError (exit 2)."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ValidationError

from whsizing.errors import ConfigError
from whsizing.schemas.project import Project


def load_yaml_model[M: BaseModel](path: Path | str, model: type[M]) -> M:
    """Load `path` with yaml.safe_load and validate it as `model`.

    Relative paths typed `ResolvedPath` resolve against the YAML file's folder.
    """
    path = Path(path)
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as e:
        raise ConfigError(f"{path}: cannot read file ({e.strerror})") from e
    except yaml.YAMLError as e:
        raise ConfigError(f"{path}: invalid YAML: {e}") from e
    if not isinstance(data, dict):
        raise ConfigError(f"{path}: expected a mapping of keys at the top level")
    try:
        return model.model_validate(data, context={"base_dir": path.parent.resolve()})
    except ValidationError as e:
        raise ConfigError(_describe(path, model, e)) from e


def _describe(path: Path, model: type[BaseModel], e: ValidationError) -> str:
    lines = [f"{path}: invalid {model.__name__} ({e.error_count()} error(s))"]
    for err in e.errors():
        key = ".".join(str(p) for p in err["loc"]) or "<root>"
        msg = "unknown key" if err["type"] == "extra_forbidden" else err["msg"]
        lines.append(f"  - {key}: {msg}")
    return "\n".join(lines)


def load_project(path: Path | str) -> Project:
    """Load project.yaml (Appendix E)."""
    return load_yaml_model(path, Project)

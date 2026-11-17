"""project.yaml (Appendix E). Relative paths resolve against the YAML file's folder."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Literal, cast

from pydantic import AfterValidator, Field, ValidationInfo

from whsizing.schemas.params import DatasetKind, StrictModel
from whsizing.schemas.profile import ProfileCfg


def _resolve(v: Path, info: ValidationInfo) -> Path:
    """Expand ~ and join relative paths to `context["base_dir"]` when a loader provides it."""
    v = v.expanduser()
    context = cast(dict[str, object], info.context or {})
    base = context.get("base_dir")
    if v.is_absolute() or base is None:
        return v
    return Path(str(base)) / v


ResolvedPath = Annotated[Path, AfterValidator(_resolve)]


class InputSpec(StrictModel):
    files: list[ResolvedPath]  # may contain glob patterns, e.g. data/stock_*.csv
    mapping: ResolvedPath | None = None
    sheet: str | int | None = None


class ProjectOptions(StrictModel):
    worlds: Literal["typ", "all"] = "all"
    sensitivity: bool = True
    delta: float = Field(default=0.2, ge=0, lt=1)  # F8 sensitivity: typ x (1 -/+ delta)
    strict: bool = False
    keep_descriptions: bool = False  # F2: keep the description and customer columns (I78 e)


class Project(StrictModel):
    name: str
    language: list[Literal["fr", "en"]] = ["fr"]
    out_dir: ResolvedPath = Path("runs")
    catalog: ResolvedPath = Path("catalog")
    salt_file: ResolvedPath | None = None
    inputs: dict[DatasetKind, InputSpec | None]
    basis: ResolvedPath
    scenarios: ResolvedPath
    profile_cfg: ProfileCfg = ProfileCfg()
    options: ProjectOptions = ProjectOptions()

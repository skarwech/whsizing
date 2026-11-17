"""Strict, versioned catalog loader (F5 loader rules, §2.5.1). Id rule: catalog/README.md."""

from __future__ import annotations

import hashlib
import re
import shutil
from collections.abc import Iterator
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ValidationError

from whsizing.catalog.models import (
    AreaFactors,
    Catalog,
    CatalogParam,
    EngineDefaults,
    Family,
    FinanceDefaults,
    IcpeTable,
    LaborStandards,
    StorageClasses,
)
from whsizing.config import _describe  # pyright: ignore[reportPrivateUsage]
from whsizing.errors import ConfigError
from whsizing.logging import get_logger
from whsizing.schemas import FamilyId, Param

# file name → (id prefix, model)
SUPPORTING: dict[str, tuple[str, type[BaseModel]]] = {
    "labor_standards.yaml": ("labor", LaborStandards),
    "finance_defaults.yaml": ("finance", FinanceDefaults),
    "storage_classes.yaml": ("storage", StorageClasses),
    "area_factors.yaml": ("area", AreaFactors),
    "icpe_1510.yaml": ("icpe", IcpeTable),
    "engine_defaults.yaml": ("engine", EngineDefaults),
}
FAMILY_IDS: tuple[FamilyId, ...] = ("manual_p2p", "amr_gtp", "cube_asrs")
# top-level grouping keys dropped from ids; a trailing `standard` (labor activities) is dropped too
GROUP_KEYS = frozenset(
    {"constraints", "storage", "throughput", "area", "capex", "opex", "life"}
    | {"activities", "profiles"}
)


def infer_pessimistic_end(unit: str, name: str = "") -> Literal["min", "max"] | None:
    """§2.5.1: which bound is pessimistic, from unit tokens (and name words). None = explicit.

    In order: an `eur` token or `€` (costs; so `eur/m2` → max) or a `kWh` token (energy) → max; a
    rate per hour (`x/h`) or a density per m² (`x/m2`) → min; a `fill`, `availability` or `oee`
    word in the unit or name → min; the unit exactly `h` (a duration), `m2 per …` or a `m2_per`
    name that is not a density (`…_per_m2_…`) (area per unit) → max. Anything else
    (`pallets/shift`, `units/month`, `share`, `-`) → None.
    """
    u, n = unit.strip().lower(), name.lower()
    per = u.partition("/")[2].strip()
    unit_words = set(re.findall(r"[a-z0-9]+", u))
    if unit_words & {"eur", "kwh"} or "€" in u:
        return "max"
    if per in ("h", "m2"):
        return "min"
    if (unit_words | set(re.findall(r"[a-z0-9]+", n))) & {"fill", "availability", "oee"}:
        return "min"
    if u == "h" or "m2 per" in u or ("m2_per" in n and "per_m2" not in n):
        return "max"
    return None


def flat_id(prefix: str, path: tuple[str, ...]) -> str:
    """`storage.pallet_rack.fill_factor` in manual_p2p → `manual_p2p.pallet_rack_fill_factor`."""
    keys = list(path)
    if len(keys) > 1 and keys[0] in GROUP_KEYS:
        keys = keys[1:]
    if len(keys) > 1 and keys[-1] == "standard":
        keys = keys[:-1]
    return f"{prefix}.{'_'.join(keys)}"


def load_catalog(catalog_dir: Path | str) -> Catalog:
    """Load and validate every catalog file; raise ConfigError naming the file and key."""
    root = Path(catalog_dir)
    if not root.is_dir():
        raise ConfigError(f"{root}: catalog folder not found")
    unknown = sorted(f.name for f in root.glob("*.yaml") if f.name not in SUPPORTING)
    missing = sorted(n for n in SUPPORTING if not (root / n).is_file())
    if unknown or missing:
        raise ConfigError(f"{root}: unknown catalog file(s) {unknown}, missing file(s) {missing}")

    params: dict[str, Param] = {}
    constants: dict[str, float] = {}
    where: dict[str, str] = {}  # id → "file: key", for duplicate messages
    warnings: list[str] = []

    def add(obj: BaseModel, prefix: str, path: Path) -> None:
        for pid, key, value in _flatten(obj, prefix, path, warnings):
            if pid in where:
                raise ConfigError(f"{path}: {key}: duplicate id {pid!r} (also {where[pid]})")
            where[pid] = f"{path}: {key}"
            if isinstance(value, Param):
                params[pid] = value
            else:
                constants[pid] = value

    families: dict[FamilyId, Family] = {}
    for path in sorted((root / "families").glob("*.yaml")):
        fam = _load(path, Family)
        if fam.id in families:
            raise ConfigError(f"{path}: id: duplicate family id {fam.id!r}")
        families[fam.id] = fam
        add(fam, fam.id, path)
    absent = [f for f in FAMILY_IDS if f not in families]
    if absent:
        raise ConfigError(f"{root / 'families'}: missing family file(s) for {absent}")

    parts: dict[str, Any] = {}
    for name, (prefix, model) in SUPPORTING.items():
        parts[prefix] = _load(root / name, model)
        add(parts[prefix], prefix, root / name)

    catalog = Catalog(
        version=_version(root, families),
        families=families,
        **parts,
        params=params,
        constants=constants,
        warnings=warnings,
    )
    log = get_logger()
    for w in warnings:
        log.warning("catalog_warning", detail=w)
    if catalog.todo_count:
        log.warning("catalog_todo_sources", count=catalog.todo_count, total=len(params))
    return catalog


def validate_catalog(catalog_dir: Path | str) -> list[str]:
    """Every problem of the catalog folder, not only the first one `load_catalog` raises: one
    message per unknown or missing file and per file that fails to load (each names the file and
    the key); an empty list means `load_catalog` succeeds. The checks across files (duplicate ids,
    a family without its file) run once every file is valid on its own."""
    return check_catalog(catalog_dir)[0]


def check_catalog(catalog_dir: Path | str) -> tuple[list[str], Catalog | None]:
    """`validate_catalog`'s errors, plus the loaded catalog when there are none (one load)."""
    root = Path(catalog_dir)
    if not root.is_dir():
        return [f"{root}: catalog folder not found"], None
    unknown = sorted(f.name for f in root.glob("*.yaml") if f.name not in SUPPORTING)
    missing = sorted(n for n in SUPPORTING if not (root / n).is_file())
    errors = []
    if unknown or missing:
        errors.append(f"{root}: unknown catalog file(s) {unknown}, missing file(s) {missing}")
    for path in sorted((root / "families").glob("*.yaml")):
        errors += _file_errors(path, None, Family)
    for name, (prefix, model) in SUPPORTING.items():
        if (root / name).is_file():
            errors += _file_errors(root / name, prefix, model)
    if not errors:
        try:
            return [], load_catalog(root)
        except ConfigError as e:
            errors.append(str(e))
    return errors, None


def _file_errors(path: Path, prefix: str | None, model: type[BaseModel]) -> list[str]:
    """The ConfigError `load_catalog` would raise for this file (its id prefix: the family's own
    id when `prefix` is None), as a list of 0 or 1 messages."""
    try:
        obj = _load(path, model)
        list(_flatten(obj, obj.id if isinstance(obj, Family) else prefix or "", path, []))
    except ConfigError as e:
        return [str(e)]
    return []


def snapshot_catalog(catalog_dir: Path | str, dest: Path | str) -> Path:
    """Copy the catalog folder into a run (runs/<id>/inputs/catalog/); returns `dest`."""
    ignore = shutil.ignore_patterns("__pycache__", ".*")
    return Path(shutil.copytree(catalog_dir, dest, ignore=ignore, dirs_exist_ok=True))


def _version(root: Path, families: dict[FamilyId, Family]) -> str:
    """Family semvers + sha256 of every YAML file (relative path + bytes, sorted): stable."""
    h = hashlib.sha256()
    for f in sorted(root.rglob("*.yaml")):
        h.update(f.relative_to(root).as_posix().encode() + b"\0" + f.read_bytes() + b"\0")
    semvers = " ".join(f"{fid}={families[fid].version}" for fid in FAMILY_IDS)
    return f"{semvers} sha256:{h.hexdigest()[:12]}"


class _UniqueKeyLoader(yaml.SafeLoader):
    """safe_load that rejects duplicate mapping keys (safe_load silently keeps the last one)."""

    def construct_mapping(self, node: Any, deep: bool = False) -> Any:
        seen: set[Any] = set()
        for key_node, _ in node.value:
            key = self.construct_object(key_node, deep=deep)
            if key in seen:
                raise yaml.constructor.ConstructorError(
                    None, None, f"duplicate key {key!r}", key_node.start_mark
                )
            seen.add(key)
        return super().construct_mapping(node, deep=deep)


def _load[M: BaseModel](path: Path, model: type[M]) -> M:
    try:
        data = yaml.load(path.read_text(encoding="utf-8"), Loader=_UniqueKeyLoader)
    except OSError as e:
        raise ConfigError(f"{path}: cannot read file ({e.strerror})") from e
    except UnicodeDecodeError as e:
        raise ConfigError(f"{path}: not UTF-8 (byte {e.start}); save the file as UTF-8") from e
    except yaml.YAMLError as e:
        raise ConfigError(f"{path}: invalid YAML: {e}") from e
    if not isinstance(data, dict):
        raise ConfigError(f"{path}: expected a mapping of keys at the top level")
    _reject_shorthand(data, (), path)
    try:
        return model.model_validate(data)
    except ValidationError as e:
        raise ConfigError(_describe(path, model, e)) from e


def _reject_shorthand(node: object, path: tuple[str, ...], file: Path) -> None:
    if isinstance(node, dict):
        for k, v in node.items():
            _reject_shorthand(v, (*path, str(k)), file)
    elif isinstance(node, str) and node.lstrip().startswith("R("):
        raise ConfigError(
            f"{file}: {'.'.join(path)}: R(...) shorthand is not allowed; spell out the Param block"
            " (id, unit, min, typ, max, source, confidence, pessimistic_end, date)"
        )


def _walk(
    node: object, path: tuple[str, ...]
) -> Iterator[tuple[tuple[str, ...], CatalogParam | float]]:
    """Yield (path, CatalogParam | number) leaves; strings, bools and lists are not parameters."""
    if isinstance(node, CatalogParam):
        yield path, node
    elif isinstance(node, BaseModel):
        for name in type(node).model_fields:
            yield from _walk(getattr(node, name), (*path, name))
    elif isinstance(node, dict):
        for k, v in node.items():  # pyright: ignore[reportUnknownVariableType]
            yield from _walk(v, (*path, str(k)))  # pyright: ignore[reportUnknownArgumentType]
    elif isinstance(node, int | float) and not isinstance(node, bool):
        yield path, float(node)


def _flatten(
    obj: BaseModel, prefix: str, file: Path, warnings: list[str]
) -> Iterator[tuple[str, str, Param | float]]:
    """Yield (id, yaml key, Param | constant); resolve pessimistic_end per §2.5.1."""
    for path, leaf in _walk(obj, ()):
        pid, key = flat_id(prefix, path), ".".join(path)
        if not isinstance(leaf, CatalogParam):
            yield pid, key, leaf
            continue
        if leaf.id is not None and leaf.id != pid:
            raise ConfigError(f"{file}: {key}: id {leaf.id!r} must be {pid!r} (catalog/README.md)")
        inferred = infer_pessimistic_end(leaf.unit, pid.split(".", 1)[1])
        end = leaf.pessimistic_end or inferred
        if end is None:
            raise ConfigError(
                f"{file}: {key}: pessimistic_end missing and not inferable from unit "
                f"{leaf.unit!r}; set it to min or max"
            )
        if inferred is not None and leaf.pessimistic_end not in (None, inferred):
            warnings.append(
                f"{file}: {key}: pessimistic_end {leaf.pessimistic_end!r} contradicts the "
                f"§2.5.1 inference {inferred!r} from unit {leaf.unit!r}"
            )
        fields = leaf.model_dump(exclude={"id", "pessimistic_end"})
        try:
            yield pid, key, Param(id=pid, pessimistic_end=end, **fields)
        except ValidationError as e:
            raise ConfigError(f"{file}: {key}: {e.errors()[0]['msg']}") from e

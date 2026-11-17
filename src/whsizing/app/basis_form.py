"""The design-basis form of page 4, generated from the `DesignBasis` schema (F10b).

`leaves` walks the schema, so a field added to `DesignBasis` shows up in the form with the right
widget. Labels and units come from `whsizing.design.basis.FIELDS`; a field with a schema default
is marked `[P]` (placeholder default, to confirm with the client) and a required one `[CLIENT]`.
Values travel as a nested dict (what basis.yaml holds); validation is the library's:
`DesignBasis.model_validate` then `check_basis` (the CLI's `load_basis` does the same).
"""

from __future__ import annotations

import math
import types
from dataclasses import dataclass
from datetime import time
from typing import Any, Literal, Union, get_args, get_origin

import streamlit as st
import yaml
from pydantic import BaseModel, ValidationError

from whsizing.app.strings import section_title, tr
from whsizing.catalog import Catalog, ParamSet
from whsizing.design.basis import EXAMPLES, FIELDS, UNSET_IN_TEMPLATE, VERIFY
from whsizing.design.validate import check_basis
from whsizing.errors import ConfigError
from whsizing.report import Lang
from whsizing.schemas import DesignBasis

PERCENTILE = "projection.design_percentile"
PERCENTILE_RANGE = (50.0, 100.0)
Kind = Literal["choice", "bool", "int", "float", "time", "text", "mapping"]


@dataclass(frozen=True)
class Leaf:
    path: str  # "operations.shifts_per_day"
    annotation: Any
    default: Any  # None when the field is required
    required: bool

    @property
    def group(self) -> str:
        head, dot, _ = self.path.partition(".")
        return head if dot or head == "overrides" else "general"


def leaves(model: type[BaseModel] = DesignBasis, prefix: str = "") -> list[Leaf]:
    """The non-model fields of the schema in declaration order (sub-models are walked)."""
    out: list[Leaf] = []
    for name, field in model.model_fields.items():
        ann = field.annotation
        if isinstance(ann, type) and issubclass(ann, BaseModel):
            out += leaves(ann, f"{prefix}{name}.")
            continue
        default = None if field.is_required() else field.get_default(call_default_factory=True)
        out.append(Leaf(f"{prefix}{name}", ann, default, field.is_required()))
    return out


def kind_of(annotation: Any) -> tuple[Kind, bool]:
    """(widget kind, optional) of a field annotation."""
    origin, args = get_origin(annotation), get_args(annotation)
    if origin in (Union, types.UnionType):
        inner = [a for a in args if a is not type(None)]
        return kind_of(inner[0])[0], len(inner) < len(args)
    if origin is Literal:
        return "choice", False
    if origin is dict:
        return "mapping", False
    kinds: dict[Any, Kind] = {bool: "bool", int: "int", float: "float", time: "time", str: "text"}
    return kinds[annotation], False


# ------------------------------------------------------------------------------------ values
LEAF_PATHS = frozenset(leaf.path for leaf in leaves())


def flatten(nested: dict[str, Any], prefix: str = "") -> dict[str, Any]:
    """basis.yaml layout to dotted leaf paths (`overrides` and the dict fields stay whole)."""
    out: dict[str, Any] = {}
    for key, value in nested.items():
        path = prefix + key
        if isinstance(value, dict) and path not in LEAF_PATHS:
            out |= flatten(value, f"{path}.")
        else:
            out[path] = value
    return out


def nest(flat: dict[str, Any]) -> dict[str, Any]:
    """Dotted paths back to the basis.yaml layout; None and empty mappings are left out (the
    schema default applies, as when the key is not written in the YAML)."""
    out: dict[str, Any] = {}
    for path, value in flat.items():
        if value is None or value == {}:
            continue
        *heads, last = path.split(".")
        node = out
        for head in heads:
            node = node.setdefault(head, {})
        node[last] = value
    return out


def initial_values(saved: dict[str, Any] | None) -> dict[str, Any]:
    """Flat values of every leaf: the saved ones, else the schema default, else the example of
    the template for a required client value. `trailing_months` stays unset (derived, I55)."""
    flat = flatten(saved or {})
    values: dict[str, Any] = {}
    for leaf in leaves():
        if leaf.path in flat:
            values[leaf.path] = flat[leaf.path]
        elif leaf.path in UNSET_IN_TEMPLATE:
            values[leaf.path] = None
        elif leaf.required:
            values[leaf.path] = EXAMPLES.get(leaf.path, _zero(leaf))
        else:
            values[leaf.path] = _plain(leaf.default)
    return values


def _zero(leaf: Leaf) -> Any:
    return {"text": "", "int": 0, "float": 0.0, "mapping": {}}.get(kind_of(leaf.annotation)[0])


def _plain(value: Any) -> Any:
    """A default as the YAML holds it: times as "HH:MM", sub-model defaults left to the schema."""
    if isinstance(value, time):
        return value.strftime("%H:%M")
    return None if isinstance(value, BaseModel) else value


def validate(
    nested: dict[str, Any], catalog: Catalog | None = None
) -> tuple[DesignBasis | None, list[str]]:
    """The basis the values make, or the messages of the library's own checks. With a `catalog`
    the overrides are also applied to it (`ParamSet`: an unknown parameter id is a ConfigError,
    which the sizing would raise later)."""
    try:
        basis = DesignBasis.model_validate(nested)
        basis = check_basis(basis, nested.get("overrides") or {})
        if catalog is not None:
            ParamSet(catalog, basis.overrides)
        return basis, []
    except ValidationError as e:
        return None, [f"{'.'.join(map(str, err['loc']))}: {err['msg']}" for err in e.errors()]
    except ConfigError as e:
        return None, [str(e)]


# ------------------------------------------------------------------------------------ widgets
def render_form(
    flat: dict[str, Any], key_prefix: str, lg: Lang
) -> tuple[dict[str, Any], list[str]]:
    """One widget per leaf, grouped by section. Returns the new flat values and the messages of
    the fields that could not be read (a mapping that is not YAML)."""
    out: dict[str, Any] = {}
    problems: list[str] = []
    groups: dict[str, list[Leaf]] = {}
    for leaf in leaves():
        groups.setdefault(leaf.group, []).append(leaf)
    for group, members in groups.items():
        with st.expander(section_title(group, lg), expanded=group in ("general", "projection")):
            for leaf in members:
                value, problem = _widget(leaf, flat[leaf.path], f"{key_prefix}.{leaf.path}", lg)
                out[leaf.path] = value
                problems += [problem] if problem else []
    return out, problems


def _label(leaf: Leaf, value: Any, lg: Lang) -> str:
    unit, en, fr = FIELDS.get(leaf.path, ("-", leaf.path, leaf.path))
    text = (fr if lg == "fr" else en).capitalize()
    text += f" [{unit}]" if unit != "-" else ""
    if leaf.required:
        tag = tr("tag_client", lg)
    elif value == _plain(leaf.default) or (leaf.path in UNSET_IN_TEMPLATE and value is None):
        tag = tr("tag_default", lg)
    else:
        tag = tr("tag_modified", lg)
    return f"{text} {tag}" + (" [VERIFY]" if leaf.path in VERIFY else "")


def _help(leaf: Leaf, lg: Lang) -> str | None:
    if leaf.required:
        return None
    return tr("default_is", lg, value=_plain(leaf.default))


def _step(value: float) -> float:
    return 0.01 if not value else max(10.0 ** (math.floor(math.log10(abs(value))) - 1), 0.001)


def _widget(leaf: Leaf, value: Any, key: str, lg: Lang) -> tuple[Any, str | None]:
    kind, optional = kind_of(leaf.annotation)
    label, help_ = _label(leaf, value, lg), _help(leaf, lg)
    if leaf.path == PERCENTILE:
        lo, hi = PERCENTILE_RANGE
        start = min(max(float(value), lo), hi)
        return st.slider(label, lo, hi, start, 0.5, key=key, help=help_), None
    if kind == "choice":
        options = list(get_args(leaf.annotation))
        index = options.index(value) if value in options else 0
        return st.selectbox(label, options, index, key=key, help=help_), None
    if kind == "bool":
        options = [None, True, False] if optional else [True, False]
        index = options.index(value) if value in options else 0
        return st.selectbox(label, options, index, key=key, help=help_), None
    if kind == "mapping":
        return _mapping_widget(leaf, label, value, key, help_)
    if kind == "int":
        start = None if value is None else int(value)
        number = st.number_input(label, 0, value=start, step=1, key=key, help=help_)
        return (None if number is None else int(number)), None
    if kind == "float":
        start = None if value is None else float(value)
        step = _step(start or 0.0)
        return st.number_input(
            label, value=start, step=step, format="%g", key=key, help=help_
        ), None
    return st.text_input(label, value, key=key, help=help_), None


def _mapping_widget(
    leaf: Leaf, label: str, value: dict[str, Any] | None, key: str, help_: str | None
) -> tuple[Any, str | None]:
    """A mapping is edited as YAML (`role: value` lines)."""
    text = yaml.safe_dump(value or {}, sort_keys=False, allow_unicode=True).removeprefix("{}\n")
    edited = st.text_area(label, text, key=key, help=help_)
    try:
        parsed = yaml.safe_load(edited) if edited.strip() else {}
    except yaml.YAMLError as e:
        return value, f"{leaf.path}: {e}"
    except (ValueError, RecursionError) as e:  # a 5000-digit integer, 3000 nested `[`: no YAMLError
        return value, f"{leaf.path}: {type(e).__name__}: {str(e)[:200]}"
    if not isinstance(parsed, dict):
        return value, f"{leaf.path}: expected `name: value` lines"
    return parsed, None

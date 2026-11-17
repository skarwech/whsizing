"""One card per scenario on page 5 (F10b): family, overrides as sliders bounded by the catalog
min / max, eligibility settings. The cards edit the content of scenarios.yaml (a dict); the
library's `ScenarioSet` validates it and writes it (`model_dump`)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, get_args

import streamlit as st
from pydantic import ValidationError

from whsizing.app.state import read_yaml
from whsizing.app.strings import tr
from whsizing.catalog import Catalog
from whsizing.report import Lang
from whsizing.schemas import ScenarioSet
from whsizing.schemas.params import FamilyId, Param

FAMILIES: tuple[str, ...] = get_args(FamilyId)
SHARED_PREFIXES = ("labor.", "finance.", "engine.")
EXAMPLE = Path("scenarios") / "example_scenarios.yaml"
KEY = "scn"  # prefix of the widget keys, cleared when the card list changes
CLIENT_CURRENT = "client_current"


def initial_scenarios(saved: dict[str, Any] | None) -> dict[str, Any]:
    """The saved scenarios, else the example file of the repository, else one manual scenario."""
    fallback = {
        "scenarios": [{"id": "S0", "name": "Manual", "family": "manual_p2p"}],
        "baseline": CLIENT_CURRENT,
    }
    return saved or read_yaml(EXAMPLE) or fallback


def validate(data: dict[str, Any], lg: Lang = "en") -> tuple[ScenarioSet | None, list[str]]:
    """The set the cards make, or the messages why not (an empty list is valid for the schema
    but there is nothing to size: both buttons of page 5 stay disabled)."""
    try:
        scenario_set = ScenarioSet.model_validate(data)
    except ValidationError as e:
        return None, [f"{'.'.join(map(str, err['loc']))}: {err['msg']}" for err in e.errors()]
    if not scenario_set.scenarios:
        return None, [tr("scn.none", lg)]
    return scenario_set, []


def with_added(data: dict[str, Any]) -> dict[str, Any]:
    ids = {s["id"] for s in data["scenarios"]}
    n = len(ids)
    while f"S{n}" in ids:
        n += 1
    new = {"id": f"S{n}", "name": f"Scenario S{n}", "family": FAMILIES[0]}
    return {**data, "scenarios": [*data["scenarios"], new]}


def reset_widgets() -> None:
    """Widget keys are per card index: forget them when a card is added or removed."""
    for key in [k for k in st.session_state if str(k).startswith(KEY)]:
        del st.session_state[key]


def override_choices(catalog: Catalog, family: str, current: dict[str, float]) -> list[str]:
    """Catalog params a scenario of `family` may override, plus any already overridden."""
    ids = [
        pid
        for pid in catalog.params
        if pid.startswith(f"{family}.") or pid.startswith(SHARED_PREFIXES)
    ]
    return sorted(set(ids) | set(current))


def render_cards(
    data: dict[str, Any], catalog: Catalog, run_key: str, lg: Lang
) -> tuple[dict[str, Any], set[int]]:
    """The cards of `data`: the edited content and the indexes the user asked to remove."""
    key = f"{KEY}.{run_key}"
    ids = [s["id"] for s in data["scenarios"]]
    baseline_options = [CLIENT_CURRENT, *ids]
    current = data.get("baseline", CLIENT_CURRENT)
    baseline = st.selectbox(
        tr("baseline", lg),
        baseline_options,
        baseline_options.index(current) if current in baseline_options else 0,
        key=f"{key}.baseline",
    )
    cards: list[dict[str, Any]] = []
    removed: set[int] = set()
    for i, scenario in enumerate(data["scenarios"]):
        card, remove = _card(scenario, catalog, f"{key}.{i}", baseline or CLIENT_CURRENT, lg)
        cards.append(card)
        if remove:
            removed.add(i)
    return {**data, "scenarios": cards, "baseline": baseline}, removed


def _card(
    s: dict[str, Any], catalog: Catalog, key: str, baseline: str, lg: Lang
) -> tuple[dict[str, Any], bool]:
    with st.container(border=True):
        c_id, c_name, c_family = st.columns([1, 3, 3])
        sid = c_id.text_input(tr("sc_id", lg), s["id"], key=f"{key}.id")
        name = c_name.text_input(tr("sc_name", lg), s.get("name", ""), key=f"{key}.name")
        family = c_family.selectbox(
            tr("sc_family", lg),
            FAMILIES,
            FAMILIES.index(s["family"]) if s["family"] in FAMILIES else 0,
            format_func=lambda f: getattr(catalog.families[f].title, lg),  # type: ignore[index]
            key=f"{key}.family",
        )
        overrides = _overrides(s.get("overrides", {}), catalog, family, key, lg)
        eligibility = _eligibility(s.get("eligibility", {}), key, lg)
        remove = st.button(tr("sc_remove", lg), key=f"{key}.remove")
    card = {**s, "id": sid, "name": name, "family": family, "is_baseline": sid == baseline}
    return {**card, "overrides": overrides, "eligibility": eligibility}, remove


def _overrides(
    current: dict[str, float], catalog: Catalog, family: str, key: str, lg: Lang
) -> dict[str, float]:
    options = override_choices(catalog, family, current)
    chosen = st.multiselect(
        tr("sc_overrides", lg), options, [p for p in current if p in options], key=f"{key}.ov"
    )
    return {pid: _slider(catalog.params[pid], current.get(pid), key, lg) for pid in chosen}


def _slider(param: Param, value: float | None, key: str, lg: Lang) -> float:
    """A value between the catalog min and max, starting at the override or the typ."""
    label = f"{param.id} [{param.unit}]  (typ {param.typ:g})"
    start = param.typ if value is None else value
    if param.min == param.max:
        st.caption(f"{label}: {param.typ:g}")
        return param.typ
    if not param.min <= start <= param.max:
        st.warning(tr("sc_out_of_range", lg, pid=param.id, value=start, lo=param.min, hi=param.max))
        start = min(max(start, param.min), param.max)
    step = (param.max - param.min) / 100
    return float(
        st.slider(
            label,
            param.min,
            param.max,
            float(start),
            step,
            key=f"{key}.ov.{param.id}",
            help=f"{param.source}; confidence {param.confidence}",
        )
    )


def _eligibility(current: dict[str, Any], key: str, lg: Lang) -> dict[str, Any]:
    cols = st.columns(3)
    catalog_limits = cols[0].checkbox(
        tr("sc_use_limits", lg), current.get("use_catalog_limits", True), key=f"{key}.limits"
    )
    assume = cols[1].checkbox(
        tr("sc_assume_dims", lg),
        current.get("assume_eligible_if_missing_dims", False),
        key=f"{key}.assume",
    )
    extra = cols[2].number_input(
        tr("sc_extra_weight", lg), 0.0, value=current.get("extra_max_weight_kg"), key=f"{key}.extra"
    )
    return {
        "use_catalog_limits": catalog_limits,
        "assume_eligible_if_missing_dims": assume,
        "extra_max_weight_kg": extra,
    }

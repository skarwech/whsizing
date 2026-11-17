"""F4 step 9: one Assumption per basis field, origin default / client / override / derived."""

from __future__ import annotations

from datetime import time
from typing import Any

from whsizing.design.basis import FIELDS, UNSET_IN_TEMPLATE, VERIFY, leaf_fields, yaml_value
from whsizing.schemas import Assumption, DesignBasis

DERIVED_NOTES = {
    "service.sla_window_hours": "carrier_departure_time − cutoff_time, modulo 24 h (I16)",
    "flows.inbound_peak_factor": (
        "derived mode: outbound peak-to-average, P95 / mean of daily lines (F4); "
        "receipts mode: 1.0 (I56)"
    ),
    "projection.trailing_months": "24 if the history covers ≥ 23.9 months, else 12 (I55)",
}


def _value(v: Any) -> float | str:
    """Numbers as float; text as is; times "HH:MM"; null ""; bools, dicts, lists as YAML."""
    if isinstance(v, int | float) and not isinstance(v, bool):
        return float(v)
    if isinstance(v, str):
        return v
    if isinstance(v, time):
        return v.strftime("%H:%M")
    return "" if v is None else yaml_value(v)


def basis_assumptions(
    basis: DesignBasis, derived: dict[str, float], extra: list[Assumption] | None = None
) -> list[Assumption]:
    """Every leaf field of `basis` exactly once (key = dotted path), `overrides` included even
    when empty (F4c), then one row per override parameter id (`overrides.<id>`, origin
    override). A field whose value F4
    computes (`derived`: service.sla_window_hours, flows.inbound_peak_factor when null,
    projection.trailing_months when not set in the file, I55) is origin derived with the value
    used. Otherwise origin client when set in the file to a value other than the schema default
    (required fields are always client), else default with the [P] tag. `extra` derived rows
    (growth factors) are appended."""
    out: list[Assumption] = []
    for path, owner, name in leaf_fields(basis):
        unit, en, _ = FIELDS[path]
        value = getattr(owner, name)
        in_file = name in owner.model_fields_set
        if path in derived and (value is None or not in_file):
            out.append(
                Assumption(
                    key=path,
                    value=derived[path],
                    unit=unit,
                    origin="derived",
                    note=DERIVED_NOTES.get(path, en),
                )
            )
            continue
        # F4c: the template writes every [P] default, so a value equal to the default is still
        # the placeholder; a field the template leaves unset is the client's once set (I55)
        default = type(owner).model_fields[name].get_default(call_default_factory=True)
        given = in_file and (value != default or path in UNSET_IN_TEMPLATE)
        tag = "[P]" + (" [VERIFY]" if path in VERIFY else "")
        out.append(
            Assumption(
                key=path,
                value=_value(value),
                unit=unit,
                origin="client" if given else "default",
                note=en if given else f"{tag} {en}",
            )
        )
    out += [
        Assumption(
            key=f"overrides.{pid}", value=v, unit="-", origin="override", note="client override"
        )
        for pid, v in basis.overrides.items()
    ]
    return out + (extra or [])

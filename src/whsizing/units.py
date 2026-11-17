"""Units at the parameter layer (spec principle 3, I87): one pint registry for the project.

Pint ships SI and a few imperial units; the project's countable units (`lines`, `orders`,
`pallets`, `eur`, ...) are added here, each as its own base dimension, so `lines/h` and
`orders/h` are different things. Aliases: `m2` (the spec's spelling of square metres) for
`meter ** 2`, `m3` for `meter ** 3`, `FTE` (as the comparison file writes it) for `fte`. A plural
is the singular plus `s` (pint strips it). The engine works in SI floats; pint only checks that a
`Param.unit` is a unit of this registry (at load time, never in a loop).
"""

from __future__ import annotations

from functools import lru_cache
from tokenize import TokenError

import pint

# singular names, each also defined in the plural (`units` would otherwise be read as micro-nits
# and pint warns about the ambiguity); `eur` also answers to `EUR`, so `kEUR` is the k prefix on it
COUNTABLES = (
    "bin", "case", "fte", "head", "line", "move", "order", "pallet", "parcel", "pod", "port",
    "robot", "shift", "station", "unit",
)  # fmt: skip
CURRENCY = "eur = [currency] = EUR"
ALIASES = ("m2 = meter ** 2", "m3 = meter ** 3", "@alias fte = FTE")  # after COUNTABLES
NEUTRAL = "-"  # a parameter with no unit (a share, a count of nothing)


@lru_cache(maxsize=1)
def registry() -> pint.UnitRegistry:
    """The project's registry, built on first use (pint costs about 0.3 s to import its table)."""
    ureg = pint.UnitRegistry()
    for definition in (
        CURRENCY,
        *(f"{name} = [{name}] = {name}s" for name in COUNTABLES),
        *ALIASES,
    ):
        ureg.define(definition)
    return ureg


def is_unit(unit: str) -> bool:
    """True for `-` and for any unit expression the registry parses (`eur/m2`, `lines/h`, `kWh`);
    False for an empty string, an unknown name, a scaling factor or a malformed expression."""
    if unit == NEUTRAL:
        return True
    if not unit.strip():
        return False
    try:
        registry().parse_units(unit)
    except (pint.errors.PintError, ValueError, TokenError, ArithmeticError, TypeError):
        return False  # 'lines/0', '1/0' (ZeroDivisionError), 'm ** m' (TypeError) are bad units too
    return True

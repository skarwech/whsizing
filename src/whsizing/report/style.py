"""F9a shared look of the charts and the block diagram: fonts, ink colours and the colour of
each scenario (the same in every chart: assigned by position in scenarios.yaml)."""

from __future__ import annotations

from collections.abc import Iterable

from matplotlib import font_manager

PREFERRED_FONTS = ("DejaVu Sans", "Liberation Sans")  # spec: DejaVu Sans / Liberation Sans
INK, MUTED, GRID, ALERT = "#1d1d1b", "#6b6b68", "#e3e3df", "#b3261e"
# the data charts (demand, design day) show no scenario: slate, outside every other palette
NEUTRAL, NEUTRAL_LIGHT = "#4a5d73", "#a9b4c1"
# Okabe-Ito: distinguishable for colour-blind readers and in greyscale print
SCENARIO_PALETTE = (
    "#0072b2",
    "#d55e00",
    "#009e73",
    "#cc79a7",
    "#e69f00",
    "#56b4e9",
    "#8c6d31",
    "#7a7a7a",
)
ACTIVITY_PALETTE = (
    "#2a78d6",
    "#7fb0e8",
    "#0b7a75",
    "#5cc0b8",
    "#8a5a00",
    "#e0a526",
    "#b84b2e",
    "#e88f73",
    "#6b4c9a",
    "#a58ccf",
    "#4d4d4d",
    "#a6a6a6",
)


def fonts() -> list[str]:
    """The preferred fonts that are installed (matplotlib warns about a missing family)."""
    installed = {f.name for f in font_manager.fontManager.ttflist}
    return [f for f in PREFERRED_FONTS if f in installed] or ["DejaVu Sans"]


def scenario_colours(scenario_ids: Iterable[str]) -> dict[str, str]:
    """scenario id → colour, by position (scenarios.yaml order): identical across all charts."""
    return {sid: SCENARIO_PALETTE[i % len(SCENARIO_PALETTE)] for i, sid in enumerate(scenario_ids)}

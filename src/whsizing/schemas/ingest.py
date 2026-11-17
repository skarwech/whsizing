"""F2 contracts: mapping YAML (Appendix E), mapping suggestions, rule results and DQ report.

Not re-exported from `whsizing.schemas` (T0.3 requires a factory example for every exported
model); import them from `whsizing.schemas.ingest`.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import field_validator

from whsizing.schemas.params import DatasetKind, StrictModel

Severity = Literal["ok", "info", "warning", "blocking"]
Band = Literal["usable", "usable with caveats", "remediation needed"]
MatchStatus = Literal["auto", "suggest", "unmapped"]


class MappingFilter(StrictModel):
    """Keep only source rows where `column` equals `equals` (e.g. one warehouse/site)."""

    column: str
    equals: str


class Mapping(StrictModel):
    """`mapping/<dataset>.yaml` (Appendix E). Sniff fields: the value all files share (None:
    each file is sniffed); when set they override the sniff. `sheet`: only a user choice."""

    dataset: DatasetKind
    files: list[str] = []
    encoding: str | None = None
    delimiter: str | None = None
    header_row: int | None = None
    decimal: str | None = None
    date_format: str | None = None
    sheet: str | int | None = None
    timezone: str = "Europe/Paris"
    columns: dict[str, str | None]  # canonical target → source column (None = unmapped)
    filters: list[MappingFilter] = []
    unit_hints: dict[str, str] = {}  # {"dims": "cm"|"mm", "weight": "g"|"kg"} once confirmed
    merge_duplicate_sku_lines: bool = True

    @field_validator("timezone")
    @classmethod
    def _known_zone(cls, v: str) -> str:
        try:
            ZoneInfo(v)
        except (ZoneInfoNotFoundError, ValueError) as e:
            raise ValueError(f"unknown time zone {v!r} (IANA name, e.g. Europe/Paris)") from e
        return v


class TargetSuggestion(StrictModel):
    target: str
    column: str | None
    score: float
    status: MatchStatus  # ≥ 0.85 auto, 0.60–0.85 suggest (confirm), < 0.60 unmapped [P]
    required: bool
    reason: str
    candidates: list[str] = []  # every column, best score first: what an interactive pick offers


class MappingSuggestion(StrictModel):
    dataset: DatasetKind
    targets: list[TargetSuggestion]


class RuleResult(StrictModel):
    """One R-rule outcome (§4.3) on one dataset."""

    rule: str  # R1..R14, or REQ (required value missing/invalid → row dropped)
    dataset: DatasetKind
    severity: Severity
    count: int  # offending rows (or SKUs for R7/R8)
    share: float  # count / rows checked
    dropped: int = 0  # rows removed by the rule's action
    message: str = ""
    sample_rows: list[dict[str, str | None]] = []


class DQReport(StrictModel):
    created_at: datetime
    score: float
    band: Band
    score_breakdown: dict[str, float]
    coverage: dict[str, float]
    rules: list[RuleResult]
    notes: list[str] = []  # unit hints, hour unknown, ... (plain language)
    rows: dict[str, int] = {}  # canonical rows per table after cleaning

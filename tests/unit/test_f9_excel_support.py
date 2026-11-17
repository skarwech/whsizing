"""Shared F9b test support (no test here): the expected sheet names and headers of the workbook,
openpyxl read helpers (plain `load_workbook`: read-only mode drops comments) and the check of the
Summary sheet against `comparison/comparison.json`, used by the unit and the e2e tests."""

from __future__ import annotations

import io
import json
import math
from datetime import datetime
from pathlib import Path
from typing import Any

import openpyxl
import pytest

from whsizing.report import t
from whsizing.report.i18n import Lang
from whsizing.schemas.run import RunOutput

LANGS: tuple[Lang, ...] = ("en", "fr")
SHEETS: dict[Lang, list[str]] = {
    "en": ["Summary", "Design basis", "Demand profile", "Design day", "Scenarios", "FTE",
           "Capex - Opex", "Cash flow", "Sensitivity", "Assumptions", "Data quality",
           "Methodology"],
    "fr": ["Synthèse", "Base de dimensionnement", "Profil de la demande",
           "Jour de dimensionnement", "Scénarios", "ETP", "Capex - Opex",
           "Flux de trésorerie", "Sensibilité", "Hypothèses", "Qualité des données",
           "Méthodologie"],
}  # fmt: skip
# per sheet: (A3 = title of the first block, header row, its first cells); written out in full
# (not rebuilt from i18n) so that a wrong or untranslated label fails the test
HEADERS: dict[Lang, list[tuple[str, int, list[str]]]] = {
    "en": [
        ("Scenario comparison", 5, ["", "Low", "Typical", "High", "Low"]),
        ("Design basis fields", 4, ["Field", "Value", "Unit", "Origin", "Note"]),
        ("Data period", 4, ["", "Value"]),
        ("Design day", 4, ["", "Value"]),
        ("Eligibility", 5, ["", "Low", "Typical", "High"]),
        ("Design-day hours by activity", 5, ["", "Low", "Typical", "High"]),
        ("Capex by item", 5, ["", "Low", "Typical", "High"]),
        ("Cash flows, years 0 to T (typical world)", 5,
         ["", "Cash flow", "Δ vs baseline", "Cumulative", "Cash flow", "Δ vs baseline"]),
        ("Tornado: one parameter at a time", 4,
         ["Parameter", "Scenario", "Low input", "High input", "TCO, low input"]),
        ("Catalog parameters", 4,
         ["Id", "Label", "Value used", "Unit", "Min", "Typical", "Max", "Source", "Confidence",
          "Validated by", "Origin", "Note"]),
        ("Data quality score", 4, ["", "Value"]),
        ("Versions and parameter counts", 4, ["", "Value"]),
    ],
    "fr": [
        ("Comparaison des scénarios", 5, ["", "Bas", "Typique", "Haut", "Bas"]),
        ("Champs de la base de dimensionnement", 4,
         ["Champ", "Valeur", "Unité", "Origine", "Remarque"]),
        ("Période des données", 4, ["", "Valeur"]),
        ("Jour de dimensionnement", 4, ["", "Valeur"]),
        ("Éligibilité", 5, ["", "Bas", "Typique", "Haut"]),
        ("Heures du jour de dimensionnement par activité", 5, ["", "Bas", "Typique", "Haut"]),
        ("Capex par poste", 5, ["", "Bas", "Typique", "Haut"]),
        ("Flux de trésorerie, années 0 à T (monde typique)", 5,
         ["", "Flux", "Δ vs référence", "Cumul", "Flux", "Δ vs référence"]),
        ("Tornade : un paramètre à la fois", 4,
         ["Paramètre", "Scénario", "Entrée basse", "Entrée haute", "TCO, entrée basse"]),
        ("Paramètres du catalogue", 4,
         ["Id", "Libellé", "Valeur retenue", "Unité", "Min", "Typique", "Max", "Source",
          "Confiance", "Validé par", "Origine", "Remarque"]),
        ("Score de qualité des données", 4, ["", "Valeur"]),
        ("Versions et comptes de paramètres", 4, ["", "Valeur"]),
    ],
}  # fmt: skip
NUMBER_FORMATS = {"#,##0", "#,##0.0", "#,##0.00", "0.0 %", "General"}
RANGE_FIELDS = {
    "storage_area_m2": "row.storage_area",
    "total_area_m2": "row.total_area",
    "fte_design_day": "row.fte_design_day",
    "core_fte_year1": "row.core_fte_y1",
    "roster": "row.roster",
    "capex": "row.capex",
    "opex_year1": "row.opex_y1",
    "tco": "row.tco",
    "npv_vs_baseline": "row.npv",
    "cost_per_line": "row.cost_per_line",
}
SCALAR_FIELDS = {
    "eligible_line_share": "row.eligible_share",
    "payback_years": "row.payback",
    "n_warnings": "row.n_warnings",
    "n_low_confidence_params": "row.n_low_confidence",
}


def open_book(path: Path | io.BytesIO) -> Any:
    return openpyxl.load_workbook(path)


def read_json(run: RunOutput, rel: str) -> Any:
    return json.loads((Path(run.run_dir) / rel).read_text(encoding="utf-8"))


def row_of(ws: Any, label: str, after: int = 1) -> int:
    """First row at or after `after` whose column A holds `label`."""
    for r in range(after, ws.max_row + 1):
        if ws.cell(r, 1).value == label:
            return r
    raise AssertionError(f"{ws.title}: no row labelled {label!r} from row {after}")


def triple(ws: Any, row: int, index: int) -> tuple[Any, Any, Any]:
    """The lo / typ / hi cells of the `index`-th scenario of a scenario sheet."""
    c = 2 + 3 * index
    return tuple(ws.cell(row, c + k).value for k in range(3))  # pyright: ignore[reportReturnType]


def numeric_cells(ws: Any) -> dict[tuple[int, int], Any]:
    """Cells holding a number or a date (data type n or d), by (row, column)."""
    return {
        (c.row, c.column): c.value
        for row in ws.iter_rows()
        for c in row
        if c.data_type in ("n", "d") and c.value is not None
    }


def string_cells(ws: Any) -> list[str]:
    return [c.value for row in ws.iter_rows() for c in row if isinstance(c.value, str)]


def comments(ws: Any) -> dict[tuple[int, int], str]:
    return {
        (c.row, c.column): c.comment.text
        for row in ws.iter_rows()
        for c in row
        if c.comment is not None
    }


def approx_range(got: tuple[Any, Any, Any], want: dict[str, Any]) -> None:
    for g, k in zip(got, ("lo", "typ", "hi"), strict=True):
        assert g == pytest.approx(want[k], rel=1e-12, abs=1e-12), (got, want)


def assert_summary_equals_comparison_json(wb: Any, run: RunOutput, lang: Lang) -> int:
    """Every `ComparisonRow` field of comparison.json is the number in the Summary sheet (the
    numbers come from the JSON, never from the report model). Returns the number of checks."""
    ws = wb[SHEETS[lang][0]]
    cmp = read_json(run, "comparison/comparison.json")
    covered = {"scenario_id", "name", "family", "status", "status_reason", "equipment", "fit"}
    first = row_of(ws, t("row.eligible_share", lang), 4)
    checks = 0
    for i, jr in enumerate(cmp["rows"]):
        assert str(ws.cell(4, 2 + 3 * i).value).startswith(jr["scenario_id"])
        assert [ws.cell(5, 2 + 3 * i + k).value for k in range(3)] == [
            t(f"col.{w}", lang) for w in ("lo", "typ", "hi")
        ]
        for field, key in RANGE_FIELDS.items():
            if jr[field] is not None:
                approx_range(triple(ws, row_of(ws, t(key, lang), first), i), jr[field])
                checks += 1
        for field, key in SCALAR_FIELDS.items():
            if jr[field] is not None:
                lo, typ, hi = triple(ws, row_of(ws, t(key, lang), first), i)
                assert (lo, hi) == (None, None)
                assert typ == pytest.approx(jr[field], rel=1e-12), (jr["scenario_id"], field)
                checks += 1
        fit = triple(ws, row_of(ws, t("row.fit", lang), first), i)
        assert fit == (None, float(jr["fit"]), None)
        for eq, rng in jr["equipment"].items():
            approx_range(triple(ws, row_of(ws, t(f"equipment.{eq}", lang), first), i), rng)
            checks += 1
        covered |= set(RANGE_FIELDS) | set(SCALAR_FIELDS)
        assert set(jr) <= covered, sorted(set(jr) - covered)  # a new field needs a row
    return checks


def numbers_by_sheet(wb: Any) -> dict[str, dict[tuple[int, int], float | datetime]]:
    """The numeric cells of every sheet, by position (sheets by position, not name: FR != EN)."""
    return {str(i): numeric_cells(ws) for i, ws in enumerate(wb.worksheets)}


def is_plain_number(v: object) -> bool:
    return isinstance(v, int | float) and not isinstance(v, bool) and math.isfinite(v)

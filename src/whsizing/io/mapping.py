"""F2 mapping steps 1-7: synonyms, scoring, greedy assignment, typed apply, unit hints, YAML.

Scores: 1.0 on an exact (normalised) synonym, else the best rapidfuzz token_set_ratio / 100;
× 0.5 when the column content does not fit the target type. Equal scores are ranked (F2c): an
exact synonym before a token_set subset ('ref' scores 'Réf client' 1.0 too), then the step-3
content preference (small integer quantities, repeated order ids), then relative cardinality
(sku prefers the column with more distinct values). A fuzzy pick tied on score with another
free column stays a suggestion (asked): the ranking only chooses which column is proposed.
"""

from __future__ import annotations

import functools
import hashlib
import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import polars as pl
import yaml
from rapidfuzz import fuzz

from whsizing.config import load_yaml_model
from whsizing.errors import MappingError
from whsizing.io.parse import (
    detect_date_format,
    looks_numeric,
    parse_bool,
    parse_date,
    parse_datetime,
    parse_int,
    parse_number,
)
from whsizing.io.readers import SOURCE_ROW, RawTable
from whsizing.io.sniff import _THOUSANDS_ONLY, DECIMAL_SAMPLE_ROWS
from whsizing.schemas.ingest import Mapping, MappingSuggestion, TargetSuggestion
from whsizing.schemas.params import DatasetKind

Kind = Literal["id", "text", "int", "float", "datetime", "date", "bool", "status", "temp"]
Confirm = Callable[
    [str, str], bool
]  # (code, question) → yes/no; codes: mapping.<target>, W_UNITS_*

AUTO_ACCEPT = 0.85  # [P] step 4
SUGGEST = 0.60  # [P] step 4
TYPE_MISMATCH = 0.5  # step 3
CONTENT_SAMPLE_ROWS = 1000  # step 3
KIND_MIN_SHARE = 0.80  # F2 choice: a column "is" numeric / datetime when 80 % of values parse
CM_P95_MAX = 100.0  # [P] step 6: P95 of length < 100 → cm
GRAMS_MEDIAN_MIN = 500.0  # [P] step 6: median weight > 500 → grams
DIMS = ("length_mm", "width_mm", "height_mm")
SYNONYMS_PATH = Path(__file__).with_name("synonyms_fr_en.yaml")

# target → (kind, required), per dataset (§4.1); description/customer are PII, dropped later.
TARGETS: dict[DatasetKind, dict[str, tuple[Kind, bool]]] = {
    "order_lines": {
        "order_id": ("id", True),
        "order_ts": ("datetime", True),
        "sku": ("id", True),
        "qty_units": ("int", True),
        "channel": ("text", False),
        "line_status": ("status", False),
        "customer": ("id", False),
    },
    "sku_master": {
        "sku": ("id", True),
        "length_mm": ("float", True),
        "width_mm": ("float", True),
        "height_mm": ("float", True),
        "weight_kg": ("float", True),
        "units_per_case": ("int", False),
        "cases_per_pallet": ("int", False),
        "category": ("text", False),
        "stackable": ("bool", False),
        "temperature_class": ("temp", False),
        "hazmat": ("bool", False),
        "description": ("text", False),
    },
    "inventory": {
        "sku": ("id", True),
        "qty_units": ("int", True),
        "snapshot_date": ("date", True),
    },
    "receipts": {
        "receipt_id": ("id", True),
        "receipt_ts": ("datetime", True),
        "sku": ("id", True),
        "qty_units": ("int", True),
        "pallets": ("float", False),
    },
}
OPTIONAL_PII = ("description", "customer")  # only emitted when mapped
_ACCEPTS: dict[Kind, set[str]] = {
    "id": {"string", "number"},
    "text": {"string", "number"},
    "status": {"string"},
    "temp": {"string"},
    "bool": {"string", "number"},
    "int": {"number"},
    "float": {"number"},
    "datetime": {"datetime"},
    "date": {"datetime"},
}
_DTYPE: dict[Kind, pl.DataType] = {
    "id": pl.Utf8(),
    "text": pl.Utf8(),
    "status": pl.Utf8(),
    "temp": pl.Utf8(),
    "bool": pl.Boolean(),
    "int": pl.Int64(),
    "float": pl.Float64(),
    "datetime": pl.Datetime("us", "UTC"),
    "date": pl.Date(),
}
_STATUS = {
    "shipped": "shipped ship expedie expediee livre livree delivered closed complete completed "
    "done solde ok invoiced facture",
    "cancelled": "cancelled canceled cancel annule annulee annulation",
    "returned": "returned return retour retourne retournee rma",
}
_TEMPERATURE = {
    "ambient": "ambient ambiant ambiante ambiance sec dry",
    "chilled": "chilled frais refrigere positive cold",
    "frozen": "frozen surgele congele negative",
}


def normalize(h: str) -> str:
    """Step 1: NFKD, strip accents, lower-case, non-alphanumerics → space, collapse spaces."""
    s = "".join(c for c in unicodedata.normalize("NFKD", h) if not unicodedata.combining(c))
    return " ".join(re.sub(r"[^0-9a-z]+", " ", s.lower()).split())


@functools.cache
def synonyms() -> dict[str, tuple[str, ...]]:
    """Appendix F synonyms, plus each target's own name (the Appendix A template headers)."""
    data = yaml.safe_load(SYNONYMS_PATH.read_text(encoding="utf-8"))
    return {t: tuple(normalize(s) for s in [t, *v]) for t, v in data.items()}


def header_score(header: str, target: str) -> tuple[float, bool, str]:
    """Step 2 → (score, exact, best synonym)."""
    h, syns = normalize(header), synonyms()[target]
    if h in syns:
        return 1.0, True, h
    return max(((fuzz.token_set_ratio(h, s) / 100, False, s) for s in syns), default=(0, False, ""))


@dataclass(frozen=True)
class _Content:
    kinds: frozenset[str]
    n: int
    n_unique: int
    integral_share: float
    median: float | None


def _content(values: pl.Series, decimal: str) -> _Content:
    v = values.drop_nulls().head(CONTENT_SAMPLE_ROWS)
    nums = v.to_frame("v").select(parse_number(pl.col("v"), decimal)).to_series().drop_nulls()
    kinds = set()
    if looks_numeric(v, decimal) >= KIND_MIN_SHARE:
        kinds.add("number")
    if v.len() and detect_date_format(v)[1] >= KIND_MIN_SHARE:
        kinds.add("datetime")
    whole = nums.to_frame("n").select((pl.col("n") == pl.col("n").round(0)).mean()).item()
    integral = float(whole or 0.0)
    median = nums.median() if nums.len() else None
    return _Content(
        kinds=frozenset(kinds or {"string"}),
        n=v.len(),
        n_unique=v.n_unique(),
        integral_share=integral,
        median=float(median) if isinstance(median, int | float) else None,
    )


def _content_factor(target: str, kind: Kind, c: _Content) -> tuple[float, str]:
    """Step 3 type compatibility: × 0.5 when the content does not fit the target."""
    if c.n == 0:
        return TYPE_MISMATCH, "column is empty"
    if not _ACCEPTS[kind] & c.kinds:
        return TYPE_MISMATCH, f"content looks like {'/'.join(sorted(c.kinds))}, not {kind}"
    return 1.0, ""


def _preference_miss(target: str, c: _Content) -> str:
    """Step 3 content preference, a tie-break only (F2c); '' when met."""
    if target == "qty_units" and (c.integral_share < 0.9 or (c.median or 0) > 1000):
        return "not small integers"
    if target == "order_id" and c.n_unique == c.n:
        # ponytail: "grouped timestamps" not checked; repeated ids alone separate orders from lines
        return "no repeated values (order ids repeat across lines)"
    return ""


def suggest_mapping(raw: RawTable, dataset: DatasetKind) -> MappingSuggestion:
    """Steps 2-4: score every (target, column), assign greedily by descending score."""
    sample = raw.df.head(CONTENT_SAMPLE_ROWS)
    content = {c: _content(sample[c], raw.sniff.decimal) for c in raw.columns}
    cands: list[tuple[float, bool, str, str, str]] = []
    rank: dict[tuple[str, str], tuple[float, bool, bool, int]] = {}
    for target, (kind, _) in TARGETS[dataset].items():
        for col in raw.columns:
            score, exact, syn = header_score(col, target)
            factor, why = _content_factor(target, kind, content[col])
            miss = _preference_miss(target, content[col])
            reason = f"exact synonym '{syn}'" if exact else f"close to '{syn}' ({score:.2f})"
            reason += f"; {why} (×{factor})" if why else ""
            reason += f"; {miss} (ranked lower on a tie)" if miss else ""
            score = round(score * factor, 4)
            n_unique = content[col].n_unique if target == "sku" else 0
            rank[target, col] = (-score, not exact, bool(miss), -n_unique)
            cands.append((score, exact, target, col, reason))
    cands.sort(key=lambda x: rank[x[2], x[3]])
    scores = {(t, c): s for s, _, t, c, _ in cands}
    chosen: dict[str, tuple[float, str, str]] = {}
    tied: set[str] = set()
    used: set[str] = set()
    best: dict[str, tuple[float, str, str]] = {}
    ranked: dict[str, list[str]] = {t: [] for t in TARGETS[dataset]}
    for score, exact, target, col, reason in cands:
        best.setdefault(target, (score, col, reason))
        ranked[target].append(col)
        if score >= SUGGEST and target not in chosen and col not in used:
            # F2: a fuzzy score tied with another free column ('Réf client' / 'Réf article',
            # both 1.00 on 'ref') is decided by column order, so it is asked, never auto
            ties = [c for c in raw.columns if c not in used | {col} and scores[target, c] == score]
            if ties and not exact:
                tied.add(target)
                reason += f"; tied with '{ties[0]}'"
            chosen[target] = (score, col, reason)
            used.add(col)
    targets = [_target(t, r, chosen, best, tied) for t, (_, r) in TARGETS[dataset].items()]
    return MappingSuggestion(
        dataset=dataset,
        targets=[t.model_copy(update={"candidates": ranked[t.target]}) for t in targets],
    )


def _target(
    target: str,
    required: bool,
    chosen: dict[str, tuple[float, str, str]],
    best: dict[str, tuple[float, str, str]],
    tied: set[str],
) -> TargetSuggestion:
    if target in chosen:
        score, col, reason = chosen[target]
        status = "auto" if score >= AUTO_ACCEPT and target not in tied else "suggest"
        return TargetSuggestion(
            target=target, column=col, score=score, status=status, required=required, reason=reason
        )
    score, col, reason = best.get(target, (0.0, "", "no column"))
    why = f"best candidate '{col}' scored {score:.2f}: {reason}" if col else "no column"
    return TargetSuggestion(
        target=target, column=None, score=score, status="unmapped", required=required, reason=why
    )


def resolve_mapping(
    suggestion: MappingSuggestion, raw: RawTable, confirm: Confirm | None = None
) -> Mapping:
    """Steps 4-5: auto-accept, ask `confirm` for suggestions; a required target still unmapped
    is offered every unused column, best first, until one is accepted (interactive prompt).
    Without `confirm` (non-interactive) nothing is assumed: MappingError (exit 2)."""
    columns: dict[str, str | None] = {}
    for t in suggestion.targets:
        ok = t.status == "auto" or (
            t.status == "suggest"
            and confirm is not None
            and confirm(
                f"mapping.{t.target}",
                f"Use column '{t.column}' as {t.target}? (score {t.score:.2f}: {t.reason})",
            )
        )
        columns[t.target] = t.column if ok else None
    for t in suggestion.targets:
        if t.required and columns[t.target] is None and confirm is not None:
            columns[t.target] = _pick(t, set(columns.values()), confirm)
    missing = [t for t in suggestion.targets if t.required and columns[t.target] is None]
    if missing:
        detail = "; ".join(
            f"{t.target} ({'needs confirmation: ' if t.status == 'suggest' else ''}{t.reason})"
            for t in missing
        )
        raise MappingError(
            f"{suggestion.dataset} ({raw.path.name}): required column(s) not mapped: {detail}. "
            f"Provide a mapping file (mapping/{suggestion.dataset}.yaml) or confirm interactively."
        )
    sn = raw.sniff
    return Mapping(
        dataset=suggestion.dataset,
        files=[str(raw.path)],
        encoding=sn.encoding,
        delimiter=sn.delimiter,
        header_row=sn.header_row,
        decimal=sn.decimal,
        date_format=sn.date_format,
        columns=columns,  # `sheet` stays None: an auto-picked sheet is not a user choice
    )


def _pick(t: TargetSuggestion, used: set[str | None], confirm: Confirm) -> str | None:
    refused = t.column if t.status == "suggest" else None  # already asked in the first pass
    for col in t.candidates:
        question = f"Required column {t.target} was not recognised. Use column '{col}'?"
        if col not in used and col != refused and confirm(f"mapping.{t.target}", question):
            return col
    return None


def _categorize(
    values: pl.Series, table: dict[str, str], default: str | None
) -> dict[str, str | None]:
    """Raw value → category: the first normalised word found in `table`, else `default`."""
    lookup = {w: cat for cat, words in table.items() for w in words.split()}
    return {
        v: next((lookup[w] for w in normalize(v).split() if w in lookup), default)
        for v in values.drop_nulls().unique().to_list()
    }


def _typed(raw: RawTable, target: str, kind: Kind, col: str | None, m: Mapping) -> pl.Expr:
    """One canonical column; the mapping's decimal and date format win over the sniff."""
    if col is None:
        if target == "line_status":
            return pl.lit("shipped").alias(target)  # §4.1 default
        return pl.lit(None, dtype=_DTYPE[kind]).alias(target)
    src, decimal, tz = pl.col(col), m.decimal or raw.sniff.decimal, m.timezone
    if kind in ("datetime", "date"):
        first = m.date_format or detect_date_format(raw.df[col])[0]
        expr = parse_datetime(src, tz, first) if kind == "datetime" else parse_date(src, tz, first)
    elif kind in ("status", "temp"):
        table, default = (_STATUS, "unknown") if kind == "status" else (_TEMPERATURE, None)
        codes = _categorize(raw.df[col], table, default)
        expr = src.replace_strict(codes, default=None, return_dtype=pl.Utf8)
        expr = expr.fill_null("shipped") if kind == "status" else expr  # §4.1 default
    else:
        parsers: dict[str, Callable[[], pl.Expr]] = {
            "int": lambda: parse_int(src, decimal),
            "float": lambda: parse_number(src, decimal),
            "bool": lambda: parse_bool(src),
        }
        expr = parsers[kind]() if kind in parsers else src
    return expr.alias(target)


def number_notes(raw: RawTable, mapping: Mapping) -> list[str]:
    """DQ notes on one file's numeric columns, with the mapping fix: values unreadable with the
    decimal mark (null, then counted by REQ / R7), and whole-number values written like a
    thousands grouping of that mark ('2.000' in a '.' file is read as 2, F2c)."""
    df, ds, decimal = _filtered(raw, mapping), mapping.dataset, mapping.decimal or raw.sniff.decimal
    other = "," if decimal == "." else "."
    grouped_shape = rf"^\s*[-+]?[1-9]\d{{0,2}}(\{decimal}\d{{3}})+\s*$"
    notes = []
    for target, (kind, _) in TARGETS[ds].items():
        col = mapping.columns.get(target)
        if kind not in ("int", "float") or not col:
            continue
        v = pl.col(col)
        parsed = (parse_int if kind == "int" else parse_number)(v, decimal)
        whole = kind == "int"  # '1.250' kg is a plain 3-decimal weight, never ambiguous
        grouped = parsed.is_not_null() & v.str.contains(grouped_shape) & pl.lit(whole)
        counts = df.select(bad=(v.is_not_null() & parsed.is_null()).sum(), ambiguous=grouped.sum())
        bad, ambiguous = counts.row(0)
        what = "whole numbers" if kind == "int" else "numbers"
        missing = (
            f"{bad} values are not {what} with the decimal mark '{decimal}' and count as missing"
        )
        small = (
            f"{ambiguous} values such as '2{decimal}000' look like thousands but were read with "
            f"the decimal mark '{decimal}' as small numbers (2)"
        )
        parts = [text for n, text in ((bad, missing), (ambiguous, small)) if n]
        if parts:
            notes.append(
                f"[{ds}] {raw.path.name}, column '{col}' ({target}): {'; '.join(parts)}. If the "
                f"file uses '{other}' as decimal mark, set decimal: '{other}' in "
                f"mapping/{ds}.yaml and re-run."
            )
    return notes


def tie_break_notes(raw: RawTable, mapping: Mapping) -> list[str]:
    """I67 step 4: the field delimiter chose the decimal mark (I54 tie-break, no sampled value
    showed it) and the mapping sets none → a DQ warning with up to 5 ambiguous values of the
    mapped numeric columns (thousands or 3 decimals: '1.250' kg read × 1000 in a ';' file),
    taken in turn from each column (5 lengths cannot hide the weight), each with its column
    and as read, and the `decimal:` override. Nothing ambiguous (integer-only file) → none."""
    sn, ds = raw.sniff, mapping.dataset
    if not sn.decimal_by_delimiter or mapping.decimal is not None:
        return []
    df = _filtered(raw, mapping)
    cols = [
        (col, kind)
        for target, (kind, _) in TARGETS[ds].items()
        if kind in ("int", "float") and (col := mapping.columns.get(target))
    ]
    shape = pl.col("v").str.strip_chars_start("-+").str.contains(_THOUSANDS_ONLY.pattern)
    per_column = [
        df.select(v=pl.col(c), col=pl.lit(c))
        .filter(shape.fill_null(False))
        .unique("v", maintain_order=True)
        # I67 (c): the column's own parser, as `_typed` reads it; Float64 so the columns concat
        .with_columns(
            turn=pl.int_range(pl.len()),
            parsed=(parse_int if kind == "int" else parse_number)(pl.col("v"), sn.decimal).cast(
                pl.Float64
            ),
        )
        for c, kind in cols
    ]
    if not per_column:
        return []
    ambiguous = pl.concat(per_column).sort("turn", maintain_order=True).head(5)
    if ambiguous.is_empty():
        return []
    examples = ", ".join(
        f"'{v}' ({c}) → "
        f"{'unreadable (counted as missing)' if x is None else f'{x:.0f}' if x == int(x) else x}"
        for v, c, x in zip(ambiguous["v"], ambiguous["col"], ambiguous["parsed"], strict=True)
    )
    other = "," if sn.decimal == "." else "."
    return [
        f"[{ds}] {raw.path.name}: warning, decimal mark '{sn.decimal}' chosen by the field "
        f"delimiter {sn.delimiter!r}, because no number in the first {DECIMAL_SAMPLE_ROWS} data "
        f"rows shows the mark; values that can be thousands or 3 decimals were read as "
        f"{examples}. If the file uses '{other}' as decimal mark, set decimal: '{other}' in "
        f"mapping/{ds}.yaml and re-run (decimal: '{sn.decimal}' confirms this reading)."
    ]


def _filtered(raw: RawTable, mapping: Mapping) -> pl.DataFrame:
    df = raw.df
    for f in mapping.filters:
        df = df.filter(pl.col(f.column) == f.equals)
    return df


def apply_mapping(raw: RawTable, mapping: Mapping) -> pl.DataFrame:
    """Filter rows, rename and type the canonical columns, apply confirmed unit hints, add
    provenance. Unmapped optional columns are null (description/customer: absent)."""
    targets = TARGETS[mapping.dataset]
    unknown = sorted(set(mapping.columns) - set(targets))
    unmapped = [t for t, (_, req) in targets.items() if req and not mapping.columns.get(t)]
    if unknown or unmapped:
        raise MappingError(
            f"{mapping.dataset} mapping: required target(s) not mapped {unmapped}, unknown "
            f"target(s) {unknown}; valid targets: {list(targets)}"
        )
    df = raw.df
    wanted = [f.column for f in mapping.filters] + [c for c in mapping.columns.values() if c]
    absent = sorted({c for c in wanted if c not in df.columns})
    if absent:
        raise MappingError(
            f"{raw.path.name}: column(s) {absent} from the {mapping.dataset} mapping are not in "
            f"the file (columns: {raw.columns})"
        )
    df = _filtered(raw, mapping)
    raw = RawTable(path=raw.path, df=df, sniff=raw.sniff)
    exprs = [
        _typed(raw, t, kind, mapping.columns.get(t), mapping)
        for t, (kind, _) in TARGETS[mapping.dataset].items()
        if t not in OPTIONAL_PII or mapping.columns.get(t)
    ]
    out = df.select(
        *exprs,
        source_file=pl.lit(raw.path.name),
        source_row=pl.col(SOURCE_ROW).cast(pl.Int64),
    )
    return apply_unit_hints(out, mapping.unit_hints)


def detect_unit_hints(df: pl.DataFrame) -> dict[str, tuple[str, str]]:
    """Step 6 on sku_master values in mm / kg → {"dims": ("cm", why), "weight": ("g", why)}."""
    hints: dict[str, tuple[str, str]] = {}
    p95 = df["length_mm"].drop_nulls().quantile(0.95) if "length_mm" in df.columns else None
    if p95 is not None and p95 < CM_P95_MAX:
        hints["dims"] = ("cm", f"95th percentile of length is {p95:g} (< {CM_P95_MAX:g})")
    median = df["weight_kg"].drop_nulls().median() if "weight_kg" in df.columns else None
    if isinstance(median, int | float) and median > GRAMS_MEDIAN_MIN:
        hints["weight"] = ("g", f"median weight is {median:g} (> {GRAMS_MEDIAN_MIN:g})")
    return hints


def apply_unit_hints(df: pl.DataFrame, hints: dict[str, str]) -> pl.DataFrame:
    """cm → mm (× 10) on the three dims; g → kg (÷ 1000) on weight."""
    if hints.get("dims") == "cm" and "length_mm" in df.columns:
        df = df.with_columns(pl.col(DIMS) * 10)
    if hints.get("weight") == "g" and "weight_kg" in df.columns:
        df = df.with_columns(pl.col("weight_kg") / 1000)
    return df


def load_mapping(path: Path) -> Mapping:
    return load_yaml_model(path, Mapping)


def save_mapping(mapping: Mapping, path: Path) -> str:
    """Write the Appendix E YAML; return its sha256 (the manifest's mapping hash)."""
    text = yaml.safe_dump(mapping.model_dump(), allow_unicode=True, sort_keys=False)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

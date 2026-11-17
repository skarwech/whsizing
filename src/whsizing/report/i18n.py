"""F9a i18n: labels and fixed texts from `report/i18n/{fr,en}.yaml`, and the number and date
formats of the two languages.

    t("flag.F_NO_FIT", "fr")                  # the text, or the sentinel "{{ missing:<key> }}"
    fmt_number(1234567.891, "fr", 2)          # "1 234 567,89"  (U+202F thousands, decimal comma)
    fmt_number(1234567.891, "en", 2)          # "1,234,567.89"
    fmt_pct(0.123, "fr")                      # "12,3 %"       (U+202F before the sign)
    fmt_date(date(2026, 11, 9), "fr")         # "09/11/2026"   (EN: "2026-11-09")
    render_cell(cell, lang)                   # any report Cell as display text
    flag_text("F_UNSTABLE:packing", "en")     # the flag's message with its detail

The YAML files are flat (`dotted.key: text`); a key present in one file is present in the other
(tested). `t` never raises: a missing key, or a text whose `{placeholders}` are not all given,
returns the sentinel, which IC8 looks for in the rendered HTML. A language other than "fr" and "en"
is a `ConfigError`.
"""

from __future__ import annotations

import math
import re
from datetime import date
from functools import cache
from pathlib import Path
from typing import Literal

import yaml

from whsizing.errors import ConfigError
from whsizing.schemas.report import Cell

Lang = Literal["fr", "en"]
LANGS: tuple[Lang, ...] = ("fr", "en")
I18N_DIR = Path(__file__).with_name("i18n")  # no __init__.py: a data folder next to this module
MISSING_PREFIX = "{{ missing:"
NNBSP = " "  # narrow no-break space
UNIT_LABELS = {"m2": "m²", "m3": "m³", "eur": "€", "eur/line": "€/line", "kg": "kg"}
PLACEHOLDER = re.compile(r"\{\w+\}")
# the generated limitation "flags raised": its `flags` argument holds the flag codes joined by
# FLAGS_SEP in both languages; `render_cell` says them as their messages
FLAGS_KEY = "limit.gen.flags"
FLAGS_SEP = ", "
NUMERIC_TAIL = re.compile(r":[0-9.]+$")  # `F_LOW_CONFIDENCE:3`: a value, not a detail
_SEPARATORS: dict[Lang, tuple[str, str]] = {"fr": (NNBSP, ","), "en": (",", ".")}
_DATE_FORMATS: dict[Lang, str] = {"fr": "%d/%m/%Y", "en": "%Y-%m-%d"}


@cache
def texts(lang: Lang) -> dict[str, str]:
    """The flat key → text mapping of one language file."""
    if lang not in LANGS:
        raise ConfigError(f"report: unsupported language {lang!r} (use one of {', '.join(LANGS)})")
    data = yaml.safe_load((I18N_DIR / f"{lang}.yaml").read_text(encoding="utf-8")) or {}
    return {str(k): str(v) for k, v in data.items()}


def has_key(key: str, lang: Lang) -> bool:
    return key in texts(lang)


def missing(key: str) -> str:
    return f"{MISSING_PREFIX}{key} }}}}"


def t(key: str, lang: Lang, **fmt: object) -> str:
    """The text of `key` in `lang` with `{name}` placeholders filled from `fmt`."""
    text = texts(lang).get(key)
    if text is None:
        return missing(key)
    if not fmt:  # a text without arguments may hold literal braces (the formulas)
        return missing(key) if PLACEHOLDER.search(text) else text
    try:
        return text.format(**fmt)
    except (KeyError, IndexError, ValueError):
        return missing(key)


def fmt_number(value: float, lang: Lang, decimals: int = 0) -> str:
    """Thousands separator and decimal mark of `lang`; "-" for negatives (never "-0")."""
    if not math.isfinite(value):
        return str(value)
    thousands, decimal = _SEPARATORS[lang]
    body = f"{abs(value):,.{decimals}f}".replace(",", "\0").replace(".", decimal)
    body = body.replace("\0", thousands)
    negative = value < 0 and any(c in "123456789" for c in body)
    return f"-{body}" if negative else body


def fmt_pct(value: float, lang: Lang, decimals: int = 1) -> str:
    """A share (0.123) as "12.3 %" (FR: "12,3 %", the space is a narrow no-break space)."""
    space = NNBSP if lang == "fr" else " "
    return f"{fmt_number(value * 100, lang, decimals)}{space}%"


def fmt_date(d: date | str, lang: Lang) -> str:
    return (date.fromisoformat(d) if isinstance(d, str) else d).strftime(_DATE_FORMATS[lang])


def fmt_general(value: float, lang: Lang, digits: int = 6) -> str:
    """Up to `digits` significant digits, no trailing zeros (parameter values)."""
    if value == 0 or not math.isfinite(value):
        return fmt_number(value, lang, 0)
    decimals = max(0, digits - 1 - math.floor(math.log10(abs(value))))
    text = fmt_number(value, lang, min(decimals, 10))
    mark = _SEPARATORS[lang][1]
    return text.rstrip("0").rstrip(mark) if mark in text else text


def flag_text(code: str, lang: Lang) -> str:
    """The message of a flag code (`flag.<base>`); the part after the colon is its `{detail}`
    (`F_UNSTABLE:packing` is the packing pool), a numeric tail is dropped."""
    base, _, detail = NUMERIC_TAIL.sub("", code).partition(":")
    return t(f"flag.{base}", lang, detail=detail)


def unit_label(unit: str) -> str:
    return UNIT_LABELS.get(unit, unit)


_DECIMALS = {"int": 0, "eur": 0, "dec1": 1, "dec2": 2}


def render_cell(cell: Cell, lang: Lang) -> str:
    """Display text of a cell (no unit): numbers by `fmt`, i18n keys translated with `args`."""
    v = cell.value
    if v is None:
        return ""
    if cell.fmt == "key":
        args = {k: _arg(a, lang) for k, a in cell.args.items()}
        if v == FLAGS_KEY:  # the table keeps the codes (same in both languages): said here
            codes = str(cell.args["flags"]).split(FLAGS_SEP)
            args["flags"] = "; ".join(flag_text(c, lang) for c in codes)
        return t(str(v), lang, **args)
    if cell.fmt == "text":
        return str(v)
    if cell.fmt == "date":
        return fmt_date(str(v), lang)
    x = float(v)
    if cell.fmt == "bool":
        return t("common.yes" if x else "common.no", lang)
    if cell.fmt == "pct":
        return fmt_pct(x, lang)
    if cell.fmt == "num":
        return fmt_general(x, lang)
    return fmt_number(x, lang, _DECIMALS[cell.fmt])


def _arg(value: str | float, lang: Lang) -> str:
    if isinstance(value, str):
        return value
    return fmt_number(value, lang, 0 if float(value).is_integer() else 2)

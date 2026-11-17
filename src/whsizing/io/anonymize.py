"""F2 anonymisation (C2): identifiers → HMAC-SHA256(salt, id)[:16]; PII and free text dropped.

The correspondence table is never written: only the hashes leave this module.
"""

from __future__ import annotations

import hashlib
import hmac
import os
from pathlib import Path

import polars as pl

from whsizing.errors import ConfigError
from whsizing.logging import get_logger

SALT_ENV = "WHSIZING_SALT"
SALT_MIN_CHARS = 16  # shorter salts are warned about, never refused
HASH_CHARS = 16
ID_COLUMNS = ("order_id", "sku", "receipt_id", "customer")
PII_COLUMNS = ("description", "customer")  # dropped unless keep_descriptions


def hash_id(value: str, salt: bytes) -> str:
    return hmac.new(salt, value.encode("utf-8"), hashlib.sha256).hexdigest()[:HASH_CHARS]


def _hash_column(s: pl.Series, salt: bytes) -> pl.Series:
    """Hash each distinct value once (1 M lines carry far fewer distinct ids)."""
    codes = {v: hash_id(v, salt) for v in s.drop_nulls().unique().to_list()}
    return s.replace_strict(codes, default=None, return_dtype=pl.Utf8)


def anonymize(
    frames: dict[str, pl.DataFrame], salt: bytes, keep_descriptions: bool = False
) -> dict[str, pl.DataFrame]:
    """New frames with hashed identifiers; description/customer columns dropped unless
    `keep_descriptions` (a kept customer column is still hashed: it identifies a person)."""
    if not salt:
        raise ConfigError("anonymisation salt is empty")
    out: dict[str, pl.DataFrame] = {}
    for name, df in frames.items():
        if not keep_descriptions:
            df = df.drop([c for c in PII_COLUMNS if c in df.columns])
        hashed = [_hash_column(df[c], salt) for c in ID_COLUMNS if c in df.columns]
        out[name] = df.with_columns(hashed)
    return out


def _warn_short(salt: bytes, source: str) -> bytes:
    """Log (never the salt itself) when the salt is shorter than SALT_MIN_CHARS; return it."""
    if len(salt) < SALT_MIN_CHARS:
        get_logger().warning(
            "salt_too_short", source=source, length=len(salt), minimum=SALT_MIN_CHARS
        )
    return salt


def load_salt(salt_file: Path | None = None) -> bytes:
    """Salt from `salt_file` (must live outside any git repository) or $WHSIZING_SALT. A salt
    file readable by group or others (runbook: mode 600) and a salt under 16 characters are
    logged as warnings, not refused (tests and some platforms use 0644)."""
    if salt_file is not None:
        path = Path(salt_file).expanduser().resolve()
        if any((p / ".git").exists() for p in path.parents):
            raise ConfigError(f"salt file {path} is inside a git repository; keep it outside")
        try:
            mode = path.stat().st_mode & 0o777
            salt = path.read_bytes().strip()
        except OSError as e:
            raise ConfigError(f"cannot read salt file {path}: {e.strerror}") from e
        if not salt:
            raise ConfigError(f"salt file {path} is empty")
        if os.name != "nt" and mode & 0o077:  # POSIX permission bits only
            get_logger().warning(
                "salt_file_permissions", file=str(path), mode=f"{mode:03o}", expected="600"
            )
        return _warn_short(salt, str(path))
    env = os.environ.get(SALT_ENV, "").strip()
    if not env:
        raise ConfigError(
            f"no anonymisation salt: set ${SALT_ENV} or pass a salt file kept outside "
            "the repository"
        )
    return _warn_short(env.encode("utf-8"), f"${SALT_ENV}")

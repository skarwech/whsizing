"""F2 ingestion: read, sniff, map, validate (R1-R14), anonymise, write canonical Parquet."""

from whsizing.io.anonymize import anonymize, hash_id, load_salt
from whsizing.io.canonical import write_canonical
from whsizing.io.dq import build_dq_report, write_dq_report
from whsizing.io.ingest import ingest
from whsizing.io.mapping import Confirm, apply_mapping, suggest_mapping
from whsizing.io.readers import RawTable, read_any
from whsizing.io.rules import CanonicalFrames, apply_rules, run_rules
from whsizing.io.sniff import sniff

__all__ = [
    "CanonicalFrames",
    "Confirm",
    "RawTable",
    "anonymize",
    "apply_mapping",
    "apply_rules",
    "build_dq_report",
    "hash_id",
    "ingest",
    "load_salt",
    "read_any",
    "run_rules",
    "sniff",
    "suggest_mapping",
    "write_canonical",
    "write_dq_report",
]

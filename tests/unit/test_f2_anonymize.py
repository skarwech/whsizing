"""F2 anonymisation: T2.8 hashing stable with the same salt, different with another; PII drop."""

from __future__ import annotations

import hashlib
import hmac
import os
from pathlib import Path

import polars as pl
import pytest
from structlog.testing import capture_logs

from whsizing.errors import ConfigError
from whsizing.io import anonymize, hash_id, load_salt

FRAMES = {
    "order_lines": pl.DataFrame(
        {
            "order_id": ["C1", "C1", None],
            "sku": ["A1", "A2", "A1"],
            "customer": ["Dupont", "Dupont", "Martin"],
        }
    ),
    "sku_master": pl.DataFrame({"sku": ["A1", "A2"], "description": ["Pâte à tartiner", "Sel"]}),
    "receipts": pl.DataFrame({"receipt_id": ["R1"], "sku": ["A2"]}),
}


def test_T2_8_hash_is_stable_with_same_salt_and_differs_with_another() -> None:
    assert hash_id("A1", b"salt-1") == hash_id("A1", b"salt-1")
    assert hash_id("A1", b"salt-1") != hash_id("A1", b"salt-2")
    assert hash_id("A1", b"salt-1") != hash_id("A2", b"salt-1")
    expected = hmac.new(b"salt-1", b"A1", hashlib.sha256).hexdigest()[:16]
    assert hash_id("A1", b"salt-1") == expected and len(expected) == 16
    a = anonymize(FRAMES, b"salt-1")
    b = anonymize(FRAMES, b"salt-1")
    c = anonymize(FRAMES, b"salt-2")
    for name in FRAMES:
        assert a[name].equals(b[name])
        assert not a[name].equals(c[name])


def test_T2_8_ids_hashed_consistently_across_tables_and_nulls_kept() -> None:
    out = anonymize(FRAMES, b"s")
    lines, master = out["order_lines"], out["sku_master"]
    assert set(lines["sku"].to_list()) <= set(master["sku"].to_list())  # joins still work
    assert lines["order_id"].to_list()[2] is None
    assert lines["order_id"][0] == lines["order_id"][1] != "C1"
    assert out["receipts"]["receipt_id"][0] == hash_id("R1", b"s")
    raw_values = {"C1", "A1", "A2", "R1"}
    assert not raw_values & {v for df in out.values() for c in df.columns for v in df[c].to_list()}


def test_T2_8_description_and_customer_dropped_unless_kept() -> None:
    out = anonymize(FRAMES, b"s")
    assert "customer" not in out["order_lines"].columns
    assert "description" not in out["sku_master"].columns
    kept = anonymize(FRAMES, b"s", keep_descriptions=True)
    assert kept["sku_master"]["description"].to_list() == ["Pâte à tartiner", "Sel"]
    assert kept["order_lines"]["customer"][0] == hash_id("Dupont", b"s")  # still an identifier
    with pytest.raises(ConfigError):
        anonymize(FRAMES, b"")


def test_salt_from_env_or_file_outside_a_repository(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("WHSIZING_SALT", raising=False)
    with pytest.raises(ConfigError, match="WHSIZING_SALT"):
        load_salt()
    monkeypatch.setenv("WHSIZING_SALT", "from-env")
    assert load_salt() == b"from-env"
    salt_file = tmp_path / "salt_client_x"
    salt_file.write_text("from-file\n")
    assert load_salt(salt_file) == b"from-file"  # the file wins over the environment
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    (repo / "salt").write_text("x")
    with pytest.raises(ConfigError, match="git repository"):
        load_salt(repo / "salt")
    (tmp_path / "empty").write_text("")
    with pytest.raises(ConfigError, match="empty"):
        load_salt(tmp_path / "empty")


@pytest.mark.skipif(os.name == "nt", reason="POSIX permission bits")
def test_salt_file_readable_by_group_or_world_is_accepted_with_a_warning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Final audit (low): the runbook says mode 600 but a 0644 salt file was accepted silently.
    It still loads (tests and some platforms use 0644) and a warning names the file and mode."""
    monkeypatch.delenv("WHSIZING_SALT", raising=False)
    salt = b"a-long-enough-salt-0123456789"
    path = tmp_path / "salt_client_x"
    path.write_bytes(salt + b"\n")
    for mode, warned in ((0o600, False), (0o400, False), (0o640, True), (0o644, True)):
        path.chmod(mode)
        with capture_logs() as logs:
            assert load_salt(path) == salt  # never refused
        assert (len(logs) == 1 and logs[0]["event"] == "salt_file_permissions") is warned, oct(mode)
        if warned:
            [log] = logs
            assert log["file"] == str(path.resolve()) and log["mode"] == f"{mode:03o}"
            assert salt.decode() not in str(logs)  # the salt is never logged


def test_salt_short_is_accepted_with_a_warning_that_never_prints_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    secret = "hunter2-short"  # 13 characters
    path = tmp_path / "salt_client_x"
    path.write_text(secret + "\n")
    path.chmod(0o600)
    with capture_logs() as logs:
        assert load_salt(path) == secret.encode()
    [log] = logs
    assert log["event"] == "salt_too_short" and log["length"] == 13 and log["minimum"] == 16
    assert log["source"] == str(path.resolve())
    monkeypatch.setenv("WHSIZING_SALT", secret)
    with capture_logs() as logs:
        assert load_salt() == secret.encode()
    [log] = logs
    assert log["event"] == "salt_too_short" and log["source"] == "$WHSIZING_SALT"
    assert secret not in str(logs)
    monkeypatch.setenv("WHSIZING_SALT", "0123456789abcdef")  # exactly 16: fine
    with capture_logs() as logs:
        load_salt()
    assert logs == []

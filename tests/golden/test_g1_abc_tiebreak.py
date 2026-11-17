"""G1g: the oracle's ABC order follows I6 as amended (lines, units, avg_stock, unit cube, weight,
all descending, then sku ascending), so the classes and the sizing do not move with the salt of
the anonymised sku id; and the receipts-mode register entry I77 leaves the golden case alone.
Part of T1.5. The oracle never imports `whsizing`; only the engine check below does (it imports
it inside the test)."""

from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path
from typing import Any

import polars as pl
import pytest
import yaml
from tests.golden import build_golden, demand

HERE = Path(__file__).resolve().parent
DATA = HERE / "tiny_golden"
OLD_ORDER = ([pl.col("lines"), pl.col("sku")], [True, False])  # I6 before the amendment

# Rows in the order I6 must give: (sku, lines, units, avg_stock, height_mm, weight_kg). Each row
# differs from the one above at one rung only, and every lower rung (and the sku id) favours the
# row below, so a wrong rung order puts a row in the wrong place. The ids descend along the ranks
# except for the fully identical pair a1 / a2 (sku ascending) and the weight pair a3 / a0.
RANKED = [
    ("z9", 4, 3, 1.0, 10.0, 1.0),  # lines 4 > 3, though z8 has more units
    ("z8", 3, 10, 1.0, 10.0, 1.0),  # units 10 > 9, though z7 has more stock
    ("z7", 3, 9, 50.0, 10.0, 1.0),  # avg_stock 50 > 40, though z6 has more cube and weight
    ("z6", 3, 9, 40.0, 50.0, 5.0),  # cube 5e-4 > 3e-4, though z5 is heavier
    ("z5", 3, 9, 40.0, 30.0, 9.0),  # weight 9 > 4, though a1 has a smaller id
    ("a1", 3, 9, 40.0, 30.0, 4.0),  # identical to a2: sku ascending
    ("a2", 3, 9, 40.0, 30.0, 4.0),
    ("a3", 3, 9, 40.0, 30.0, 0.5),  # an unknown weight counts 0 (I10): after 0.5 kg ...
    ("a0", 3, 9, 40.0, 30.0, None),  # ... though its id is smaller
    ("a9", 0, 0, 0.0, 30.0, 4.0),  # no line: last
]


def _tables() -> tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame]:
    """sku frame (copy of tiny_golden master rows with the RANKED ids, dims and weight),
    inventory (one snapshot) and shipped lines."""
    master = pl.read_parquet(DATA / "sku_master.parquet").head(len(RANKED))
    master = master.with_columns(
        sku=pl.Series([r[0] for r in RANKED]),
        length_mm=pl.lit(100.0),
        width_mm=pl.lit(100.0),
        height_mm=pl.Series([r[4] for r in RANKED]),
        weight_kg=pl.Series([r[5] for r in RANKED], dtype=pl.Float64),
        unit_cube_m3=pl.lit(None, dtype=pl.Float64),
    )
    inv = pl.DataFrame(
        {
            "sku": [r[0] for r in RANKED],
            "qty_units": [int(r[3]) for r in RANKED],
            "snapshot_date": [date(2025, 3, 31)] * len(RANKED),
        }
    )
    rows = []
    for sku, n_lines, units, *_ in RANKED:
        for i in range(n_lines):  # the surplus units on the first line, 1 on the others
            rows.append((sku, date(2025, 3, 1 + i), units - (n_lines - 1) if i == 0 else 1))
    lines = pl.DataFrame(rows, schema=["sku", "date", "qty_units"], orient="row")
    return demand.prepare_sku(master), inv, lines


def _ranked(sku: pl.DataFrame, inv: pl.DataFrame, lines: pl.DataFrame) -> list[str]:
    return [r["sku"] for r in demand.sku_table(sku, inv, lines)]


def _with_order(order: tuple[list[pl.Expr], list[bool]]) -> tuple[list[Any], list[bool]]:
    """Swap the oracle's ABC order in place, return the previous one."""
    saved = (list(demand.ABC_ORDER), list(demand.ABC_DESC))
    demand.ABC_ORDER[:], demand.ABC_DESC[:] = order
    return saved


def test_T1_5_abc_order_ties_by_lines_units_stock_cube_weight_then_sku() -> None:
    """I6: each rung decides exactly one pair, in the order lines > units > avg_stock > unit cube >
    weight > sku; two SKUs identical in every attribute are ordered by sku ascending; an unknown
    weight sorts as 0. Input row order does not matter."""
    sku, inv, lines = _tables()
    expected = [r[0] for r in RANKED]
    assert _ranked(sku, inv, lines) == expected
    assert _ranked(sku.reverse(), inv.reverse(), lines.reverse()) == expected
    rows = demand.sku_table(sku, inv, lines)
    assert rows[-1]["lines"] == 0 and rows[-1]["abc"] == "C"  # no line: C (I6)


def test_T1_5_abc_order_is_not_the_old_sku_ascending_tie_break() -> None:
    """The amendment is real: the same data under the pre-amendment order (lines, sku) is ranked
    differently, so the rung test above fails on it."""
    sku, inv, lines = _tables()
    saved = _with_order(OLD_ORDER)
    try:
        old = _ranked(sku, inv, lines)
    finally:
        _with_order(saved)
    assert old != [r[0] for r in RANKED]
    assert old[0] == "z9" and old[1:9] == sorted(old[1:9])  # lines, then the sku id inside the tie


def test_T1_5_engine_abc_follows_the_same_tie_break_chain() -> None:
    """The engine's ABC ranking equals the oracle's on the RANKED rows (F3f made the engine
    follow I6 as amended; before it the engine tied by the salt-dependent sku id)."""
    from whsizing.profile.abc import classify

    rows = demand.sku_table(*_tables())
    cols = ["sku", "lines", "units", "avg_stock", "unit_cube_m3", "weight_kg"]
    skus = pl.DataFrame({c: [r[c] for r in rows] for c in cols}).reverse()
    ranked = classify(skus, "lines", (0.80, 0.95))
    assert ranked["sku"].to_list() == [r[0] for r in RANKED]


def _relabelled(tmp: Path, salt: str) -> Path:
    """tiny_golden with every sku id replaced by a salted hash (another anonymisation salt)."""
    frames = {
        n: pl.read_parquet(DATA / f"{n}.parquet")
        for n in ("order_lines", "sku_master", "inventory")
    }
    ids = {s for f in frames.values() for s in f["sku"].to_list()}
    mapping = {s: hashlib.sha256(f"{salt}:{s}".encode()).hexdigest()[:16] for s in ids}
    for name, df in frames.items():
        df.with_columns(pl.col("sku").replace_strict(mapping)).write_parquet(
            tmp / f"{name}.parquet"
        )
    return tmp


def _differs(g0: dict[str, Any], g1: dict[str, Any]) -> list[str]:
    """Keys whose values differ: exact for non-floats, 1e-9 relative for floats."""
    assert set(g0) == set(g1)
    bad = []
    for k, a in g0.items():
        b = g1[k]
        same = a == pytest.approx(b, rel=1e-9, abs=1e-12) if isinstance(a, float) else a == b
        bad += [] if same else [k]
    return bad


def test_T1_5_golden_values_do_not_depend_on_the_sku_salt(tmp_path: Path) -> None:
    """I6's purpose: relabel every sku id (another salt) and every golden value is unchanged. On
    tiny_golden 12 SKUs tie at 5 lines across the B / C boundary, so under the old order the
    hashed id decided which of them are B and the replenishment hours, opex and NPV moved."""
    g0 = json.loads((HERE / "golden_values.json").read_text(encoding="utf-8"))
    g1 = build_golden.run(data_dir=_relabelled(tmp_path, "other-salt"))[0].values()
    assert _differs(g0, g1) == []


def test_T1_5_old_order_made_the_golden_values_depend_on_the_sku_salt(tmp_path: Path) -> None:
    """Control for the test above: with the pre-amendment order the same relabelling moves the
    sizing keys (so the test above discriminates): one more pick face in S0, replenishment hours,
    area, capex and opex. No class size moves (the same number of SKUs is B)."""
    data = _relabelled(tmp_path, "other-salt")
    saved = _with_order(OLD_ORDER)
    try:
        g_old = build_golden.run()[0].values()
        g_old_relabelled = build_golden.run(data_dir=data)[0].values()
    finally:
        _with_order(saved)
    moved = _differs(g_old, g_old_relabelled)
    assert "S0.labor.replenishment.workload" in moved
    assert "S0.storage.pallet_rack.pick_faces" in moved
    assert not any(k.startswith("abc.") for k in moved)


def test_T1_5_golden_class_boundary_inside_a_line_tie_follows_the_chain() -> None:
    """On the golden case itself: SKUs tied on lines but in different classes are split by the
    chain, never by the sku id: every better class of the tie outranks every worse one on (units,
    avg_stock, unit cube, weight). Only the units rung decides on tiny_golden."""
    c = build_golden.run()[1]
    by_lines: dict[int, list[dict[str, Any]]] = {}
    for r in c["skus"]:
        by_lines.setdefault(r["lines"], []).append(r)
    split = [g for g in by_lines.values() if len({r["abc"] for r in g}) > 1]
    assert [len(g) for g in split] == [12], "the 5-line tie across B / C is gone from tiny_golden"

    def key(r: dict[str, Any]) -> tuple[float, ...]:
        return (r["units"], r["avg_stock"], r["unit_cube_m3"], r["weight_kg"] or 0.0)

    for hi in split[0]:
        for lo in split[0]:
            if hi["abc"] < lo["abc"]:  # 'A' < 'B' < 'C'
                assert key(hi) > key(lo), (hi["sku"], lo["sku"])


# --- I75-I77 against the oracle -------------------------------------------------------------
def test_T1_5_receipts_mode_is_not_silently_derived_in_the_oracle(tmp_path: Path) -> None:
    """I56 / I77: the oracle sizes the derived inbound. A basis in receipts mode, the only mode in
    which F_INBOUND_SPARSE and F_RECEIPTS_NO_PALLETS exist, is refused instead of being computed
    as derived. The golden basis is derived, so no I77 flag is in any golden value (I75 and I76
    describe the runner and the sensitivity, which the oracle does not have)."""
    basis = yaml.safe_load((HERE / "golden_basis.yaml").read_text(encoding="utf-8"))
    assert basis["flows"]["inbound_mode"] == "derived"
    golden = json.loads((HERE / "golden_values.json").read_text(encoding="utf-8"))
    flags = [v for k, v in golden.items() if k.endswith(".flags")]
    assert len(flags) >= 3 and not any(
        "F_INBOUND_SPARSE" in f or "F_RECEIPTS_NO" in f for f in flags
    )
    basis["flows"]["inbound_mode"] = "receipts"
    path = tmp_path / "receipts_basis.yaml"
    path.write_text(yaml.safe_dump(basis), encoding="utf-8")
    with pytest.raises(NotImplementedError, match="derived inbound only"):
        build_golden.run(basis_path=path)

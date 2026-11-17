"""F5 catalog loader: T5.1 malformed fixtures, T5.5 pessimistic_end inference, shipped catalog."""

from __future__ import annotations

import re
import shutil
from pathlib import Path

import pytest

from whsizing.catalog import infer_pessimistic_end, load_catalog, snapshot_catalog
from whsizing.catalog.assumptions import render_assumptions_md
from whsizing.catalog.models import FAMILY_KEYS, Area, Capex, Opex, Storage, Throughput
from whsizing.errors import ConfigError

ROOT = Path(__file__).resolve().parents[2]
CATALOG = ROOT / "catalog"
BAD = ROOT / "tests/fixtures/catalog_bad"

# fixture folder → substrings the ConfigError must contain (file, key, reason)
BAD_CASES: dict[str, tuple[str, ...]] = {
    "missing_unit": ("finance_defaults.yaml", "packaging_eur_per_order.unit", "Field required"),
    "missing_source": ("finance_defaults.yaml", "packaging_eur_per_order.source", "Field required"),
    "missing_confidence": (
        "finance_defaults.yaml",
        "packaging_eur_per_order.confidence",
        "Field required",
    ),
    "min_gt_typ": ("finance_defaults.yaml", "packaging_eur_per_order", "min ≤ typ ≤ max violated"),
    "not_inferable": ("cube_asrs.yaml", "throughput.dig_factor", "pessimistic_end missing"),
    "unknown_key": ("area_factors.yaml", "circulation_shar", "unknown key"),
    "duplicate_family_id": ("cube_asrs_copy.yaml", "duplicate family id 'cube_asrs'"),
    "duplicate_key": ("finance_defaults.yaml", "duplicate key 'packaging_eur_per_order'"),
    "bad_semver": ("cube_asrs.yaml", "version", "not semver"),
    "r_shorthand": ("finance_defaults.yaml", "packaging_eur_per_order", "R(...) shorthand"),
    "id_mismatch": (
        "finance_defaults.yaml",
        "packaging_eur_per_order",
        "must be 'finance.packaging_eur_per_order'",
    ),
    "missing_family_param": (
        "cube_asrs.yaml",
        "throughput.port_rate_lines_h",
        "missing (required for cube_asrs)",
    ),
    "cross_family_key": (
        "manual_p2p.yaml",
        "throughput.port_rate_lines_h",
        "not a manual_p2p parameter",
    ),
}


@pytest.fixture(scope="module")
def catalog():
    return load_catalog(CATALOG)


def _overlay(tmp_path: Path, files: Path | dict[str, str]) -> Path:
    """Copy the shipped catalog to tmp_path and overlay a fixture folder or {relpath: text}."""
    cat = tmp_path / "catalog"
    shutil.copytree(CATALOG, cat)
    if isinstance(files, Path):
        shutil.copytree(files, cat, dirs_exist_ok=True)
    else:
        for rel, text in files.items():
            (cat / rel).write_text(text, encoding="utf-8")
    return cat


def test_T5_1_every_fixture_has_a_case() -> None:
    assert {p.name for p in BAD.iterdir() if p.is_dir()} == set(BAD_CASES)


@pytest.mark.parametrize("case", sorted(BAD_CASES))
def test_T5_1_loader_rejects_malformed_fixture(case: str, tmp_path: Path) -> None:
    with pytest.raises(ConfigError) as exc:
        load_catalog(_overlay(tmp_path, BAD / case))
    assert exc.value.exit_code == 2
    for needle in BAD_CASES[case]:
        assert needle in str(exc.value), f"{needle!r} not in: {exc.value}"


def test_T5_1_missing_and_unknown_catalog_files(tmp_path: Path) -> None:
    cat = _overlay(tmp_path, {"extra.yaml": "a: 1\n"})
    (cat / "icpe_1510.yaml").unlink()
    with pytest.raises(ConfigError, match=r"unknown catalog file\(s\) \['extra.yaml'\].*icpe_1510"):
        load_catalog(cat)


CUBE = "families/cube_asrs.yaml"


@pytest.mark.parametrize(
    ("rel", "old", "new", "key"),
    [
        # `weight <= NaN` is True in polars: a .nan limit would make a 500 kg SKU eligible
        (CUBE, "max_weight_kg: 25 ", "max_weight_kg: .nan ", "constraints.max_weight_kg"),
        (CUBE, "max_item_mm: [600,", "max_item_mm: [.inf,", "constraints.max_item_mm.0"),
        (CUBE, "typ: 350, max: 450", "typ: 350, max: .inf", "port_rate_lines_h.max"),
        (CUBE, "empty_bin_reserve: 0.05", "empty_bin_reserve: .inf", "storage.empty_bin_reserve"),
        (CUBE, "empty_bin_reserve: 0.05", 'empty_bin_reserve: "nan"', "storage.empty_bin_reserve"),
        ("area_factors.yaml", "staging_days: 1.0", "staging_days: -.inf", "staging_days"),
        ("icpe_1510.yaml", "max_m3: 50000}", "max_m3: .inf}", "regimes.0.max_m3"),
    ],
)
def test_T5_1_loader_rejects_non_finite_values(
    rel: str, old: str, new: str, key: str, tmp_path: Path
) -> None:
    text = (CATALOG / rel).read_text(encoding="utf-8")
    assert old in text
    with pytest.raises(ConfigError, match="finite number") as exc:
        load_catalog(_overlay(tmp_path, {rel: text.replace(old, new, 1)}))
    assert exc.value.exit_code == 2
    assert rel.rsplit("/", 1)[-1] in str(exc.value)
    assert key in str(exc.value)


def test_T5_1_non_utf8_file_is_a_config_error(tmp_path: Path) -> None:
    """An expert saving a family file as cp1252 (French text) gets ConfigError, exit 2."""
    cat = _overlay(tmp_path, {})
    text = (cat / CUBE).read_text(encoding="utf-8")
    (cat / CUBE).write_bytes("# capacité\n".encode("cp1252") + text.encode("utf-8"))
    with pytest.raises(ConfigError, match=r"cube_asrs.yaml: not UTF-8") as exc:
        load_catalog(cat)
    assert exc.value.exit_code == 2


@pytest.mark.parametrize(
    ("rel", "old", "new", "message"),
    [
        (
            CUBE,
            r"max_robots_per_m2: \{.*\}",  # the whole Param block line
            "max_robots_per_m2: 0.05",
            "max_robots_per_m2: must be a Param block for cube_asrs",
        ),
        (
            "families/amr_gtp.yaml",
            "max_robots_per_m2: 0.05",
            "max_robots_per_m2: {unit: robots/m2, min: 0.04, typ: 0.05, max: 0.06, source: TODO,"
            " confidence: L, pessimistic_end: min, date: 2026-11}",
            "max_robots_per_m2: must be a number for amr_gtp",
        ),
    ],
)
def test_T5_1_max_robots_per_m2_shape_is_pinned_per_family(
    rel: str, old: str, new: str, message: str, tmp_path: Path
) -> None:
    text, n = re.subn(old, new, (CATALOG / rel).read_text(encoding="utf-8"), count=1)
    assert n == 1
    with pytest.raises(ConfigError, match=message):
        load_catalog(_overlay(tmp_path, {rel: text}))


@pytest.mark.parametrize(
    ("unit", "name", "expected"),
    [
        ("lines/h", "port_rate_lines_h", "min"),
        ("pallets/h", "receiving", "min"),
        ("1/m2", "bins_per_m2_per_level", "min"),
        ("1/m2", "pallet_rack_positions_per_m2_per_level", "min"),  # /m2 before m2_per
        ("-", "fill_factor", "min"),
        ("-", "shelving_fill_factor", "min"),
        ("-", "robot_availability", "min"),
        ("-", "oee", "min"),
        ("eur", "per_port_eur", "max"),
        ("eur/m2", "grid_structure_per_m2_eur", "max"),  # eur wins over /m2
        ("kWh", "kwh_per_robot_year", "max"),  # energy
        ("h", "receiving_window", "max"),  # duration
        ("m2", "m2_per_port", "max"),
        ("m2 per station", "station_area", "max"),
        ("-", "dig_factor", None),
        ("-", "maintenance_share_of_equipment_capex", None),
        ("units", "replen_units_per_move", None),
        ("m2", "pod_footprint_m2", None),
        # unit tokens, not substrings (W1 audit finding 5)
        ("orders/h", "packing_S", "min"),  # x/h: per hour
        ("bins/m2", "density", "min"),
        ("robots/m2", "max_robots_per_m2", "min"),
        ("eur/year", "software_eur_year", "max"),  # eur anywhere
        ("eur/h", "labor_cost", "max"),  # eur wins over /h
        ("kWh/year", "energy", "max"),
        ("pallets/shift", "forklift_moves_shift", None),  # 'h' inside 'shift' is not an hour
        ("units/month", "units_month", None),  # 'h' inside 'month' is not an hour
        ("share", "renewal_share", None),  # 'h' inside 'share' is not a duration
        ("lines/day", "lines_day", None),
        ("hours", "window", None),  # only the exact unit 'h' is a duration
        ("1/shift", "refill", None),  # 'fill' inside 'refill' is not a fill factor
        # tokens again (F5b audit): 'eur' inside a word is not a cost, '€' is
        ("europallets/h", "receiving", "min"),
        ("€/h", "labor_cost", "max"),
        # a density name (…_per_m2_…) is not an area per unit, even if it contains 'm2_per'
        ("positions", "pallet_rack_positions_per_m2_per_level", None),
        ("-", "bins_per_m2_per_level", None),
    ],
)
def test_T5_5_pessimistic_end_inference(unit: str, name: str, expected: str | None) -> None:
    assert infer_pessimistic_end(unit, name) == expected


def test_T5_5_loader_infers_absent_end_and_warns_on_contradiction(tmp_path: Path) -> None:
    text = (CATALOG / "finance_defaults.yaml").read_text()
    absent = text.replace(
        "source: TODO, confidence: L, pessimistic_end: max, date",
        "source: TODO, confidence: L, date",
        1,
    )
    assert absent != text
    cat = load_catalog(_overlay(tmp_path / "a", {"finance_defaults.yaml": absent}))
    assert cat.params["finance.packaging_eur_per_order"].pessimistic_end == "max"
    assert cat.warnings == []

    wrong = text.replace("pessimistic_end: max", "pessimistic_end: min", 1)
    cat = load_catalog(_overlay(tmp_path / "b", {"finance_defaults.yaml": wrong}))
    assert cat.params["finance.packaging_eur_per_order"].pessimistic_end == "min"  # explicit wins
    assert len(cat.warnings) == 1
    assert "packaging_eur_per_order" in cat.warnings[0]
    assert "contradicts" in cat.warnings[0]


def test_T5_5_loader_rejects_absent_end_for_unit_with_no_rule(tmp_path: Path) -> None:
    text = (CATALOG / "labor_standards.yaml").read_text()
    tail = "max: 18, source: TODO, confidence: L"
    old = f'unit: "pallets/h", min: 10, typ: 14, {tail}, pessimistic_end: min'
    new = f'unit: "pallets/shift", min: 10, typ: 14, {tail}'  # no rule matches: must be explicit
    assert old in text
    cat = _overlay(tmp_path, {"labor_standards.yaml": text.replace(old, new, 1)})
    with pytest.raises(ConfigError, match=r"receiving.standard: pessimistic_end missing.*shift"):
        load_catalog(cat)


def test_shipped_catalog_loads_cleanly_and_counts_todos(catalog) -> None:
    assert set(catalog.families) == {"manual_p2p", "amr_gtp", "cube_asrs"}
    assert catalog.warnings == []  # no explicit pessimistic_end contradicts §2.5.1
    assert len(catalog.params) == 72  # 68 at 0.1.0 + 4 placeholders (CHANGELOG 0.2.0)
    assert len(catalog.constants) == 72  # + engine.max_equipment_count (I85 b)
    assert catalog.todo_count == 72  # every range is still source: TODO
    assert all(p.confidence == "L" for p in catalog.params.values())
    assert catalog.version.startswith("manual_p2p=0.1.0 amr_gtp=0.2.0 cube_asrs=0.2.0 sha256:")


def test_family_schemas_cover_exactly_the_section_models(catalog) -> None:
    """Every key of a section model belongs to some family; each shipped file has its own set."""
    models = {"storage": Storage, "throughput": Throughput, "area": Area}
    for section, model in {**models, "capex": Capex, "opex": Opex}.items():
        families_keys = set[str]().union(*(k[section] for k in FAMILY_KEYS.values()))
        assert set(model.model_fields) == families_keys, section
    for fid, fam in catalog.families.items():
        for section, expected in FAMILY_KEYS[fid].items():
            sec = getattr(fam, section)
            assert {k for k in type(sec).model_fields if getattr(sec, k) is not None} == expected


def test_f6_f7_placeholders_are_in_the_catalog(catalog) -> None:
    """W1 audit finding 4: parameters F6d/F7 consume, [P] placeholders, source TODO, conf. L."""
    for pid, typ in {
        "cube_asrs.floor_prep_per_m2_eur": 20,  # F7 l.1091
        "cube_asrs.max_robots_per_m2": 0.05,  # F5 l.847
        "cube_asrs.m2_per_robot_parking": 2.0,  # F6d l.995
        "amr_gtp.charging_per_robot_eur": 0,  # F7 l.1089
    }.items():
        p = catalog.params[pid]
        assert (p.typ, p.source, p.confidence) == (typ, "TODO", "L"), pid


def test_shipped_ids_follow_the_readme_rule(catalog) -> None:
    for pid in [
        "manual_p2p.pick_rate_shelving_lines_h",  # Appendix E basis override
        "amr_gtp.station_rate_lines_h",  # Appendix E scenario override
        "cube_asrs.port_rate_lines_h",  # §2.5 Param example
        "manual_p2p.pallet_rack_positions_per_m2_per_level",
        "manual_p2p.shelving_fill_factor",
        "labor.receiving",
        "finance.packaging_eur_per_order",
        "engine.pack_station_oee",
    ]:
        assert pid in catalog.params, pid
    for cid, value in {
        "cube_asrs.max_levels": 20,
        "manual_p2p.pallet_rack_max_levels": 6,
        "labor.indirect_share_of_direct_hours": 0.12,
        "storage.default_units_per_pallet": 400,
        "area.peak_hour_share_inbound": 0.2,
        "engine.eta_flow": 0.85,
        "finance.default_roles_cost_eur_h_operator": 26,
    }.items():
        assert catalog.constants[cid] == value, cid
    assert not set(catalog.params) & set(catalog.constants)


def _spec_ranges() -> list[tuple[str, float, float, float, str, str]]:
    """Every R(...) of Appendix C/D and every F5-schema range block, keyed by its YAML key."""
    spec = (ROOT / "description.md").read_text(encoding="utf-8")
    r_short = re.compile(
        r'^\s*(\w+):.*?R\(([\d.]+), ([\d.]+), ([\d.]+), "([^"]*)", (min|max)\)', re.M
    )
    f5 = re.compile(
        r"^\s*(\w+): \{min: ([\d.]+), typ: ([\d.]+), max: ([\d.]+), unit: \"([^\"]*)\".*?"
        r"pessimistic_end: (min|max)",
        re.M,
    )
    found = [*r_short.findall(spec), *f5.findall(spec)]
    return [(k, float(a), float(b), float(c), u, e) for k, a, b, c, u, e in found]


def test_shipped_ranges_are_verbatim_from_the_spec(catalog) -> None:
    spec = _spec_ranges()
    assert len(spec) == 66  # 19 + 19 + 18 family ranges, 9 labor, 1 finance
    shipped = {
        (p.id.rsplit(".", 1)[1], p.min, p.typ, p.max, p.unit, p.pessimistic_end)
        for p in catalog.params.values()
    }
    for key, lo, typ, hi, unit, end in spec:
        assert any(s[0].endswith(key) and s[1:] == (lo, typ, hi, unit, end) for s in shipped), (
            f"spec range {key} R({lo}, {typ}, {hi}, {unit!r}, {end}) not in the catalog"
        )


def test_catalog_version_is_stable_and_snapshot_reproduces_it(catalog, tmp_path: Path) -> None:
    assert load_catalog(CATALOG).version == catalog.version
    snap = snapshot_catalog(CATALOG, tmp_path / "inputs" / "catalog")
    assert (snap / "CHANGELOG.md").is_file()
    assert load_catalog(snap).version == catalog.version
    (snap / "area_factors.yaml").write_text(
        (snap / "area_factors.yaml").read_text().replace("staging_days: 1.0", "staging_days: 2.0")
    )
    assert load_catalog(snap).version != catalog.version


def test_icpe_regime_lookup(catalog) -> None:
    assert catalog.icpe.regime(12000 * 10.5) == "Enregistrement (E)"  # Appendix E building
    assert catalog.icpe.regime(1000) is None
    assert catalog.icpe.regime(900000) == "Autorisation (A)"


def test_docs_assumptions_md_is_regenerated(catalog) -> None:
    """C4: docs/assumptions.md equals the generator output; rerun it after any catalog change."""
    text = (ROOT / "docs/assumptions.md").read_text(encoding="utf-8")
    assert text == render_assumptions_md(catalog)
    assert "| cube_asrs.port_rate_lines_h | lines/h | 250 | 350 | 450 | min | TODO | L |" in text

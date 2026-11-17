"""The `inputs` stage of the staged flow (`ingest` → `size`): the run's manifest and the marks that
let `whsizing rerun` replay it like a `run-all` run (C1, I78)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from whsizing.catalog import Catalog, ParamSet
from whsizing.cli._runio import read_model
from whsizing.config import load_yaml_model
from whsizing.io.canonical import DEFAULT_UNITS_PER_PALLET
from whsizing.io.canonical import MANIFEST as INGEST_MANIFEST
from whsizing.logging import get_logger, stage_timer
from whsizing.scenarios.manifest import PROJECT_COPY, build_manifest, copy_inputs, write_manifest
from whsizing.scenarios.runner import (
    HASHES_FILE,
    KEY_FILE,
    UPP_ID,
    _reused_files,  # pyright: ignore[reportPrivateUsage]
    ingest_key,
)
from whsizing.schemas import (
    DesignBasis,
    IngestManifest,
    ProfileCfg,
    Project,
    RunManifest,
    ScenarioSet,
)

PROFILE_CFG_COPY = Path("inputs") / "profile_cfg.yaml"  # `profile --cfg` saves it, `size` reads it


def profile_cfg_of(run: Path) -> ProfileCfg:
    saved = run / PROFILE_CFG_COPY
    return load_yaml_model(saved, ProfileCfg) if saved.is_file() else ProfileCfg()


def warn_units_per_pallet(catalog: Catalog, basis: DesignBasis) -> None:
    """`ingest` ran before the catalog was known, so it used the I59 default units per pallet."""
    value = round(ParamSet(catalog, basis.overrides).value(UPP_ID))
    if value != DEFAULT_UNITS_PER_PALLET:
        get_logger().warning(
            "units_per_pallet_differs", ingested=DEFAULT_UNITS_PER_PALLET, catalog_or_basis=value
        )


def start_run(
    run: Path, project: Project, catalog: Catalog, basis: DesignBasis, scenarios: ScenarioSet
) -> RunManifest:
    """Stage `inputs`: the copies under inputs/, manifest.json (data hashes from the ingest
    manifest) and the canonical/ marks `rerun` needs. Returns the manifest."""
    with stage_timer("inputs"):
        project_sha = copy_inputs(project, run)
    ing = read_model(run / "dq" / INGEST_MANIFEST, IngestManifest, "run `whsizing ingest`")
    external = {f.path: f.sha256 for d in ing.datasets for f in d.files}
    draft = build_manifest(project, catalog, basis, scenarios, datetime.now(UTC), external)
    manifest = draft.model_copy(
        update={
            "run_id": run.name,
            "mapping_hashes": {d.dataset: d.mapping_hash for d in ing.datasets},
            "inputs": {**draft.inputs, PROJECT_COPY: project_sha},
        }
    )
    _seal_canonical(run, project, external, round(ParamSet(catalog, basis.overrides).value(UPP_ID)))
    write_manifest(manifest, run)
    return manifest


def _seal_canonical(run: Path, project: Project, external: dict[str, str], upp: int) -> None:
    """What the runner writes after its ingest: canonical/.ingest_key and .sha256.json, so that
    `rerun` can copy canonical/, dq/ and inputs/mapping/ of this run. The anonymisation salt of the
    staged ingest is not known here (b""); the key never equals a project's (its inputs are {}),
    so `run-all` never reuses a staged run's canonical tables, and `rerun` needs no salt."""
    key = ingest_key(project, external, b"", upp)
    (run / "canonical" / KEY_FILE).write_text(key, encoding="utf-8")
    (run / "canonical" / HASHES_FILE).write_text(
        json.dumps(_reused_files(run), sort_keys=True, indent=1) + "\n", encoding="utf-8"
    )

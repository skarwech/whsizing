"""F6 sizing engine: `size_scenario` (size.py, F6z) runs every part below once per world and
writes `scenarios/<id>/result.json` + `trace.jsonl` (`write_scenario`). The parts: inputs,
storage classes, storage, throughput (F6a/F6b/F6f), labor (F6c), area and docks (F6d), queue
(F6e). Per world `w` in `WORLDS` (lo = pessimistic, typ, hi = optimistic; ADR-002):

    sku = sku_frame(tables, sku_master)                  # I58, once per run (also given to F4)
    inp = world_inputs(basis, design_day, scenario, catalog, sku, w, tracer)
    st = size_storage(inp)                               # StorageWorld
    tp = size_throughput(inp, st)                        # ThroughputWorld
    ...                                                  # F6c/F6d/F6e read inp, st, tp
    storage = storage_result({w: st_w}, inp_typ.eligibility)    # StorageResult (Ranges)
    equipment = {k: to_range({w: tp_w.equipment[k]}, "-") for k in tp_typ.equipment}

- Parameter values: `inp.v("<catalog id>")` (basis + scenario overrides, world applied).
- Trace: `inp.record("<key>", label, value, unit, formula, inputs)` records
  `<scenario id>.<key>` in the world (scope = scenario id); `inp.tid("<key>")` is the id to put
  in another node's `inputs`. Leaves are `param:<catalog id>` or `data:<name>`.
  Ids already recorded here: `S*.eligibility.*`, `S*.storage[.overflow].<class>.*`,
  `S*.storage.total_area_m2`, `S*.throughput.*` (lambda, lambda_e/o, lambda.<zone>,
  line_share.<zone>, replen_moves, peak_hour_share, decant_cases_in, sla_window_hours),
  `S*.equipment.*`, `S*.utilisation.*`. Recording an id twice with other content raises.
- Per-SKU frame `inp.sku` (sorted by sku): the I58 columns plus `eligible` (scenario mask
  after I48), `assumed`, `design_stock`, `design_stock_cube_m3`, `fits_shelf`, `manual_class`,
  `storage_class` (= the SKU's picking zone, I17: cube_bin | pod_bin | shelving | pallet_rack)
  and `zone` (main | overflow). F6c joins `storage_class` onto shipped lines for daily lines
  per zone.
- From `ThroughputWorld`: `line_share` / `lam_zone` per manual zone, `replen_moves` (I21),
  `cases_in` (cube, amr) and `decant_port_load_peak_h` (cube, I23), counts in `equipment`,
  `utilisation`, `bottleneck` (use the typ world's), `flags` (F_SCALE_LOW, F_ROBOT_DENSITY).
- `inp.eligibility` is the scenario's `EligibilityResult` (flags F_ELIG_LOW, F_ELIG_ASSUMED).
"""

from whsizing.engine.area import AreaWorld, area_result, size_area
from whsizing.engine.classify import classify_skus, fits_shelf
from whsizing.engine.inputs import WORLDS, WorldInputs, sku_frame, to_range, world_inputs
from whsizing.engine.labor import (
    ActivityWorld,
    LaborDays,
    LaborWorld,
    labor_days,
    labor_result,
    size_labor,
)
from whsizing.engine.queue import QueueWorld, erlang_c, queue_resource, queue_result, size_queue
from whsizing.engine.size import size_scenario, write_scenario
from whsizing.engine.storage import ClassWorld, StorageWorld, size_storage, storage_result
from whsizing.engine.throughput import ThroughputWorld, size_throughput

__all__ = [
    "WORLDS",
    "ActivityWorld",
    "AreaWorld",
    "ClassWorld",
    "LaborDays",
    "LaborWorld",
    "QueueWorld",
    "StorageWorld",
    "ThroughputWorld",
    "WorldInputs",
    "area_result",
    "classify_skus",
    "erlang_c",
    "fits_shelf",
    "labor_days",
    "labor_result",
    "queue_resource",
    "queue_result",
    "size_area",
    "size_labor",
    "size_queue",
    "size_scenario",
    "size_storage",
    "size_throughput",
    "sku_frame",
    "storage_result",
    "to_range",
    "world_inputs",
    "write_scenario",
]

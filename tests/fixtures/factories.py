"""Valid mock instances of every contract. Later features reuse them:

from tests.fixtures import mock_result, mock_basis
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time
from pathlib import Path

from pydantic import BaseModel

from whsizing.schemas import (
    ABC,
    EIQ,
    AbcClassStats,
    ActivityLabor,
    AreaResult,
    Assumption,
    Baseline,
    BreakEven,
    Building,
    Cell,
    Comparison,
    ComparisonRow,
    DatasetIngest,
    DemandProfile,
    DesignBasis,
    DesignDay,
    EligibilityCfg,
    EligibilityResult,
    FinanceBasis,
    FinancialResult,
    Flag,
    Flows,
    Inbound,
    IngestManifest,
    InputSpec,
    IntegrityIssue,
    LaborResult,
    Operations,
    Param,
    PercentileSweepRow,
    ProfileCfg,
    Project,
    Projection,
    ProjectOptions,
    QueueResource,
    QueueResult,
    Range,
    ReportTable,
    RunManifest,
    RunOutput,
    ScenarioDef,
    ScenarioResult,
    ScenarioSet,
    Seasonality,
    Sensitivity,
    SeriesStats,
    Service,
    ShiftRow,
    ShipmentSplit,
    SniffResult,
    SourceFile,
    StockStats,
    StorageClassResult,
    StorageResult,
    TableBlock,
    TableColumn,
    TableRow,
    TornadoBar,
    TraceNode,
)

FIXTURES = Path(__file__).parent


def rng(lo: float, typ: float, hi: float, unit: str = "-") -> Range:
    return Range(lo=lo, typ=typ, hi=hi, unit=unit)


def mock_param() -> Param:
    return Param(
        id="cube_asrs.port_rate_lines_h",
        unit="lines/h",
        min=250,
        typ=350,
        max=450,
        source="TODO",
        confidence="L",
        pessimistic_end="min",
        date=date(2026, 11, 1),
        note="[EXPERT] placeholder",
    )


def mock_basis() -> DesignBasis:
    """Appendix E basis.yaml as a model."""
    return DesignBasis(
        client="Client X",
        site="Lyon",
        operations=Operations(operating_days_per_year=252, shifts_per_day=2),
        service=Service(
            cutoff_time=time(15, 0), carrier_departure_time=time(18, 30), same_day_share=0.6
        ),
        projection=Projection(growth_rate=0.04, trailing_months=24),
        flows=Flows(returns_rate=0.04),
        building=Building(
            area_m2=12000,
            clear_height_m=10.5,
            dock_doors_in=4,
            dock_doors_out=6,
            rent_eur_m2_year=58,
        ),
        finance=FinanceBasis(
            energy_price_eur_kwh=0.17,
            labor_cost_eur_h={"operator": 25.5, "forklift_driver": 27.8, "team_leader": 33.0},
        ),
        baseline=Baseline(
            description="Current manual operation, 2 shifts",
            actual_fte={"picking": 18, "packing": 9, "receiving": 4, "shipping": 5, "indirect": 4},
            actual_hours_month={"picking": [2800.0, 2950.0]},
            equipment={"forklifts": 4},
        ),
        overrides={"manual_p2p.pick_rate_shelving_lines_h": 62},
    )


def _stats(mean: float, cv: float = 0.3) -> SeriesStats:
    return SeriesStats(
        mean=mean,
        p50=mean * 0.97,
        p90=mean * 1.3,
        p95=mean * 1.45,
        p98=mean * 1.6,
        max=mean * 2.1,
        cv=cv,
    )


def _abc_classes() -> dict[str, AbcClassStats]:
    return {
        "A": AbcClassStats(n_skus=900, sku_share=0.2, line_share=0.8, cube_share=0.62),
        "B": AbcClassStats(n_skus=1350, sku_share=0.3, line_share=0.15, cube_share=0.25),
        "C": AbcClassStats(n_skus=2250, sku_share=0.5, line_share=0.05, cube_share=0.13),
    }


def mock_profile() -> DemandProfile:
    peak = [0.0] * 7 + [0.04, 0.08, 0.11, 0.13, 0.12, 0.09, 0.1, 0.11, 0.1, 0.07, 0.05] + [0.0] * 6
    return DemandProfile(
        dataset_hash="3f9a1c0d2e4b5a69",
        period_start=date(2024, 11, 1),
        period_end=date(2026, 10, 31),
        operating_days=500,
        daily={
            "orders": _stats(800),
            "lines": _stats(2100),
            "units": _stats(2900),
            "cube_m3": _stats(55),
            "weight_kg": _stats(9800),
        },
        eiq=EIQ(
            lines_per_order=_stats(2.6, 0.8),
            units_per_line=_stats(1.4, 0.5),
            units_per_order=_stats(3.6, 0.9),
            cube_per_order_m3=_stats(0.068, 1.1),
            weight_per_order_kg=_stats(12.2, 1.2),
            single_line_share=0.55,
            order_class_shares={"S": 0.55, "M": 0.4, "L": 0.05},
        ),
        abc=ABC(
            thresholds=(0.8, 0.95),
            by_lines=_abc_classes(),
            by_cube_movement=_abc_classes(),
            by_stock_cube=_abc_classes(),
            pareto_lines=[min(1.0, (k / 100) ** 0.25) for k in range(1, 101)],
        ),
        stock=StockStats(
            n_snapshots=24,
            last_snapshot=date(2026, 10, 31),
            n_skus_in_stock=4400,
            avg_units=72000,
            avg_cube_m3=1450,
            cover_days=25.0,
            dead_stock_skus=310,
            dead_stock_cube_m3=60,
            growth_units_per_year=2900,
        ),
        seasonality=Seasonality(
            monthly_index=[0.9, 0.85, 0.95, 0.95, 0.95, 0.9, 0.85, 0.75, 1.0, 1.05, 1.35, 1.5],
            weekday_index=[1.2, 1.15, 1.1, 1.05, 1.0, 0.5, 0.0],
            peak_to_average=1.45,
            trend_cagr=0.05,
            trend_confidence="L",
        ),
        intraday={d: peak for d in range(5)},
        peak_hour_share=0.13,
        shipment_split=ShipmentSplit(
            parcel_share_orders=0.97,
            pallet_share_orders=0.03,
            parcel_share_lines=0.9,
            pallet_share_lines=0.1,
            mean_parcels_per_order=1.1,
        ),
        dims_coverage_lines=0.96,
        daily_series_path="canonical/daily_series.parquet",
    )


def mock_design_day() -> DesignDay:
    lines = 3700.0
    shares = (
        [0.0] * 7 + [0.04, 0.08, 0.11, 0.13, 0.12, 0.09, 0.1, 0.11, 0.1, 0.07, 0.05] + [0.0] * 6
    )
    hourly = [s * lines for s in shares]
    return DesignDay(
        percentile=95.0,
        growth_rate=0.04,
        horizon_years=5,
        reference_date=date(2025, 12, 1),
        lines=lines,
        orders=1420,
        units=5100,
        cube_m3=97,
        weight_kg=17300,
        design_weekday=0,
        hourly_lines=hourly,
        peak_hour_lines=max(hourly),
        parcels=1520,
        pallets_out=40,
        stock_units=100700,
        stock_cube_m3=2030,
        inbound=Inbound(
            mode="derived",
            units_per_day=3600,
            pallets_per_day=22,
            receipt_lines_per_day=22,
            trucks_per_day=0.85,
            peak_factor=1.45,
        ),
        assumptions=[
            Assumption(key="projection.design_percentile", value=95.0, unit="-", origin="client"),
            Assumption(key="flows.inbound_mode", value="derived", unit="-", origin="default"),
        ],
        percentile_values={"lines": 3700, "orders": 1400},
        flags=[
            Flag(
                code="F_RATIO_DRIFT",
                severity="info",
                message="orders ratio drift 1.4 %",
                value=0.014,
            )
        ],
    )


def mock_scenario() -> ScenarioDef:
    return ScenarioDef(
        id="S2",
        name="AS/RS cube",
        family="cube_asrs",
        overrides={"cube_asrs.port_rate_lines_h": 330},
        eligibility=EligibilityCfg(assume_eligible_if_missing_dims=False),
    )


def _labor() -> LaborResult:
    picking = ActivityLabor(
        activity="picking",
        role="operator",
        driver="lines",
        workload=3700,
        hours=rng(12.4, 14.8, 18.9, "h"),
        heads=rng(2.1, 2.5, 3.2, "-"),
        roster=rng(2.2, 2.7, 3.4, "-"),
        annual_hours=[rng(3100, 3650, 4600, "h") for _ in range(5)],
    )
    return LaborResult(
        activities=[picking],
        total_hours=rng(120, 140, 175, "h"),
        total_heads=rng(20.2, 23.5, 29.4, "-"),
        roster=rng(22, 25.6, 32, "-"),
        annual_hours=[rng(28000, 33000, 41000, "h") for _ in range(5)],
        core_fte=[rng(20, 24, 30, "-") for _ in range(5)],
        temp_hours=[rng(500, 900, 1600, "h") for _ in range(5)],
        shifts=[
            ShiftRow(shift=1, start_hour=6, end_hour=13, activity="picking", hours=8.1, heads=1.4)
        ],
    )


def mock_result() -> ScenarioResult:
    return ScenarioResult(
        scenario=mock_scenario(),
        eligibility=EligibilityResult(
            family="cube_asrs",
            share_lines=0.82,
            share_stock_cube=0.64,
            share_skus=0.78,
            n_skus_eligible=3510,
            n_skus_total=4500,
        ),
        storage=StorageResult(
            classes=[
                StorageClassResult(
                    storage_class="cube_bin",
                    zone="main",
                    n_skus=3510,
                    positions=rng(24100, 25300, 27400, "bins"),
                    levels=16,
                    area_m2=rng(500, 570, 650, "m2"),
                    grid_area_m2=rng(463, 528, 602, "m2"),
                ),
                StorageClassResult(
                    storage_class="pallet_rack",
                    zone="overflow",
                    n_skus=990,
                    positions=rng(1450, 1520, 1610, "pallets"),
                    levels=6,
                    area_m2=rng(560, 667, 845, "m2"),
                ),
            ],
            total_area_m2=rng(1060, 1237, 1495, "m2"),
            height_utilisation=0.91,
        ),
        equipment={"ports": rng(10, 13, 17, "-"), "robots": rng(38, 47, 64, "-")},
        bottleneck="ports",
        labor=_labor(),
        area=AreaResult(
            zones={"storage": rng(1060, 1237, 1495, "m2"), "packing": rng(100, 120, 150, "m2")},
            total_m2=rng(4100, 4600, 5300, "m2"),
            building_m2=12000,
            fit=True,
            utilisation=rng(0.34, 0.38, 0.44, "-"),
            deficit_m2=rng(0, 0, 0, "m2"),
            docks_in_required=2,
            docks_out_required=3,
            icpe_volume_m3=126000,
            icpe_regime="Enregistrement (E)",
        ),
        queue=QueueResult(
            resources=[
                QueueResource(
                    resource="ports",
                    servers=13,
                    arrival_rate_h=560,
                    service_rate_h=297.5,
                    offered_load=1.88,
                    stable=True,
                    p_wait=0.0001,
                    w_q_h=1e-7,
                    t_h=1.75,
                    p_wait_gt_t=0.0,
                )
            ]
        ),
        flags=[
            Flag(
                code="F_LOW_CONFIDENCE",
                severity="info",
                message="21 parameters with confidence L",
                value=21,
            )
        ],
        trace_path="scenarios/S2/trace.jsonl",
    )


def mock_financial() -> FinancialResult:
    return FinancialResult(
        scenario_id="S2",
        capex={
            "storage": rng(1.2e6, 1.6e6, 2.3e6, "eur"),
            "equipment": rng(2.1e6, 2.9e6, 4.2e6, "eur"),
        },
        capex_total=rng(3.6e6, 5.0e6, 7.4e6, "eur"),
        opex_by_year=[{"labor": 1.1e6, "maintenance": 1.45e5} for _ in range(5)],
        opex_year1=rng(1.2e6, 1.4e6, 1.7e6, "eur"),
        tco=rng(8.5e6, 1.06e7, 1.38e7, "eur"),
        npv_vs_baseline=rng(-1.9e6, 4.0e5, 1.8e6, "eur"),
        irr_vs_baseline=0.11,
        payback_years=4.2,
        cost_per_line=rng(0.32, 0.41, 0.55, "eur"),
        cash_flows_typ=[-5.0e6, 1.2e6, 1.25e6, 1.3e6, 1.35e6, 1.4e6],
    )


def mock_manifest() -> RunManifest:
    return RunManifest(
        run_id="2026-11-18T14-02-11_3f9a1c",
        created_at=datetime(2026, 11, 18, 14, 2, 11, tzinfo=UTC),
        engine_version="0.1.0",
        git_sha="abc1234",
        catalog_version="0.1.0",
        inputs={"basis/example_basis.yaml": "e3b0c44298fc1c14"},
        basis_hash="1a2b3c",
        scenarios_hash="4d5e6f",
        mapping_hashes={"order_lines": "7a8b9c"},
        params_snapshot={"cube_asrs.port_rate_lines_h": 330},
        seed=42,
        python="3.12.13",
        platform="darwin-arm64",
        packages={"polars": "1.0"},
        timings={"profile": 1.2, "size": 0.4},
        project_hash="9c1d2e3f4a5b6c7d",
    )


def mock_ingest_manifest() -> IngestManifest:
    sniff = SniffResult(
        encoding="cp1252",
        delimiter=";",
        header_row=1,
        decimal=",",
        date_format="%d/%m/%Y %H:%M",
        n_rows=1000,
    )
    return IngestManifest(
        tool_version="0.1.0",
        created_at=datetime(2026, 11, 18, 14, 0, tzinfo=UTC),
        datasets=[
            DatasetIngest(
                dataset="order_lines",
                files=[
                    SourceFile(
                        path="data/ventes.csv",
                        sha256="ab" * 32,
                        size_bytes=52000,
                        n_rows=1000,
                        sniff=sniff,
                    )
                ],
                mapping_hash="7a8b9c",
                rows_in=1000,
                rows_out=990,
                dropped_by_rule={"R3": 4, "R5": 6},
            )
        ],
        coverage={"dims_coverage_lines": 0.96},
        dq_score=84.0,
        anonymized=True,
    )


def mock_project() -> Project:
    return Project(
        name="pilot_client_x",
        inputs={
            "order_lines": InputSpec(
                files=[Path("data/ventes_2025.csv")], mapping=Path("mapping/order_lines.yaml")
            ),
            "sku_master": InputSpec(files=[Path("data/articles.xlsx")], sheet="Articles"),
            "receipts": None,
        },
        basis=Path("basis/client_x.yaml"),
        scenarios=Path("scenarios/client_x.yaml"),
        profile_cfg=ProfileCfg(abc_thresholds=(0.8, 0.95), dead_stock_days=180),
        options=ProjectOptions(worlds="all"),
    )


def mock_comparison() -> Comparison:
    return Comparison(
        baseline_id="S0",
        rows=[
            ComparisonRow(
                scenario_id="S2",
                name="AS/RS cube",
                family="cube_asrs",
                eligible_line_share=0.82,
                total_area_m2=rng(4100, 4600, 5300, "m2"),
                fit=True,
                equipment={"ports": rng(10, 13, 17, "-")},
                tco=rng(8.5e6, 1.06e7, 1.38e7, "eur"),
                payback_years=4.2,
                n_warnings=1,
                n_low_confidence_params=21,
            ),
            ComparisonRow(
                scenario_id="S1",
                name="AMR goods-to-person",
                family="amr_gtp",
                status="not_computed",
                status_reason="SizingInfeasibleError: no eligible SKU",
            ),
        ],
        ranking_tco=["S2"],
        ranking_payback=["S2"],
        overlaps=[("S0", "S2")],
        confidence_note="Ranking at typical values; ranges overlap for scenarios S0 and S2",
    )


def mock_sensitivity() -> Sensitivity:
    bar = TornadoBar(
        scenario_id="S2",
        param="labor_cost",
        low_input=0.8,
        high_input=1.2,
        tco_low=9.9e6,
        tco_high=1.13e7,
        delta_tco=7.0e5,
        payback_low=5.1,
        payback_high=3.6,
        fte_low=24,
        fte_high=24,
    )
    return Sensitivity(
        delta=0.2,
        base_tco={"S2": 1.06e7},
        tornado=[bar],
        break_even=[
            BreakEven(scenario_id="S2", target_payback_years=5.0, labor_cost_multiplier=0.83)
        ],
        percentile_sweep=[
            PercentileSweepRow(
                scenario_id="S2",
                percentile=95,
                design_lines=3700,
                equipment={"ports": 13},
                fte=24,
                capex=5e6,
                tco=1.06e7,
            )
        ],
        skipped=["S1 growth_rate high: SizingInfeasibleError: no eligible SKU"],
    )


def mock_run_output() -> RunOutput:
    """One finished run: S2 computed; `mock_comparison` lists a not-computed S1 as well."""
    result = mock_result()
    return RunOutput(
        run_dir=Path("runs/2026-11-18T14-02-11_3f9a1c"),
        manifest=mock_manifest(),
        results={result.scenario.id: result},
        finances={result.scenario.id: mock_financial()},
        comparison=mock_comparison(),
        sensitivity=mock_sensitivity(),
    )


def schema_examples() -> dict[type[BaseModel], BaseModel]:
    """One valid instance per contract model, keyed by its class (T0.3)."""
    basis = mock_basis()
    profile = mock_profile()
    design = mock_design_day()
    result = mock_result()
    ingest = mock_ingest_manifest()
    comparison = mock_comparison()
    sensitivity = mock_sensitivity()
    instances: list[BaseModel] = [
        mock_param(),
        rng(1, 2, 3, "m2"),
        basis,
        basis.operations,
        basis.service,
        basis.projection,
        basis.flows,
        basis.building,
        basis.finance,
        basis.baseline,
        profile,
        profile.daily["lines"],
        profile.eiq,
        profile.abc,
        profile.abc.by_lines["A"],
        profile.stock,
        profile.seasonality,
        profile.shipment_split,
        ProfileCfg(holiday_overrides=[date(2026, 12, 24)]),
        design,
        design.inbound,
        design.assumptions[0],
        result.scenario,
        result.scenario.eligibility,
        ScenarioSet(scenarios=[result.scenario], baseline="S2"),
        result,
        result.eligibility,
        result.storage,
        result.storage.classes[0],
        result.labor,
        result.labor.activities[0],
        result.labor.shifts[0],
        result.area,
        result.queue,
        result.queue.resources[0],
        result.flags[0],
        mock_financial(),
        mock_manifest(),
        ingest,
        ingest.datasets[0],
        ingest.datasets[0].files[0],
        ingest.datasets[0].files[0].sniff,
        mock_project(),
        mock_project().inputs["order_lines"] or InputSpec(files=[]),
        mock_project().options,
        comparison,
        comparison.rows[0],
        sensitivity,
        sensitivity.tornado[0],
        sensitivity.break_even[0],
        sensitivity.percentile_sweep[0],
        mock_run_output(),
        TraceNode(
            id="S2.equipment.ports",
            label="Cube ports",
            value=4,
            unit="-",
            formula="ceil(lambda_e / (port_rate * oee))",
            inputs={
                "lambda_e": "S2.throughput.lambda_e",
                "port_rate": "param:cube_asrs.port_rate_lines_h",
            },
            scope="S2",
        ),
        *mock_report_table_parts(),
    ]
    return {type(i): i for i in instances}


def mock_report_table_parts() -> list[BaseModel]:
    """F9a report model: a cell, column, row, block, table and integrity issue."""
    cell = Cell(value=1048.9, unit="m2", fmt="int", trace_id="S0.area.total", world="typ")
    label = Cell(value="label.area_total", fmt="key")
    column = TableColumn(key="S0.typ", label=label, scenario_id="S0", world="typ")
    row = TableRow(key="area.total", label=label, cells=[cell], kind="total")
    block = TableBlock(key="area", title=label, columns=[column], rows=[row])
    table = ReportTable(id="scenarios", title=label, blocks=[block], notes=[label])
    issue = IntegrityIssue(id="IC4", severity="error", message="x", location="scenarios/area")
    return [cell, column, row, block, table, issue]

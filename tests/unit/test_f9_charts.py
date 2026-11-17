"""F9a charts: ten PNGs per language with a title, a caption and the source note, labels from
i18n, one colour per scenario in every chart, and the plotted numbers are the run's."""

from __future__ import annotations

import dataclasses
import itertools
import warnings

import matplotlib.image as mpimg
import numpy as np
import pytest
from matplotlib.axes import Axes
from matplotlib.colors import to_hex, to_rgba
from matplotlib.figure import Figure
from matplotlib.lines import Line2D
from matplotlib.patches import Rectangle
from tests.unit.test_f9_tables_support import baseline_scenario_run, private_run, report_data

from whsizing.errors import ReportIntegrityError
from whsizing.report import CHART_IDS, ReportData, build_charts, chart_png, t
from whsizing.report.charts import SIZE_IN, chart_figure
from whsizing.report.i18n import Lang
from whsizing.report.style import ACTIVITY_PALETTE, SCENARIO_PALETTE, fonts, scenario_colours
from whsizing.schemas.run import RunOutput

PNG = b"\x89PNG\r\n\x1a\n"


@pytest.fixture(scope="module")
def run(tmp_path_factory: pytest.TempPathFactory) -> RunOutput:
    return private_run(tmp_path_factory, "f9a_charts")


@pytest.fixture(scope="module")
def data(run: RunOutput) -> ReportData:
    return report_data(run)


def bars(ax: Axes) -> list[Rectangle]:
    return [p for p in ax.patches if isinstance(p, Rectangle)]


def ydata(line: Line2D) -> list[float]:
    return [float(v) for v in np.asarray(line.get_ydata(), dtype=float)]


def fig_of(data: ReportData, chart_id: str) -> Figure:
    fig = chart_figure(data, chart_id)
    assert fig is not None
    return fig


def test_charts_build_every_chart_as_a_png_named_by_id_and_language(
    data: ReportData, tmp_path
) -> None:
    written = build_charts(data, tmp_path / "charts")
    assert tuple(written) == CHART_IDS and len(CHART_IDS) == 10
    for chart_id, path in written.items():
        assert path.name == f"chart_{chart_id}_en.png"
        assert path.read_bytes().startswith(PNG)
        img = mpimg.imread(path)
        height_in = fig_of(data, chart_id).get_size_inches()[1]  # the tornado grows (R7.1)
        if chart_id != "tornado":
            assert height_in == SIZE_IN[1]
        assert img.shape[:2] == (round(height_in * 150), round(SIZE_IN[0] * 150))
        assert float(np.std(img[..., :3])) > 0.05  # not a blank canvas


def test_charts_png_is_reproducible(data: ReportData) -> None:
    assert chart_png(data, "tco") == chart_png(data, "tco")


@pytest.mark.parametrize("lang", ["fr", "en"])
def test_charts_have_title_caption_and_source_note_from_i18n(run: RunOutput, lang: Lang) -> None:
    data = report_data(run, lang)
    for chart_id in CHART_IDS:
        fig = fig_of(data, chart_id)
        assert fig.get_suptitle() == t(f"chart.{chart_id}.title", lang)
        texts = [x.get_text() for x in fig.texts]
        assert t(f"chart.{chart_id}.caption", lang) in texts, chart_id
        source = next(x for x in texts if x.startswith(t("chart.source", lang, note="")[:6]))
        m = run.manifest
        assert m.engine_version in source and m.catalog_version in source and m.run_id in source
        assert not any("{{ missing" in x for x in texts)
        for ax in fig.axes:
            for label in (ax.get_xlabel(), ax.get_ylabel(), ax.get_title()):
                assert "{{ missing" not in label


def test_charts_labels_are_translated_and_numbers_use_the_language_format(run: RunOutput) -> None:
    fr, en = fig_of(report_data(run, "fr"), "tco"), fig_of(report_data(run, "en"), "tco")
    assert fr.axes[0].get_ylabel() == "Euro" and en.axes[0].get_ylabel() == "Euro"
    daily_fr, daily_en = (
        fig_of(report_data(run, "fr"), "daily"),
        fig_of(report_data(run, "en"), "daily"),
    )
    assert daily_fr.axes[0].get_ylabel() == "Lignes par jour"
    assert daily_en.axes[0].get_ylabel() == "Lines per day"
    for fig in (fr, en):
        fig.canvas.draw()
    tick_fr = [x.get_text() for x in fr.axes[0].get_yticklabels() if x.get_text().strip()]
    tick_en = [x.get_text() for x in en.axes[0].get_yticklabels() if x.get_text().strip()]
    assert any("\u202f" in x for x in tick_fr) and not any("," in x for x in tick_fr)
    assert any("," in x for x in tick_en) and not any("\u202f" in x for x in tick_en)
    legend = daily_fr.axes[0].get_legend()
    assert legend is not None
    legend_fr = [x.get_text() for x in legend.get_texts()]
    assert legend_fr[1].startswith("Percentile de dimensionnement P")


def test_charts_a_scenario_has_the_same_colour_in_every_chart(data: ReportData) -> None:
    colours = scenario_colours(data.run.results)
    assert list(colours.values()) == list(SCENARIO_PALETTE[:3])
    assert colours == scenario_colours(["S0", "S1", "S2"])  # by position in scenarios.yaml
    tco = fig_of(data, "tco").axes[0]
    by_label = {
        lab.get_text(): p.get_facecolor()
        for p, lab in zip(bars(tco), tco.get_xticklabels(), strict=True)
    }
    cash = fig_of(data, "cash").axes[0]
    lines = {
        line.get_label(): line.get_color() for line in cash.lines if line.get_label() in colours
    }
    sweep = fig_of(data, "sweep").axes[0]
    swept = {
        line.get_label(): line.get_color() for line in sweep.lines if line.get_label() in colours
    }
    tornado = {
        ax.get_title(loc="left"): [p.get_facecolor()[:3] for p in bars(ax)]
        for ax in fig_of(data, "tornado").axes
    }
    for sid, colour in colours.items():
        want = to_rgba(colour)
        assert tuple(by_label[sid]) == pytest.approx(want)
        assert to_rgba(lines[sid]) == pytest.approx(want)
        assert to_rgba(swept[sid]) == pytest.approx(want)
        assert all(c == pytest.approx(want[:3]) for c in tornado[sid])  # the low and high shade
    assert set(ACTIVITY_PALETTE).isdisjoint(
        SCENARIO_PALETTE
    )  # activities never look like scenarios


def test_charts_plot_the_numbers_of_the_run(run: RunOutput, data: ReportData) -> None:
    ids = list(run.results)
    tco = fig_of(data, "tco").axes[0]
    assert [p.get_height() for p in bars(tco)] == pytest.approx(
        [run.finances[s].tco.typ for s in ids]
    )
    stack = fig_of(data, "fte").axes[0]
    heights = np.zeros(3)
    for p in bars(stack):
        heights[round(p.get_x() + p.get_width() / 2)] += p.get_height()
    assert heights == pytest.approx([run.results[s].labor.total_heads.typ for s in ids])
    cash = fig_of(data, "cash").axes[0]
    for line in cash.lines:
        label = str(line.get_label())
        if label in run.finances:
            f = run.finances[label]
            flow = f.delta_cash_flows_typ or f.cash_flows_typ
            assert ydata(line) == pytest.approx(np.cumsum(flow))
    hourly = fig_of(data, "hourly").axes[0]
    assert [p.get_height() for p in bars(hourly)] == pytest.approx(data.design_day.hourly_lines)
    pareto = fig_of(data, "pareto").axes[0]
    assert ydata(pareto.lines[0])[1:] == pytest.approx(data.profile.abc.pareto_lines)
    daily = fig_of(data, "daily").axes[0]
    levels = sorted(ydata(line)[0] for line in daily.lines[1:])
    assert levels == pytest.approx(
        sorted([data.profile.daily["lines"].p50, data.design_day.percentile_values["lines"]])
    )


def test_charts_without_sensitivity_leave_out_tornado_and_sweep(run: RunOutput, tmp_path) -> None:
    d = report_data(run.model_copy(update={"sensitivity": None}))
    assert chart_png(d, "tornado") is None and chart_png(d, "sweep") is None
    written = build_charts(d, tmp_path)
    assert set(written) == set(CHART_IDS) - {"tornado", "sweep"}


def test_charts_use_the_spec_fonts() -> None:
    assert fonts()[0] == "DejaVu Sans"  # bundled with matplotlib; Liberation Sans if installed
    assert set(fonts()) <= {"DejaVu Sans", "Liberation Sans"}


# ------------------------------------------------------------------ fix round 1
DATA_CHARTS = ("daily", "seasonality", "pareto", "split", "hourly")


def test_charts_the_data_charts_use_no_scenario_colour(data: ReportData) -> None:
    """S0 was drawn in the demand charts' blue: a scenario colour means that scenario only."""
    scenario = {c.lower() for c in SCENARIO_PALETTE}
    for chart_id in DATA_CHARTS:
        fig = fig_of(data, chart_id)
        used = {to_hex(p.get_facecolor()) for ax in fig.axes for p in bars(ax)}
        used |= {to_hex(line.get_color()) for ax in fig.axes for line in ax.lines}
        assert used and used.isdisjoint(scenario), (chart_id, used & scenario)


def test_charts_cash_flow_with_a_baseline_scenario_plots_cumulative_deltas_only(
    run: RunOutput,
) -> None:
    """The baseline's own cumulative cost was drawn on the axis of the others' Δ, so the baseline
    looked the worst option while its Δ is zero by definition (the zero line)."""
    run2 = baseline_scenario_run(run)
    cash = fig_of(report_data(run2), "cash").axes[0]
    series = {
        str(line.get_label()): ydata(line)
        for line in cash.lines
        if line.get_label() in run2.results
    }
    assert sorted(series) == ["S1", "S2"]
    for sid, ys in series.items():
        delta = run2.finances[sid].delta_cash_flows_typ
        assert ys == pytest.approx([sum(delta[: t + 1]) for t in range(len(delta))]), sid
    assert any(ydata(line) == [0.0, 0.0] for line in cash.lines)  # the zero line


def test_charts_an_unwritable_folder_is_a_whsizing_error(data: ReportData, tmp_path) -> None:
    from whsizing.errors import WhsizingError

    blocker = tmp_path / "afile"
    blocker.write_text("x", encoding="utf-8")
    with pytest.raises(WhsizingError, match="cannot write the charts"):
        build_charts(data, blocker / "charts")


@pytest.mark.parametrize("lang", ["fr", "en"])
def test_charts_title_caption_and_source_note_fit_inside_the_picture(
    run: RunOutput, lang: Lang
) -> None:
    """The cash-flow caption was one unwrapped line wider than the PNG: its end was cut off."""
    data = report_data(run, lang)
    for chart_id in CHART_IDS:
        fig = fig_of(data, chart_id)
        renderer = fig.canvas.get_renderer()  # pyright: ignore[reportAttributeAccessIssue]
        suptitle = fig.get_suptitle()
        texts = [x for x in fig.texts if x.get_text().strip()]
        assert len(texts) >= 3 and any(x.get_text() == suptitle for x in texts), chart_id
        for x in texts:
            box = x.get_window_extent(renderer)
            assert box.x0 >= 0 and box.x1 <= fig.bbox.width, (chart_id, x.get_text(), box.x1)
            assert box.y0 >= 0 and box.y1 <= fig.bbox.height, (chart_id, x.get_text())


def only_the_baseline_computed(run: RunOutput) -> RunOutput:
    from whsizing.scenarios.compare import compare, not_computed_result

    results = dict(run.results)
    for sid in ("S1", "S2"):
        results[sid] = not_computed_result(run.results[sid].scenario, "x", 12000.0)
    finances = {"S0": run.finances["S0"]}
    return run.model_copy(
        update={
            "results": results,
            "finances": finances,
            "comparison": compare(results, finances, "S0"),
        }
    )


@pytest.mark.parametrize("lang", ["fr", "en"])
def test_charts_cash_caption_says_what_is_drawn(run: RunOutput, lang: Lang) -> None:
    """Δ against the baseline when a scenario has a Δ; the own cumulative flow otherwise (the
    baseline alone, or no baseline): the Δ caption was printed over own-flow lines."""
    delta = t("chart.cash.caption", lang)
    own = t("chart.cash.caption_own", lang)
    assert delta != own and "{{ missing" not in own
    for r, want in (
        (run, delta),  # baseline = the client's current operation: every scenario has a Δ
        (baseline_scenario_run(run), delta),
        (only_the_baseline_computed(baseline_scenario_run(run)), own),
    ):
        fig = fig_of(report_data(r, lang), "cash")
        texts = [x.get_text() for x in fig.texts]
        assert want in texts and (own if want == delta else delta) not in texts


# ------------------------------------------------------------------ R7.1: the tornado scales
def with_scenarios(data: ReportData, n: int) -> ReportData:
    """`data` as if the study had `n` scenarios S0..S<n-1>: the three example scenarios (their
    result, base TCO and seven tornado bars) repeated under new ids."""
    run, sens = data.run, data.run.sensitivity
    assert sens is not None
    ids = [f"S{i}" for i in range(n)]
    source = {sid: f"S{i % 3}" for i, sid in enumerate(ids)}
    results = {sid: run.results[source[sid]] for sid in ids}
    tornado = [
        b.model_copy(update={"scenario_id": sid})
        for sid in ids
        for b in sens.tornado
        if b.scenario_id == source[sid]
    ]
    base = {sid: sens.base_tco[source[sid]] for sid in ids}
    sens2 = sens.model_copy(update={"tornado": tornado, "base_tco": base})
    run2 = run.model_copy(update={"results": results, "sensitivity": sens2})
    return dataclasses.replace(data, run=run2)


def test_R7_1_a_tornado_whose_bars_belong_to_no_scenario_of_the_run_is_a_clear_error(
    run: RunOutput,
) -> None:
    """Hand-edited sensitivity data: the stacked tornado has no panel to draw (it was a raw
    matplotlib `ValueError: Number of rows must be a positive integer, not 0`)."""
    sens = run.sensitivity
    assert sens is not None
    stray = [b.model_copy(update={"scenario_id": "ZZ"}) for b in sens.tornado]
    d = report_data(
        run.model_copy(update={"sensitivity": sens.model_copy(update={"tornado": stray})})
    )
    with pytest.raises(ReportIntegrityError, match=r"tornado: no bar belongs to a scenario.*ZZ"):
        chart_png(d, "tornado")


def tornado_fig(data: ReportData, n: int) -> Figure:
    """The tornado of an n-scenario study, drawn; a layout warning is an error."""
    with warnings.catch_warnings():
        warnings.simplefilter("error")  # 'constrained_layout not applied' (the collapse) and any
        fig = fig_of(with_scenarios(data, n), "tornado")
        fig.canvas.draw()
    return fig


def drawn_labels(ax: Axes, axis: str) -> list:
    """The tick labels of an axis that are drawn: visible, not empty, at a tick inside the view
    (the locator also makes ticks beyond it). The figure has been drawn."""
    a = ax.xaxis if axis == "x" else ax.yaxis
    lo, hi = sorted(a.get_view_interval())
    return [
        tick.label1
        for tick in a.get_major_ticks()
        if lo <= tick.get_loc() <= hi
        and tick.label1.get_visible()
        and tick.label1.get_text().strip()
    ]


def boxes_of(fig: Figure, labels: list) -> list:
    renderer = fig.canvas.get_renderer()  # pyright: ignore[reportAttributeAccessIssue]
    return [x.get_window_extent(renderer) for x in labels]


def x_extent(ax: Axes) -> tuple[float, float]:
    box = ax.get_position()
    return round(box.x0, 6), round(box.x1, 6)


@pytest.mark.parametrize("n", [1, 2, 3, 4, 6, 8])
def test_R7_1_the_tornado_stacks_one_panel_per_scenario_on_a_shared_x_axis(
    data: ReportData, n: int
) -> None:
    fig = tornado_fig(data, n)
    panels = fig.axes
    assert [ax.get_title(loc="left") for ax in panels] == [f"S{i}" for i in range(n)]
    tops = [ax.get_position().y1 for ax in panels]
    assert tops == sorted(tops, reverse=True) and len(set(tops)) == n  # one under the other
    assert len({x_extent(ax) for ax in panels}) == 1  # and as wide as each other
    assert all(panels[0].get_shared_x_axes().joined(panels[0], ax) for ax in panels[1:])
    assert len({tuple(ax.get_xlim()) for ax in panels}) == 1  # one scale: bars are comparable
    shown = [ax for ax in panels if drawn_labels(ax, "x")]
    assert shown == [panels[-1]]  # tick labels and title of the x axis once, under the last panel
    assert [ax for ax in panels if ax.get_xlabel()] == [panels[-1]]


def test_R7_1_the_figure_grows_with_the_scenarios_and_a_bar_keeps_its_thickness(
    data: ReportData,
) -> None:
    heights, thickness = [], []
    for n in (1, 2, 3, 4, 6, 8):
        fig = tornado_fig(data, n)
        heights.append(fig.get_size_inches()[1])
        ax = fig.axes[0]
        bar = bars(ax)[0]
        y = [(0, bar.get_y()), (0, bar.get_y() + bar.get_height())]
        (_, y0), (_, y1) = ax.transData.transform(y)
        thickness.append(abs(y1 - y0) / fig.dpi)  # inches
    assert heights == sorted(heights) and len(set(heights)) == 6
    assert 1.5 < heights[0] < SIZE_IN[1]  # one scenario needs less than the fixed 3.8 in
    assert heights[-1] < 11.0  # eight still fit one A4 page (10.3 in at 7.2 in wide: scaled)
    assert min(thickness) > 0.07  # a bar is at least 5 pt thick whatever the number of scenarios
    assert max(thickness) / min(thickness) < 1.1


@pytest.mark.parametrize("lang", ["en", "fr"])
@pytest.mark.parametrize("n", [3, 4, 6, 8])
def test_R7_1_tornado_labels_do_not_touch_and_nothing_collapses_up_to_eight_scenarios(
    run: RunOutput, lang: Lang, n: int
) -> None:
    """The old figure was 7.2 x 3.8 in whatever n: its x tick labels touched at four panels
    (French: '-500 0000 500 000') and the layout collapsed, with a warning, above four."""
    fig = tornado_fig(report_data(run, lang), n)
    assert all(ax.get_position().height * fig.get_size_inches()[1] > 0.6 for ax in fig.axes)
    for ax in fig.axes:
        where = (lang, n, ax.get_title(loc="left"))
        xs = sorted(boxes_of(fig, drawn_labels(ax, "x")), key=lambda b: b.x0)
        ys = sorted(boxes_of(fig, drawn_labels(ax, "y")), key=lambda b: b.y0)
        assert all(b.x0 - a.x1 >= 4.0 for a, b in itertools.pairwise(xs)), where  # 4 px apart
        assert all(b.y0 - a.y1 >= 1.0 for a, b in itertools.pairwise(ys)), where
        for box in xs + ys:  # nothing is cut off
            assert box.x0 >= fig.bbox.x0 and box.x1 <= fig.bbox.x1, where

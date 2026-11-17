"""F9c test support (no test here): runs to build PDFs from, a locale number parser, and helpers
that read numbers back out of the rendered HTML and out of the PDF text (pypdf, tests only)."""

from __future__ import annotations

import html as htmllib
import re
from pathlib import Path

import pytest
from pypdf import PdfReader
from tests.unit.test_f9_tables_support import (
    DATASETS,
    NOW,
    ROOT,
    SMALL,
    private_run,
)

from whsizing.report.i18n import NNBSP, Lang, t
from whsizing.report.pdf import STYLES
from whsizing.scenarios import run_scenarios
from whsizing.scenarios.compare import compare, not_computed_result
from whsizing.schemas import Project, ProjectOptions
from whsizing.schemas.project import InputSpec
from whsizing.schemas.run import RunOutput
from whsizing.synth import export, generate, load_synth_profile

NUMBER = {
    "en": re.compile(r"-?\d{1,3}(?:,\d{3})+(?:\.\d+)?|-?\d+(?:\.\d+)?"),
    "fr": re.compile(r"-?\d{1,3}(?: \d{3})+(?:,\d+)?|-?\d+(?:,\d+)?"),
}
TD = re.compile(r'<td class="r[^"]*">(.*?)</td>', re.DOTALL)
RANGE_SPAN = re.compile(r'<span class="rng">(.*?)</span>', re.DOTALL)
YES_NO = {"Yes": 1.0, "Oui": 1.0, "No": 0.0, "Non": 0.0}


def own_run(factory: pytest.TempPathFactory, name: str) -> RunOutput:
    """A private copy of the small run (`private_run`): a build writes `report/` there."""
    return private_run(factory, name)


RIGHT_EDGE_PT = 595.28 - 18 / 25.4 * 72  # A4 width minus the 18 mm margin, in points
EXTRA_SCENARIOS = (  # S3.. of a study with more scenarios than the three of the example
    '  - {id: S3, name: "AMR variant B with a really long scenario name to test wrapping", '
    "family: amr_gtp}",
    '  - {id: S4, name: "Cube variant B", family: cube_asrs}',
    '  - {id: S5, name: "Manual variant C", family: manual_p2p}',
)


def many_scenarios_run(factory: pytest.TempPathFactory, n: int) -> RunOutput:
    """The small synthetic site sized with `n` scenarios (3 <= n <= 6): the three of the example
    scenarios file and `n - 3` more of the three families; baseline = the client's current one."""
    base = load_synth_profile(ROOT / "data" / "synth" / "profiles" / "ecom_mid.yaml")
    work = factory.mktemp(f"f9_{n}_scenarios")
    export(generate(base.model_copy(update=SMALL), seed=7), work, ("csv_en",))
    text = (ROOT / "scenarios" / "example_scenarios.yaml").read_text()
    extra = "\n".join(EXTRA_SCENARIOS[: n - 3])
    (work / "scenarios.yaml").write_text(text.replace("\nbaseline:", f"\n{extra}\nbaseline:"))
    project = Project(
        name=f"f9_{n}",
        out_dir=work / "runs",
        catalog=ROOT / "catalog",
        inputs={ds: InputSpec(files=[work / "csv_en" / f"{ds}.csv"]) for ds in DATASETS},
        basis=ROOT / "basis" / "example_basis.yaml",
        scenarios=work / "scenarios.yaml",
        options=ProjectOptions(sensitivity=True),
    )
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("WHSIZING_SALT", "f9-test-salt")
        return run_scenarios(project, now=NOW)


def text_starts(path: Path) -> list[tuple[int, float, str]]:
    """(page number, x in points from the left edge, text) of every text run of a PDF."""
    out: list[tuple[int, float, str]] = []
    for number, page in enumerate(PdfReader(path).pages, 1):

        def visit(text: str, cm: list[float], tm: list[float], *_: object, n: int = number) -> None:
            if text.strip():
                out.append((n, cm[0] * tm[4] + cm[2] * tm[5] + cm[4], text.strip()))

        page.extract_text(visitor_text=visit)
    return out


def text_sizes(path: Path) -> list[tuple[int, float, str]]:
    """(page number, size in points as set on the page, text) of every text run of a PDF: the font
    size scaled by the text and the page matrices (a drawing scaled down to fit, like the block
    diagrams, has its text set at the scaled size)."""
    out: list[tuple[int, float, str]] = []
    for number, page in enumerate(PdfReader(path).pages, 1):

        def visit(
            text: str,
            cm: list[float],
            tm: list[float],
            _font: object,
            size: float,
            n: int = number,
        ) -> None:
            if text.strip():
                a, b = cm[0] * tm[0] + cm[2] * tm[1], cm[1] * tm[0] + cm[3] * tm[1]
                scale = (a * a + b * b) ** 0.5
                out.append((n, scale * size, text.strip()))

        page.extract_text(visitor_text=visit)
    return out


def image_boxes(path: Path) -> list[tuple[int, int, int, float, float]]:
    """(page, width px, height px, width pt, height pt) of every image drawn on the pages of a PDF:
    the size it is set at, from the content stream (the current matrix when `Do` paints it)."""
    from pypdf.generic import ContentStream

    def times(m1: list[float], m2: list[float]) -> list[float]:
        a1, b1, c1, d1, e1, f1 = m1
        a2, b2, c2, d2, e2, f2 = m2
        return [
            a1 * a2 + b1 * c2,
            a1 * b2 + b1 * d2,
            c1 * a2 + d1 * c2,
            c1 * b2 + d1 * d2,
            e1 * a2 + f1 * c2 + e2,
            e1 * b2 + f1 * d2 + f2,
        ]

    reader = PdfReader(path)
    out: list[tuple[int, int, int, float, float]] = []
    for number, page in enumerate(reader.pages, 1):
        xobjects = page["/Resources"].get("/XObject", {})  # type: ignore[union-attr]
        matrix, stack = [1.0, 0.0, 0.0, 1.0, 0.0, 0.0], []
        for operands, op in ContentStream(page.get_contents(), reader).operations:
            if op == b"q":
                stack.append(matrix)
            elif op == b"Q":
                matrix = stack.pop()
            elif op == b"cm":
                matrix = times([float(x) for x in operands], matrix)
            elif op == b"Do":
                xobject = xobjects[operands[0]].get_object()
                if xobject.get("/Subtype") == "/Image":
                    size = (int(xobject["/Width"]), int(xobject["/Height"]))
                    out.append((number, *size, abs(matrix[0]), abs(matrix[3])))
    return out


DIAGRAM_MIN_PT = 6.5  # zone labels of a block diagram: 7.1 pt as set (4.4 pt with 5.5 px type)
APPENDIX_C_MIN_PT = 5.7  # the loosest typesetting sets Appendix C at 5.8 pt or more
LEGEND = re.compile(r"^\D+\d[\d,.]*m²$")  # "Circulation137m²": a zone label, spaces removed


def unspaced(text: str) -> str:
    """`text` without any whitespace. WeasyPrint sets the text of an SVG one letter at a time and
    draws no space: a label's word gaps are positions, which an extractor turns back into spaces
    from the font's space width. A font subset that holds no space glyph (the DejaVu Sans of the
    diagrams when the pages are set in Liberation Sans, both installed) gives pypdf no reliable
    width: it can read "Circulation137m²" from a PDF that looks as it does with one font."""
    return "".join(text.split())


def diagram_label_sizes(path: Path, lang: Lang, scenarios: list[str]) -> list[float]:
    """Sizes (pt) of the zone labels ("Name 137 m²") on the pages that hold a block diagram; every
    scenario's diagram title must be found, and its labels (3 zones at least). Text is compared
    without its spaces (`unspaced`)."""
    pages = [unspaced(p) for p in pdf_pages(path)]
    on = set()
    for sid in scenarios:
        title = t("diagram.title", lang, scenario=sid)
        found = {n for n, text in enumerate(pages, 1) if unspaced(title) in text}
        assert found, f"no block diagram titled {title!r}"
        on |= found
    sizes = [s for n, s, x in text_sizes(path) if n in on and LEGEND.match(unspaced(x))]
    assert len(sizes) >= 3 * len(scenarios), len(sizes)
    return sizes


def appendix_c_sizes(path: Path, lang: Lang) -> list[tuple[int, float, str]]:
    """Every text run from the page of the Appendix C heading to the end of the PDF."""
    title = t("pdf.section.appendix_methodology", lang)
    pages = [squash(p) for p in pdf_pages(path)]
    start = max(n for n, text in enumerate(pages, 1) if title in text)  # after the TOC entry
    runs = [r for r in text_sizes(path) if r[0] >= start]
    assert any(".finance.tco" in x for _, _, x in runs) and len(runs) > 200
    return runs


def layout_overflow(html: str) -> list[tuple[int, float, str]]:
    """(page, excess in CSS px, text) of every text box, image and table of the WeasyPrint layout
    of `html` whose right edge is beyond the margin of its page: `text_starts` sees where a run
    starts, this sees where it ends (a run that starts inside the margin and runs on, clipped)."""
    from weasyprint import CSS, HTML
    from weasyprint.formatting_structure import boxes

    doc = HTML(string=html, base_url=str(STYLES.parent)).render(
        stylesheets=[CSS(filename=str(STYLES))]
    )
    out: list[tuple[int, float, str]] = []
    for number, page in enumerate(doc.pages, 1):
        box = page._page_box  # pyright: ignore[reportPrivateUsage]
        right = box.content_box_x() + box.width
        for b in box.descendants():
            if isinstance(b, boxes.TextBox | boxes.ReplacedBox | boxes.TableBox):
                excess = b.position_x + b.width - right  # pyright: ignore[reportAttributeAccessIssue]
                if excess > 0.5:
                    out.append((number, excess, getattr(b, "text", type(b).__name__)[:30]))
    return out


def without_scenario(run: RunOutput, sid: str, reason: str) -> RunOutput:
    """`run` with scenario `sid` not computed (F8 edge case): zero parts, a reason, no finance."""
    building = run.results[sid].area.building_m2
    results = {**run.results, sid: not_computed_result(run.results[sid].scenario, reason, building)}
    finances = {k: v for k, v in run.finances.items() if k != sid}
    comparison = compare(results, finances, run.comparison.baseline_id)
    return run.model_copy(
        update={"results": results, "finances": finances, "comparison": comparison}
    )


def without_baseline(run: RunOutput) -> RunOutput:
    """`run` with no baseline at all: no NPV, IRR, payback or delta cash flow."""
    own = {
        "npv_vs_baseline": None,
        "irr_vs_baseline": None,
        "payback_years": None,
        "delta_cash_flows_typ": [],
    }
    finances = {k: v.model_copy(update=own) for k, v in run.finances.items()}
    comparison = compare(run.results, finances, None)
    return run.model_copy(update={"finances": finances, "comparison": comparison})


def plain(text: str) -> str:
    """Text with the narrow and no-break spaces as plain spaces (pypdf returns plain spaces)."""
    return text.replace(NNBSP, " ").replace(" ", " ")


def squash(text: str) -> str:
    """All whitespace runs as one space (a title wrapped by the layout is one line of text)."""
    return " ".join(plain(text).split())


def parse_number(text: str, lang: Lang) -> float:
    """A printed number back to a float: FR U+202F (or space) thousands and decimal comma, EN
    comma thousands and decimal point; a trailing % is dropped (the value stays in percent)."""
    body = plain(text).strip().removesuffix("%").strip()
    token = NUMBER[lang].match(body)
    if token is None:
        raise ValueError(f"no number in {text!r}")
    thousands, decimal = (" ", ",") if lang == "fr" else (",", ".")
    return float(token.group().replace(thousands, "").replace(decimal, "."))


def html_numbers(html: str, lang: Lang) -> list[tuple[float, tuple[float, float] | None]]:
    """(typical value, (low, high) or None) of every right-aligned table cell of the report HTML,
    parsed back through the locale parser; yes / no cells give 1.0 / 0.0, text cells are not
    included."""
    out: list[tuple[float, tuple[float, float] | None]] = []
    for raw in TD.findall(html):
        rng = RANGE_SPAN.search(raw)
        main = htmllib.unescape(RANGE_SPAN.sub("", raw)).strip()
        if not main:
            continue
        value = YES_NO[main] if main in YES_NO else parse_number(main, lang)
        bounds = None
        if rng:
            low, _, high = htmllib.unescape(rng.group(1)).partition(" – ")
            bounds = (parse_number(low, lang), parse_number(high, lang))
        out.append((value, bounds))
    return out


def pdf_pages(path: Path) -> list[str]:
    return [plain(p.extract_text()) for p in PdfReader(path).pages]


def trace_entry(text: str, trace_id: str) -> str:
    """The Appendix C text of one trace id: from its line to the next trace id of its scenario."""
    sid = trace_id.split(".")[0]
    start = text.rindex(f"\n{trace_id}\n")  # the last one: the first sentence of a cover or TOC
    nxt = re.compile(rf"\n{sid}\.[A-Za-z0-9_.]+\n").search(text, start + len(trace_id) + 2)
    return text[start : nxt.start() if nxt else len(text)]


def printed_value_and_inputs(entry: str, lang: Lang) -> tuple[float, list[float]]:
    """The value printed for a trace id and the numbers printed in brackets after its inputs.
    The label under the id must hold no digit (true for the area, heads and TCO rows)."""
    body = entry.strip("\n").split("\n", 1)[1]  # after the id line
    value = parse_number(NUMBER[lang].search(body).group(), lang)  # pyright: ignore[reportOptionalMemberAccess]
    inputs = [parse_number(m, lang) for m in re.findall(r"\((-?[\d ,.]*\d)\)", body) if m.strip()]
    return value, inputs

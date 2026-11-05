"""Build the report: analysis outputs -> Markdown + HTML + PDF, with a page-count gate."""

from __future__ import annotations

import json
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from slm.analysis import figures
from slm.analysis.pipeline import run_analysis
from slm.analysis.schema import normalize_qa_table
from slm.analysis.sensitivity import run_sensitivity, sensitivity_markdown

from .inputs import load_inputs, simulate_report_inputs
from .markup import RenderContext, blocks_to_html, parse_blocks, render_template
from .numbers import collect_numbers
from .pdf import (
    available_backends,
    blocks_to_pdf_matplotlib,
    check_page_count,
    html_to_pdf_chrome,
    pdf_page_count,
)

TEMPLATE = Path(__file__).resolve().parents[3] / "docs" / "report" / "report_template.md"
FIGURE_NAMES = ("loss_curves", "stored_rate_by_cell", "learning_curves", "eval_before_after")


@dataclass
class BuildResult:
    markdown: Path
    html: Path
    pdf: Path
    numbers: Path
    backend: str
    pages: int
    banner: bool
    simulated: bool


def run_simulated_analysis(work: Path, seed: int = 0) -> tuple[Path, Path]:
    """Simulate every input and run the analysis + sensitivity into `work`."""
    inputs_dir, results = work / "inputs", work / "results"
    paths = simulate_report_inputs(inputs_dir, seed)
    run_analysis(paths["probe"], results, qa_path=paths["qa"], mixed_sensitivity=False, real=False)
    probe = pd.read_csv(paths["probe"])
    qa = normalize_qa_table(pd.read_csv(paths["qa"]))
    realized = pd.read_csv(paths["realized"])
    table, extras = run_sensitivity(probe, qa, realized)
    (results / "tables" / "sensitivity.md").write_text(
        sensitivity_markdown(table, extras), encoding="utf-8"
    )
    table.to_csv(results / "tables" / "sensitivity.csv", index=False, float_format="%.6g")
    return inputs_dir, results


def build(
    out_dir: Path,
    *,
    simulate: bool = True,
    real: bool = False,
    results_dir: Path | None = None,
    inputs_dir: Path | None = None,
    backend: str = "auto",
    min_pages: int = 5,
    max_pages: int = 7,
    seed: int = 0,
    template: Path = TEMPLATE,
) -> BuildResult:
    """Build report.md/html/pdf in `out_dir`. Raises PageCountError outside the page range."""
    if simulate and real:
        raise ValueError("--simulate and --real are mutually exclusive: simulated data cannot "
                         "be presented as real results")
    banner = not real
    out_dir.mkdir(parents=True, exist_ok=True)
    work_ctx = tempfile.TemporaryDirectory() if simulate else None
    try:
        if simulate:
            inputs_dir, results_dir = run_simulated_analysis(Path(work_ctx.name), seed)
        if results_dir is None or inputs_dir is None:
            raise ValueError("real builds need --results-dir and --inputs-dir")
        _facts, loss, samples = load_inputs(inputs_dir)
        fig_dir = results_dir / "figures"
        figures.plot_loss_curves(loss, fig_dir, banner)
        numbers = collect_numbers(results_dir, inputs_dir)

        (out_dir / "figures").mkdir(exist_ok=True)
        for name in FIGURE_NAMES:
            src = fig_dir / f"{name}.png"
            if not src.exists():
                raise FileNotFoundError(f"missing figure {src}")
            shutil.copyfile(src, out_dir / "figures" / f"{name}.png")

        ctx = RenderContext(numbers, results_dir / "tables", samples, banner)
        md = render_template(template.read_text(encoding="utf-8"), ctx)
        md_path = out_dir / "report.md"
        md_path.write_text(md, encoding="utf-8")
        num_path = out_dir / "numbers.json"
        num_path.write_text(json.dumps(numbers, indent=1, default=str, sort_keys=True),
                            encoding="utf-8")

        blocks = parse_blocks(md)
        html_path = out_dir / "report.html"
        html_path.write_text(blocks_to_html(blocks, banner, "Report"), encoding="utf-8")
        pdf_path = out_dir / "report.pdf"
        chosen = backend if backend != "auto" else available_backends()[0]
        if chosen == "chrome":
            try:
                html_to_pdf_chrome(html_path, pdf_path)
            except Exception:
                if backend == "chrome":
                    raise
                chosen = "matplotlib"
        if chosen == "matplotlib":
            blocks_to_pdf_matplotlib(blocks, pdf_path, banner, out_dir)
        pages = pdf_page_count(pdf_path)
        check_page_count(pdf_path, min_pages, max_pages)
        return BuildResult(md_path, html_path, pdf_path, num_path, chosen, pages, banner, simulate)
    finally:
        if work_ctx is not None:
            work_ctx.cleanup()

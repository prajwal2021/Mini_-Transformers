"""Template rendering (macros), the no-hand-typed-numbers lint, and a small Markdown subset."""

from __future__ import annotations

import html
import math
import re
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

MACRO = re.compile(r"\{\{\s*([A-Za-z0-9_.:]+?)(?::([^{}]*))?\s*\}\}")
# tokens that contain digits but are names, not results
ALLOWED_TOKENS = re.compile(
    r"\b(?:H[1-4]|E[0-2]|base_[02]shot|[02]-shot|GEE|log3|SFT|P0\d+|Q\d)\b"
)
BANNER_TEXT = "SIMULATED DATA - NOT RESULTS"

TABLES: dict[str, tuple[str, list[str], str]] = {
    # name: (csv file, columns, caption)
    "family": ("analysis_family.csv",
               ["hypothesis", "label", "estimate", "ci_low", "ci_high", "p_holm", "status"],
               "Hypotheses H1-H4. H1-H3 are confirmatory (Holm adjusted); H4 is secondary "
               "(effect and CI only). Estimates are log-odds (H1, H2) or risk differences "
               "(H3, H4)."),
    "per_condition": ("analysis_per_condition.csv",
                      ["div_bin", "n_facts", "acc_base", "acc_sft", "gain", "mcnemar_p"],
                      "E2 held-out facts by diversity condition: base (2-shot) and SFT "
                      "fact-level accuracy, gain and the exact McNemar test."),
    "eval_accuracy": ("eval_accuracy.csv",
                      ["eval_set", "model", "n_facts", "accuracy", "ci_low", "ci_high"],
                      "Exact-match accuracy by evaluation set and model (fact bootstrap CI)."),
    "sensitivity": ("sensitivity.csv",
                    ["analysis", "hypothesis", "estimate", "ci_low", "ci_high"],
                    "Pre-registered sensitivity analyses (none is part of the Holm family)."),
}
FIGURES: dict[str, str] = {
    "loss_curves": "Training and validation loss for each seed.",
    "stored_rate_by_cell": "Stored rate by exposure bin, diversity condition and probe frame "
                           "at the final checkpoint (95% fact-bootstrap CI).",
    "learning_curves": "Stored rate across checkpoints by exposure, diversity and probe frame.",
    "eval_before_after": "E0/E1/E2 accuracy for the base models and the SFT model.",
}


class TemplateError(ValueError):
    """A macro refers to something that does not exist, or the template contains a bare number."""


def lint_template(template: str) -> list[str]:
    """Return the numbers typed directly into the template (macros and names are exempt)."""
    text = re.sub(r"<!--.*?-->", "", template, flags=re.S)
    text = MACRO.sub("", text)
    text = ALLOWED_TOKENS.sub("", text)
    bad = []
    for lineno, line in enumerate(text.splitlines(), 1):
        for m in re.finditer(r"\d+(?:[.,]\d+)*", line):
            bad.append(f"line {lineno}: bare number {m.group(0)!r} in {line.strip()[:60]!r}")
    return bad


def fmt_number(value, spec: str | None) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        return "yes" if value else "no"
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return "n/a"
    if spec:
        return format(value, spec)
    if isinstance(value, int):
        return f"{value:,}"
    return format(value, ".3g")


def _cell(v, spec: str = ".3g") -> str:
    if isinstance(v, str):
        return v.replace("|", "/")
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "n/a"
    if isinstance(v, bool):
        return "yes" if v else "no"
    if isinstance(v, int):
        return str(v)
    return format(v, spec)


def md_table(frame: pd.DataFrame, columns: list[str]) -> str:
    cols = [c for c in columns if c in frame.columns]
    lines = ["| " + " | ".join(cols) + " |", "|" + "|".join("---" for _ in cols) + "|"]
    for _, row in frame.iterrows():
        lines.append("| " + " | ".join(_cell(row[c]) for c in cols) + " |")
    return "\n".join(lines)


@dataclass
class RenderContext:
    numbers: dict
    tables_dir: Path
    samples: pd.DataFrame
    banner: bool
    figure_counter: int = 0
    table_counter: int = 0


def _render_macro(m: re.Match, ctx: RenderContext) -> str:
    key, spec = m.group(1), m.group(2)
    if key == "banner_notice":
        if not ctx.banner:
            return ""
        return (f"> **{BANNER_TEXT}.** Every number, table and figure in this document was "
                "generated from simulated inputs to test the report pipeline. None of it is a "
                "result of the study.")
    if key.startswith("table:") or (key == "table" and spec):
        name = spec if key == "table" else key.split(":", 1)[1]
        return _render_table(name, ctx)
    if key.startswith("figure:") or (key == "figure" and spec):
        name = spec if key == "figure" else key.split(":", 1)[1]
        if name not in FIGURES:
            raise TemplateError(f"unknown figure {name!r}")
        ctx.figure_counter += 1
        return f"![Figure {ctx.figure_counter}. {FIGURES[name]}](figures/{name}.png)"
    if key not in ctx.numbers:
        raise TemplateError(f"macro {{{{{key}}}}} has no source in the result files")
    return fmt_number(ctx.numbers[key]["value"], spec)


def _render_table(name: str, ctx: RenderContext) -> str:
    ctx.table_counter += 1
    if name == "samples":
        s = ctx.samples.copy()
        for col in ("prompt", "completion"):
            s[col] = s[col].astype(str).str.replace("\n", " ").str.slice(0, 70)
        body = md_table(s, ["category", "prompt", "completion", "note"])
        caption = "Generated-text samples: successes and failures."
    elif name in TABLES:
        fname, cols, caption = TABLES[name]
        frame = pd.read_csv(ctx.tables_dir / fname)
        if name == "sensitivity":
            frame = frame[frame["hypothesis"] != "-"]
            frame["analysis"] = frame["analysis"].str.slice(0, 48)
        body = md_table(frame, cols)
    else:
        raise TemplateError(f"unknown table {name!r}")
    return f"**Table {ctx.table_counter}.** {caption}\n\n{body}"


def render_template(template: str, ctx: RenderContext) -> str:
    """Substitute macros. Raises TemplateError on bare numbers or unknown macros."""
    bad = lint_template(template)
    if bad:
        raise TemplateError("numbers typed in the template:\n  " + "\n  ".join(bad))
    return MACRO.sub(lambda m: _render_macro(m, ctx), template)


# --- Markdown subset -> blocks -> HTML -------------------------------------------------------

@dataclass
class Block:
    kind: str  # heading | para | list | table | image | quote
    text: str = ""
    level: int = 0
    items: list | None = None
    rows: list | None = None


def parse_blocks(md: str) -> list[Block]:
    lines = md.splitlines()
    blocks: list[Block] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1
            continue
        if line.startswith("#"):
            level = len(line) - len(line.lstrip("#"))
            blocks.append(Block("heading", line.lstrip("# ").strip(), level))
            i += 1
        elif line.startswith("!["):
            m = re.match(r"!\[(.*)\]\((.*)\)", line.strip())
            blocks.append(Block("image", m.group(1), items=[m.group(2)]))
            i += 1
        elif line.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].startswith("|"):
                cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                if not all(set(c) <= set("-: ") for c in cells):
                    rows.append(cells)
                i += 1
            blocks.append(Block("table", rows=rows))
        elif line.lstrip().startswith("- "):
            items = []
            while i < len(lines) and lines[i].lstrip().startswith("- "):
                items.append(lines[i].lstrip()[2:].strip())
                i += 1
            blocks.append(Block("list", items=items))
        elif line.startswith(">"):
            buf = []
            while i < len(lines) and lines[i].startswith(">"):
                buf.append(lines[i].lstrip("> ").strip())
                i += 1
            blocks.append(Block("quote", " ".join(buf)))
        else:
            buf = []
            while i < len(lines) and lines[i].strip() and not re.match(r"(#|!\[|\||>|\s*- )",
                                                                    lines[i]):
                buf.append(lines[i].strip())
                i += 1
            blocks.append(Block("para", " ".join(buf)))
    return blocks


def inline_html(text: str) -> str:
    t = html.escape(text, quote=False)
    t = re.sub(r"`([^`]+)`", r"<code>\1</code>", t)
    t = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", t)
    t = re.sub(r"(?<![\w*])\*([^*]+)\*(?![\w*])", r"<em>\1</em>", t)
    return t


CSS = """
@page { size: Letter; margin: 0.65in 0.7in 0.7in 0.7in; }
html { font-family: Georgia, 'Times New Roman', serif; font-size: 9.6pt; color: #111;
  line-height: 1.32; }
body { margin: 0; }
h1 { font-size: 17pt; margin: 0 0 4pt 0; }
h2 { font-size: 11.5pt; margin: 11pt 0 3pt 0; border-bottom: 0.6pt solid #999; }
p { margin: 3pt 0 5pt 0; text-align: justify; }
ul { margin: 2pt 0 5pt 0; padding-left: 16pt; }
table { border-collapse: collapse; width: 100%; font-size: 7.6pt; margin: 3pt 0 7pt 0;
  font-family: Arial, Helvetica, sans-serif; page-break-inside: avoid; }
th, td { border-bottom: 0.4pt solid #bbb; padding: 1.5pt 3pt; text-align: left;
  vertical-align: top; }
th { border-bottom: 0.8pt solid #333; }
figure { margin: 4pt 0 7pt 0; text-align: center; page-break-inside: avoid; }
figure img { max-width: 100%; max-height: 3.0in; }
figcaption { font-size: 8pt; color: #333; font-family: Arial, Helvetica, sans-serif; }
blockquote { margin: 4pt 0 6pt 0; padding: 3pt 7pt; background: #fde8ec;
  border-left: 3pt solid #b00020; font-family: Arial, Helvetica, sans-serif; font-size: 8.5pt; }
code { font-family: Consolas, monospace; font-size: 8.4pt; }
table.page, table.page > thead > tr > th, table.page > tbody > tr > td, table.page > thead,
table.page > tbody { display: block; border: 0; padding: 0; margin: 0; width: 100%;
  font-size: inherit; font-family: inherit; page-break-inside: auto; }
table.page { display: table; }
table.page > thead { display: table-header-group; }
table.page > tbody { display: table-row-group; }
table.page > thead > tr, table.page > tbody > tr { display: table-row; }
table.page > thead > tr > th, table.page > tbody > tr > td { display: table-cell; }
th.sim-banner { background: #b00020; color: #fff; text-align: center;
  font: bold 8.5pt Arial, Helvetica, sans-serif; padding: 2pt 0; border: 0; }
.page td > table { font-size: 7.6pt; }
.sim-mark { position: fixed; top: 38%; left: 0; right: 0; text-align: center;
  font: bold 92pt Arial, Helvetica, sans-serif; color: rgba(176, 0, 32, 0.07);
  transform: rotate(-24deg); z-index: 0; }
"""


def blocks_to_html(blocks: list[Block], banner: bool, title: str = "Report") -> str:
    out = [f"<!doctype html><html><head><meta charset='utf-8'><title>{html.escape(title)}</title>"
           f"<style>{CSS}</style></head><body>"]
    if banner:
        # the banner sits in a table header, which prints at the top of every page in normal
        # flow (a fixed element would overlap the text)
        out.append("<div class='sim-mark'>SIMULATED</div><table class='page'><thead><tr>"
                   f"<th class='sim-banner'>{BANNER_TEXT}</th></tr></thead><tbody><tr><td>")
    for b in blocks:
        if b.kind == "heading":
            out.append(f"<h{b.level}>{inline_html(b.text)}</h{b.level}>")
        elif b.kind == "para":
            out.append(f"<p>{inline_html(b.text)}</p>")
        elif b.kind == "quote":
            out.append(f"<blockquote>{inline_html(b.text)}</blockquote>")
        elif b.kind == "list":
            out.append("<ul>" + "".join(f"<li>{inline_html(i)}</li>" for i in b.items) + "</ul>")
        elif b.kind == "image":
            out.append(f"<figure><img src='{html.escape(b.items[0])}'>"
                       f"<figcaption>{inline_html(b.text)}</figcaption></figure>")
        elif b.kind == "table":
            head, *body = b.rows
            rows = "".join(
                "<tr>" + "".join(f"<td>{inline_html(c)}</td>" for c in r) + "</tr>" for r in body
            )
            heads = "".join(f"<th>{inline_html(c)}</th>" for c in head)
            out.append(f"<table><thead><tr>{heads}</tr></thead><tbody>{rows}</tbody></table>")
    if banner:
        out.append("</td></tr></tbody></table>")
    out.append("</body></html>")
    return "\n".join(out)

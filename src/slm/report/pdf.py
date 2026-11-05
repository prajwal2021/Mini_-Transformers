"""PDF backends and the page-count check.

Backend order (first available wins; `--backend` forces one):
  1. chrome   headless Chrome or Edge printing the HTML (banner = fixed element, repeats per page)
  2. matplotlib   built-in text/figure layout, always available (plain, but never fails)
pandoc/LaTeX and weasyprint are not used: neither is installed here, and untested code paths
would not be trustworthy.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
import textwrap
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.image as mpimg  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.backends.backend_pdf import PdfPages  # noqa: E402

from slm.analysis import banner as _banner  # noqa: E402

from .markup import Block  # noqa: E402

CHROME_CANDIDATES = (
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    "/usr/bin/google-chrome",
    "/usr/bin/chromium",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
)


class PageCountError(RuntimeError):
    """The PDF is outside the required page range."""


def find_chrome() -> str | None:
    for name in ("chrome", "google-chrome", "chromium", "msedge"):
        found = shutil.which(name)
        if found:
            return found
    for path in CHROME_CANDIDATES:
        if Path(path).exists():
            return path
    return None


def available_backends() -> list[str]:
    return (["chrome"] if find_chrome() else []) + ["matplotlib"]


def pdf_page_count(path: Path) -> int:
    """Number of pages, from the page tree's /Count (fallback: count /Type /Page objects)."""
    data = Path(path).read_bytes()
    counts = [int(m) for m in re.findall(rb"/Type\s*/Pages\b[^>]*?/Count\s+(\d+)", data)]
    counts += [int(m) for m in re.findall(rb"/Count\s+(\d+)[^>]*?/Type\s*/Pages\b", data)]
    if counts:
        return max(counts)
    return len(re.findall(rb"/Type\s*/Page\b(?!s)", data))


def check_page_count(path: Path, lo: int = 5, hi: int = 7) -> int:
    n = pdf_page_count(path)
    if not lo <= n <= hi:
        raise PageCountError(f"{path.name} has {n} pages; the report must have {lo}-{hi}")
    return n


def html_to_pdf_chrome(html_path: Path, pdf_path: Path, timeout: int = 180) -> None:
    exe = find_chrome()
    if exe is None:
        raise RuntimeError("no Chrome/Edge found")
    with tempfile.TemporaryDirectory() as profile:
        cmd = [
            exe, "--headless=new", "--disable-gpu", "--no-sandbox", "--no-pdf-header-footer",
            "--allow-file-access-from-files", f"--user-data-dir={profile}",
            f"--print-to-pdf={pdf_path.resolve()}", html_path.resolve().as_uri(),
        ]
        subprocess.run(cmd, check=True, capture_output=True, timeout=timeout)
    if not pdf_path.exists() or pdf_path.stat().st_size < 1000:
        raise RuntimeError("Chrome produced no PDF")


# --- matplotlib fallback ----------------------------------------------------------------------

PAGE_W, PAGE_H = 8.5, 11.0
MARGIN = 0.7


def _new_page(banner: bool):
    fig = plt.figure(figsize=(PAGE_W, PAGE_H))
    if banner:
        fig.text(0.5, 0.995, _banner.text(), ha="center", va="top", fontsize=9, color="white",
                 fontweight="bold", bbox={"facecolor": "#B00020", "edgecolor": "none", "pad": 3})
        fig.text(0.5, 0.5, _banner.label(), ha="center", va="center", rotation=28, fontsize=80,
                 color="#B00020", alpha=0.07, fontweight="bold")
    return fig


def render_pages(blocks: list[Block], banner: bool, base_dir: Path) -> list:
    """Lay the blocks out on Letter pages; returns matplotlib figures (not yet saved)."""
    pages = []
    fig = _new_page(banner)
    y = 1.0 - 0.07  # fraction of page height

    def line_h(pt: float) -> float:
        return pt * 1.5 / 72 / PAGE_H

    def need(h: float):
        nonlocal fig, y
        if y - h < MARGIN / PAGE_H:
            pages.append(fig)
            fig = _new_page(banner)
            y = 1.0 - 0.07

    def put(text: str, size: float, weight="normal", family="DejaVu Serif", indent=0.0):
        nonlocal y
        fig.text((MARGIN + indent) / PAGE_W, y, text, fontsize=size, fontweight=weight,
                 family=family, va="top", ha="left")
        y -= line_h(size)

    for b in blocks:
        if b.kind == "heading":
            size = {1: 15, 2: 11}.get(b.level, 10)
            need(line_h(size) * 2.5)
            y -= line_h(size) * 0.4
            put(b.text, size, "bold", "DejaVu Sans")
        elif b.kind in ("para", "quote"):
            wrapped = textwrap.wrap(b.text.replace("**", ""), 96)
            for ln in wrapped:
                need(line_h(9.4))
                put(ln, 9.4, family="DejaVu Serif")
            y -= line_h(9.4) * 0.4
        elif b.kind == "list":
            for it in b.items:
                for k, ln in enumerate(textwrap.wrap(it.replace("**", ""), 94)):
                    need(line_h(9.4))
                    put(("- " if k == 0 else "  ") + ln, 9.4)
            y -= line_h(9.4) * 0.4
        elif b.kind == "table":
            widths = [max(len(r[i]) if i < len(r) else 0 for r in b.rows) for i in
                      range(len(b.rows[0]))]
            widths = [min(w, 34) for w in widths]
            scale = min(1.0, 118 / max(sum(widths) + 2 * len(widths), 1))
            size = 6.4 * scale if scale < 1 else 6.4
            for r in b.rows:
                cells = [(c[: widths[i]]).ljust(widths[i]) for i, c in enumerate(r)]
                need(line_h(size))
                put("  ".join(cells), size, family="DejaVu Sans Mono")
            y -= line_h(8) * 0.5
        elif b.kind == "image":
            img = mpimg.imread(base_dir / b.items[0])
            h_in = 3.1
            w_in = min(PAGE_W - 2 * MARGIN, h_in * img.shape[1] / img.shape[0])
            h_in = w_in * img.shape[0] / img.shape[1]
            need(h_in / PAGE_H + line_h(8) * 2)
            ax = fig.add_axes([(PAGE_W - w_in) / 2 / PAGE_W, (y * PAGE_H - h_in) / PAGE_H,
                               w_in / PAGE_W, h_in / PAGE_H])
            ax.imshow(img)
            ax.axis("off")
            y -= h_in / PAGE_H + line_h(8) * 0.3
            for ln in textwrap.wrap(b.text, 120):
                put(ln, 7.4, family="DejaVu Sans")
            y -= line_h(8) * 0.4
    pages.append(fig)
    return pages


def blocks_to_pdf_matplotlib(blocks: list[Block], pdf_path: Path, banner: bool,
                             base_dir: Path) -> None:
    pages = render_pages(blocks, banner, base_dir)
    with PdfPages(pdf_path, metadata={"Creator": "", "Producer": "", "CreationDate": None}) as pp:
        for fig in pages:
            pp.savefig(fig)
            plt.close(fig)

"""Deterministic figures: stored rate by cell, learning curves by checkpoint."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from .schema import DIV_BINS, FREQ_BINS, REGIMES  # noqa: E402

COLORS = {"templated": "#0072B2", "paraphrased": "#D55E00"}  # Okabe-Ito blue / vermillion
INK = "#222222"
MUTED = "#6b6b6b"
GRID = "#e4e4e4"
# no timestamps / versions in the files -> byte-stable output for identical inputs
_PNG_META = {"Software": None}
_PDF_META = {"Creator": "", "Producer": "", "CreationDate": None}
FIG_STORED = "stored_rate_by_cell"
FIG_CURVES = "learning_curves"


def _style(ax) -> None:
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(MUTED)
    ax.tick_params(colors=MUTED, labelcolor=INK)


def _save(fig, out_dir: Path, name: str) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for ext, meta in (("png", _PNG_META), ("pdf", _PDF_META)):
        path = out_dir / f"{name}.{ext}"
        fig.savefig(path, dpi=150, bbox_inches="tight", metadata=meta)
        paths.append(path)
    plt.close(fig)
    return paths


def plot_stored_by_cell(cells: pd.DataFrame, out_dir: Path, checkpoint: int) -> list[Path]:
    fig, axes = plt.subplots(1, len(REGIMES), figsize=(8, 3.6), sharey=True)
    x = np.arange(len(FREQ_BINS))
    for ax, rg in zip(axes, REGIMES):
        for k, db in enumerate(DIV_BINS):
            sub = cells[(cells["regime"] == rg) & (cells["div_bin"] == db)].set_index("freq_bin")
            sub = sub.loc[list(FREQ_BINS)]
            xs = x + (k - 0.5) * 0.12
            ax.errorbar(
                xs,
                sub["stored_rate"],
                yerr=[sub["stored_rate"] - sub["ci_low"], sub["ci_high"] - sub["stored_rate"]],
                color=COLORS[db],
                marker="o",
                markersize=7,
                linewidth=1.5,
                capsize=3,
                label=db,
            )
        ax.set_xticks(x, FREQ_BINS)
        ax.set_xlabel("exposure bin")
        ax.set_title(f"{rg} probes", color=INK, fontsize=10)
        ax.set_ylim(0, 1)
        _style(ax)
    axes[0].set_ylabel("stored rate")
    axes[0].legend(frameon=False, title="diversity", loc="upper left")
    fig.suptitle(
        f"Stored rate by exposure x diversity (checkpoint {checkpoint}, 95% fact-bootstrap CI)",
        fontsize=10,
        color=INK,
    )
    fig.tight_layout()
    return _save(fig, out_dir, FIG_STORED)


def plot_learning_curves(curves: pd.DataFrame, out_dir: Path) -> list[Path]:
    fig, axes = plt.subplots(
        len(REGIMES), len(FREQ_BINS), figsize=(9, 5.4), sharex=True, sharey=True
    )
    for r, rg in enumerate(REGIMES):
        for c, fb in enumerate(FREQ_BINS):
            ax = axes[r, c]
            for db in DIV_BINS:
                mask = (curves["regime"] == rg) & (curves["freq_bin"] == fb)
                sub = curves[mask & (curves["div_bin"] == db)].sort_values("checkpoint")
                ax.fill_between(
                    sub["checkpoint"], sub["ci_low"], sub["ci_high"], color=COLORS[db], alpha=0.15,
                    linewidth=0,
                )
                ax.plot(sub["checkpoint"], sub["stored_rate"], color=COLORS[db], linewidth=2,
                        label=db)
            ax.set_xscale("log")
            ax.set_ylim(0, 1)
            ax.set_title(f"{fb} exposure, {rg}", fontsize=9, color=INK)
            _style(ax)
            if r == len(REGIMES) - 1:
                ax.set_xlabel("checkpoint (step)")
            if c == 0:
                ax.set_ylabel("stored rate")
    axes[0, 0].legend(frameon=False, title="diversity", loc="upper left", fontsize=8)
    fig.suptitle(
        "Learning curves (mean over seeds and prompts; band = 95% fact-bootstrap CI)",
        fontsize=10,
        color=INK,
    )
    fig.tight_layout()
    return _save(fig, out_dir, FIG_CURVES)

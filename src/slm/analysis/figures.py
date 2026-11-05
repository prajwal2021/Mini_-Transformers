"""Deterministic figures: stored rate by cell, learning curves by checkpoint."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from . import banner as _banner  # noqa: E402
from .schema import DIV_BINS, FRAMES, FREQ_BINS  # noqa: E402

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


BANNER_TEXT = "SIMULATED DATA - NOT RESULTS"  # default label; see slm.analysis.banner


def add_banner(fig) -> None:
    """Visible simulated-data marks: a red strip at the top and a faint diagonal watermark."""
    fig.text(0.5, 0.995, _banner.text(), ha="center", va="top", fontsize=9, color="white",
             fontweight="bold", bbox={"facecolor": "#B00020", "edgecolor": "none", "pad": 3})
    fig.text(0.5, 0.5, _banner.label(), ha="center", va="center", rotation=28, fontsize=64,
             color="#B00020", alpha=0.10, fontweight="bold", zorder=0)


def has_banner(fig) -> bool:
    return any(_banner.text() in t.get_text() for t in fig.texts)


def _save(fig, out_dir: Path, name: str, banner: bool = True) -> list[Path]:
    if banner:
        add_banner(fig)
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for ext, meta in (("png", _PNG_META), ("pdf", _PDF_META)):
        path = out_dir / f"{name}.{ext}"
        fig.savefig(path, dpi=150, bbox_inches="tight", metadata=meta)
        paths.append(path)
    plt.close(fig)
    return paths


def plot_stored_by_cell(
    cells: pd.DataFrame, out_dir: Path, checkpoint: int, banner: bool = True
) -> list[Path]:
    fig, axes = plt.subplots(1, len(FRAMES), figsize=(8, 3.6), sharey=True)
    x = np.arange(len(FREQ_BINS))
    for ax, rg in zip(axes, FRAMES):
        for k, db in enumerate(DIV_BINS):
            mask = (cells["probe_frame"] == rg) & (cells["div_bin"] == db)
            sub = cells[mask].set_index("freq_bin").loc[list(FREQ_BINS)]
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
        ax.set_title(f"{rg}-frame probes", color=INK, fontsize=10)
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
    return _save(fig, out_dir, FIG_STORED, banner)


def plot_learning_curves(curves: pd.DataFrame, out_dir: Path, banner: bool = True) -> list[Path]:
    fig, axes = plt.subplots(
        len(FRAMES), len(FREQ_BINS), figsize=(9, 5.4), sharex=True, sharey=True
    )
    for r, rg in enumerate(FRAMES):
        for c, fb in enumerate(FREQ_BINS):
            ax = axes[r, c]
            for db in DIV_BINS:
                mask = (curves["probe_frame"] == rg) & (curves["freq_bin"] == fb)
                sub = curves[mask & (curves["div_bin"] == db)].sort_values("checkpoint")
                ax.fill_between(
                    sub["checkpoint"], sub["ci_low"], sub["ci_high"], color=COLORS[db], alpha=0.15,
                    linewidth=0,
                )
                ax.plot(sub["checkpoint"], sub["stored_rate"], color=COLORS[db], linewidth=2,
                        label=db)
            ax.set_xscale("log")
            ax.set_ylim(0, 1)
            ax.set_title(f"{fb} exposure, {rg} frame", fontsize=9, color=INK)
            _style(ax)
            if r == len(FRAMES) - 1:
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
    return _save(fig, out_dir, FIG_CURVES, banner)


FIG_LOSS = "loss_curves"
FIG_EVAL = "eval_before_after"
MODEL_COLORS = {"base_0shot": "#999999", "base_2shot": "#0072B2", "sft": "#D55E00"}


def plot_loss_curves(loss: pd.DataFrame, out_dir: Path, banner: bool = True) -> list[Path]:
    """Train and validation loss against step, one line per seed (loss_curves.csv)."""
    fig, axes = plt.subplots(1, 2, figsize=(8, 3.2), sharey=True)
    for ax, split in zip(axes, ("train", "val")):
        sub = loss[loss["split"] == split]
        for seed, g in sub.groupby("seed"):
            g = g.sort_values("step")
            ax.plot(g["step"], g["loss"], linewidth=1.6, label=f"seed {seed}")
        ax.set_xscale("log")
        ax.set_xlabel("step")
        ax.set_title(f"{split} loss", fontsize=10, color=INK)
        _style(ax)
    axes[0].set_ylabel("cross-entropy (nats)")
    axes[1].legend(frameon=False, fontsize=8)
    fig.tight_layout()
    return _save(fig, out_dir, FIG_LOSS, banner)


def plot_eval_bars(acc: pd.DataFrame, out_dir: Path, banner: bool = True) -> list[Path]:
    """E0/E1/E2 accuracy for base (0-shot, 2-shot) and SFT with fact-bootstrap CIs."""
    sets = ["E0", "E1", "E2"]
    models = [m for m in MODEL_COLORS if m in set(acc["model"])]
    fig, ax = plt.subplots(figsize=(6.5, 3.2))
    width = 0.8 / max(len(models), 1)
    for k, m in enumerate(models):
        sub = acc[acc["model"] == m].set_index("eval_set").reindex(sets)
        xs = np.arange(len(sets)) + (k - (len(models) - 1) / 2) * width
        ax.bar(xs, sub["accuracy"], width=width * 0.9, color=MODEL_COLORS[m], label=m)
        ax.errorbar(xs, sub["accuracy"],
                    yerr=[sub["accuracy"] - sub["ci_low"], sub["ci_high"] - sub["accuracy"]],
                    fmt="none", ecolor=INK, capsize=3, linewidth=1)
    ax.set_xticks(np.arange(len(sets)), sets)
    ax.set_ylim(0, 1)
    ax.set_ylabel("exact-match accuracy")
    ax.legend(frameon=False, fontsize=8, ncol=3, loc="upper left")
    _style(ax)
    fig.tight_layout()
    return _save(fig, out_dir, FIG_EVAL, banner)

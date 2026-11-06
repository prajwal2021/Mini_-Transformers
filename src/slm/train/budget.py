# ruff: noqa: E501
"""Training-budget rule E* by VALIDATION probes (R03; DESIGN 5 picks checkpoints by val probes).

Rows of the sweep are ``(config, epoch)`` pairs with the validation loss and the validation-probe
stored rate (probe level, mean of ``stored`` over the val-split probes) at that checkpoint. Test
probes never enter. Rule, with tolerance ``tol = 0.01``:

1. a config's score is the best stored rate over its checkpoints;
2. the best score over configs is ``best``; the near-ties are the configs with score >= best - tol;
3. among the near-ties the winner has the LOWEST validation loss over its checkpoints (first row wins
   a further tie);
4. ``E*`` = the earliest checkpoint of the winner whose stored rate is >= its own best - tol.

The val-loss-optimal epoch of the winner (its argmin of validation loss) is returned next to E* so
that the difference is visible (on a small corpus validation loss bottoms out early, while fact
storage keeps improving).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

SCHEDULE = (1, 2, 3, 5, 8, 12, 16, 20, 25, 30, 40, 50, 60)
TOL = 0.01
MAX_EPOCHS = 60


def schedule_upto(max_epochs: int, schedule: Sequence[int] = SCHEDULE) -> list[int]:
    return sorted({e for e in schedule if 1 <= e <= max_epochs} | {max_epochs})


def select_budget(rows: Sequence[Mapping], tol: float = TOL) -> dict:
    """Winner config and ``E*`` from rows with keys ``config, epoch, val_loss, stored_rate``."""
    by_cfg: dict[str, list[Mapping]] = {}
    for r in rows:
        by_cfg.setdefault(r["config"], []).append(r)
    if not by_cfg:
        raise ValueError("no sweep rows")
    for cfg_rows in by_cfg.values():
        cfg_rows.sort(key=lambda r: r["epoch"])
    score = {c: max(r["stored_rate"] for r in rs) for c, rs in by_cfg.items()}
    best = max(score.values())
    near = [c for c in by_cfg if score[c] >= best - tol]  # insertion order = grid order
    min_loss = {c: min(r["val_loss"] for r in by_cfg[c]) for c in near}
    winner = min(near, key=lambda c: min_loss[c])
    rs = by_cfg[winner]
    e_star = next(r["epoch"] for r in rs if r["stored_rate"] >= score[winner] - tol)
    loss_row = min(rs, key=lambda r: (r["val_loss"], r["epoch"]))
    peak_row = max(rs, key=lambda r: (r["stored_rate"], -r["epoch"]))
    return {
        "config": winner, "e_star": int(e_star), "best_rate": float(score[winner]),
        "rate_at_e_star": float(next(r["stored_rate"] for r in rs if r["epoch"] == e_star)),
        "val_loss_at_e_star": float(next(r["val_loss"] for r in rs if r["epoch"] == e_star)),
        "val_loss_optimal_epoch": int(loss_row["epoch"]), "min_val_loss": float(loss_row["val_loss"]),
        "rate_at_val_loss_optimal_epoch": float(loss_row["stored_rate"]),
        "peak_rate_epoch": int(peak_row["epoch"]),
        "near_ties": near, "tolerance": tol, "best_over_configs": float(best),
        "config_scores": {c: float(v) for c, v in score.items()},
    }


def final_schedule(e_star: int, schedule: Sequence[int] = SCHEDULE, cap: int = MAX_EPOCHS) -> tuple[int, list[int]]:
    """Epochs of the final runs and their checkpoints: train to 2E* (capped), save E*, 2E* and the schedule."""
    total = min(2 * e_star, cap)
    return total, sorted({e for e in schedule if e <= total} | {e_star, total})


def decision_markdown(rows: Sequence[Mapping], sel: Mapping, init_rates: Mapping[str, float],
                      null_rates: Mapping[str, float], label: str = "REAL") -> str:
    """The decision table: every config x checkpoint, with the chosen config, E* and val-loss epoch."""
    cfgs = list(dict.fromkeys(r["config"] for r in rows))
    epochs = sorted({r["epoch"] for r in rows})
    cell = {(r["config"], r["epoch"]): r for r in rows}
    banner = "**MOCK RUN: toy corpus. NOTHING HERE IS A RESULT.**\n\n" if label == "MOCK" else ""
    out = [f"# Sweep decision (validation probes)\n\n{banner}"
           f"Rule: config score = best val-probe stored rate over the schedule; near-ties within {sel['tolerance']} "
           "go to the lower validation loss; **E\\*** = earliest checkpoint within the tolerance of the chosen config's best "
           "rate. Validation probes only (no test probe is scored); chance reference = the untrained model (`init`).\n",
           f"- chosen config: `{sel['config']}`; **E\\* = {sel['e_star']}** (stored rate {sel['rate_at_e_star']:.3f}; "
           f"config best {sel['best_rate']:.3f} at epoch {sel['peak_rate_epoch']})",
           f"- validation-loss-optimal epoch of the same config: **{sel['val_loss_optimal_epoch']}** "
           f"(val loss {sel['min_val_loss']:.4f}, stored rate there {sel['rate_at_val_loss_optimal_epoch']:.3f}); "
           f"val loss at E\\*: {sel['val_loss_at_e_star']:.4f}",
           f"- near-ties considered ({len(sel['near_ties'])}): {', '.join(f'`{c}`' for c in sel['near_ties'])}",
           "- `init` (untrained, per config): stored rate " + ", ".join(f"{v:.3f}" for v in dict.fromkeys(init_rates.values())) +
           "; null_stored_rate " + ", ".join(f"{v:.3f}" for v in dict.fromkeys(null_rates.values()))]
    chance = max([*init_rates.values(), *null_rates.values()] or [0.0])
    if sel["best_rate"] <= chance + sel["tolerance"]:
        out.append(f"- **WARNING: the chosen config's best stored rate ({sel['best_rate']:.3f}) is not above chance ({chance:.3f} = the larger of "
                   "`init` and `null_stored_rate`) by more than the tolerance: no storage is detected, so E\\* only picks the noisiest "
                   "early checkpoint and must not be used for a real run.**")
    out += ["",
           "Cells are `stored rate / val loss`; `*` marks the config's best stored rate, `E` marks E* of the chosen config.", "",
           "| config | " + " | ".join(str(e) for e in epochs) + " |", "|---|" + "---|" * len(epochs)]
    for c in cfgs:
        best = max(r["stored_rate"] for r in rows if r["config"] == c)
        cells = []
        for e in epochs:
            r = cell.get((c, e))
            if r is None:
                cells.append("")
                continue
            mark = ("*" if r["stored_rate"] == best else "") + ("E" if (c == sel["config"] and e == sel["e_star"]) else "")
            cells.append(f"{r['stored_rate']:.3f} / {r['val_loss']:.2f}{mark}")
        out.append(f"| {'**' + c + '**' if c == sel['config'] else c} | " + " | ".join(cells) + " |")
    return "\n".join(out) + "\n"

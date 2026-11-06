# ruff: noqa: E501
"""Training-budget rule E* by VALIDATION probes (R03, rule v2 in R04; DESIGN 5 picks checkpoints by val probes).

Rows of the sweep are ``(config, epoch)`` pairs with the validation loss and the validation-probe
stored rate (probe level, mean of ``stored`` over the val-split probes) at that checkpoint, plus its
standard error ``se`` (fact-clustered: two probes of a fact are not independent; a row without ``se``
falls back to the binomial SE from ``n_probes``). Test probes never enter. Rule v2:

1. per config, the stored rate is smoothed with a 3-checkpoint moving average (centred, shortened at
   the two ends); the SE of a smoothed value is the mean of the SEs in its window (the checkpoints are
   correlated, so this is the conservative end);
2. a config's score is its best smoothed rate; the best score over configs is ``best``; the near-ties
   are the configs whose score is within 1 SE (that of the best config) of ``best``; among them the
   winner has the LOWEST validation loss over its checkpoints (first in grid order on an exact tie);
3. ``E*`` = the earliest checkpoint of the winner whose smoothed rate is within 1 SE of the winner's
   best smoothed rate;
4. CHANCE GUARD: if the winner's best smoothed rate is not above the ``init`` (untrained) stored rate
   by more than 2 SE, no storage is detectable on validation: ``E*`` = the epoch of minimum validation
   loss of the winner and the result carries ``no_val_storage = True``.

The val-loss-optimal epoch of the winner is always returned next to E*.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence

SCHEDULE = (1, 2, 3, 5, 8, 12, 16, 20, 25, 30, 40, 50, 60)
MAX_EPOCHS = 60
SMOOTH = 3          # moving-average window, in checkpoints
Z_TIE = 1.0         # near-ties and E*: within this many SE
Z_GUARD = 2.0       # chance guard: best smoothed rate must exceed init by more than this many SE
SWEEP_SEED = 100    # the sweep seed; NOT one of the final seeds (0, 1, 2)


def schedule_upto(max_epochs: int, schedule: Sequence[int] = SCHEDULE) -> list[int]:
    return sorted({e for e in schedule if 1 <= e <= max_epochs} | {max_epochs})


def binomial_se(p: float, n: int) -> float:
    return math.sqrt(max(p * (1 - p), 0.0) / n) if n > 0 else float("nan")


def clustered_se(values_by_cluster: Sequence[float]) -> float:
    """SE of the mean of per-cluster means (one value per fact); NaN with fewer than two clusters."""
    g = len(values_by_cluster)
    if g < 2:
        return float("nan")
    m = sum(values_by_cluster) / g
    return math.sqrt(sum((v - m) ** 2 for v in values_by_cluster) / (g - 1) / g)


def _se(r: Mapping) -> float:
    if r.get("se") is not None and not (isinstance(r["se"], float) and math.isnan(r["se"])):
        return float(r["se"])
    if r.get("n_probes"):
        return binomial_se(float(r["stored_rate"]), int(r["n_probes"]))
    raise ValueError("a sweep row needs 'se' or 'n_probes' for the standard error")


def smooth(rs: Sequence[Mapping], window: int = SMOOTH) -> list[tuple[float, float]]:
    """(smoothed rate, SE) per row of one config, rows sorted by epoch; centred, shortened at the ends."""
    half = window // 2
    out = []
    for i in range(len(rs)):
        w = rs[max(0, i - half): i + half + 1]
        out.append((sum(x["stored_rate"] for x in w) / len(w), sum(_se(x) for x in w) / len(w)))
    return out


def select_budget(rows: Sequence[Mapping], init_rates: Mapping[str, float] | None = None) -> dict:
    """Winner config and ``E*`` from rows with keys ``config, epoch, val_loss, stored_rate, se|n_probes``.

    ``init_rates`` maps config to the stored rate of the untrained model (for the chance guard); without
    it the guard compares against 0.
    """
    by_cfg: dict[str, list[Mapping]] = {}
    for r in rows:
        by_cfg.setdefault(r["config"], []).append(r)
    if not by_cfg:
        raise ValueError("no sweep rows")
    sm: dict[str, list[tuple[float, float]]] = {}
    for c, rs in by_cfg.items():
        rs.sort(key=lambda r: r["epoch"])
        sm[c] = smooth(rs)
    top = {c: max(range(len(v)), key=lambda i: (v[i][0], -i)) for c, v in sm.items()}  # earliest argmax
    score = {c: sm[c][top[c]][0] for c in by_cfg}
    best_c = max(by_cfg, key=lambda c: (score[c], 0))  # first in grid order on an exact tie (max keeps the first)
    best = score[best_c]
    se_best = sm[best_c][top[best_c]][1]
    near = [c for c in by_cfg if score[c] >= best - Z_TIE * se_best]  # insertion order = grid order
    min_loss = {c: min(r["val_loss"] for r in by_cfg[c]) for c in near}
    winner = min(near, key=lambda c: min_loss[c])
    rs, s = by_cfg[winner], sm[winner]
    w_best, w_se = s[top[winner]]
    init = float((init_rates or {}).get(winner, 0.0))
    guard = (w_best - init) <= Z_GUARD * w_se
    loss_i = min(range(len(rs)), key=lambda i: (rs[i]["val_loss"], rs[i]["epoch"]))
    if guard:
        e_i = loss_i
    else:
        e_i = next(i for i in range(len(rs)) if s[i][0] >= w_best - Z_TIE * w_se)
    peak_i = top[winner]
    return {
        "config": winner, "e_star": int(rs[e_i]["epoch"]), "no_val_storage": bool(guard),
        "e_star_rule": "min validation loss (chance guard)" if guard else "earliest smoothed rate within 1 SE of the best",
        "best_rate": float(w_best), "best_se": float(w_se), "best_raw_rate": float(max(r["stored_rate"] for r in rs)),
        "init_rate": init, "guard_threshold": float(init + Z_GUARD * w_se),
        "rate_at_e_star": float(rs[e_i]["stored_rate"]), "smoothed_at_e_star": float(s[e_i][0]),
        "val_loss_at_e_star": float(rs[e_i]["val_loss"]),
        "val_loss_optimal_epoch": int(rs[loss_i]["epoch"]), "min_val_loss": float(rs[loss_i]["val_loss"]),
        "rate_at_val_loss_optimal_epoch": float(rs[loss_i]["stored_rate"]),
        "peak_rate_epoch": int(rs[peak_i]["epoch"]),
        "near_ties": near, "z_tie": Z_TIE, "z_guard": Z_GUARD, "smooth_window": SMOOTH, "best_over_configs": float(best),
        "config_scores": {c: float(v) for c, v in score.items()},
        "smoothed": {c: [[int(by_cfg[c][i]["epoch"]), float(v[0]), float(v[1])] for i, v in enumerate(sm[c])] for c in by_cfg},
    }


def decision_markdown(rows: Sequence[Mapping], sel: Mapping, init_rates: Mapping[str, float],
                      null_rates: Mapping[str, float], label: str = "REAL") -> str:
    """The decision table: every config x checkpoint, with the chosen config, E*, the guard and val-loss epoch."""
    cfgs = list(dict.fromkeys(r["config"] for r in rows))
    epochs = sorted({r["epoch"] for r in rows})
    cell = {(r["config"], r["epoch"]): r for r in rows}
    banner = "**MOCK RUN: toy corpus. NOTHING HERE IS A RESULT.**\n\n" if label == "MOCK" else ""
    out = [f"# Sweep decision (validation probes)\n\n{banner}"
           "Rule v2: stored rate smoothed over 3 checkpoints; config score = best smoothed rate; near-ties (within 1 SE) go to the "
           "lower validation loss; **E\\*** = earliest checkpoint whose smoothed rate is within 1 SE of the chosen config's best. "
           "Chance guard: if that best is not above `init` by more than 2 SE, **E\\*** = the epoch of minimum validation loss and the "
           "result is flagged `no_val_storage`. Validation probes only (no test probe is scored).\n",
           f"- chosen config: `{sel['config']}`; **E\\* = {sel['e_star']}** ({sel['e_star_rule']}; raw stored rate {sel['rate_at_e_star']:.3f}, "
           f"smoothed {sel['smoothed_at_e_star']:.3f})",
           f"- config best smoothed rate {sel['best_rate']:.3f} (SE {sel['best_se']:.3f}, raw best {sel['best_raw_rate']:.3f}) at epoch "
           f"{sel['peak_rate_epoch']}; `init` {sel['init_rate']:.3f}; guard threshold (init + 2 SE) {sel['guard_threshold']:.3f}",
           f"- `no_val_storage`: **{str(sel['no_val_storage']).lower()}**",
           f"- validation-loss-optimal epoch of the same config: **{sel['val_loss_optimal_epoch']}** "
           f"(val loss {sel['min_val_loss']:.4f}, stored rate there {sel['rate_at_val_loss_optimal_epoch']:.3f}); "
           f"val loss at E\\*: {sel['val_loss_at_e_star']:.4f}",
           f"- near-ties considered ({len(sel['near_ties'])}): {', '.join(f'`{c}`' for c in sel['near_ties'])}",
           "- `init` (untrained, per config): stored rate " + ", ".join(f"{v:.3f}" for v in dict.fromkeys(init_rates.values())) +
           "; null_stored_rate " + ", ".join(f"{v:.3f}" for v in dict.fromkeys(null_rates.values()))]
    if sel["no_val_storage"]:
        out.append(f"- **WARNING: no storage is detectable on validation (best smoothed rate {sel['best_rate']:.3f} is not above `init` "
                   f"{sel['init_rate']:.3f} by more than 2 SE = {2 * sel['best_se']:.3f}). The chance guard set E\\* to the epoch of minimum "
                   "validation loss; the sweep cannot tune lr/dropout/batch size by storage and must not be read as a result.**")
    out += ["",
           "Cells are `raw stored rate / val loss`; `*` marks the config's best SMOOTHED checkpoint, `E` marks E* of the chosen config.", "",
           "| config | " + " | ".join(str(e) for e in epochs) + " |", "|---|" + "---|" * len(epochs)]
    for c in cfgs:
        sm = sel["smoothed"].get(c, [])
        best_e = max(sm, key=lambda x: (x[1], -x[0]))[0] if sm else None
        cells = []
        for e in epochs:
            r = cell.get((c, e))
            if r is None:
                cells.append("")
                continue
            mark = ("*" if e == best_e else "") + ("E" if (c == sel["config"] and e == sel["e_star"]) else "")
            cells.append(f"{r['stored_rate']:.3f} / {r['val_loss']:.2f}{mark}")
        out.append(f"| {'**' + c + '**' if c == sel['config'] else c} | " + " | ".join(cells) + " |")
    return "\n".join(out) + "\n"


def schedule_hash(epochs: int, checkpoints: Sequence[int], warmup_frac: float, min_warmup_steps: int, min_lr_ratio: float) -> str:
    """sha256 of the LR/checkpoint schedule shared by the sweep and the final seeds (recorded by the freeze)."""
    import hashlib
    import json

    blob = json.dumps({"epochs": int(epochs), "checkpoints": [int(e) for e in checkpoints], "warmup_frac": warmup_frac,
                       "min_warmup_steps": int(min_warmup_steps), "min_lr_ratio": min_lr_ratio, "decay": "cosine"}, sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()

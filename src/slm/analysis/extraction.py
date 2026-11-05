"""Extraction tests for H3 and H4 (DESIGN section 8, Part B), as DESIGN specifies them.

DESIGN: "2x2 tables (stored x QA-correct) per diversity condition; Fisher exact tests; McNemar
for base vs SFT on the same items", evidence "E1/E2 before vs after SFT"; hypotheses use E2.

The unit of analysis is the FACT. Facts are the independent units (the same fact is probed under
several seeds and question templates, so item-level Fisher/McNemar would be anticonservative).
Per fact (E2 only):

    stored    = stored on >= 2 of 3 test probes within a seed (the producer's `stored_pretrain`),
                and so in a majority of seeds
    correct_m = correct on >= 2 of the 3 E2 phrasings within a seed, and in a majority of
                seeds, for the SFT model and for the base comparator (same items)

(PREREG v3 section 4: "majority" = more than half at both levels; `any` / `all` rules are the
sensitivity analyses, see aggregation.py.)

H3a  McNemar (exact binomial on discordant facts), base vs SFT       -> gain = P_sft - P_base
H3b  Fisher exact on the 2x2 stored x correct_sft                     -> P(c|stored) - P(c|not)
H3   intersection-union: supported only if both a and b are, p = max(p_a, p_b)
H4   difference in per-fact gain (sft - base) between paraphrased and templated facts, by a
     permutation test stratified by freq_bin (DESIGN names no between-condition test); the
     per-condition McNemar tests and 2x2 tables DESIGN asks for are reported alongside.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy import stats

from .aggregation import PRIMARY_RULE, apply_rule
from .schema import DIV_BINS, FREQ_BINS, normalize_qa_table, validate_qa_table

COMPARATOR = "base_2shot"  # fixed 2-shot base, same prompt format as SFT (PREREG v3)
N_PERM = 5000
N_BOOT = 1000
SEED = 20261106


@dataclass
class ExtractionResult:
    family: pd.DataFrame  # H3 and H4 rows
    components: pd.DataFrame  # H3a, H3b, H4 tests with effect sizes
    tables_2x2: pd.DataFrame  # stored x correct (SFT) counts per diversity condition
    per_condition: pd.DataFrame  # McNemar base vs SFT within each diversity condition
    n_facts: int
    warnings: list[str]


def fact_level(
    qa: pd.DataFrame,
    eval_set: str = "E2",
    comparator: str = COMPARATOR,
    rule: str = PRIMARY_RULE,
    stored: pd.DataFrame | None = None,
):
    """One row per fact: stored, correct_sft, correct_base (0/1) + cell labels.

    `rule` is applied twice: to the items within a seed, then to the seeds within a fact.
    `stored` (fact_id, seed, stored_pretrain) replaces the table's own `stored_pretrain`
    column, e.g. when the probe-level rule is varied (sensitivity analysis).
    """
    sub = qa[(qa["eval_set"] == eval_set) & qa["model"].isin([comparator, "sft"])]
    fs = sub.drop_duplicates(["fact_id", "seed"])[["fact_id", "seed", "stored_pretrain"]]
    if stored is not None:
        fs = stored[stored["fact_id"].isin(fs["fact_id"])]
    stored_fact = apply_rule(fs.groupby("fact_id")["stored_pretrain"].mean(), rule)
    share_items = sub.groupby(["fact_id", "seed", "model"])["exact_match"].mean()
    seed_correct = apply_rule(share_items, rule)
    fact_correct = apply_rule(seed_correct.groupby(["fact_id", "model"]).mean(), rule)
    wide = fact_correct.unstack("model")
    out = pd.DataFrame({"stored": stored_fact})
    out["correct_sft"] = wide["sft"]
    out["correct_base"] = wide[comparator]
    cells = sub.groupby("fact_id")[["freq_bin", "div_bin"]].first()
    return out.join(cells).dropna().reset_index()


def mcnemar_exact(base: np.ndarray, sft: np.ndarray) -> tuple[float, int, int]:
    """Exact McNemar: returns (two-sided p, base-only correct, sft-only correct)."""
    b = int(((base == 1) & (sft == 0)).sum())
    c = int(((base == 0) & (sft == 1)).sum())
    if b + c == 0:
        return 1.0, b, c
    return float(stats.binomtest(c, b + c, 0.5).pvalue), b, c


def fisher_stored(stored: np.ndarray, correct: np.ndarray) -> tuple[float, float, int]:
    """Fisher exact on stored x correct. Returns (two-sided p, odds ratio, n_degenerate flag)."""
    a = int(((stored == 1) & (correct == 1)).sum())
    b = int(((stored == 1) & (correct == 0)).sum())
    c = int(((stored == 0) & (correct == 1)).sum())
    d = int(((stored == 0) & (correct == 0)).sum())
    if a + b == 0 or c + d == 0:
        return 1.0, float("nan"), 1
    odds, p = stats.fisher_exact([[a, b], [c, d]], alternative="two-sided")
    return float(p), float(odds), 0


def _rd_stored(stored: np.ndarray, correct: np.ndarray) -> float:
    s, n = stored == 1, stored == 0
    if s.sum() == 0 or n.sum() == 0:
        return float("nan")
    return float(correct[s].mean() - correct[n].mean())


def _perm_p(d: np.ndarray, para: np.ndarray, strata: np.ndarray, rng, n_perm: int) -> float:
    """Two-sided permutation p for the difference in mean gain, permuting div within strata."""
    n_para = int(para.sum())
    n_tmpl = len(d) - n_para
    if n_para == 0 or n_tmpl == 0:
        return 1.0
    total = float(d.sum())
    obs = d[para == 1].mean() - d[para == 0].mean()
    sum_para = np.zeros(n_perm)
    for s in np.unique(strata):
        idx = np.where(strata == s)[0]
        lab = para[idx]
        order = np.argsort(rng.random((n_perm, len(idx))), axis=1)
        sum_para += (lab[order] * d[idx][None, :]).sum(axis=1)
    stat = sum_para / n_para - (total - sum_para) / n_tmpl
    return float((1 + (np.abs(stat) >= abs(obs) - 1e-12).sum()) / (1 + n_perm))


def _boot_ci(facts: pd.DataFrame, rng, n_boot: int) -> dict[str, tuple[float, float]]:
    """Stratified (freq x div cell) fact bootstrap percentile CIs for the three effect sizes."""
    groups = [g.index.to_numpy() for _, g in facts.groupby(["freq_bin", "div_bin"])]
    idx = np.concatenate([rng.choice(g, (n_boot, len(g)), replace=True) for g in groups], axis=1)
    st = facts["stored"].to_numpy()[idx]
    cs = facts["correct_sft"].to_numpy()[idx]
    cb = facts["correct_base"].to_numpy()[idx]
    para = (facts["div_bin"] == "paraphrased").to_numpy()[idx]
    d = (cs - cb).astype(float)
    gain = d.mean(axis=1)
    n_s = (st == 1).sum(axis=1)
    n_n = (st == 0).sum(axis=1)
    with np.errstate(invalid="ignore", divide="ignore"):
        rd = (cs * st).sum(axis=1) / n_s - (cs * (1 - st)).sum(axis=1) / n_n
        diff = (d * para).sum(axis=1) / para.sum(axis=1) - (d * ~para).sum(axis=1) / (~para).sum(
            axis=1
        )
    rd[(n_s == 0) | (n_n == 0)] = np.nan
    out = {}
    for name, v in (("gain", gain), ("rd_stored", rd), ("gain_diff", diff)):
        lo, hi = np.nanpercentile(v, [2.5, 97.5])
        out[name] = (float(lo), float(hi))
    return out


def run_extraction(
    qa: pd.DataFrame,
    n_perm: int = N_PERM,
    n_boot: int = N_BOOT,
    seed: int = SEED,
    ci: bool = True,
    comparator: str = COMPARATOR,
    validate: bool = True,
    rule: str = PRIMARY_RULE,
    stored: pd.DataFrame | None = None,
) -> ExtractionResult:
    """Run H3a, H3b, H4 (and the per-diversity tables) on a QA table."""
    qa = normalize_qa_table(qa)
    notes = validate_qa_table(qa) if validate else []
    facts = fact_level(qa, comparator=comparator, rule=rule, stored=stored)
    rng = np.random.default_rng(seed)
    base, sft = facts["correct_base"].to_numpy(), facts["correct_sft"].to_numpy()
    stored = facts["stored"].to_numpy()
    para = (facts["div_bin"] == "paraphrased").to_numpy().astype(int)
    d = (sft - base).astype(float)

    p_a, b_only, c_only = mcnemar_exact(base, sft)
    gain = float(d.mean())
    p_b, odds, degenerate = fisher_stored(stored, sft)
    rd_b = _rd_stored(stored, sft)
    if degenerate:
        notes.append("H3b degenerate: all facts have the same stored status (non-informative)")
    strata = facts["freq_bin"].map({b: i for i, b in enumerate(FREQ_BINS)}).to_numpy()
    p4 = _perm_p(d, para, strata, rng, n_perm)
    gain_para = float(d[para == 1].mean()) if para.sum() else float("nan")
    gain_tmpl = float(d[para == 0].mean()) if (1 - para).sum() else float("nan")
    diff = gain_para - gain_tmpl

    cis = _boot_ci(facts, rng, n_boot) if ci else {}
    nan2 = (float("nan"), float("nan"))
    components = pd.DataFrame(
        [
            {"component": "H3a", "test": "McNemar exact, base vs SFT (E2)", "scale": "risk diff",
             "estimate": gain, "ci_low": cis.get("gain", nan2)[0],
             "ci_high": cis.get("gain", nan2)[1], "p_raw": p_a, "direction_ok": gain > 0,
             "detail": f"base-only correct {b_only}, SFT-only correct {c_only}"},
            {"component": "H3b", "test": "Fisher exact, stored x correct (SFT, E2)",
             "scale": "risk diff", "estimate": rd_b,
             "ci_low": cis.get("rd_stored", nan2)[0], "ci_high": cis.get("rd_stored", nan2)[1],
             "p_raw": p_b, "direction_ok": bool(rd_b > 0), "detail": f"odds ratio {odds:.3g}"},
            {"component": "H4", "test": "permutation, gain(paraphrased) - gain(templated)",
             "scale": "risk diff", "estimate": diff,
             "ci_low": cis.get("gain_diff", nan2)[0], "ci_high": cis.get("gain_diff", nan2)[1],
             "p_raw": p4, "direction_ok": bool(diff > 0),
             "detail": f"gain paraphrased {gain_para:.3f}, templated {gain_tmpl:.3f}"},
        ]
    )
    h3_dir = bool(gain > 0 and rd_b > 0)
    family = pd.DataFrame(
        [
            {"hypothesis": "H3", "label": "E2 gain after SFT, bounded by pre-SFT storage (IUT)",
             "scale": "risk diff (gain)", "predicted_sign": 1, "estimate": gain,
             "ci_low": cis.get("gain", nan2)[0], "ci_high": cis.get("gain", nan2)[1],
             "p_raw": max(p_a, p_b), "direction_ok": h3_dir},
            {"hypothesis": "H4", "label": "extraction gain larger for paraphrased (secondary)",
             "scale": "risk diff (gain diff)", "predicted_sign": 1, "estimate": diff,
             "ci_low": cis.get("gain_diff", nan2)[0], "ci_high": cis.get("gain_diff", nan2)[1],
             "p_raw": p4, "direction_ok": bool(diff > 0)},
        ]
    )

    t_rows, c_rows = [], []
    for db in DIV_BINS:
        m = (facts["div_bin"] == db).to_numpy()
        for s in (1, 0):
            sel = m & (stored == s)
            t_rows.append(
                {"div_bin": db, "stored": "stored" if s else "not stored",
                 "n_correct": int(sft[sel].sum()), "n_wrong": int((1 - sft[sel]).sum())}
            )
        pm, bo, co = mcnemar_exact(base[m], sft[m]) if m.any() else (1.0, 0, 0)
        pf, _, _ = fisher_stored(stored[m], sft[m]) if m.any() else (1.0, 0, 0)
        c_rows.append(
            {"div_bin": db, "n_facts": int(m.sum()),
             "acc_base": float(base[m].mean()) if m.any() else float("nan"),
             "acc_sft": float(sft[m].mean()) if m.any() else float("nan"),
             "gain": float(d[m].mean()) if m.any() else float("nan"),
             "mcnemar_p": pm, "fisher_p_stored_x_correct": pf}
        )
    return ExtractionResult(
        family, components, pd.DataFrame(t_rows), pd.DataFrame(c_rows), len(facts), notes
    )

# ruff: noqa: E501, E702
"""R07 B: raw counts behind the degenerate H3/H4 CIs and non-degenerate supplementary estimates (SECONDARY, outside Holm).

Reads only the already-written QA prediction file (runs/real/qa/qa_predictions.csv); no decoding, no test file.
Primary H3/H4 (PREREG: majority-of-items, majority-of-seeds, per fact) are NOT changed.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from slm.analysis import extraction as X  # noqa: E402
from slm.analysis.schema import normalize_qa_table  # noqa: E402

qa = normalize_qa_table(pd.read_csv(ROOT / "runs/real/analysis_inputs/qa.csv"))
out: dict = {}
print("models:", qa.model.unique().tolist(), "eval sets:", qa.eval_set.unique().tolist())
e2 = qa[qa.eval_set == "E2"]
print("\nE2 rows per model:", e2.groupby("model").size().to_dict(), "facts", e2.fact_id.nunique(), "items per fact-seed", e2.groupby(["fact_id", "seed", "model"]).size().max())
for model in ("base_0shot", "base_2shot", "sft"):
    m = e2[e2.model == model]
    print(model, "item-level correct", int(m.exact_match.sum()), "of", len(m), "| facts with >=1 correct item (any seed)", int(m.groupby("fact_id").exact_match.max().sum()), "| facts correct under 'any'", int(X.fact_level(qa, rule="any", comparator=model).correct_sft.sum()) if model != "sft" else "")
for rule in ("majority", "any", "all"):
    f = X.fact_level(qa, rule=rule)
    b = f.correct_base.to_numpy(); s = f.correct_sft.to_numpy(); st = f.stored.to_numpy()
    p, bo, co = X.mcnemar_exact(b, s)
    tab = {"base_correct_sft_correct": int(((b == 1) & (s == 1)).sum()), "base_only": bo, "sft_only": co, "neither": int(((b == 0) & (s == 0)).sum())}
    print(f"\nrule {rule}: n facts {len(f)}; McNemar paired 2x2 {tab}; p={p:.4f}; gain {s.mean() - b.mean():.4f}")
    fa = {"stored_correct": int(((st == 1) & (s == 1)).sum()), "stored_wrong": int(((st == 1) & (s == 0)).sum()), "notstored_correct": int(((st == 0) & (s == 1)).sum()), "notstored_wrong": int(((st == 0) & (s == 0)).sum())}
    print("   Fisher stored x correct(SFT):", fa)
    for db in ("templated", "paraphrased"):
        mm = (f.div_bin == db).to_numpy()
        print(f"   H4 {db}: n={int(mm.sum())}, base correct {int(b[mm].sum())}, sft correct {int(s[mm].sum())}, gain {(s[mm] - b[mm]).mean():.4f}")
    out[rule] = {"mcnemar": tab, "p": p, "fisher": fa}

# supplementary, non-degenerate estimates (secondary)
rng = np.random.default_rng(20261107)
f = X.fact_level(qa)
n = len(f)
b_, c_ = out["majority"]["mcnemar"]["base_only"], out["majority"]["mcnemar"]["sft_only"]
cp = lambda k, n: (stats.beta.ppf(0.025, k, n - k + 1) if k else 0.0, stats.beta.ppf(0.975, k + 1, n - k) if k < n else 1.0)  # noqa: E731
print(f"\nSupplementary fact-level (majority): SFT correct {int(f.correct_sft.sum())}/{n}, Clopper-Pearson 95% CI {tuple(round(x, 4) for x in cp(int(f.correct_sft.sum()), n))}; base {int(f.correct_base.sum())}/{n} CI {tuple(round(x, 4) for x in cp(int(f.correct_base.sum()), n))}")
print("  rule of three: with 0 discordant facts out of", n, "the 95% upper bound on |gain| is about", round(3 / n, 3))

# item-level paired gain (sft - base_2shot) per E2 question, fact-clustered bootstrap, across seeds
w = e2[e2.model.isin(["sft", "base_2shot"])].pivot_table(index=["fact_id", "seed", "question_id"], columns="model", values="exact_match", aggfunc="first")
w["d"] = w["sft"].astype(float) - w["base_2shot"].astype(float)
per_fact = w.groupby("fact_id").d.mean()
est = float(w.d.mean())
boots = [per_fact.sample(len(per_fact), replace=True, random_state=int(rng.integers(1e9))).mean() for _ in range(4000)]
lo, hi = np.percentile(boots, [2.5, 97.5])
print(f"Item-level E2 gain (SFT - base_2shot), per-question exact_value_match, facts as clusters: {est:.4f}, 95% fact-bootstrap CI ({lo:.4f}, {hi:.4f}); sft {w.sft.astype(float).mean():.4f} base {w.base_2shot.astype(float).mean():.4f}")
out["item_level_gain"] = {"estimate": est, "ci": [float(lo), float(hi)], "sft": float(w.sft.astype(float).mean()), "base_2shot": float(w.base_2shot.astype(float).mean())}
for db in ("templated", "paraphrased"):
    facts_db = set(f[f.div_bin == db].fact_id)
    pf = per_fact[per_fact.index.isin(facts_db)]
    out[f"item_gain_{db}"] = float(pf.mean())
    print(f"  item-level gain {db}: {pf.mean():.4f} (n facts {len(pf)})")
fa = f.copy(); fb = per_fact
dpara = fb[fb.index.isin(set(f[f.div_bin == 'paraphrased'].fact_id))].to_numpy(); dtm = fb[fb.index.isin(set(f[f.div_bin == 'templated'].fact_id))].to_numpy()
bd = [rng.choice(dpara, len(dpara)).mean() - rng.choice(dtm, len(dtm)).mean() for _ in range(4000)]
print(f"  H4 item-level (paraphrased - templated) gain: {dpara.mean() - dtm.mean():.4f}, 95% CI ({np.percentile(bd, 2.5):.4f}, {np.percentile(bd, 97.5):.4f})")
out["item_level_h4"] = {"estimate": float(dpara.mean() - dtm.mean()), "ci": [float(np.percentile(bd, 2.5)), float(np.percentile(bd, 97.5))]}
Path(ROOT / "reports/integration/r07/h3_supplement.json").write_text(json.dumps(out, indent=1, default=float), encoding="utf-8")

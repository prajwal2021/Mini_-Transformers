# ruff: noqa: E501, E702
"""R08 item 3: H3 (McNemar + Fisher, raw counts) for BOTH the pre-specified early-stopped SFT (primary) and the post-hoc fixed-3-epoch SFT (secondary).

Reads only written files: runs/real/analysis_inputs/qa.csv (primary QA table), runs/real/qa/qa_predictions_sft_fixed3.csv (post-hoc predictions).
The base zero-shot / 2-shot rows are the SAME rows in both. Post-hoc results are labelled POST-HOC SECONDARY and are outside the Holm family.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from slm.analysis import extraction as X  # noqa: E402
from slm.analysis.schema import normalize_qa_table  # noqa: E402
from slm.sft_eval.ranking import ranking_summary  # noqa: E402

pd.set_option("display.width", 220, "display.max_columns", 30)
qa = pd.read_csv(ROOT / "runs/real/analysis_inputs/qa.csv")
fx = pd.read_csv(ROOT / "runs/real/qa/qa_predictions_sft_fixed3.csv", keep_default_na=False)
primary_pred = pd.read_csv(ROOT / "runs/real/qa/qa_predictions.csv", keep_default_na=False)
out: dict = {"label": "primary = pre-specified early-stopped SFT; fixed3 = POST-HOC SECONDARY (outside Holm)"}
key = ["question_id", "seed"]
cols = ["exact_value_match", "contains_gold", "sentence_exact", "error_class"] + [c for c in qa.columns if c.startswith("rank_")]
fxq = fx[key + [c for c in cols if c in fx.columns]].copy()
for c in ("exact_value_match", "contains_gold", "sentence_exact"):
    fxq[c] = fxq[c].astype(str).str.lower().map({"true": 1, "false": 0, "1": 1, "0": 0}).astype(int)
for c in [c for c in fxq.columns if c.startswith("rank_")]:
    fxq[c] = pd.to_numeric(fxq[c])
sft = qa[qa.model == "sft"].drop(columns=[c for c in fxq.columns if c not in key]).merge(fxq, on=key, how="left", validate="one_to_one")
assert len(sft) == (qa.model == "sft").sum() and sft.exact_value_match.notna().all()
qa_fixed = pd.concat([qa[qa.model != "sft"], sft[qa.columns]], ignore_index=True)
variants = {"primary_early_stopped": qa, "fixed3_posthoc": qa_fixed}

print("=== exact_value_match by model and eval set (questions x 3 seeds) ===")
acc = {}
for name, q in variants.items():
    t = q.groupby(["model", "eval_set"]).exact_value_match.agg(["mean", "size"]).round(4)
    acc[name] = {f"{m}/{e}": [float(v["mean"]), int(v["size"])] for (m, e), v in t.iterrows()}
t = pd.DataFrame({"early_stopped_sft": qa[qa.model == "sft"].groupby("eval_set").exact_value_match.mean(),
                  "fixed3_sft": qa_fixed[qa_fixed.model == "sft"].groupby("eval_set").exact_value_match.mean(),
                  "base_2shot": qa[qa.model == "base_2shot"].groupby("eval_set").exact_value_match.mean(),
                  "base_0shot": qa[qa.model == "base_0shot"].groupby("eval_set").exact_value_match.mean()}).round(4)
print(t.to_string())
out["exact_value_match"] = t.to_dict()
print("\nper seed (SFT exact_value_match, E0/E1/E2):")
for name, q in variants.items():
    print(" ", name, q[q.model == "sft"].pivot_table(index="seed", columns="eval_set", values="exact_value_match", aggfunc="mean").round(3).to_dict("index"))

print("\n=== H3 and H4 for both SFT variants (fact-level, majority rule = PREREG) ===")
res = {}
for name, q in variants.items():
    r = X.run_extraction(normalize_qa_table(q))
    comp = r.components.set_index("component")
    f = X.fact_level(normalize_qa_table(q))
    b, s, st = f.correct_base.to_numpy(), f.correct_sft.to_numpy(), f.stored.to_numpy()
    p_a, bo, co = X.mcnemar_exact(b, s)
    tab = {"both_correct": int(((b == 1) & (s == 1)).sum()), "base_only": bo, "sft_only": co, "neither": int(((b == 0) & (s == 0)).sum())}
    fish = {"stored_correct": int(((st == 1) & (s == 1)).sum()), "stored_wrong": int(((st == 1) & (s == 0)).sum()), "notstored_correct": int(((st == 0) & (s == 1)).sum()), "notstored_wrong": int(((st == 0) & (s == 0)).sum())}
    h3 = r.family.set_index("hypothesis")
    row = {"n_facts": len(f), "mcnemar_2x2": tab, "mcnemar_p": float(p_a), "fisher_2x2": fish, "fisher_p": float(comp.loc["H3b", "p_raw"]),
           "gain": [float(comp.loc["H3a", "estimate"]), float(comp.loc["H3a", "ci_low"]), float(comp.loc["H3a", "ci_high"])],
           "rd_stored": [float(comp.loc["H3b", "estimate"]), float(comp.loc["H3b", "ci_low"]), float(comp.loc["H3b", "ci_high"])],
           "H3_p_iut": float(h3.loc["H3", "p_raw"]), "H3_direction_ok": bool(h3.loc["H3", "direction_ok"]),
           "H4": [float(comp.loc["H4", "estimate"]), float(comp.loc["H4", "ci_low"]), float(comp.loc["H4", "ci_high"]), float(comp.loc["H4", "p_raw"])],
           "per_condition": r.per_condition.round(4).to_dict("records")}
    res[name] = row
    print(f"\n[{name}] facts {len(f)}  base_2shot correct {int(b.sum())}  SFT correct {int(s.sum())}")
    print("  McNemar paired 2x2 (base vs SFT):", tab, f"exact p = {p_a:.4g}")
    print("  Fisher 2x2 stored x SFT-correct:", fish, f"p = {row['fisher_p']:.4g}")
    print("  H3a gain %.4f (%.4f, %.4f) | H3b P(c|stored)-P(c|not) %.4f (%.4f, %.4f) | H3 (IUT) p = %.4g, direction ok: %s" % (*row["gain"], *row["rd_stored"], row["H3_p_iut"], row["H3_direction_ok"]))
    print("  H4 (paraphrased - templated gain) %.4f (%.4f, %.4f) perm p %.4g" % tuple(row["H4"]))
    print("  per diversity condition:", [(c["div_bin"], c["n_facts"], c["acc_base"], c["acc_sft"], c["gain"], c["mcnemar_p"]) for c in row["per_condition"]])
    # item-level (secondary) E2 gain with fact-clustered bootstrap
    e2 = q[(q.eval_set == "E2") & q.model.isin(["sft", "base_2shot"])]
    w = e2.pivot_table(index=["fact_id", "seed", "question_id"], columns="model", values="exact_match" if "exact_match" in e2.columns else "exact_value_match", aggfunc="first")
    pf = (w["sft"].astype(float) - w["base_2shot"].astype(float)).groupby("fact_id").mean()
    rng = np.random.default_rng(20261107)
    bs = [pf.sample(len(pf), replace=True, random_state=int(rng.integers(1e9))).mean() for _ in range(4000)]
    row["item_level_E2_gain"] = [float(pf.mean()), float(np.percentile(bs, 2.5)), float(np.percentile(bs, 97.5))]
    print("  item-level E2 gain (SFT - base_2shot, fact-clustered bootstrap): %.4f (%.4f, %.4f)" % tuple(row["item_level_E2_gain"]))
out["h3"] = res

print("\n=== ranking accuracy / MRR (rank_sentence = the full gold sentence ranked among the 6 candidates; rank_value = value only) ===")
rk = {}
for name, pred in (("early_stopped", primary_pred), ("fixed3", fx)):
    p = pred[pred.checkpoint == "sft"].copy()
    for c in [c for c in p.columns if c.startswith("rank_")]:
        p[c] = pd.to_numeric(p[c])
    s = ranking_summary(p)
    rk[name] = s.round(4).to_dict("records")
    print(name); print(s[["eval_set", "n", "rank_value_acc", "rank_value_mrr", "rank_sentence_acc", "rank_sentence_mrr"]].round(3).to_string(index=False))
base_rank = pd.read_csv(ROOT / "runs/real/analysis_inputs/ranking_accuracy.csv")
print("base (unchanged):"); print(base_rank[base_rank.checkpoint == "pretrained"][["prompt_mode", "eval_set", "n", "rank_value_acc", "rank_value_mrr", "rank_sentence_acc", "rank_sentence_mrr"]].round(3).to_string(index=False))
out["ranking"] = rk

print("\n=== error taxonomy counts (SFT; R08 classes) ===")
tx = {}
for name, pred in (("early_stopped", primary_pred), ("fixed3", fx)):
    p = pred[pred.checkpoint == "sft"]
    t = p.groupby(["eval_set", "error_class"]).size().unstack(fill_value=0)
    tx[name] = t.to_dict("index")
    print(name); print(t.to_string())
out["taxonomy"] = tx
(ROOT / "reports/integration/r08").mkdir(parents=True, exist_ok=True)
(ROOT / "reports/integration/r08/fixed3_results.json").write_text(json.dumps(out, indent=1, default=float), encoding="utf-8")

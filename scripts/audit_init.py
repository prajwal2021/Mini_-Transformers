# ruff: noqa: E501, E702
"""R07 C: what drives the stored rate of the UNTRAINED model (init checkpoint), TEST probes already written in probes_raw.csv. No new decode."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
pd.set_option("display.width", 220, "display.max_columns", 30)
p = pd.read_csv(ROOT / "runs/real/analysis_inputs_secondary/probe.csv")
p["checkpoint"] = p["checkpoint"].astype(str)
init = p[(p.split == "test") & (p.checkpoint.isin(["init", "0"]))].copy()
init["stored"] = init.stored.astype(int)
print("init test rows", len(init), "facts", init.fact_id.nunique(), "overall", round(init.stored.mean(), 3), "null", round(init.null_stored_rate.mean(), 3))
# value length: tokens of the continuation = value_len in the table (token count of the value string)
f = init.groupby("fact_id").agg(attr=("attribute_id", "first"), fb=("freq_bin", "first"), db=("div_bin", "first"), vl=("value_len", "first"), rate=("stored", "mean"))
f["n_candidates"] = f.groupby("attr").vl.transform("size")
f["is_shortest"] = f.vl == f.groupby("attr").vl.transform("min")
f["strictly_shortest"] = f.is_shortest & (f.groupby("attr").vl.transform(lambda s: (s == s.min()).sum()) == 1)
print("\ncandidate values per attribute (n facts per attribute among the 120):", f.n_candidates.value_counts().to_dict(), "(each probe ranks the true value against the 6 values of its attribute)")
print("\nBY FREQ x DIV (init):"); print(f.pivot_table(index="fb", columns="db", values="rate", aggfunc="mean").round(3).to_string())
print("\nBY VALUE TOKEN LENGTH (init):"); print(f.groupby("vl").rate.agg(["mean", "size"]).round(3).T.to_string())
print("\nBY 'is the (a) shortest value of its attribute' (init):"); print(f.groupby("is_shortest").rate.agg(["mean", "size"]).round(3).T.to_string())
print("share of all init stored events that come from shortest-value facts:", round(float((f.rate * f.is_shortest).sum() / f.rate.sum()), 3))
print("\nfacts per freq bin that are shortest-in-attribute:", f.groupby("fb").is_shortest.mean().round(3).to_dict())
print("mean value_len by freq bin:", f.groupby("fb").vl.mean().round(2).to_dict())
print("\nBY ATTRIBUTE (init rate, mean value_len):"); print(f.groupby("attr").agg(rate=("rate", "mean"), vl=("vl", "mean")).sort_values("rate", ascending=False).round(3).to_string())
r = init.groupby("rank").size(); print("\nrank distribution at init:", r.to_dict())
print("binding>0 share among rank-1 rows:", round(float((init[init["rank"] == 1].binding_score > 0).mean()), 3))
print("true_logprob mean by value_len (init):", init.groupby("value_len").true_logprob.mean().round(2).to_dict())
f2 = f.copy(); f2["pred_if_short"] = f2.is_shortest.astype(float) * 0.5
print("\nPrediction 'stored iff shortest value and binding>0 (~50%)': predicted overall", round(f2.pred_if_short.mean(), 3), "observed", round(f.rate.mean(), 3))
print("\nAfter conditioning on value_len: freq bin rate among facts with value_len==2:"); print(f[f.vl == 2].groupby("fb").rate.agg(["mean", "size"]).round(3).T.to_string())
f.to_csv(ROOT / "reports/integration/r07/init_by_fact.csv")

# ruff: noqa: E501
"""R07 A1-A2: the exact table fed to the H1 GEE at E*, hand-computed rates and slopes against the GEE."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from slm.analysis import models as M  # noqa: E402

pd.set_option("display.width", 250, "display.max_columns", 40)
df = pd.read_csv(ROOT / "runs/real/analysis_inputs/probe.csv")
sub, ck, warns = M.prepare_primary(df, "final")
print("checkpoint", ck, "rows", len(sub), "facts", sub.fact_id.nunique(), "seeds", sorted(sub.seed.unique()), "frames", sub.probe_frame.value_counts().to_dict(), "warns", warns)
cols = ["fact_id", "seed", "probe_frame", "prompt_variant", "freq_bin", "train_mentions", "freq_c", "div_bin", "div_c", "frame_c", "stored", "attribute_id", "value_len", "entity_freq"]
print(sub[cols].head(12).to_string())
print("outcome dtype/values", sub.stored.dtype, sorted(sub.stored.unique()), "| cluster = fact_id, n clusters", sub.fact_id.nunique())
print("coding maps", M.FREQ_BIN_CODE, M.DIV_CODE, M.FRAME_CODE)
print("freq_c: log3(train_mentions) minus its mean over facts; range", sub.freq_c.min().round(3), sub.freq_c.max().round(3), "mean", round(sub.freq_c.mean(), 3))
print("formula:", M.build_formula(sub))
f = sub.groupby("fact_id").agg(freq_bin=("freq_bin", "first"), div_bin=("div_bin", "first"), logm=("freq_c", "first"), mentions=("train_mentions", "first"), ent=("entity_freq", "first"), vlen=("value_len", "first"), attr=("attribute_id", "first"), rate=("stored", "mean"))
print("\nstored rate by freq bin:\n", sub.groupby("freq_bin").stored.agg(["mean", "size"]).round(3).T.to_string())
print("\nby freq x div:\n", sub.pivot_table(index="freq_bin", columns="div_bin", values="stored", aggfunc="mean").round(3).to_string())
print("\nby frame:\n", sub.groupby("probe_frame").stored.mean().round(3).to_string())
print("\nmentions by freq bin (facts):\n", f.groupby("freq_bin").mentions.describe().round(1).to_string())
print("\nentity_freq by freq bin:\n", f.groupby("freq_bin").ent.describe().round(1).to_string())
print("corr(log mentions, entity_freq):", round(np.corrcoef(f.logm, np.log(f.ent.clip(lower=1)))[0, 1], 3), "corr(logm, value_len):", round(np.corrcoef(f.logm, f.vlen)[0, 1], 3))
# empirical logit slope on log3(exposure), unadjusted and with a plain logistic GLM
import statsmodels.api as sm  # noqa: E402

X = sm.add_constant(sub[["freq_c"]])
r = sm.GLM(sub.stored.astype(float), X, family=sm.families.Binomial()).fit(cov_type="cluster", cov_kwds={"groups": sub.fact_id.astype("category").cat.codes})
print("\nunadjusted logit slope per tripling (GLM, cluster SE):", r.params["freq_c"].round(3), "CI", r.conf_int().loc["freq_c"].round(3).tolist())
rate = f.groupby(pd.cut(f.logm, 4)).rate.mean()
print("fact-level rate by quartile-ish bins of log3 mentions:\n", rate.round(3).to_string())
print("spearman(logm, fact rate):", round(f[["logm", "rate"]].corr("spearman").iloc[0, 1], 3))


def show(name, res):
    t = res.table.set_index("term")
    keep = [k for k in ("freq_c", "div_c", "frame_c", "div_c:frame_c", "freq_c:frame_c", "value_len_z", "entity_freq_z") if k in t.index]
    print()
    print(f"[{name}] converged={res.converged} {res.covariance}")
    print(t.loc[keep, ["estimate", "se", "p_raw"]].round(4).to_string())


sub2 = sub.copy()
show("PRIMARY as run (all covariates + attribute FE)", M.fit_gee(sub2))
show("no optional covariates", M.fit_gee(sub2, covariates=False))
show("no covariates, independence", M.fit_gee(sub2, covariates=False, cov_struct="independence"))
import statsmodels.formula.api as smf  # noqa: E402

for name, extra in [("value_len_z only", "+ value_len_z"), ("entity_freq_z only", "+ entity_freq_z"), ("attribute FE only", "+ C(attribute_id)"), ("value_len_z + attribute FE", "+ value_len_z + C(attribute_id)")]:
    base = "stored ~ freq_c * div_c * frame_c + C(seed) + pv_1 " + extra
    m = smf.gee(base, groups="fact_id", data=sub2.assign(stored=sub2.stored.astype(float)), family=sm.families.Binomial(), cov_struct=sm.cov_struct.Exchangeable()).fit()
    print(f"[{name}] freq_c = {m.params['freq_c']:.3f} (se {m.bse['freq_c']:.3f}); H2 div_c:frame_c = {m.params['div_c:frame_c']:.3f}")
print()
print("attribute_id x freq bin (facts):")
fa = sub2.groupby("fact_id").agg(attr=("attribute_id", "first"), fb=("freq_bin", "first"), vl=("value_len", "first"))
print(pd.crosstab(fa.attr, fa.fb).to_string())
print("value_len by freq bin:", fa.groupby("fb").vl.mean().round(2).to_dict())
print("stored rate by value_len:")
print(sub2.groupby("value_len").stored.agg(["mean", "size"]).round(3).T.to_string())
sub2.to_csv(ROOT / "reports/integration/r07/h1_gee_input_table.csv", index=False)

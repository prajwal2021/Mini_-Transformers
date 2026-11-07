# ruff: noqa: E501, E702
"""R08 item 2: value-length confound check. POST-UNBLINDING SENSITIVITY, OUTSIDE HOLM. Existing probe tables only (no new probes).

(a) stored rate at E* by freq x div restricted to rows/facts NOT stored at init;
(b) per freq bin, how many facts hold the shortest value of their attribute (and the value-length distribution);
(c) H1 with value-length rank within attribute as a covariate, with value_len_z only, without it, restricted to non-shortest facts,
    within value-length strata, and the mid-vs-low contrast alone.
Primary model for reference: stored ~ freq_c*div_c*frame_c + C(seed) + pv + value_len_z + entity_freq_z + C(attribute_id) (GEE logit).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import statsmodels.api as sm
import statsmodels.formula.api as smf
from scipy import stats

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from slm.analysis import models as M  # noqa: E402

pd.set_option("display.width", 220, "display.max_columns", 30)
raw = pd.read_csv(ROOT / "runs/real/analysis_inputs/probe.csv")
n = M.normalize_probe_table(raw)
test = n[n.split == "test"]
ck = int(test.checkpoint.max())
e = test[test.checkpoint == ck].copy()
i0 = test[test.checkpoint == 0][["fact_id", "seed", "prompt_variant", "stored"]].rename(columns={"stored": "init_stored"})
d = M.add_codes(e).merge(i0, on=["fact_id", "seed", "prompt_variant"])
d["stored"] = d.stored.astype(float)
d["init_stored"] = d.init_stored.astype(float)
# value-length rank within attribute among the 6 candidate values (1 = shortest; ties share the minimum rank)
vl = d.groupby("fact_id").agg(attr=("attribute_id", "first"), vl=("value_len", "first"), fb=("freq_bin", "first"), db=("div_bin", "first"))
vl["len_rank"] = vl.groupby("attr").vl.rank(method="min")
vl["shortest"] = vl.len_rank == 1
vl["strict_shortest"] = vl.shortest & (vl.groupby("attr").vl.transform(lambda s: (s == s.min()).sum()) == 1)
d = d.merge(vl[["len_rank", "shortest", "strict_shortest"]], left_on="fact_id", right_index=True)
d["len_rank_z"] = (d.len_rank - d.len_rank.mean()) / d.len_rank.std(ddof=0)
res: dict = {"label": "POST-UNBLINDING SENSITIVITY, OUTSIDE HOLM", "checkpoint_step": ck}
print("E* step", ck, "rows", len(d), "facts", d.fact_id.nunique())

print("\n(b) facts holding the shortest value of their attribute, by freq bin (40 facts per bin)")
b = vl.groupby("fb").agg(n_facts=("shortest", "size"), shortest_or_tied=("shortest", "sum"), strictly_shortest=("strict_shortest", "sum"), mean_value_tokens=("vl", "mean"), min_tokens=("vl", "min"), max_tokens=("vl", "max"))
print(b.loc[["low", "mid", "high"]].round(2).to_string())
print("value tokens by freq bin (counts):")
print(pd.crosstab(vl.fb, vl.vl).loc[["low", "mid", "high"]].to_string())
res["b_shortest_by_freq_bin"] = b.reset_index().to_dict("records")
mw = stats.mannwhitneyu(vl[vl.fb == "mid"].vl, vl[vl.fb == "low"].vl).pvalue
print("mid vs low value tokens: Mann-Whitney p = %.4f; mean mid %.2f low %.2f" % (mw, vl[vl.fb == "mid"].vl.mean(), vl[vl.fb == "low"].vl.mean()))
res["b_mid_vs_low_value_tokens"] = {"mannwhitney_p": float(mw), "mid_mean": float(vl[vl.fb == "mid"].vl.mean()), "low_mean": float(vl[vl.fb == "low"].vl.mean())}

fa = d.groupby("fact_id").agg(init_rate=("init_stored", "mean"), rate=("stored", "mean"), fb=("freq_bin", "first"), db=("div_bin", "first"))
print("\n(a) stored rate at E* by freq x div, rows NOT stored at init (row level, same fact/seed/prompt)")
r = d[d.init_stored == 0]
print(r.pivot_table(index="freq_bin", columns="div_bin", values="stored", aggfunc="mean").loc[["low", "mid", "high"]].round(3).to_string())
print("row counts:")
print(r.pivot_table(index="freq_bin", columns="div_bin", values="stored", aggfunc="size").loc[["low", "mid", "high"]].to_string())
print("by freq bin:", r.groupby("freq_bin").stored.mean().round(3).to_dict())
res["a_rows_not_stored_at_init"] = {"by_bin": r.groupby("freq_bin").stored.mean().round(4).to_dict(), "n_rows": len(r),
                                    "by_cell": {f"{k[0]}/{k[1]}": round(float(v), 4) for k, v in r.groupby(["freq_bin", "div_bin"]).stored.mean().items()}}
f0 = fa[fa.init_rate == 0]
print("facts never stored at init (all seeds, all probes): n =", len(f0), "by bin", f0.groupby("fb").size().to_dict(), "| E* rate by bin:", f0.groupby("fb").rate.mean().round(3).to_dict())
print(f0.pivot_table(index="fb", columns="db", values="rate", aggfunc="mean").loc[["low", "mid", "high"]].round(3).to_string())
res["a_facts_never_stored_at_init"] = {"n": len(f0), "n_by_bin": f0.groupby("fb").size().to_dict(), "rate_by_bin": f0.groupby("fb").rate.mean().round(4).to_dict()}


def fit(name, formula, data, key="freq_c"):
    data = data.copy()
    data["stored"] = data.stored.astype(float)
    m = smf.gee(formula, groups="fact_id", data=data, family=sm.families.Binomial(), cov_struct=sm.cov_struct.Exchangeable()).fit(cov_type="bias_reduced")
    dof = max(data.fact_id.nunique() - len(m.params), 1)
    t = stats.t.ppf(0.975, dof)
    est, se = m.params[key], m.bse[key]
    row = {"model": name, "estimate": round(float(est), 3), "ci_low": round(float(est - t * se), 3), "ci_high": round(float(est + t * se), 3), "p": float(2 * stats.t.sf(abs(est / se), dof)), "n_facts": int(data.fact_id.nunique())}
    print(f"  {name:66s} H1 {row['estimate']:+.3f} ({row['ci_low']:+.3f}, {row['ci_high']:+.3f}) p={row['p']:.3g} facts={row['n_facts']}")
    return row


pv = " + ".join(c for c in d.columns if c.startswith("pv_")); print("pv terms:", pv)
core = "stored ~ freq_c * div_c * frame_c + C(seed) + " + pv
print("\n(c) H1 (freq_c) under alternative covariate sets, exchangeable GEE logit, bias-reduced + t")
rows = [
    fit("A. primary: value_len_z + entity_freq_z + attribute FE", core + " + value_len_z + entity_freq_z + C(attribute_id)", d),
    fit("B. + value-length rank within attribute (len_rank_z)", core + " + value_len_z + len_rank_z + entity_freq_z + C(attribute_id)", d),
    fit("C. len_rank_z instead of value_len_z", core + " + len_rank_z + entity_freq_z + C(attribute_id)", d),
    fit("D. no value-length covariate at all", core + " + entity_freq_z + C(attribute_id)", d),
    fit("E. non-shortest facts only (drops the init-artefact facts)", core + " + value_len_z + entity_freq_z + C(attribute_id)", d[~d.shortest]),
    fit("F. non-shortest facts only, no attribute FE", core + " + value_len_z", d[~d.shortest]),
    fit("G. init_stored + value_len_z + len_rank_z", core + " + value_len_z + len_rank_z + entity_freq_z + C(attribute_id) + init_stored", d),
]
print("  within value-length strata (no value-length term needed):")
for k in sorted(d.value_len.unique()):
    s = d[d.value_len == k]
    if s.freq_bin.nunique() >= 2 and s.fact_id.nunique() >= 20:
        try:
            rows.append(fit(f"H. value_len == {k} only (facts by bin {s.groupby('freq_bin').fact_id.nunique().to_dict()})", core, s))
        except Exception as ex:  # noqa: BLE001
            print("   stratum", k, "failed:", type(ex).__name__)
sub = d[d.freq_bin.isin(["low", "mid"])].copy()
sub["freq_c"] = sub.freq_bin.map({"low": -0.5, "mid": 0.5}).astype(float)
print("  mid vs low contrast alone (freq_c = -0.5 low / +0.5 mid; high facts removed):")
rows.append(fit("I. mid vs low, with value_len_z + attribute FE", core + " + value_len_z + entity_freq_z + C(attribute_id)", sub))
rows.append(fit("J. mid vs low, no value-length covariate", core + " + entity_freq_z + C(attribute_id)", sub))
sub2 = d[d.freq_bin.isin(["mid", "high"])].copy()
sub2["freq_c"] = sub2.freq_bin.map({"mid": -0.5, "high": 0.5}).astype(float)
rows.append(fit("K. high vs mid, with value_len_z + attribute FE", core + " + value_len_z + entity_freq_z + C(attribute_id)", sub2))
res["c_models"] = rows


def lpm(name, formula, data, key="freq_c"):
    data = data.copy()
    data["stored"] = data.stored.astype(float)
    m = smf.gee(formula, groups="fact_id", data=data, family=sm.families.Gaussian(), cov_struct=sm.cov_struct.Exchangeable()).fit(cov_type="robust")
    dof = max(data.fact_id.nunique() - len(m.params), 1)
    t = stats.t.ppf(0.975, dof)
    est, se = m.params[key], m.bse[key]
    row = {"model": name, "estimate": round(float(est), 4), "ci_low": round(float(est - t * se), 4), "ci_high": round(float(est + t * se), 4), "n_facts": int(data.fact_id.nunique())}
    print(f"  {name:66s} risk difference {row['estimate']:+.4f} ({row['ci_low']:+.4f}, {row['ci_high']:+.4f}) facts={row['n_facts']}")
    return row


print("\n(c2) linear-probability GEE (identity link, robust SE): risk difference in stored rate per tripling (no separation problem)")
lp = [
    lpm("L1. all facts, primary covariates", core + " + value_len_z + entity_freq_z + C(attribute_id)", d),
    lpm("L2. all facts, no value-length covariate", core + " + entity_freq_z + C(attribute_id)", d),
    lpm("L3. all facts, + len_rank_z", core + " + value_len_z + len_rank_z + entity_freq_z + C(attribute_id)", d),
    lpm("L4. non-shortest facts only (76), value_len_z", core + " + value_len_z + entity_freq_z", d[~d.shortest]),
    lpm("L5. value_len == 3 only", core, d[d.value_len == 3]),
    lpm("L6. mid vs low (freq_c -0.5/+0.5), value_len_z + attribute FE", core + " + value_len_z + entity_freq_z + C(attribute_id)", sub),
    lpm("L7. mid vs low, no value-length covariate", core + " + entity_freq_z + C(attribute_id)", sub),
    lpm("L8. high vs mid, value_len_z + attribute FE", core + " + value_len_z + entity_freq_z + C(attribute_id)", sub2),
    lpm("L9. high vs mid, no value-length covariate", core + " + entity_freq_z + C(attribute_id)", sub2),
]
res["c2_linear_probability"] = lp
for r_ in rows:
    if r_["estimate"] != r_["estimate"] or abs(r_["estimate"]) > 8:
        r_["note"] = "separation or non-estimable (the low cell has 8 stored rows in 360); not interpretable"
print("\nmean stored by freq bin: ", d.groupby("freq_bin").stored.mean().round(3).to_dict())
print("raw mid-minus-low stored-rate difference:", round(float(d[d.freq_bin == "mid"].stored.mean() - d[d.freq_bin == "low"].stored.mean()), 3))
(ROOT / "reports/integration/r08").mkdir(parents=True, exist_ok=True)
(ROOT / "reports/integration/r08/value_length_check.json").write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")

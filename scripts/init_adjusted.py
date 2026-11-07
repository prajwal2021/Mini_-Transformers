# ruff: noqa: E501
"""R07 C: SECONDARY init-adjusted H1/H2 (outside the Holm family; the primary model is not replaced).

(1) per-row change stored(E*) - stored(init) on the same (fact, seed, prompt_variant): linear GEE (identity link), clusters = facts;
(2) the primary logistic GEE with the row's init stored as an extra covariate.
Uses only the already-written probe table (analysis_inputs/probe.csv, TEST rows); no decoding.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import statsmodels.api as sm
import statsmodels.formula.api as smf
from scipy import stats

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from slm.analysis import models as M  # noqa: E402

df = pd.read_csv(ROOT / "runs/real/analysis_inputs/probe.csv")
n = M.normalize_probe_table(df)
test = n[n.split == "test"]
ck = int(test.checkpoint.max())
estar = test[test.checkpoint == ck]
init = test[test.checkpoint == 0][["fact_id", "seed", "prompt_variant", "stored"]].rename(columns={"stored": "init_stored"})
print("E* checkpoint step", ck, "rows", len(estar), "init rows", len(init))
d = M.add_codes(estar).merge(init, on=["fact_id", "seed", "prompt_variant"], how="left")
assert d.init_stored.notna().all()
d["stored"] = d.stored.astype(float)
d["init_stored"] = d.init_stored.astype(float)
d["delta"] = d.stored - d.init_stored
print("mean stored(E*) %.3f, init %.3f, delta %.3f" % (d.stored.mean(), d.init_stored.mean(), d.delta.mean()))
terms = "freq_c * div_c * frame_c + C(seed) + " + " + ".join(c for c in d.columns if c.startswith("pv_")) + " + value_len_z + entity_freq_z + C(attribute_id)"
dof = d.fact_id.nunique() - 1


def table(res, names):
    out = []
    t = stats.t.ppf(0.975, max(d.fact_id.nunique() - len(res.params), 1))
    for k in names:
        out.append({"term": k, "estimate": res.params[k], "se": res.bse[k], "ci_low": res.params[k] - t * res.bse[k], "ci_high": res.params[k] + t * res.bse[k], "p": 2 * stats.t.sf(abs(res.params[k] / res.bse[k]), max(d.fact_id.nunique() - len(res.params), 1))})
    return pd.DataFrame(out).round(4)


m1 = smf.gee("delta ~ " + terms, groups="fact_id", data=d, family=sm.families.Gaussian(), cov_struct=sm.cov_struct.Exchangeable()).fit(cov_type="robust")
print("\n(1) SECONDARY: change stored(E*) - stored(init), linear GEE (risk-difference scale)")
print(table(m1, ["freq_c", "div_c:frame_c"]).to_string(index=False))
m2 = smf.gee("stored ~ " + terms + " + init_stored", groups="fact_id", data=d, family=sm.families.Binomial(), cov_struct=sm.cov_struct.Exchangeable()).fit(cov_type="robust")
print("\n(2) SECONDARY: primary logistic GEE + init_stored covariate (log-odds)")
print(table(m2, ["freq_c", "div_c:frame_c", "init_stored"]).to_string(index=False))
m0 = M.fit_gee(d.assign(stored=d.stored)).table.set_index("term")
print("\nprimary (corrected, for comparison): H1 %.4f  H2 %.4f" % (m0.loc["freq_c", "estimate"], m0.loc["div_c:frame_c", "estimate"]))
print("fact-level cells: mean delta by freq bin:", d.groupby("freq_bin").delta.mean().round(3).to_dict())
print("mean delta by freq x div:\n", d.pivot_table(index="freq_bin", columns="div_bin", values="delta", aggfunc="mean").round(3).to_string())
table(m1, ["freq_c", "div_c:frame_c"]).assign(model="delta_linear").to_csv(ROOT / "reports/integration/r07/init_adjusted.csv", index=False)
table(m2, ["freq_c", "div_c:frame_c", "init_stored"]).assign(model="logit_with_init").to_csv(ROOT / "reports/integration/r07/init_adjusted.csv", mode="a", index=False, header=False)

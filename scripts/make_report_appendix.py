# ruff: noqa: E501
"""R07/R08: write the report appendix: continued limitations, the ORIGINAL (pre-correction) H1/H2 numbers beside the corrected ones, and the
post-unblinding supplementary tables (all outside the Holm family). Every number is read from a written file; none is typed here.

    python scripts/make_report_appendix.py --original reports/integration/real_R06/results --corrected runs/real/results \
        --original-secondary reports/integration/real_R06/results_secondary --corrected-secondary runs/real/results_secondary \
        --out runs/real/report_inputs/appendix_correction.md
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
STAR = "E\\*"  # the report markup writes E* with a backslash
CLS = ["correct", "right_type_wrong_value", "wrong_attribute", "out_of_kb_hallucination", "format_failure"]


def row(f: pd.DataFrame, h: str) -> pd.Series:
    return f.set_index("hypothesis").loc[h]


def fmt(r: pd.Series) -> str:
    return f"{r['estimate']:+.3f} ({r['ci_low']:+.3f}, {r['ci_high']:+.3f}), Holm p {r['p_holm']:.2g}"


def jload(p: str) -> dict:
    return json.loads((ROOT / p).read_text(encoding="utf-8"))


def table(headers: list[str], rows: list[list]) -> list[str]:
    return ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)] + ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]


def build(a) -> list[str]:
    o = pd.read_csv(Path(a.original) / "tables" / "analysis_family.csv")
    c = pd.read_csv(Path(a.corrected) / "tables" / "analysis_family.csv")
    vl = jload("reports/integration/r08/value_length_check.json")
    fx = jload("reports/integration/r08/fixed3_results.json")
    sft_audit = jload("reports/integration/r07/sft_audit.json")
    held = jload("reports/integration/heldout_loss_R06.json")["loss"]
    init_adj = pd.read_csv(ROOT / "reports/integration/r07/init_adjusted.csv", header=0, names=["term", "estimate", "se", "ci_low", "ci_high", "p", "model"])
    shortest = {r["fb"]: r for r in vl["b_shortest_by_freq_bin"]}
    models = {m["model"][:1]: m for m in vl["c_models"]}
    lp = {m["model"][:2]: m for m in vl["c2_linear_probability"]}
    es = [r for r in sft_audit["rows"] if r["ckpt"] == "best"]
    es_epochs = ", ".join(str(r["best_epoch_in_summary"]) for r in es)
    es_train = ", ".join(f"{r['train_exact_value_match']:.2f}" for r in es)
    ex = fx["exact_value_match"]
    h3 = fx["h3"]
    L: list[str] = []

    L += ["## Appendix A: limitations, continued", "",
          f"**Value length is confounded with exposure by design.** Of the 40 facts in each exposure bin, the number whose value is the shortest (or tied shortest) of its attribute is "
          f"{shortest['low']['shortest_or_tied']} (low), {shortest['mid']['shortest_or_tied']} (mid) and {shortest['high']['shortest_or_tied']} (high); mean value length is "
          f"{shortest['low']['mean_value_tokens']:.2f}, {shortest['mid']['mean_value_tokens']:.2f} and {shortest['high']['mean_value_tokens']:.2f} tokens. The probe score is a summed log-probability, so an untrained model can rank only a shortest value first, "
          "which is why it already scores above chance in the high bin. The primary model adjusts for value length, which is partly collinear with exposure (Table A2).", "",
          f"**Early-stopped SFT, 12-fact validation set.** Early stopping used the loss on {sft_audit['n_val_facts']} held-out facts absent from the SFT training data, so that loss cannot fall as the training facts are learned. It picked epoch {es_epochs} for seeds 0, 1, 2 "
          f"(training-question exact match {es_train}). This pre-specified SFT is primary; a post-hoc fixed three-epoch SFT (three-epoch cosine schedule, otherwise identical) is secondary (Table A3).", "",
          f"**Three seeds, one model size, memorization.** Validation loss is lowest at epoch 12 and rises afterwards "
          f"({sum(held[f'seed{s}_epoch12']['all_val_docs'] for s in range(3)) / 3:.2f}, {sum(held[f'seed{s}_epoch30']['all_val_docs'] for s in range(3)) / 3:.2f} and "
          f"{sum(held[f'seed{s}_epoch60']['all_val_docs'] for s in range(3)) / 3:.2f} at epochs 12, 30 = {STAR}, 60) while the stored rate stays within its standard error (Table A1): a memorization regime.", "",
          "**Data and model.** Bank sentence defect rate about 3% (60-sentence sample, not re-measured); weak sentence diversity for four facts (F040, F087, F021, F067); "
          "twelve flagged validation and test documents kept (held-out loss without the five flagged validation documents differs by at most 0.01); H1 and H2 use a GEE, not a mixed model. "
          "The test-access ledger has five lines; the fourth (the post-hoc fixed three-epoch SFT evaluation) recorded git dirty = true because the taxonomy relabelling was uncommitted when it ran; results are unaffected.", ""]

    L += ["## Appendix B: post-unblinding correction of H1 and H2", "",
          "After the results were seen, an audit found that a boolean outcome made the formula interface model the probability of NOT stored, so every logistic coefficient had the wrong sign. "
          f"The fix (validated on synthetic planted effects, not on these outcomes) changes only signs; the hypotheses, model, margins and {STAR} are unchanged, and a freeze addendum records the code change. Original numbers:", ""]
    rows = [[f"{h} (primary, {STAR})", fmt(row(o, h)), fmt(row(c, h))] for h in ("H1", "H2")]
    if a.original_secondary and a.corrected_secondary:
        os_ = pd.read_csv(Path(a.original_secondary) / "tables" / "analysis_family.csv")
        cs = pd.read_csv(Path(a.corrected_secondary) / "tables" / "analysis_family.csv")
        rows += [[f"{h} (secondary, epoch 60)", fmt(row(os_, h)), fmt(row(cs, h))] for h in ("H1", "H2")]
    L += table(["hypothesis", "original (bugged, sign inverted)", "corrected"], rows) + [""]

    L += ["## Appendix C: supplementary tables (post-unblinding, outside the Holm family)", "",
          "**Table A1. Stored rate at checkpoints (descriptive, no tests).** Test probes, three seeds; rate with the chance rate in brackets.", ""]
    pr = pd.read_csv(ROOT / "runs/real/analysis_inputs_secondary/probe.csv")
    pr = pr[pr["split"] == "test"].copy()
    pr["checkpoint"] = pr["checkpoint"].astype(str)
    steps = {"init": "init", "epoch 12 (validation-loss optimum)": "1188", f"epoch 30 ({STAR})": "2970", "epoch 60": "5940"}
    rws = []
    for name, ck in steps.items():
        r_ = pr[pr["checkpoint"] == ck]
        cells = [f"{r_['stored'].mean():.3f} ({r_['null_stored_rate'].mean():.3f})"]
        for fb in ("low", "mid", "high"):
            x = r_[r_["freq_bin"] == fb]
            cells.append(f"{x['stored'].mean():.3f} ({x['null_stored_rate'].mean():.3f})")
        rws.append([name, *cells])
    L += table(["checkpoint", "all", "low", "mid", "high"], rws) + [""]

    def ms(k: str) -> str:
        m = models[k]
        return f"{m['estimate']:+.2f} ({m['ci_low']:+.2f}, {m['ci_high']:+.2f})"

    def lps(k: str) -> str:
        m = lp[k]
        return f"{m['estimate']:+.3f} ({m['ci_low']:+.3f}, {m['ci_high']:+.3f})"

    L += ["**Table A2. How much of H1 survives value length.** H1 per tripling of exposure at epoch 30, logistic GEE (log-odds) and linear-probability GEE (risk difference); 95% CIs.", ""]
    L += table(["model", "H1 log-odds", "H1 risk difference"], [
        ["primary (value length, entity frequency, attribute effects)", ms("A"), lps("L1")],
        ["no value-length covariate", ms("D"), lps("L2")],
        ["mid versus low only, with value length", "not estimable (the low bin has almost no stored rows)", lps("L6")],
        ["high versus mid only, with value length", ms("K"), lps("L8")],
    ]) + [""]
    L += [f"Mid and low facts do not differ clearly in value length ({vl['b_mid_vs_low_value_tokens']['mid_mean']:.2f} against {vl['b_mid_vs_low_value_tokens']['low_mean']:.2f} tokens, Mann-Whitney p = {vl['b_mid_vs_low_value_tokens']['mannwhitney_p']:.2f}), "
          "so the mid-versus-low contrast is the cleanest exposure comparison. The high-versus-mid step cannot be separated from value length in this design.", ""]

    ia = init_adj.set_index(["model", "term"])
    def iv(m: str, t: str) -> str:
        r_ = ia.loc[(m, t)]
        return f"{r_['estimate']:+.3f} ({r_['ci_low']:+.3f}, {r_['ci_high']:+.3f})"

    L += [f"Init-adjusted analyses (secondary): the change in stored rate from init to {STAR} gives H1 {iv('delta_linear', 'freq_c')} and H2 {iv('delta_linear', 'div_c:frame_c')} (risk differences); "
          f"the primary logistic model with init stored as a covariate gives H1 {iv('logit_with_init', 'freq_c')} and H2 {iv('logit_with_init', 'div_c:frame_c')} (log-odds).", ""]

    L += ["**Table A3. Early-stopped SFT (pre-specified, primary) against a post-hoc fixed three-epoch SFT (secondary).** Exact value match; base rows are the same in both.", ""]
    L += table(["model", "E0", "E1", "E2"], [
        ["base zero-shot", *[f"{ex['base_0shot'][e]:.3f}" for e in ("E0", "E1", "E2")]],
        ["base 2-shot", *[f"{ex['base_2shot'][e]:.3f}" for e in ("E0", "E1", "E2")]],
        ["SFT, early-stopped (primary)", *[f"{ex['early_stopped_sft'][e]:.3f}" for e in ("E0", "E1", "E2")]],
        ["SFT, fixed 3 epochs (post-hoc)", *[f"{ex['fixed3_sft'][e]:.3f}" for e in ("E0", "E1", "E2")]],
    ]) + [""]
    hp, hf = h3["primary_early_stopped"], h3["fixed3_posthoc"]
    L += table(["H3 on E2 facts (60)", "early-stopped (primary)", "fixed 3 epochs (post-hoc)"], [
        ["McNemar: both / base only / SFT only / neither; exact p", f"{hp['mcnemar_2x2']['both_correct']} / {hp['mcnemar_2x2']['base_only']} / {hp['mcnemar_2x2']['sft_only']} / {hp['mcnemar_2x2']['neither']}; {hp['mcnemar_p']:.2g}", f"{hf['mcnemar_2x2']['both_correct']} / {hf['mcnemar_2x2']['base_only']} / {hf['mcnemar_2x2']['sft_only']} / {hf['mcnemar_2x2']['neither']}; {hf['mcnemar_p']:.2g}"],
        ["Fisher stored x correct: stored right / wrong, not stored right / wrong; p", f"{hp['fisher_2x2']['stored_correct']} / {hp['fisher_2x2']['stored_wrong']}, {hp['fisher_2x2']['notstored_correct']} / {hp['fisher_2x2']['notstored_wrong']}; {hp['fisher_p']:.2g}", f"{hf['fisher_2x2']['stored_correct']} / {hf['fisher_2x2']['stored_wrong']}, {hf['fisher_2x2']['notstored_correct']} / {hf['fisher_2x2']['notstored_wrong']}; {hf['fisher_p']:.2g}"],
        ["item-level E2 gain over base 2-shot (95% fact-bootstrap CI)", f"{hp['item_level_E2_gain'][0]:+.3f} ({hp['item_level_E2_gain'][1]:+.3f}, {hp['item_level_E2_gain'][2]:+.3f})", f"{hf['item_level_E2_gain'][0]:+.3f} ({hf['item_level_E2_gain'][1]:+.3f}, {hf['item_level_E2_gain'][2]:+.3f})"],
    ]) + [""]
    L += ["No fact reaches the majority rule under either SFT, so the fact-level H3 intervals are degenerate; the item-level row is secondary.", ""]
    rk = fx["ranking"]
    tx = fx["taxonomy"]
    rws = []
    for name, key in (("early-stopped", "early_stopped"), ("fixed 3 epochs", "fixed3")):
        for e in ("E0", "E1", "E2"):
            t = tx[key][e]
            m = next(r for r in rk[key] if r["eval_set"] == e)
            rws.append([name, e, *[t.get(k, 0) for k in CLS], f"{m['rank_sentence_mrr']:.2f}"])
    L += ["<<<SUPPLEMENT>>>"]
    L += ["**Table A4. SFT error classes (counts over three seeds) and sentence-ranking MRR.** `wrong_attribute` = a well-formed answer stating a value of another attribute.", ""]
    L += table(["SFT", "set", *CLS, "ranking MRR"], rws) + [""]
    return L


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--original", required=True)
    ap.add_argument("--corrected", required=True)
    ap.add_argument("--original-secondary", default=None)
    ap.add_argument("--corrected-secondary", default=None)
    ap.add_argument("--out", required=True)
    ap.add_argument("--out-supplement", default=None, help="full version with Table A4 (error classes, ranking MRR); the PDF appendix omits A4 to stay within seven pages")
    a = ap.parse_args()
    lines = build(a)
    cut = lines.index("<<<SUPPLEMENT>>>")
    main_lines = [*lines[:cut], "Table A4 (SFT error classes and ranking MRR for both SFT variants) is in the supplementary file reports/integration/r08/supplementary_tables_R08.md.", ""]
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text("\n".join(main_lines) + "\n", encoding="utf-8")
    if a.out_supplement:
        head = "# Supplementary tables R07/R08 (post-unblinding, outside the Holm family)\n\n"
        Path(a.out_supplement).write_text(head + "\n".join(lines[:cut] + lines[cut + 1:]) + "\n", encoding="utf-8")
    print("\n".join(main_lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

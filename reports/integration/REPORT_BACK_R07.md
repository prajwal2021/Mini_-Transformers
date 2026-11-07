# REPORT BACK R07 (result audit)

No retraining. `data/eval/qa_test.jsonl` not opened; no new test-split decode or probe (ledger still 3 lines). Not pushed. `.env` not read.

## a) Tests / lint / git
Full pytest: **715 passed, 0 failed, 0 skipped** (9:24). `ruff check .`: all checks passed. Commit and status: see the end of the chat report.

## b) H1/H2 audit: a sign bug, now fixed
- **Table fed to the GEE** (`reports/integration/r07/h1_gee_input_table.csv`): 1,080 rows = 120 facts x 3 seeds x 3 probe rows (1 canonical + 2 novel), checkpoint step 2970 (E\*=30), TEST split. Outcome `stored` = bool. `freq_c` = log3(train_mentions) minus its mean over facts (mentions 5/15/45, so about -1 / 0 / +1); `div_c` templated -0.5, paraphrased +0.5; `frame_c` canonical -0.5, novel +0.5; cluster = `fact_id`. Formula: `stored ~ freq_c*div_c*frame_c + C(seed) + pv_1 + value_len_z + entity_freq_z + C(attribute_id)`, exchangeable, bias-reduced + t.
- **Hand computation, same table:** stored rate low 0.022 / mid 0.142 / high 0.433 (rising). Plain logit slope on log3 mentions: **+1.65** per tripling (cluster CI 1.34, 1.97). The GEE reported **-0.948**. Disagreement in sign, so a bug.
- **Cause:** `stored` was a bool column. patsy turns a bool response into two columns (`stored[False]`, `stored[True]`) and the GEE took the first, i.e. it modelled P(NOT stored). Same data with an int or float outcome: H1 +0.9484, H2 +1.8439; with bool: -0.9484, -1.8439 (exact mirror). The earlier synthetic validation used int outcomes and could not see it.
- **PREREG check:** H1 = `freq_c`, H2 = `div_c:frame_c`, predicted sign +, novel frame = `frame_c` +0.5 (probe_frame `novel`). The code implements that; only the outcome coding was wrong.
- **Planted-effect tests** (`tests/test_r07_sign.py`, 7 tests, bool outcome, 120 facts, 3 seeds, 3 frames): planted H1 slope +1 and -1, planted H2 +1.5 and -1.5, bool vs int identical, robust-ladder path, non-binary refusal. **All 7 fail on the old code and pass on the fix.**
- **Fix:** `_numeric_outcome` in `fit_gee` and `fit_bayes_mixed`. Made on synthetic and hand-computed evidence, not on the outcome.
- **Before / after (primary, E\*=30):**

| | before (R06 report) | after |
|---|---|---|
| H1 | -0.948 (-1.528, -0.369), Holm p 0.0032, "reversed" | **+0.948 (0.369, 1.528), Holm p 0.0032, supported** |
| H2 | -1.844 (-2.778, -0.910), Holm p 0.00052, "reversed" | **+1.844 (0.910, 2.778), Holm p 0.00052, supported** |
| H1 epoch 60 (secondary) | -1.164 | +1.164 (0.621, 1.707) |
| H2 epoch 60 (secondary) | -1.624 | +1.624 (0.737, 2.512) |
- All sensitivity re-fits flip the same way (the Bayesian mixed logit, which had been skipped, now runs: H1 1.286, H2 2.204, point estimates). H2 within frame: paraphrased minus templated is -1.22 (CI -2.13, -0.31) on canonical and +0.62 (CI -0.05, 1.30) on novel probes, which matches the predicted pattern.
- Adjustment matters for size, not sign: with no optional covariates H1 is +1.77; value length alone brings it to +1.32; the full model +0.95 (value length is correlated -0.60 with exposure by design).
- Documented as post-unblinding deviation row 56 of `DESIGN_CHANGES_v1.3.md` and I-D056; the original numbers are kept in `reports/integration/real_R06/` and in a new report appendix (6 pages still).
- **Caveat to note:** the frozen PREREG file hash is unchanged, but the freeze's `analysis_code_sha256` no longer matches `src/slm/analysis/models.py`. The report build verifies the PREREG hash only.

## c) H3/H4 counts (E2, 60 facts; `r07/h3_supplement.json`)
- Primary rule (majority of items within seed, majority of seeds): SFT correct **0 of 60**, base_2shot **0 of 60**. McNemar paired 2x2: both correct 0, base-only 0, SFT-only 0, neither 60; p = 1. Fisher stored x correct (SFT): stored 7 (0 correct, 7 wrong), not stored 53 (0 correct, 53 wrong). H4: templated base 0 / SFT 0, paraphrased 0 / 0.
- So estimate 0 with CI (0, 0) is **not a bug**: the vector is all zeros, so every bootstrap resample is zero. Item-level E2 correct: SFT 8 of 540 (1.5%), base_2shot 1 of 540, base_0shot 3 of 540. Under the `any` rule: McNemar base-only 1, SFT-only 5, p 0.219, gain +0.067 (0, 0.15).
- Supplementary non-degenerate estimates (secondary): fact-level SFT 0/60, Clopper-Pearson upper bound 0.060 (about 0.05 by the rule of three for the gain); item-level E2 gain (SFT - base_2shot) **+0.0130, 95% fact-bootstrap CI (0.000, 0.032)**; H4 item-level (paraphrased - templated gain) **-0.0185 (-0.056, 0.007)**. The primary H3/H4 definitions are unchanged.

## d) Init baseline (TEST probes at `init`, already computed; `r07/init_by_fact.csv`)
- By freq x div: high-paraphrased 0.217, high-templated 0.356, mid 0.017 / 0.033, low 0.000 / 0.000.
- By value token length: 2 tokens 0.258, 3 tokens 0.083, 4 or more 0.000. By attribute: 0.04 to 0.19 (follows attribute value length). Candidates per probe: 6 for every attribute (constant).
- **Driver:** an untrained model gives every token about the same log-prob (true log-prob at init is about -8.4 per token: -16.8 / -25.3 / -33.6 for 2 / 3 / 4 tokens), so the summed score ranks the **shortest** value of each attribute first. All 100% of init stored events are facts whose value is the shortest of its attribute (rank distribution at init is flat 1 to 6), and binding > 0 in 62% of those. The confound: **all 40 high-frequency facts hold the shortest value of their attribute; none of the low ones do** (value length 2.25 / 3.62 / 4.12 tokens for high / mid / low). The 0.22-0.36 comes from cell-by-length confounding, not an embedding prior or a bug in binding.
- Secondary analyses (outside Holm; `r07/init_adjusted.csv`): (1) change stored(E\*) - stored(init), linear GEE: H1 **+0.025 (-0.026, 0.076)**, H2 **+0.225 (0.125, 0.325)**; (2) the primary logit plus init stored as a covariate: H1 **+0.934 (0.50, 1.37)**, H2 **+1.848 (0.95, 2.75)**, init_stored coefficient +0.14 (n.s.). So the H1 effect on the log-odds scale survives init adjustment but not on the change-in-rate scale (the change is similar across exposure bins because high-frequency facts start from a high init rate).

## e) SFT / QA audit (train and val SFT files only; `r07/sft_audit.json`)
- **Train-question exact match** (same evaluator code path, greedy, 48 tokens), by SFT epoch (seed 0 / 1 / 2): epoch 1 0.125 / 0.155 / 0.152; epoch 2 0.670 / 0.563 / 0.569; epoch 3 **0.926 / 0.884 / 0.905**. Teacher-forced answer loss on train: 0.39 / 0.09 / 0.03 (seed 0), matching the training log; on sft_val about 0.77 to 0.83 (log-prob about -9.8 per answer), val exact match 0 to 0.08.
- **Which checkpoint was evaluated:** `best.pt` = lowest sft_val loss = **epoch 1, 2, 1** for seeds 0, 1, 2 (21 to 42 optimiser steps, warmup is 20). sft_val holds **12 held-out facts** (none in train), so its loss cannot fall as the model learns the training facts; it rises from epoch 1 and early stopping (patience 2) picks the least-trained checkpoint. Evaluated SFT train accuracy for best.pt is 0.125 / 0.563 / 0.152 (mean 0.28), which equals the reported E0 accuracy 0.280.
- **Checked, no bug:** `model.eval()` (dropout off); tokenisation boundary (prompt ids + answer ids equal the joint encoding); eos is produced (all 294 and 25 non-exact train decodes stopped on eos, none hit the 48-token cap); loss is on answer + eos only (labels -100 on the prompt); padding is right-padded with `doc_ids` 0 masking, decoding uses single unpadded sequences. So no eval-code bug, and **no test re-evaluation was run.**
- **10 format-failure examples** (`r07/format_failures.json`). The 10 existing E0 SFT test predictions are well-formed sentences about the wrong attribute, e.g. gold "The lounge manager at Vellmar is Miren Quill." predicted "The relief-area gate at Ashenfell is RG-615."; none empty. Token ids exist only for fresh train-question decodes (test prompts are not re-decoded): the same pattern, `eos` produced, 10 to 14 tokens. **Cause of the label:** `format_failure` = empty, degenerate repetition, or "no value-like string of the attribute's type", so a clean answer about another attribute is labelled format failure. The class name overstates what it holds; I did not rename it.
- Taxonomy counts, the original corrected numbers: unchanged (no re-run): SFT E0/E1/E2 exact_value_match 0.280 / 0.234 / 0.015; base 2-shot 0.005 / 0.002 / 0.002.

## f) What the report PDF needs to change
Already regenerated with the corrected H1/H2 (statuses "supported") and an appendix showing original vs corrected numbers (6 pages). Still to do by hand: the Limitations text should mention the early-stopped SFT checkpoint and the value-length confound; the sensitivity file still says "PREREG v3"; the supplementary R07 tables (init-adjusted, item-level E2, epoch 12, held-out loss) are not in the PDF.

## g) Still unexplained / for the architect
- SFT early stopping on a validation set of unseen facts selects epoch 1-2; with 3 epochs the model reaches 0.88-0.93 on training questions. Whether to keep DESIGN 7.3's rule or SFT for a fixed number of epochs is a design decision; changing it means a re-run of SFT and a second QA test evaluation, which I did not do.
- The value-length/exposure confound is built into the design, not removed by the primary model (value_len_z is a covariate, partly collinear with exposure).
- The freeze's analysis-code hash is now stale (see b).
- E2 extraction is essentially zero for every model; H3 stays unsupported with this SFT checkpoint.

# REPORT BACK R08 (close the analysis)

No pretraining rerun. Not pushed. `.env` not read. The QA test file was opened once, through the ledger, for the post-hoc fixed 3-epoch SFT evaluation (ledger line 4).

## a) Tests / lint / git
Full pytest: 725 passed, 0 failed, 0 skipped (9:47). `ruff check .`: all checks passed after two import fixes in the new post-hoc script.

## b) Freeze addendum
- `docs/FREEZE_ADDENDUM.json` (id R08-1): fix commit `5c94523`; old analysis-code hash `8a6fab56...` (reproduced from the freeze commit's files); new hash `3fa3b4a9...`; PREREG hash `6fbf098a...` unchanged; references DESIGN_CHANGES row 56 and I-D056. The freeze block was not touched.
- `verify_analysis_code` (`slm.integration.freeze`) is used by `build_report.py --real`. It passes if the code hash equals the freeze, or equals the `new` hash of the ONE addendum whose PREREG and `old` hashes match the freeze; anything else is refused. 9 tests (`tests/test_r08_freeze_addendum.py`): unchanged code ok; changed code without addendum refused; recorded addendum accepted and named in the output; any further change after the addendum refused; addendum with another PREREG hash or start hash refused; incomplete addendum refused; edited PREREG refused; the real repository accepted via R08-1. Real build output: "analysis code: matches addendum R08-1 (fix commit 5c94523)".

## c) Value-length check (existing probe tables; POST-UNBLINDING SENSITIVITY, outside Holm; `r08/value_length_check.json`)
- Facts (of 40 per bin) holding the shortest or tied-shortest value of their attribute: **low 0, mid 4, high 40**; mean value tokens 4.12 / 3.62 / 2.25 (value tokens 2 to 3 for every high fact). Mid versus low value length: Mann-Whitney p = 0.12, so mid and low are close in length.
- (a) Rows not stored at init: stored rate at E\*=30 low 0.017/0.028, mid 0.147/0.138, high 0.468/0.353 (paraphrased/templated); by bin 0.022 / 0.142 / 0.416. Facts never stored at init: 80 (40 low, 36 mid, 4 high), E\* rates 0.022 / 0.130 / 0.417.
- (c) H1 per tripling:

| model | log-odds | risk difference |
|---|---|---|
| primary (value_len_z, entity freq, attribute effects) | +0.948 (0.369, 1.528) | +0.143 (0.093, 0.193) |
| plus value-length rank within attribute | +0.989 (0.415, 1.562) | +0.137 (0.095, 0.178) |
| no value-length covariate | +1.793 (1.310, 2.276) | +0.213 (0.175, 0.251) |
| non-shortest facts only (76) | not estimable (separation) | +0.102 (0.054, 0.150) |
| value length = 3 only (44 facts) | +1.592 (1.044, 2.140) | +0.210 (0.156, 0.264) |
| mid vs low only, with value length | not estimable (low has 8 stored rows of 360) | **+0.116 (0.072, 0.160)** (without: +0.125) |
| high vs mid only, with value length | +0.198 (-0.921, 1.316) | **+0.110 (-0.026, 0.244)** (without: +0.302) |
- **How much of H1 survives:** the sign and significance survive every adjustment that could be estimated. Size: the primary log-odds slope is 53% of the unadjusted one (0.95 against 1.79) and the risk-difference slope 67% (0.143 against 0.213). The mid-versus-low contrast, where value lengths are similar, keeps 92% of its size (0.116 against 0.125). The high-versus-mid step keeps 36% (0.110 against 0.302) and its CI includes zero, so the high-bin advantage cannot be separated from value length in this design.

## d) Fixed 3-epoch SFT (POST-HOC SECONDARY; early-stopped SFT remains primary)
- Training: epochs 3, patience off, same config otherwise (its cosine schedule is 3 epochs long, so epochs 2-3 differ from the early-stopped run's 6-epoch schedule). Train-question exact match (seed 0/1/2): fixed-3 **0.87 / 0.84 / 0.84**; early-stopped best.pt 0.13 / 0.56 / 0.15.
- QA exact_value_match (same questions, 3 seeds; base rows unchanged):

| | E0 | E1 | E2 |
|---|---|---|---|
| base zero-shot | 0.008 | 0.016 | 0.006 |
| base 2-shot | 0.005 | 0.002 | 0.002 |
| SFT early-stopped (primary) | 0.280 | 0.234 | 0.015 |
| SFT fixed 3 epochs (post-hoc) | **0.851** | **0.704** | **0.028** |
- Taxonomy counts (R08 classes: correct / right_type_wrong_value / wrong_attribute / out_of_kb_hallucination / format_failure), E0 of 1,008: early-stopped 282 / 288 / 285 / 100 / **53**; fixed-3 858 / 115 / 29 / 4 / **2**. E2 of 540: early-stopped 8 / 185 / 241 / 90 / 16; fixed-3 15 / 323 / 146 / 47 / 9. `format_failure` is now the true-format count only (empty, repeating or value-free). The old label is kept in `error_class_r06`; originals in `real_R06/*.original_taxonomy.csv`.
- Ranking MRR (sentence ranking): early-stopped E0 0.939 / E1 0.932 / E2 0.644; fixed-3 0.994 / 0.995 / 0.569; base zero-shot 0.597 / 0.596 / 0.636, 2-shot 0.437 / 0.442 / 0.507. Value-only MRR: early-stopped 0.621 / 0.589 / 0.444; fixed-3 0.733 / 0.700 / 0.424. On E2 (held-out facts) the fixed-3 sentence MRR (0.569) is below the base zero-shot MRR (0.636).
- **H3 raw counts (E2, 60 facts, majority rule), both SFTs identical:** base correct 0, SFT correct 0; McNemar paired 2x2 both 0 / base-only 0 / SFT-only 0 / neither 60, p = 1; Fisher stored x correct: stored 7 (0 correct, 7 wrong), not stored 53 (0 correct, 53 wrong), p = 1. H3 unsupported under both; H4 0 (0, 0) under both (degenerate). Item-level E2 gain over base 2-shot (secondary): early-stopped +0.013 (0.000, 0.032), fixed-3 **+0.026 (0.007, 0.048)**.

## e) Test-ledger lines now
**4** (probes, QA eval, samples, "post-hoc sensitivity: fixed 3-epoch SFT"). The 4th line records `git dirty: true`: the tracked tree had the uncommitted taxonomy change when the evaluation ran.

## f) Report PDF (`reports/integration/r08/report.pdf`)
- **7 pages** (limit 7). The text no longer contains "PREREG v3": that string is only in the generated `sensitivity.md` and in `src/slm/analysis/sensitivity.py`; I did not edit the code because that would change the pinned analysis-code hash (I-D058). The earlier claim that the report PDF held that text was wrong.
- Added: Appendix A (limitations, continued: value-length confound, early-stopped SFT with a 12-fact validation set and the post-hoc result, 3 seeds / one model size / memorization with the validation-loss numbers, ~3% bank defect rate, weak-diversity facts F040/F087/F021/F067, 12 flagged documents, GEE not a mixed model); Appendix B (original and corrected H1/H2); Appendix C: Table A1 (stored rate at init / epoch 12 / epoch 30 / epoch 60 by exposure bin with chance), Table A2 (H1 under value-length adjustments, plus a sentence with the init-adjusted results), Table A3 (early-stopped vs fixed-3 SFT, H3 counts, item-level E2 gain). Table A4 (error classes and ranking MRR for both SFTs) did not fit in 7 pages and is in `r08/supplementary_tables_R08.md`.
- Every number in the appendices is read from a written file. Because the template linter bans typed digits, nothing was typed into the template.

## g) Unexplained / caveats
- The fixed-3 SFT raises E0/E1 to 0.85 / 0.70 but E2 stays at 0.03 and H3 stays unsupported: the model learns the SFT facts (a memorization of the answers), not retrieval of held-out facts.
- The fixed-3 run uses a 3-epoch cosine schedule, not a truncation of the 6-epoch one; this is a second difference besides early stopping.
- Sentence-ranking MRR on E2 falls after longer SFT (0.569 against 0.636 base); not investigated.
- The report appendices state the confound and the post-hoc status; I did not claim a causal reading of H1 beyond what Table A2 shows.

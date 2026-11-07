# REPORT BACK R06 (real run, override of R05 STOP (c); ran to the real report)

All 13 stages ran. No R06 STOP condition fired. Nothing pushed; main untouched; `.env` not read. Test split touched only through the orchestrator's ledgered stages (3 ledger lines: probes, QA eval, samples).

## a) Tests / lint / git
Full pytest after the real run: 707 passed, 1 failed (a stale assertion that PREREG is unfrozen, test_r03_prereg); fixed to verify the freeze record, that file then passes 4/4 (full suite not rerun after the fix). ruff: all checks passed. Artifacts: `reports/integration/real_R06/` (results tables, report.md/pdf, numbers.json, freeze.json, final_config.json, taxonomy counts), `epoch_descriptive_R06.md`, `heldout_loss_R06.json`.

## b) Freeze
- PREREG v5 + sensitivity paragraph (section 10 item 9) committed first; tree clean; then frozen.
- Recorded commit **e1dce48c98ccad02fcc1b7191b56e748ddae17c7** (clean), PREREG sha256 6fbf098a..., config sha256 890e497106..., **E\* = 30**, `no_val_storage` = **false**, schedule sha256 e412bdb4..., validation-loss-optimal epoch **12**, sweep seed 100.
- I-D055 recorded (override of STOP (c); rule and E\* unchanged).

## c) Per-seed pretraining (cfg06: lr 1e-3, dropout 0.1, batch 16, 12.4M, 60 epochs, 5,940 steps)
| seed | final train loss | final val loss | val loss at 12 / 30 / 60 | train seconds |
|---|---|---|---|---|
| 0 | 0.121 | 4.612 | 2.71 / 3.70 / 4.61 | 447 |
| 1 | 0.124 | 4.597 | 2.72 / 3.68 / 4.60 | 411 |
| 2 | 0.119 | 4.625 | 2.73 / 3.70 / 4.63 | 349 |
No NaN. Checkpoints saved at epochs 1,2,3,5,8,12,16,20,25,30,40,50,60 plus `init` for the probes. Stage wall time 1,232 s. Validation loss at E\* is about 35% above its epoch-12 minimum (disclosed, I-D055).

## d) Probes (TEST probes, 120 facts, 3 seeds; rate +- fact-clustered SE; chance = mean null_stored_rate of the same rows)
| checkpoint | all (chance) |
|---|---|
| init | 0.104 +- 0.017 (0.096) |
| epoch 12 (sensitivity) | 0.220 +- 0.025 (0.071) |
| **epoch 30 = E\*** | **0.199 +- 0.022 (0.079)** |
| epoch 60 (secondary) | 0.218 +- 0.022 (0.081) |

By freq x div at E\*=30 (rate, chance in brackets): high x paraphrased 0.461 (0.052); high x templated 0.406 (0.050); mid x paraphrased 0.150 (0.094); mid x templated 0.133 (0.083); low x paraphrased 0.017 (0.099); low x templated 0.028 (0.093). Epoch 12 and 60 cells: `epoch_descriptive_R06.md` (descriptive, no tests).
- Stop-rule check, init to E\*: paired fact-clustered z = 4.9 / 3.1 / 2.4 for seeds 0 / 1 / 2, so all above 2 SE.
- Oddity: the untrained model already scores 0.22 to 0.36 in the high-frequency cells (0.00 in low), well above chance there (0.05 to 0.06). I did not investigate; it looks like a bias of the untrained scorer toward values of high-frequency entities, and the rule stored = rank 1 and binding > 0 does not remove it.

## e) Hypothesis tests (primary, E\*=30; GEE logit; Holm over H1-H3)
| | estimate | 95% CI | Holm p | status |
|---|---|---|---|---|
| H1 exposure (per tripling, log-odds) | **-0.948** | -1.528, -0.369 | 0.0032 | **significant in the REVERSED direction** (predicted +) |
| H2 diversity x frame (log-odds) | **-1.844** | -2.778, -0.910 | 0.00052 | **significant in the REVERSED direction** |
| H3 E2 gain after SFT (risk diff) | 0 | 0, 0 | 1 | not supported (CI inside margin) |
| H4 (secondary) gain diff paraphrased - templated | 0 | 0, 0 | n/a | effect and CI only |
- Secondary at epoch 60 (outside Holm, marked provisional by the code): H1 -1.164 (-1.707, -0.621), H2 -1.624 (-2.512, -0.737); same reversed direction.
- Sensitivity: results stable across bins vs measured exposure and the token-normalised outcome. Realized diversity replacing div_bin: H2 per SD -0.037 (CI -0.082, 0.008). The Bayesian mixed logit was skipped (ValueError).
- The "reversed" status means the estimate is significant with the opposite sign to the prediction. I read nothing into it beyond reporting it. I did not diagnose the cause. Descriptively, paraphrased and templated cells at E\* are close (e.g. high 0.461 vs 0.406), and the H2 contrast is about canonical vs novel frames within diversity, which I did not break out here.

## f) SFT and QA (E0 / E1 / E2 questions: 336 / 144 / 180; 3 seeds; exact_value_match)
| model | E0 | E1 | E2 |
|---|---|---|---|
| base zero-shot | 0.0079 | 0.0162 | 0.0056 |
| base 2-shot | 0.0050 | 0.0023 | 0.0019 |
| SFT (from E\*=30) | **0.2798** | **0.2338** | **0.0148** |
- SFT: train loss falls (seed 0: 2.83 to 0.12); validation loss best at epoch 1/2/1 (0.773, 0.758, 0.795) and early stopping ended at 3-4 epochs (as per configs/sft.yaml, patience 2).
- Error taxonomy counts (class counts over rows; 3 seeds): SFT E0 correct 282, format_failure 338, out_of_kb_hallucination 100, right_type_wrong_value 288. SFT E2 correct 8, format_failure 257, hallucination 90, right_type_wrong_value 185. Base rows are 80 to 85% format_failure. Full table: `real_R06/error_taxonomy_counts.csv`.
- E2 (held-out facts): SFT 0.0148 against base 0.0019 to 0.0056, so SFT teaches the question format and recalls trained facts (E0/E1) but does not extract facts it never saw as questions.

## g) Held-out loss (val docs only; per-document pooled; `heldout_loss_R06.json`)
| | all 120 val docs | without 5 flagged |
|---|---|---|
| seed 0 epoch 12 / 30 / 60 | 2.707 / 3.693 / 4.611 | 2.706 / 3.696 / 4.610 |
| seed 1 | 2.715 / 3.681 / 4.598 | 2.716 / 3.684 / 4.607 |
| seed 2 | 2.734 / 3.695 / 4.625 | 2.736 / 3.692 / 4.623 |
Excluding the flagged documents (val-0031, 0047, 0070, 0085, 0112) changes the loss by at most 0.009; the trend is unchanged.

## h) Real report
`runs/real/report/report.pdf`: **6 pages** (gate 5-7 passes), banner off after the freeze verified. Copy in `real_R06/report/`. Still missing or unchecked: the report's sensitivity file text still says "PREREG v3 section 10" (stale string); the Bayesian mixed model result; the report's loss-curve and cell tables were not proofread by me; the epoch-12 descriptive table and the flagged-docs loss are in this report back and `reports/integration`, not in the PDF.

## i) STOP conditions
None hit: init-to-E\* rise above 2 SE in all 3 seeds; no NaN; SFT loss decreases; SFT E0 0.28 is neither 0 nor equal to base; the ledger holds 3 entries (probes, QA eval, samples), all from the orchestrator's planned stages.

## j) Deviations / unsure
- The `samples` stage (needed by the report) writes a third ledger line that uses the KB test facts for sample generation; it is an orchestrator stage from R01 but not named in your plan.
- New scripts `scripts/heldout_loss.py` and `scripts/epoch_descriptive.py` (outside the frozen analysis hash) compute the two PREREG item-9 outputs; loss is per document, so it differs slightly from the packed training-log loss.
- H1/H2 reversal and the high init stored rate in high-frequency cells deserve scrutiny before any interpretation; I did not check the probe harness for a cause.
- E\*=30 vs epoch 12: stored rate 0.199 at E\* against 0.220 at 12; the stored rate does not rise past epoch 12 in a meaningful way (0.218 at 60). The rule picked 30 because of smoothing and the 1-SE tolerance on the sweep seed.
- SFT was run only from E\*=30 as agreed.

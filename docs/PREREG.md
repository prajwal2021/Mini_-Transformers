# Preregistration DRAFT v5 (NOT FROZEN)

**Status:** draft. It is frozen at P05, before the full three-seed run and before any real probe or
QA result is seen, by committing it with the hash below. Nothing here has been fitted on real
data: the analysis code was validated on simulated data only
(`reports/tables/analysis_validation.md`).

| field | value |
|---|---|
| Frozen at | `<commit hash>`, `<date>` = TBD (P05) |
| Analysis code commit | `<analysis commit hash>` = TBD (hash of `src/slm/analysis/` + `scripts/run_analysis.py` + `scripts/run_sensitivity.py` at freeze) |
| Equivalence margins | **final researcher-chosen values, not derived from any data**: odds ratio 1.25 per tripling of exposure (+-0.223 log-odds) for H1/H2; +-0.10 risk difference for H3/H4 |
| Training budget | **E\*** from the smoothed validation-probe rule with the chance guard of section 9; the sweep and the three final seeds use the same 60-epoch schedule; the freeze records the sweep seed (100), E\*, the guard flag and the schedule hash |
| Supersedes | draft v4 (R03; E\* was chosen with a 0.01 tolerance on the raw rate, the sweep shared seed 0 with a final seed and the final runs used a 2x longer schedule), draft v3 (A03; margins were placeholders, one checkpoint chosen on validation loss), draft v2 (A02) and v1/v0; v1's labels were wrong (journal/analysis/FAILURES_A.md A-F001) |

Hypothesis labels and wording follow docs/DESIGN.md section 8. Map of outcome, predictors, unit,
test and columns: docs/ANALYSIS_HYPOTHESES.md. Input contracts: docs/ANALYSIS_INPUT.md.

## 0. Deviations from DESIGN.md (to fold into DESIGN v1.3)

| # | DESIGN.md | This preregistration | Reason |
|---|---|---|---|
| D1 | H4 is a hypothesis of the preregistered investigation (section 8) | **H4 is pre-registered as SECONDARY**: effect size and CI are reported, with no significance claim and no place in the Holm family | Power is 0.33 at 120 facts (60 held-out facts, the KB split is frozen); a test that cannot detect the planted effect would mislead |
| D2 | no multiple-comparison rule | Holm over H1, H2, H3 (m = 3) | PREREG v0 stated Holm; with H4 secondary the family has three tests |
| D3 | `(1 \| fact) + (1 \| template) + (1 \| seed)` random intercepts | logistic GEE with fact clusters; seed fixed; template as within-frame fixed dummies | three seeds cannot estimate a variance; templates are nested in frames; GEE gives valid p-values (A-D001, A-D003) |
| D4 | released checkpoint = earliest checkpoint within one point of the best validation-probe ranking accuracy (section 5) | **one analysed checkpoint, E\***: the earliest sweep checkpoint whose 3-checkpoint-smoothed VALIDATION-probe stored rate is within 1 SE of the chosen config's best (section 9), with a chance guard (E\* = the epoch of minimum validation loss when no storage is detectable on validation). The sweep uses seed 100, which is not a final seed, and the same 60-epoch schedule as the final runs, so E\* is exact, not a proxy. E\* is the analysed checkpoint, the SFT starting point and the source of `stored_pretrain`; epoch 60 is analysed as a secondary analysis | v3 chose the epoch count on validation loss, which on a corpus of about 0.75M tokens bottoms out early (overfitting) while fact storage keeps improving (I-D039); the R03 rule picked E\*=1 on noise when every stored rate was at chance (I-D047). DESIGN section 5 selects by validation probes. Test probes never select anything |
| D5 | (silent) | fact-level aggregation, comparator and exposure coding are fixed in section 4 | DESIGN leaves them open |

## 1. Research question

How do exposure frequency and paraphrase diversity during pretraining determine whether a small
Transformer stores a fact, and does supervised fine-tuning make stored facts retrievable as
answers to questions about facts it never saw in fine-tuning? (DESIGN section 8)

## 2. Hypotheses

| id | DESIGN wording (verbatim) | test | status |
|---|---|---|---|
| H1 | "storage rate rises with log exposure." | `freq_c` coefficient of the storage model, predicted + | **confirmatory, primary** |
| H2 | "at matched exposure, paraphrased facts generalize better to *novel-frame* probes; templated facts do better only on *canonical-frame* probes." | `div_c:frame_c` coefficient, predicted + | confirmatory |
| H3 | "E2 QA accuracy after SFT >> base, but bounded by pre-SFT storage (P(correct \| stored) >> P(correct \| not stored))." | McNemar (base_2shot vs SFT) AND Fisher (stored x correct) on E2 facts; both must reject | confirmatory |
| H4 | "the extraction gain is larger for paraphrased facts (cf. Allen-Zhu & Li, *Physics of LMs 3.1*)." | difference in per-fact gain, paraphrased minus templated, with a bootstrap CI | **secondary: effect and CI only** |

Holm family: H1, H2, H3 (m = 3). The "templated facts do better only on canonical-frame probes"
clause of H2 is judged descriptively from the simple-effect CIs.

## 3. Primary outcome

**The primary outcome is `stored` (the correct value ranks first among the six same-attribute
values and its binding score is above zero), measured on the test probes at the final pretraining
checkpoint of each seed and analysed per fact x seed x prompt variant; the primary confirmatory
estimate is H1, the log-odds increase in `stored` per tripling of measured exposure, from a
logistic GEE with fact clusters.**

## 4. Operational definitions

- **Stored (probe level):** `rank == 1 and binding_score > 0` (DESIGN section 6).
- **Fact-level stored:** stored on at least 2 of the 3 test probes within a seed; a fact is stored
  when this holds in a majority of seeds. The same "more than half" rule is applied at both levels.
  Sensitivity rules: `any` (at least 1) and `all`.
- **Fact-level QA-correct:** exact match on at least 2 of the 3 E2 phrasings within a seed, in a
  majority of seeds; computed separately for each model on the same items. Sensitivity: `any`,
  `all`.
- **Comparator "base" for H3/H4:** `base_2shot` (fixed 2-shot pretrained model, same prompt
  format as SFT). `base_0shot` is reported as a secondary comparison.
- **Exposure:** measured train mentions of the value (string-match count in train documents; DESIGN
  section 2.1). `freq_c` = log3(measured mentions) centred on its mean (one unit = a tripling).
  Until the P03 counts exist the design-bin code -1/0/+1 is used (bins of about 5/15/45
  documents); the switch to log3(measured mentions) is made, and logged, before the freeze.
- **Diversity:** assigned `div_bin`; `div_c` = +0.5 paraphrased, -0.5 templated. **Realized
  diversity** (`data/bank/realized_diversity.csv`, one row per fact) is used only in the
  sensitivity analyses; it enters as `rdiv_z` = z-score of 1 - `mean_pairwise_jaccard`.
- **Frame:** `probe_frame`; `frame_c` = +0.5 novel, -0.5 canonical.
- **The checkpoint:** the checkpoint at epoch E\* of each seed (section 9, D4). It is the
  checkpoint analysed for H1/H2, the SFT starting point, and the source of `stored_pretrain` for
  H3/H4. Other checkpoints are used only for learning curves, acquisition steps and the secondary
  epoch-60 secondary analysis (section 9).
- **Chance baseline:** every stored rate is reported together with `null_stored_rate` (the same
  procedure with a pseudo-true value of another entity, E-D012) and with the stored rate of the
  `init` checkpoint (the untrained model of the same seed). A stored rate is read as storage only
  relative to those two references.
- **Test probes and test questions only.** Validation probes never enter any test.

## 5. Exact tests

### H1, H2 (storage; DESIGN Part A)

```text
stored ~ freq_c * div_c * frame_c + C(seed) + within-frame template dummies
         + value_len_z + entity_freq_z + C(attribute_id)
```

- Estimator: logistic GEE (`statsmodels`), Binomial/logit, clusters = `fact_id`, exchangeable
  working correlation, bias-reduced (Mancl-DeRouen) sandwich covariance; Wald t with
  (facts - parameters) degrees of freedom; two-sided p; 95% CI on the log-odds scale.
- H1 = `freq_c`; H2 = `div_c:frame_c`. Predicted sign + for both.
- Effect sizes: log-odds and odds ratios; risk differences with 95% percentile CIs from a stratified
  fact bootstrap (2000 resamples, fixed seed). The bootstrap describes effect size and is not used
  for the tests.
- Fallback ladder, applied in this order and never chosen by p-value: (1) primary fit; (2)
  independence working correlation; (3) no optional covariates. A fit that fails to converge, is
  non-finite or shows separation (|coefficient| or SE above 8 log-odds) counts as failed. If all
  fail, H1/H2 are reported as non-informative (p = 1, no claim) together with the table of design
  cells whose outcome is all 0 or all 1.

### H3 (extraction; DESIGN Part B), E2 held-out facts only; unit = fact

- **H3a:** exact McNemar test, base_2shot vs SFT, on the same facts; effect = accuracy gain.
- **H3b:** Fisher exact test on stored x correct(SFT); effect = P(correct | stored) - P(correct |
  not stored).
- **H3** is an intersection-union test: supported only if both reject with positive effects; its
  p-value is max(p_a, p_b).
- CIs: stratified fact-bootstrap percentile intervals (1000 resamples, fixed seed).

### H4 (secondary)

Mean per-fact gain (SFT correct minus base_2shot correct) for paraphrased minus templated facts,
with a stratified fact-bootstrap 95% CI and the per-condition McNemar tests and 2x2 tables DESIGN
lists. A permutation p-value (stratified by `freq_bin`) is computed but is descriptive: no
significance claim is made.

## 6. Multiple comparisons

Holm step-down at family-wise alpha 0.05 across H1, H2, H3 (m = 3). H4 and everything in sections
10 and 11 are outside the family and are labelled secondary or exploratory wherever reported. If
H3 data are missing at analysis time the pipeline reports provisional H1/H2 values with H3's
p-value set to 1.

## 7. Decision rules, null and inconclusive results (per hypothesis)

Common rules. **Supported:** Holm-adjusted p <= 0.05 and the effect has the predicted sign.
**Reversed:** Holm-adjusted p <= 0.05 with the opposite sign (reported as a refutation of the
predicted direction). **Not supported:** Holm-adjusted p > 0.05; never re-fitted under other
specifications. **"No meaningful effect"** is claimed only if the whole 95% CI lies inside the
pre-declared margin (header; chosen by the researchers, not derived from data); otherwise the
result is **inconclusive**. No "no effect" claim is made from a non-significant p-value or a CI
that merely includes zero.

**Interpretation of nulls.** A null (not supported) is interpreted through its confidence interval
and never through its p-value alone: equivalence ("no meaningful effect") is concluded only when
the whole CI lies inside the margins above; a CI that crosses a margin is inconclusive and is
reported as such, whatever the p-value. The same applies to the secondary epoch-60 analysis, which
cannot rescue or overturn a primary result.

| id | not supported means | no meaningful effect (CI inside margin) | inconclusive |
|---|---|---|---|
| H1 | exposure did not raise storage detectably | CI inside +-0.223 log-odds per tripling | CI extends beyond the margin on either side |
| H2 | the paraphrased advantage did not differ by frame detectably | interaction CI inside +-0.223 | wider CI. Weak manipulation biases this toward the null (section 10) |
| H3 | SFT did not improve E2 over base_2shot (H3a), or extraction is not tied to storage (H3b); report which component failed | gain and stored-vs-not CIs inside +-0.10 | CI crossing zero and the margin; E2 has about 60 facts. A degenerate 2x2 (all or no facts stored) is non-informative, not a null |
| H4 | no claim is made | no claim is made | report the effect and CI; the CI is expected to be wide (30 facts per condition) |

Failed analysis (not a scientific null): a table fails its input contract; every fit in the ladder
fails; or a design cell has stored rate 0 or 1, in which case the affected test is reported as
non-informative with the cell table.

## 8. Exclusion rules

- Exclude malformed KB records, failed-validator records, and documents failing the generation
  validator.
- Exclude val/test documents from measured exposure.
- No probe row or question is excluded for being an outlier or for model output quality; missing
  outputs are reported, not imputed.
- Do not use test probes, test loss, or E2 results for any selection.
- Do not post hoc change cell membership, probe templates, model seeds, covariates, the
  checkpoint, the aggregation rules, or the comparator.
- Report residual contradiction-audit failures and missing probe outputs.

## 9. Training budget E\* and checkpoint (D4; DESIGN section 5 selects by validation probes)

**Schedule (identical everywhere).** The sweep runs and the three final seeds (0, 1, 2) all use the same 60-epoch schedule: cosine decay to 10% of the peak, warmup 5% of the optimiser steps (at least 10, at most half the run), validation loss 40 times and train loss 200 times per run, checkpoints at epochs 1, 2, 3, 5, 8, 12, 16, 20, 25, 30, 40, 50, 60. The freeze records the sha256 of this schedule. The final runs are not longer than the sweep: E\* is read off the very schedule the final seeds follow.

**Sweep (one seed, seed 100, which is not a final seed).** Stage 1: learning rate {3e-4, 6e-4, 1e-3} x dropout {0, 0.1} at batch size 32 (6 configs). Stage 2: the best stage-1 config at batch size 16, and (the `sizing` stage) the same config at the 8/8/512 size (about 27.6M parameters) against the 12M size. At every checkpoint the validation loss and the **validation-probe stored rate** (validation split of the probes only, 2 probes per fact) are computed, plus the untrained `init` model. No test probe is scored in the sweep. After the first stage-1 run the wall-clock time gives an ETA for the rest; the sweep aborts if the projection exceeds 3 hours.

**Rule (applied identically to the config choice, the batch size and the model size).** (1) For each config the stored rate is smoothed with a centred 3-checkpoint moving average (shortened at the two ends); its standard error is the mean of the standard errors in the window, each being the fact-clustered SE of that checkpoint's probe rows (the two probes of a fact are not independent). (2) A config's score is its best smoothed rate; the configs whose score is within 1 SE of the best score are near-ties, and among them the config with the lowest validation loss wins (the first in grid order on an exact tie). (3) **E\*** = the earliest checkpoint of the chosen config whose smoothed rate is within 1 SE of that config's best smoothed rate. (4) **Chance guard.** If the chosen config's best smoothed rate is not above the `init` stored rate by more than 2 SE, no storage is detectable on validation: **E\*** is then the epoch of minimum validation loss of the chosen config, the decision table prints a WARNING, and the result and the freeze record carry the flag `no_val_storage = true`. (5) The validation-loss-optimal epoch is reported next to E\* in every case (`reports/tables/sweep_decision.md` lists every config at every checkpoint). Outside the guard, validation loss never chooses E\*. The rule was fixed before any real run and is covered by unit tests (plateau start, at-chance guard, determinism).

**Final runs and analyses.** Seeds 0, 1 and 2 train with the chosen config for 60 epochs. **Primary analysis (H1-H4, SFT start, `stored_pretrain`): the checkpoint at E\*.** **Secondary analysis (outside the Holm family, labelled secondary): H1 and H2 on the same test probes at epoch 60.** Learning-curve figures use all checkpoints. The secondary analysis cannot rescue or overturn a primary result.

**Freeze.** The freeze records the configuration hash, the sweep seed, E\*, the guard flag, the schedule hash, the model size, the learning rate, dropout and batch size next to the hash of this file and the git commit. It **refuses to freeze if the git working tree is dirty (the PREREG file itself excepted), or if a test-split probe row, a QA test prediction file or a test-split entry of the test-access ledger already exists**. The commit recorded is therefore the clean commit that produced the sweep.


## 10. Pre-registered sensitivity analyses (`scripts/run_sensitivity.py`; none in the family)

Each re-estimates H1/H2 or H3/H4 under one change and reports estimate and CI beside the primary:
1. aggregation rule `any` / `majority` / `all` (H3, H4);
2. exposure coding: design bins vs log3(measured mentions) (H1, H2);
3. with and without within-frame template terms (H1, H2);
4. GEE vs the conditional Bayesian mixed logit (fact and fact-by-seed intercepts; point estimates);
5. token-normalised outcome `stored_tokennorm` as the secondary outcome (H1, H2);
6. comparator `base_0shot` (H3, H4);
7. complete-separation report: design cells with outcome all 0 or all 1, and the fallback used;
8. **realized diversity** (`rdiv_z`): the model with `rdiv_z` replacing `div_bin`, and with both.
   Reported with H2 converted to the nominal contrast. **A weak manipulation (a `div_bin` that only
   partly separates realized diversity) biases the nominal H2 toward zero**, so nominal H2 is a lower
   bound on the effect of realized diversity; this analysis shows how H2 changes. It is
   pre-registered to avoid a post hoc explanation of a weak H2; it does not replace the primary test.

9. **Validation-loss-optimal epoch and held-out loss (R06; descriptive, outside the Holm family).** The primary analysis is at E\* = 30 (the validation-probe rule of section 9) and the secondary at epoch 60. Validation loss of the chosen sweep configuration is lowest at epoch 12 and is 34.8% higher at E\* = 30 because the model memorizes; this is disclosed, not corrected (E\* is not changed). Probes at the validation-loss-optimal epoch (12, as recorded by the freeze) are reported descriptively beside the secondary epoch-60 analysis: stored rate by freq x div with the chance rate, no hypothesis tests. Held-out loss is reported on all validation documents and on validation documents excluding those flagged `leak_flag` or `meta_flag` in `data/corpus/manifest.json` (val-0031, val-0047, val-0070, val-0085, val-0112).

## 11. Exploratory (not corrected, not confirmatory)

Learning curves with fact-bootstrap bands and per-fact acquisition steps; freq x div and the
three-way interaction; item-level (clustered) QA models; E0 and E1 results; relationship-direction
asymmetry; attention inspection; two-hop probes; free-generation galleries; the temperature sweep.

## 12. Power and validation (simulated data; planned size 120 facts, E2 = 60 facts)

From `reports/tables/analysis_validation.md` (400 replicates per scenario, 500 per null). The
planted effects are assumptions, so these are sensitivity numbers, not forecasts.

| id | Holm power at 20 facts/cell | at 10 / 30 facts per cell | status |
|---|---|---|---|
| H1 | 1.00 | 0.96 / 1.00 | confirmatory, adequately powered |
| H2 | 0.87 | 0.44 / 0.96 | confirmatory, adequately powered; falls to 0.44 at half the size |
| H3 | 0.97 | 0.64 / 1.00 | confirmatory, adequately powered under the planted effect |
| H4 | 0.33 raw (no Holm) | 0.10 / 0.46 | **secondary; underpowered by design** |

False positives (alpha 0.05, 500 replicates, all effects zero): H1 0.034, H2 0.042 (nominal);
H3 and H4 are valid but conservative (0.00); family-wise 0.076 before and 0.026 after Holm.
Weak manipulation (nominal H2, power): 0.80 / 0.84 at full strength, 0.49 / 0.41 at strength 0.6,
0.25 / 0.14 at 0.3, while the realized-diversity estimate stays near 0.78 with power about 0.80.
H3/H4 bootstrap CIs under-cover (0.89-0.92).

## 13. Open items before the freeze

1. Set the equivalence margins (placeholders above; the 0.10 risk-difference margin is mine).
2. Join measured `train_mentions` and switch `freq_c` to log3(mentions); confirm the realized
   diversity column definitions with the bank stream (this draft assumes `mean_pairwise_jaccard`
   is the mean pairwise 3-gram Jaccard similarity of a fact's mentions, higher = more similar).
3. Confirm the eval stream emits 3 test probes per fact (1 canonical + 2 novel here; its docs say
   `test-canon`, `test-n1..n3`) and the QA result table columns of ANALYSIS_INPUT section 2.
4. Freeze the epoch count from the sweep; record the sweep validation losses in `run_facts.json`.

## 14. Deviations log

| date | deviation | reason | impact |
|---|---|---|---|
| | | | |

<!-- FREEZE:BEGIN -->
## Freeze record

| field | value |
|---|---|
| PREREG sha256 (this file without this block) | `6fbf098a29a5828fc3996368dd21fe5f9382c6dbef198282b2bddf87351ec5fa` |
| git commit | `e1dce48c98ccad02fcc1b7191b56e748ddae17c7` (branch `integration`, working tree clean) |
| analysis code sha256 | `8a6fab562f6ff28d48333d2364de25449dd3a6fe292c888751571f3e69925cd0` |
| frozen at (UTC) | 2026-11-07T01:37:24+00:00 |
| config_sha256 | `890e497106540ac2d78a123927d38fdc9057657e46b53346802f0faf32bc94cd` |
| config_file | `configs/real.yaml` |
| e_star | `30` |
| no_val_storage | `False` |
| sweep_seed | `100` |
| schedule_sha256 | `e412bdb412bc62b727d7a8d56eef6a04c78e436cf5d5d9d1650d84ad2326e06a` |
| total_epochs | `60` |
| model_size | `small` |
| lr | `0.001` |
| dropout | `0.1` |
| batch_size | `16` |
| val_loss_optimal_epoch | `12` |
| test evidence at freeze | none (no test probe, QA test or ledger entry) |

```json
{
 "analysis_code_sha256": "8a6fab562f6ff28d48333d2364de25449dd3a6fe292c888751571f3e69925cd0",
 "extra": {
  "batch_size": 16,
  "config_file": "configs/real.yaml",
  "config_sha256": "890e497106540ac2d78a123927d38fdc9057657e46b53346802f0faf32bc94cd",
  "dropout": 0.1,
  "e_star": 30,
  "lr": 0.001,
  "model_size": "small",
  "no_val_storage": false,
  "schedule_sha256": "e412bdb412bc62b727d7a8d56eef6a04c78e436cf5d5d9d1650d84ad2326e06a",
  "sweep_seed": 100,
  "total_epochs": 60,
  "val_loss_optimal_epoch": 12
 },
 "frozen_at": "2026-11-07T01:37:24+00:00",
 "git": {
  "branch": "integration",
  "commit": "e1dce48c98ccad02fcc1b7191b56e748ddae17c7",
  "dirty": false
 },
 "ledger": "C:\\Users\\prajsrin\\Documents\\slm-integration\\reports\\test_access_log.jsonl",
 "prereg_file": "C:\\Users\\prajsrin\\Documents\\slm-integration\\docs\\PREREG.md",
 "prereg_sha256": "6fbf098a29a5828fc3996368dd21fe5f9382c6dbef198282b2bddf87351ec5fa",
 "run_dir": "C:\\Users\\prajsrin\\Documents\\slm-integration\\runs\\real"
}
```
<!-- FREEZE:END -->

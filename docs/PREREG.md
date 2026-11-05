# Preregistration DRAFT v3 (NOT FROZEN)

**Status:** draft. It is frozen at P05, before the full three-seed run and before any real probe or
QA result is seen, by committing it with the hash below. Nothing here has been fitted on real
data: the analysis code was validated on simulated data only
(`reports/tables/analysis_validation.md`).

| field | value |
|---|---|
| Frozen at | `<commit hash>`, `<date>` = TBD (P05) |
| Analysis code commit | `<analysis commit hash>` = TBD (hash of `src/slm/analysis/` + `scripts/run_analysis.py` + `scripts/run_sensitivity.py` at freeze) |
| Equivalence margins | PLACEHOLDERS, set at the freeze: odds ratio 1.25 (+-0.223 log-odds) for H1/H2; +-0.10 risk difference for H3/H4 |
| Supersedes | draft v2 (A02) and v1/v0; v1's labels were wrong (journal/analysis/FAILURES_A.md A-F001) |

Hypothesis labels and wording follow docs/DESIGN.md section 8. Map of outcome, predictors, unit,
test and columns: docs/ANALYSIS_HYPOTHESES.md. Input contracts: docs/ANALYSIS_INPUT.md.

## 0. Deviations from DESIGN.md (to fold into DESIGN v1.3)

| # | DESIGN.md | This preregistration | Reason |
|---|---|---|---|
| D1 | H4 is a hypothesis of the preregistered investigation (section 8) | **H4 is pre-registered as SECONDARY**: effect size and CI are reported, with no significance claim and no place in the Holm family | Power is 0.33 at 120 facts (60 held-out facts, the KB split is frozen); a test that cannot detect the planted effect would mislead |
| D2 | no multiple-comparison rule | Holm over H1, H2, H3 (m = 3) | PREREG v0 stated Holm; with H4 secondary the family has three tests |
| D3 | `(1 \| fact) + (1 \| template) + (1 \| seed)` random intercepts | logistic GEE with fact clusters; seed fixed; template as within-frame fixed dummies | three seeds cannot estimate a variance; templates are nested in frames; GEE gives valid p-values (A-D001, A-D003) |
| D4 | released checkpoint = earliest checkpoint within one point of the best validation-probe ranking accuracy (section 5) | **one checkpoint**: the final checkpoint of each seed, after a fixed number of epochs chosen on validation loss in the sweep; it is the analysed checkpoint, the SFT starting point and the source of `stored_pretrain` | simplicity and no selection on probes; one checkpoint cannot leak test probes |
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
- **The checkpoint:** the final checkpoint of each seed, after the number of epochs fixed on
  validation loss in the sweep (D4). It is the checkpoint analysed for H1/H2, the SFT starting
  point, and the source of `stored_pretrain` for H3/H4. Earlier checkpoints are used only for
  learning curves and acquisition steps.
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
pre-declared margin (placeholders in the header); otherwise the result is **inconclusive**. No
"no effect" claim is made from a non-significant p-value or a CI that merely includes zero.

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

## 9. Checkpoint (replaces DESIGN's val-probe selection rule; D4)

The final checkpoint of each seed after the fixed number of epochs chosen on validation loss in the
sweep. No probe is used to choose it.

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

# Preregistration DRAFT v1 (NOT FROZEN)

**Status:** draft. It is frozen at P05, before the full three-seed run and before any real probe
result is seen, by committing it with the hash below. Nothing in this file has been fitted on real
data: the analysis code was validated on simulated data only (`reports/tables/analysis_validation.md`).

| field | value |
|---|---|
| Frozen at | `<commit hash>`, `<date>` = TBD (P05) |
| Analysis code commit | `<analysis commit hash>` = TBD (git hash of `src/slm/analysis/` + `scripts/run_analysis.py` at freeze) |
| Supersedes | draft v0 (same path; see git history) |

## 1. Research question

How do exposure frequency and paraphrase diversity during pretraining determine whether a small
Transformer stores a fact, and does supervised fine-tuning make stored facts retrievable as
answers to questions about facts it never saw in fine-tuning? (docs/DESIGN.md section 8)

## 2. Hypotheses

### Storage family (confirmatory; implemented in `slm.analysis`)

| id | hypothesis | coefficient | predicted sign |
|---|---|---|---|
| H1 | Storage rate rises with log exposure | `freq_c` (log-odds per tripling of exposure) | + |
| H2 | At equal exposure, paraphrased facts are stored more often than templated ones (averaged over regimes) | `div_c` (paraphrased - templated) | + |
| H3 | The exposure slope differs by diversity condition | `freq_c:div_c` | two-sided (no direction predicted) |
| H4 | Storage is lower under novel-wording probes than under iid-wording probes | `regime_c` (novel - iid) | - |

### Extraction family (confirmatory; analysis code NOT part of A01, to be added before freeze)

- **H5:** E2 QA accuracy after SFT is much greater than base, and P(correct | stored) is much
  greater than P(correct | not stored) (DESIGN H3).
- **H6:** The extraction gain is larger for paraphrased facts (DESIGN H4).

Naming note: DESIGN.md calls the extraction hypotheses H3/H4 and puts the diversity-by-frame
test inside H2. This draft re-labels so that H1-H4 are the four storage tests the pipeline
implements. The diversity-by-regime interaction (`div_c:regime_c`, DESIGN's "paraphrasing helps
on novel wording") is reported as **exploratory** unless the team promotes it to the family
before freeze (open item).

## 3. Primary outcome

**The primary outcome is `stored` (the correct value ranks first among the six same-attribute
values and its binding score is above zero), measured on the test probes at the final pretraining
checkpoint and analysed per fact x seed x prompt variant x regime; the primary confirmatory
estimate is H1, the log-odds increase in `stored` per tripling of measured exposure, from a
logistic GEE with fact clusters.**

## 4. Operational definitions

- **Stored:** `rank == 1 and binding_score > 0` (DESIGN.md section 6).
- **Exposure bin:** assigned `freq_bin` (low ~5, mid ~15, high ~45 train documents); coded
  `freq_c` = -1, 0, +1. Measured string-match exposure is a manipulation check; if measured counts
  break the roughly 3x spacing, switch to a numeric log-exposure covariate (requires a logged
  amendment before freeze).
- **Diversity:** assigned `div_bin`; `div_c` = +0.5 paraphrased, -0.5 templated.
- **Regime:** `iid` or `novel` probe wording; `regime_c` = +0.5 novel, -0.5 iid.
- **Primary checkpoint:** the largest checkpoint present in all three seeds (end of training).
  The released-checkpoint selection rule (section 9) uses validation probes and is separate.
- **Test probes** only; validation probes never enter any test.

## 5. Exact tests

Model (fitted once, at the primary checkpoint, all seeds pooled):

```text
stored ~ freq_c * div_c * regime_c + C(seed) + C(prompt_variant)
         + value_len_z + entity_freq_z + C(attr_type)
```

- Estimator: logistic GEE (`statsmodels` `GEE`, Binomial/logit), clusters = `fact_id`,
  exchangeable working correlation, bias-reduced (Mancl-DeRouen) sandwich covariance.
- Inference per coefficient: Wald t with (number of facts - number of parameters) degrees of
  freedom; two-sided p-value; 95% CI on the log-odds scale (odds ratios reported).
- Family tests are the coefficients named in section 2, taken from the full-factorial model above
  (effect coding makes each an average effect).
- Effect sizes: log-odds (and odds ratio) with 95% CI; plus risk differences in stored rate with
  95% percentile CIs from a fact-level stratified cluster bootstrap (2000 resamples, fixed
  seed). The bootstrap CIs describe effect sizes and are not used for the tests.
- Seeds: 3 model seeds are too few for a variance component, so seed is a fixed nuisance factor
  and seed-to-seed dependence within a fact is absorbed by the fact clusters. Seed-by-fact
  variability is part of the within-cluster correlation.
- Sensitivity (not confirmatory, no tests): conditional mixed logit with fact and fact-by-seed
  random intercepts (`BinomialBayesMixedGLM`, variational Bayes), point estimates only.
- Convergence rule: if the primary fit does not converge, refit in this fixed order and log it:
  (1) independence working correlation, (2) drop the optional covariates. The order is not
  decided by p-values.

## 6. Multiple comparisons

Holm step-down at family-wise alpha = 0.05 across the four storage tests H1-H4 (m = 4). The
extraction tests H5-H6 form a second family (Holm, m = 2) because they answer a separate
question on separate data. Exploratory analyses (section 10) are not corrected and are labelled
exploratory wherever reported.

## 7. Decision rules, and what counts as a null or failed result

- **Supported:** Holm-adjusted p <= 0.05 and the effect has the predicted sign (H3: either sign;
  report the direction).
- **Not supported (null):** Holm-adjusted p > 0.05. Reported as a null result, never re-fit
  with other specifications to "rescue" it.
- **Reversed:** Holm-adjusted p <= 0.05 with the opposite sign to the prediction. Reported as a
  refutation of the predicted direction.
- **Inconclusive vs. evidence of no effect:** a null is called "evidence of no meaningful
  effect" only if the whole 95% CI lies within +-log(1.25) = +-0.223 log-odds (smallest effect
  of interest, to be confirmed by the team before freeze); otherwise it is "inconclusive".
  Power at the planned size is low for H3 (see validation report), so a null H3 will normally be
  inconclusive.
- **Failed analysis (not a scientific null):** the probe table fails the input contract; the
  primary model fails to converge under every fallback; or a design cell has stored rate 0 or 1
  (complete separation / floor / ceiling), in which case the affected test is reported as
  non-informative together with the cell table, and the DESIGN.md floor/ceiling contingency
  (use early checkpoints for the acquisition curves) applies to descriptives only.

## 8. Exclusion rules

- Exclude malformed KB records, failed-validator records, and documents failing the generation
  validator.
- Exclude val/test documents from measured exposure.
- No probe row is excluded for being "an outlier" or for model output quality; missing probe
  outputs are reported, not imputed.
- Do not use test probes, test loss, or E2 results for checkpoint selection.
- Do not post hoc change cell membership, probe templates, model seeds, covariates, or the
  primary checkpoint.
- Report any residual contradiction-audit failures and any missing probe outputs.

## 9. Checkpoint selection (release only)

Select the earliest checkpoint within one percentage point of the maximum validation-probe
ranking accuracy. Validation probes only. This rule picks the released model; it does not change
the primary analysis checkpoint (section 4).

## 10. Exploratory (not corrected, not confirmatory)

Diversity-by-regime and frequency-by-regime interactions; the full 3-way interaction; learning
curves and per-fact acquisition steps; relationship-direction asymmetry; attention inspection;
two-hop probes; free-generation galleries; temperature sweep; the mixed-model sensitivity fit.

## 11. Validation of the analysis code (simulated data only)

Recovery of planted effects, null false-positive rate (1000 replicates) and power at the planned
size are in `reports/tables/analysis_validation.md`. At the planned 20 facts per cell the
analysis has high power for H1 and H4, about 0.9 for H2 and about 0.3 for H3 under the planted
effects (which are assumptions, not predictions).

## 12. Deviations log

| date | deviation | reason | impact |
|---|---|---|---|
| | | | |

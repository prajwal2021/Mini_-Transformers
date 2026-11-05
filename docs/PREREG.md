# Preregistration DRAFT v2 (NOT FROZEN)

**Status:** draft. It is frozen at P05, before the full three-seed run and before any real probe or
QA result is seen, by committing it with the hash below. Nothing here has been fitted on real
data: the analysis code was validated on simulated data only
(`reports/tables/analysis_validation.md`).

| field | value |
|---|---|
| Frozen at | `<commit hash>`, `<date>` = TBD (P05) |
| Analysis code commit | `<analysis commit hash>` = TBD (hash of `src/slm/analysis/` + `scripts/run_analysis.py` at freeze) |
| Equivalence margins | PLACEHOLDERS, to be set at the freeze: odds ratio 1.25 (+-0.223 log-odds) for H1/H2; +-0.10 risk difference for H3/H4 |
| Supersedes | draft v1 (A01) and v0; the A01 hypothesis labels were wrong (journal/analysis/FAILURES_A.md A-F001) |

Hypothesis labels, wording and tests follow docs/DESIGN.md section 8 exactly. The full map (outcome,
predictors, unit, test, columns, ambiguities) is docs/ANALYSIS_HYPOTHESES.md.

## 1. Research question

How do exposure frequency and paraphrase diversity during pretraining determine whether a small
Transformer stores a fact, and does supervised fine-tuning make stored facts retrievable as
answers to questions about facts it never saw in fine-tuning? (DESIGN section 8)

## 2. Hypotheses (DESIGN.md wording, verbatim)

| id | part | DESIGN wording | test | status |
|---|---|---|---|---|
| H1 | A, storage | "storage rate rises with log exposure." | `freq_c` coefficient of the storage model, predicted + | **confirmatory (primary)** |
| H2 | A, storage | "at matched exposure, paraphrased facts generalize better to *novel-frame* probes; templated facts do better only on *canonical-frame* probes." | `div_c:frame_c` coefficient, predicted + | confirmatory |
| H3 | B, extraction | "E2 QA accuracy after SFT >> base, but bounded by pre-SFT storage (P(correct \| stored) >> P(correct \| not stored))." | McNemar (base vs SFT) and Fisher (stored x correct) on E2 facts; both must reject | confirmatory |
| H4 | B, extraction | "the extraction gain is larger for paraphrased facts (cf. Allen-Zhu & Li, *Physics of LMs 3.1*)." | permutation test on per-fact gain, paraphrased vs templated | confirmatory, **underpowered** (section 11) |

The "templated facts do better only on canonical-frame probes" clause of H2 is judged descriptively
from the simple-effect CIs (diversity effect within each frame); the confirmatory test is the
interaction.

## 3. Primary outcome

**The primary outcome is `stored` (the correct value ranks first among the six same-attribute
values and its binding score is above zero), measured on the test probes at the final pretraining
checkpoint and analysed per fact x seed x prompt variant; the primary confirmatory estimate is H1,
the log-odds increase in `stored` per tripling of measured exposure, from a logistic GEE with fact
clusters.**

## 4. Operational definitions

- **Stored:** `rank == 1 and binding_score > 0` (DESIGN section 6), per probe.
- **Exposure:** measured train mentions of the value (string-match count in train documents;
  DESIGN section 2.1: "Analysis uses **measured** exposure"). Coding: `freq_c` = log3(measured
  mentions) centred on its mean once the P03 counts exist and are joined as `train_mentions`
  (one unit = a tripling). Until then `freq_c` is the design-bin code -1/0/+1 (bins of about
  5/15/45 documents are a factor of 3 apart). The switch is made before the freeze and logged;
  after the freeze it does not change.
- **Diversity:** assigned `div_bin`; `div_c` = +0.5 paraphrased, -0.5 templated.
- **Frame:** `probe_frame`; `frame_c` = +0.5 novel, -0.5 canonical. Not the document-level
  iid/novel regime, which is used by no hypothesis.
- **Primary checkpoint (H1, H2):** the largest test checkpoint present in all seeds (end of
  training). The released-checkpoint rule (section 9) is separate.
- **Fact-level stored status (H3):** from `stored_pretrain`, the stored status of the pretrained
  checkpoint that the SFT started from, same seed; a fact is stored when more than half of its
  seeds say stored. The per-seed aggregation over probes is set by the eval stream and fixed here
  before the freeze (proposal: >= 2 of 3 test probes) **[OPEN]**.
- **Fact-level QA correctness (H3, H4):** a fact is correct for a model when more than half of its
  E2 items (seeds x questions) are exact matches. Comparator for "base": the fixed 2-shot pretrained
  model; zero-shot is reported alongside **[OPEN: confirm comparator]**.
- **Test probes / test questions only.** Validation probes never enter any test.

## 5. Exact tests

### H1, H2 (storage; DESIGN Part A)

```text
stored ~ freq_c * div_c * frame_c + C(seed) + within-frame template dummies
         + value_len_z + entity_freq_z + C(attribute_id)
```

DESIGN's model has random intercepts for fact, template and seed; they are implemented as fact
clusters (GEE) and fixed template/seed terms because three seeds cannot estimate a variance and
templates are nested in frames (A-D001, A-D003).

- Estimator: logistic GEE (`statsmodels`, Binomial/logit), clusters = `fact_id`, exchangeable
  working correlation, bias-reduced (Mancl-DeRouen) sandwich covariance; Wald t with
  (facts - parameters) degrees of freedom; two-sided p; 95% CI on the log-odds scale.
- H1 = `freq_c`; H2 = `div_c:frame_c`. Predicted sign + for both.
- Effect sizes: log-odds and odds ratios with CIs; risk differences with 95% percentile CIs from a
  stratified fact bootstrap (2000 resamples, fixed seed). The bootstrap describes effect size and
  is not used for the tests.
- Sensitivity (no tests): conditional mixed logit with fact and fact-by-seed intercepts
  (`BinomialBayesMixedGLM`).
- Convergence rule: if the fit fails, refit (1) with independence working correlation, then (2)
  without the optional covariates, logging each step; never chosen by p-value.

### H3, H4 (extraction; DESIGN Part B)

The unit is the fact; E2 (held-out facts) only, so that items are not pseudo-replicated.

- **H3a:** exact McNemar test, base vs SFT, on the same E2 facts; effect = accuracy gain.
- **H3b:** Fisher exact test on the 2x2 table stored x correct(SFT); effect = P(correct | stored)
  - P(correct | not stored), with the odds ratio.
- **H3** is an intersection-union test: supported only if H3a and H3b both reject with positive
  effects; its p-value is max(p_a, p_b).
- **H4:** difference in mean per-fact gain (SFT correct - base correct), paraphrased minus
  templated; permutation test permuting `div_bin` within `freq_bin` (5000 permutations, fixed
  seed), two-sided p, predicted sign +. DESIGN names no between-condition test; this is the
  choice. The per-condition McNemar tests and 2x2 tables DESIGN lists are reported with it.
- CIs for H3/H4 effects: stratified fact-bootstrap percentile intervals (1000 resamples).

## 6. Multiple comparisons

Holm step-down at family-wise alpha 0.05 across the four tests H1, H2, H3, H4 (m = 4). DESIGN
states no correction; this follows PREREG v0. Exploratory analyses (section 10) are not corrected
and are labelled exploratory wherever reported. If H3/H4 data are missing at analysis time the
pipeline reports provisional H1/H2 values with the missing p-values set to 1.

## 7. Decision rules, null and inconclusive results (per hypothesis)

Common rules. **Supported:** Holm-adjusted p <= 0.05 and the effect has the predicted sign.
**Reversed:** Holm-adjusted p <= 0.05 with the opposite sign (reported as a refutation of the
predicted direction). **Not supported:** Holm-adjusted p > 0.05, never re-fitted under other
specifications. **"No meaningful effect"** may be claimed only if the whole 95% CI lies inside the
pre-declared margin (placeholders above); otherwise the result is **inconclusive**. No "no effect"
claim is made from a non-significant p-value.

| id | a null means | inconclusive means | note on this design |
|---|---|---|---|
| H1 | exposure does not raise storage: p > 0.05 with the CI inside +-0.223 log-odds per tripling | CI includes both 0 and effects larger than the margin | |
| H2 | the paraphrased advantage does not differ by frame (CI of the interaction inside the margin) | wider CI | also report the simple effects of diversity per frame, descriptively |
| H3 | SFT did not improve E2 over base (H3a), or extraction is not tied to storage (H3b); report which component failed | the gain or the stored-vs-not difference has a CI crossing 0 and the margin (E2 has about 60 facts) | a degenerate 2x2 (all facts stored or none) is non-informative, not a null |
| H4 | the gain does not differ by diversity (CI inside +-0.10) | the CI is wider than the margin, which is expected with 30 facts per condition | **expect inconclusive** unless the effect is large |

Failed analysis (not a scientific null): a table fails its input contract; the primary model fails
to converge under every fallback; a design cell has stored rate 0 or 1 (complete separation), in
which case the affected test is reported as non-informative with the cell table.

## 8. Exclusion rules

- Exclude malformed KB records, failed-validator records, and documents failing the generation
  validator.
- Exclude val/test documents from measured exposure.
- No probe row or question is excluded for being an outlier or for model output quality; missing
  outputs are reported, not imputed.
- Do not use test probes, test loss, or E2 results for checkpoint selection.
- Do not post hoc change cell membership, probe templates, model seeds, covariates, the primary
  checkpoint, the fact-level aggregation rules, or the comparator.
- Report residual contradiction-audit failures and missing probe outputs.

## 9. Checkpoint selection (release only)

The earliest checkpoint within one percentage point of the maximum validation-probe ranking
accuracy, using validation probes only. It picks the released model and the checkpoint that is
fine-tuned; it does not change the primary analysis checkpoint (section 4).

## 10. Exploratory (not corrected, not confirmatory)

Learning curves with fact-bootstrap bands and per-fact acquisition steps; freq x div and the
three-way interaction; item-level (clustered) QA models; E0 and E1 results; zero-shot comparator;
token- vs character-normalised ranking; relationship-direction asymmetry; attention inspection;
two-hop probes; free-generation galleries; the temperature sweep; the mixed-model sensitivity fit.

## 11. Power and validation (simulated data; planned size 120 facts, E2 = 60 facts)

From `reports/tables/analysis_validation.md` (400 replicates per scenario, 500 per null). Planted
effects are assumptions, so these are sensitivity numbers, not forecasts.

| id | power at 20 facts/cell (Holm) | at 10 / 30 facts per cell | verdict |
|---|---|---|---|
| H1 | 1.00 | 0.94 / 1.00 | confirmatory, adequately powered |
| H2 | 0.84 | 0.47 / 0.98 | confirmatory, adequately powered; marginal if the planted effect is overstated |
| H3 | 0.96 | 0.56 / 1.00 | confirmatory, adequately powered under the planted effect |
| H4 | 0.36 | 0.11 / 0.64 | confirmatory but **underpowered**; a null is inconclusive by design |

False-positive control: per-test null rejection of H1/H2 is 0.03-0.05 (nominal 0.05); H3/H4 are
valid but conservative (0.00-0.02); family-wise 0.08 before and 0.018 after Holm in the all-null
simulation. Recovery of the planted effects: H1/H2 CI coverage 0.96-0.97 and unbiased; H3/H4
bootstrap CIs under-cover (0.88-0.92).

## 12. Open items to settle before the freeze

1. Confirm Holm over H1-H4 as the family (DESIGN is silent).
2. Set the equivalence margins (placeholders above).
3. Fix the fact-level `stored` and QA-correct aggregation rules and the base comparator.
4. Decide what to do about H4's power: raise E2 (30 facts/cell gives about 0.64), or keep it
   confirmatory and accept an expected inconclusive result, or move it to exploratory.
5. Join measured `train_mentions` and switch `freq_c` to log3(mentions).
6. Confirm the canonical frame having 1 test probe against 3 novel ones (DESIGN says 3 templates).

## 13. Deviations log

| date | deviation | reason | impact |
|---|---|---|---|
| | | | |

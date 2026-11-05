# REPORT BACK: A02 (hypotheses aligned with DESIGN, extraction tests, probe_frame)

Simulated data only; PREREG is an unfrozen draft.

## 1. Checks
- pytest: `244 passed in 242.93s (0:04:02)` (full suite, foreground). My new tests: 42, about 35 s
  together; the heaviest, `test_null_false_positive_rate_is_controlled` (200 replicates), is marked
  `slow`. The only tests over 30 s (`test_p02b7.py`, `test_p02b5.py`) belong to the data stream and
  were not touched.
- ruff: `All checks passed!`
- git log --oneline -3: `A02: hypotheses aligned with DESIGN, extraction tests, probe_frame` (this
  commit), then `f72457c A01: analysis pipeline, simulator, PREREG draft`, `c092070 P02b7f: ...`.
- git status --short: clean after the commit.

## 2. Hypothesis table (DESIGN.md section 8 labels and wording)

| label | DESIGN wording | outcome | predictors | test | status | power (Holm, 120 facts) |
|---|---|---|---|---|---|---|
| H1 | "storage rate rises with log exposure." | `stored` (probe) | `freq_c` (log3 mentions; bin code for now), `div_c`, `frame_c`, covariates, seed, template | `freq_c` coefficient, logistic GEE (fact clusters), predicted + | confirmatory, primary | 1.00 |
| H2 | "at matched exposure, paraphrased facts generalize better to *novel-frame* probes; templated facts do better only on *canonical-frame* probes." | `stored` | `div_c` x `frame_c` | `div_c:frame_c` coefficient, predicted + (simple effects per frame, descriptive) | confirmatory | 0.84 |
| H3 | "E2 QA accuracy after SFT >> base, but bounded by pre-SFT storage (P(correct \| stored) >> P(correct \| not stored))." | fact-level E2 correctness (base, SFT); fact-level stored | model; stored | McNemar base vs SFT AND Fisher stored x correct (intersection-union, p = max) | confirmatory | 0.96 |
| H4 | "the extraction gain is larger for paraphrased facts (cf. Allen-Zhu & Li, *Physics of LMs 3.1*)." | per-fact gain (SFT - base) on E2 | `div_bin` | permutation test, paraphrased - templated gain, stratified by `freq_bin` | confirmatory, **underpowered** | **0.36** |

Holm over H1-H4. DESIGN states no correction; Holm comes from PREREG v0 (flagged).

## 3. Validation (`reports/tables/analysis_validation.md`)

Recovery, 400 replicates at 120 facts (truth = population value of the same estimator on a very
large simulation; the planted H1/H2 values are conditional on random effects and larger):

| | scale | planted (conditional) | population truth | mean estimate | bias | CI coverage | sign correct |
|---|---|---|---|---|---|---|---|
| H1 | log-odds | 0.90 | 0.721 | 0.735 | +0.014 | 0.973 | 1.00 |
| H2 | log-odds | 1.00 | 0.795 | 0.815 | +0.020 | 0.960 | 1.00 |
| H3 gain | risk diff | n/a | 0.410 | 0.398 | -0.012 | 0.882 | 1.00 |
| H3b (P(c\|stored) - P(c\|not)) | risk diff | n/a | 0.486 | 0.492 | +0.006 | 0.920 | 1.00 |
| H4 | risk diff | n/a | 0.256 | 0.232 | -0.023 | 0.915 | 0.973 |

Null false-positive rates, alpha 0.05, 500 replicates (MC half-width 0.019):

| scenario | H1 | H2 | H3 | H4 | any of H1-H4 |
|---|---|---|---|---|---|
| A, all effects zero: raw | 0.032 | 0.050 | 0.000 | 0.000 | 0.080 |
| A: after Holm | 0.012 | 0.006 | 0.000 | 0.000 | 0.018 |
| B, extraction active, no diversity effect: raw | 0.048 | 0.050 | (power 0.950) | 0.018 | |
| B: after Holm | 0.014 | 0.008 | (power 0.852) | 0.010 | |

Power, Holm-adjusted (raw in the report), predicted sign required:

| facts per cell (total, E2) | H1 | H2 | H3 | H4 |
|---|---|---|---|---|
| 10 (60, 30) | 0.94 | 0.47 | 0.56 | 0.11 |
| **20 (120, 60)** | **1.00** | **0.84** | **0.96** | **0.36** |
| 30 (180, 90) | 1.00 | 0.98 | 1.00 | 0.64 |

Plain reading: H1, H2, H3 are adequately powered at the planned size under the planted effects;
H4 is underpowered and a null H4 will be inconclusive. H1/H2 are calibrated; H3/H4 tests are valid
but conservative; H3/H4 bootstrap CIs under-cover (0.88-0.92). H3 power is high partly because the
majority rule leaves the 2-shot base near floor at fact level. Planted effects are assumptions.

## 4. PREREG draft v2 (unfrozen)
Headings: 1 Research question; 2 Hypotheses (DESIGN wording, verbatim); 3 Primary outcome; 4
Operational definitions; 5 Exact tests (H1/H2; H3/H4); 6 Multiple comparisons; 7 Decision rules,
null and inconclusive results (per hypothesis); 8 Exclusion rules; 9 Checkpoint selection; 10
Exploratory; 11 Power and validation; 12 Open items to settle before the freeze; 13 Deviations log.
Header placeholders: frozen-at hash/date, analysis-code hash, equivalence margins.

Primary outcome sentence: "The primary outcome is `stored` (the correct value ranks first among the
six same-attribute values and its binding score is above zero), measured on the test probes at the
final pretraining checkpoint and analysed per fact x seed x prompt variant; the primary confirmatory
estimate is H1, the log-odds increase in `stored` per tripling of measured exposure, from a logistic
GEE with fact clusters."

## 5. Decisions, deviations, unsure
Decisions A-D011 to A-D021 and failure A-F001 are in journal/analysis/. Things that need the
architect:
1. **Holm family:** DESIGN has no correction; I kept Holm over H1-H4 from PREREG v0.
2. **Aggregation rules (A-D014):** fact-level stored and correct use majority rules; the eval stream
   proposes >= 2 of 3 test probes for stored. Pick one before the freeze. The base is near floor
   at fact level under my rule.
3. **Comparator (A-D017):** base_2shot assumed; DESIGN only says "base".
4. **H4 (A-D020):** underpowered at 60 E2 facts. Choose: raise E2 (30 facts per cell gives 0.64),
   accept an expected inconclusive result, or move it to exploratory. DESIGN's H4 test is also
   unnamed; I used a permutation test.
5. **Margins (A-D018):** OR 1.25 kept as placeholder; the +-0.10 risk-difference margin for H3/H4 is
   my placeholder, not given.
6. **Canonical frame has 1 test probe against 3 novel** in the eval stream's table; DESIGN says 3
   templates. Variants are nested in frames, so template terms are within-frame fixed dummies.
7. **Checkpoint for H3:** `stored_pretrain` must come from the checkpoint that was fine-tuned
   (val-selected), while H1/H2 use the final checkpoint.
8. **E0/E1/E2 meaning matches DESIGN** and the eval stream's mock qa_test.jsonl (E2 = 60 held-out
   facts x 3 test templates); its result table still lacks seed, question_id, stored_pretrain,
   freq_bin, div_bin, sft_split.
9. A01's `regime` is gone from the probe table; the eval stream's `regime` stays doc-loss only.
10. Cross-session: I answered another session's question that the M03 files in slm-model are not mine.

No figures or tables from simulated data were written to `reports/figures/`; only the validation
report is committed.

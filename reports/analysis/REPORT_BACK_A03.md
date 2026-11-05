# REPORT BACK: A03 (PREREG v3, realized diversity, sensitivity, report generator)

Simulated data only. PREREG is an unfrozen draft. The committed report under
`docs/report/simulated/` is simulated and carries the SIMULATED banner on every page and figure.

## 1. Checks
- pytest: `268 passed in 261.45s (0:04:21)` (full suite, foreground). My new A03 tests: 28, about
  45 s together. The report-build tests are marked `slow`; the slowest A03 test takes 8 s. The only
  tests over 30 s (`test_p02b7.py`, `test_p02b5.py`) belong to the data stream and were not touched.
- ruff: `All checks passed!`
- git log --oneline -3: `A03: PREREG v3, realized diversity, sensitivity, report generator` (this
  commit), then `95c3e07 A02: ...`, `f72457c A01: ...`.
- git status --short: clean after the commit.

## 2. PREREG v3

| id | DESIGN wording (short) | test | status | Holm power, 120 facts |
|---|---|---|---|---|
| H1 | storage rate rises with log exposure | `freq_c` coefficient, logistic GEE, fact clusters | **confirmatory, primary** | 1.00 |
| H2 | at matched exposure, paraphrased facts generalize better to novel-frame probes; templated do better only on canonical | `div_c:frame_c` coefficient | confirmatory | 0.87 |
| H3 | E2 accuracy after SFT >> base, bounded by pre-SFT storage | McNemar (base_2shot vs SFT) AND Fisher (stored x correct) | confirmatory | 0.97 |
| H4 | extraction gain larger for paraphrased facts | gain difference with bootstrap CI | **secondary: effect and CI only** | 0.33 raw, no test |

Holm over H1, H2, H3 (m = 3). H4 as secondary is deviation D1 (D2-D5 also logged in PREREG section
0) for the DESIGN v1.3 fold-in. Rules: fact-level stored = stored on >= 2 of 3 test probes,
QA-correct = correct on >= 2 of 3 E2 phrasings, each in a majority of seeds; `any`/`all` are
sensitivity rules. Comparator base_2shot (0-shot secondary). One checkpoint: the final one of each
seed after a fixed epoch count chosen on validation loss. Margins remain placeholders (OR 1.25;
+-0.10 risk difference, the second is mine).

Primary outcome: "The primary outcome is `stored` (the correct value ranks first among the six
same-attribute values and its binding score is above zero), measured on the test probes at the final
pretraining checkpoint of each seed and analysed per fact x seed x prompt variant; the primary
confirmatory estimate is H1, the log-odds increase in `stored` per tripling of measured exposure,
from a logistic GEE with fact clusters."

## 3. Realized diversity
Schema (`data/bank/realized_diversity.csv`, one row per fact; the file does not exist in the main
checkout yet, so the column meanings are my assumption): `fact_id`, `n_distinct`, `n_reused`,
`core_uniqueness` (0..1), `mean_pairwise_jaccard` (0..1, higher = more similar). Validated by
`schema.validate_realized_diversity`. Covariate `rdiv_z` = z-score of 1 - `mean_pairwise_jaccard`.

H2 when the manipulation is weak (200 replicates per row; nominal `div_bin` correlates with realized
diversity at the given strength; storage is driven by realized diversity):

| strength | nominal H2 (mean) | nominal H2 power | realized H2, scaled to a full contrast | realized power |
|---|---|---|---|---|
| 1.0 | 0.797 | 0.840 | 0.789 | 0.830 |
| 0.6 | 0.493 | 0.410 | 0.780 | 0.805 |
| 0.3 | 0.249 | 0.140 | 0.776 | 0.800 |

Population truth at full strength 0.831. A weak manipulation biases the nominal H2 toward zero and
cuts its power, while the realized-diversity model stays near the full-strength effect. This is
pre-registered as a sensitivity analysis (PREREG section 10), not as a replacement for the test.

## 4. Sensitivity table (simulated report build, seed 0; log-odds for H1/H2, risk difference for H3/H4)

| analysis | hypothesis | estimate | CI low | CI high |
|---|---|---|---|---|
| primary (GEE, log3 mentions, with templates) | H1 | 0.688 | 0.413 | 0.963 |
| | H2 | 0.189 | -0.332 | 0.710 |
| exposure coding: bins | H1 / H2 | 0.707 / 0.173 | 0.422 / -0.347 | 0.993 / 0.694 |
| without prompt_variant terms | H1 / H2 | 0.687 / 0.188 | 0.412 / -0.333 | 0.962 / 0.710 |
| Bayesian mixed logit (point estimate) | H1 / H2 | 0.848 / 0.220 | n/a | n/a |
| outcome: stored_tokennorm | H1 / H2 | 0.477 / 0.095 | 0.232 / -0.421 | 0.723 / 0.610 |
| realized diversity replaces div_bin (H2 per nominal contrast) | H2 | 0.489 | 0.085 | 0.893 |
| div_bin and realized together | H2 nominal term / realized term per SD | -0.933 / 0.682 | -1.82 / 0.261 | -0.046 / 1.10 |
| fact-level rule any | H3 gain / H4 | 0.267 / 0.267 | 0.133 / 0.000 | 0.400 / 0.567 |
| fact-level rule majority (primary) | H3 gain / H4 | 0.300 / 0.133 | 0.200 / -0.067 | 0.409 / 0.333 |
| fact-level rule all | H3 gain / H4 | 0.017 / 0.033 | 0.000 / 0.000 | 0.050 / 0.100 |
| comparator base_0shot | H3 gain / H4 | 0.300 / 0.133 | 0.200 / -0.067 | 0.409 / 0.333 |

In this simulated build (a weak manipulation, strength 0.8) the realized-diversity H2 is larger than
the nominal one, as expected. The `all` rule collapses H3 and H4 (almost no fact is correct on every
item), which shows how much the fact-level rule matters. Separation: none in this build. One command:
`scripts/run_sensitivity.py --input <probe> --qa-input <qa> --realized-diversity <csv> --out reports/`.

Report build: `scripts/build_report.py --simulate`: backend **headless Chrome**, **6 pages**,
banner on; Matplotlib fallback 5 pages (also within 5-7); the gate fails the build at 4 pages and
outside any other range. pandoc, LaTeX, weasyprint and reportlab are not installed, so those paths
do not exist (an untested path is not trustworthy). Output: `docs/report/simulated/` (`report.md`,
`report.html`, `report.pdf`, `numbers.json` with the source of every number, four figures).

## 5. Decisions, deviations, unsure
Decisions A-D022 to A-D032 and failures A-F002 to A-F004 are in journal/analysis/. Needs the
architect:
1. **Spec files absent:** `docs/Term_Project.pdf` and `docs/SPEC_COMPLIANCE.md` exist nowhere in the
   repo or the sibling worktrees. The outline (dataset, research question, architecture, training
   procedure, evaluation, findings, limitations) and the 5-7 page limit come from your prompt. Check
   them against the spec.
2. **Report inputs I defined:** `run_facts.json`, `loss_curves.csv` and `samples.csv` (ANALYSIS_INPUT
   section 4) do not exist yet in other streams. The simulated values in them (model size, losses,
   sample texts) are invented and banner-marked. The data, model and eval streams must emit them, or
   the contract must change.
3. **Realized-diversity file:** column meanings are assumed; confirm with the bank stream.
4. **3 test probes:** the simulator now has 1 canonical + 2 novel; the eval stream documents
   `test-canon`, `test-n1..3`.
5. **H4 power is 0.33, not 0.36,** after the 3-probe change; the H4 decision does not depend on it.
6. **Fact-level rule sensitivity:** the `all` rule nearly erases H3/H4; the `majority` rule was your
   decision, and the margins are still placeholders (0.10 risk-difference is mine).
7. **Banner policy:** on by default in the report, the figures and `run_analysis.py`; off only with
   `--real`; `--simulate --real` is refused. A real build still needs `--results-dir` and
   `--inputs-dir`.
8. **PDF backend:** Chrome/Edge or Matplotlib only. If the submission needs LaTeX-quality typesetting
   on another machine, a pandoc path must be added and tested there.
9. The committed simulated PDF (0.5 MB) and PNGs are deliberate, for review; delete the folder
   before submission if it should not ship.

# REPORT BACK I01

Branch `integration` (worktree `../slm-integration`), local only: nothing pushed, main untouched, no
OpenAI call, `.env` never read. Spec files `docs/Term_Project.pdf` and `docs/SPEC_COMPLIANCE.md`
**do not exist** (searched all worktrees and branches); `docs/SPLIT_MANIFEST.md` exists.

## 1. Checks
- pytest (whole merged repo, no PYTHONPATH, one invocation): `482 passed, 1 skipped, 7 warnings in 514.20s (0:08:34)`.
  It was started through a background shell because the tool's foreground limit is 10 minutes; it ran as a
  single `pytest -q` and I changed no code while it ran (only docs and journals). The one skip is main's `tests/test_p02c.py` ("corpus not generated yet": `data/corpus` is absent in this worktree).
  Slowest: 59.6 s (P02 allocation fixture), 56.9 s and 52.9 s (both P02), 50.3 s `test_mock_pipeline_runs_end_to_end` (mine, marked `slow`), 29.1 s. New integration tests: 25 in `tests/integration/`.
- ruff: `All checks passed!`
- git log --oneline -8 and git status --short: 

```
86f984e I01: merge streams, interfaces, end-to-end mock
edc854e I01: merge analysis-stream
51bdd8e I01: merge eval-stream
6faf198 I01: merge model-stream
951471d P02c: corpus runner, helpers, tests (code only)
a181f08 A03: PREREG v3, realized diversity, sensitivity, report generator
56c2818 P02b7i: report back
c14c649 P02b7i-b: pilot v6 (mini eligible under A1)
```
`git status --short`: clean after the commit (the commit hash printed above is the one before this line was filled in; amended once, local only).

## 2. Merge conflicts and resolutions
Order: model-stream (29b63f8), eval-stream (5e14988), analysis-stream (a181f08). spec-stream is an
ancestor of main (nothing to merge, I-D013).

| merge | file | conflict | resolution |
|---|---|---|---|
| model-stream | `AI_USE.md` | main's P02c row vs four model rows (M01-M04) at the same place | kept every row (all different), main's row first |
| eval-stream | `AI_USE.md` | main/model rows vs the E01/E02 row | kept all |
| analysis-stream | `AI_USE.md` | same | kept all |
| analysis-stream | `tests/conftest.py` | add/add: eval and analysis each added one (eval: `slow` marker; analysis: `sys.path` hack + `slow` marker); model stream had its markers in `tests/model_stream/conftest.py` | one `tests/conftest.py` registering `slow` and `gpu` once, with the GPU-skip hook, no `sys.path` edits; `tests/model_stream/conftest.py` lost its `pytest_configure`/skip hook and keeps its fixtures (I-D002) |
| none | `pyproject.toml`, `track.txt` | no conflict: no stream touched them (model/eval/analysis keep `track_*.txt`, journals in own folders) | `track.txt` got an INTEGRATION section; markers live in conftest only |

`pip install -e .` points at this worktree through a worktree-local `.venv` (main's venv is left alone,
I-D001, I-F001); `slm.__file__` is `slm-integration/src/slm/__init__.py`.

## 3. INTERFACES.md summary (docs/INTERFACES.md)
1. Scorer: `score` (summed log-prob) + `score_detailed` (logprob, n_tokens); `ModelScorer` implements both plus batched `score_details`; the harness prefetches batches; a test runs the full harness with a ModelScorer.
2. Probe table: `TABLE_COLUMNS`; `checkpoint` = optimiser step or `init`; `probe_frame` canonical/novel; fact-level rule "more than half of the table's test probes, then of seeds", computed from the share, never a constant.
3. Exposure/plan/KB: exposure from CSV > measured counts over the manifest's train files > planned counts from the plan (mock); the realized-diversity file is mapped to the analysis names (`core_unique_share`, `mean_pair_skeleton_jaccard`).
4. QA tables: evaluator rows -> `qa.csv` with `model, exact_value_match, contains_gold, sentence_exact, stored_pretrain, freq_bin, div_bin, sft_split`; `scripts/build_analysis_tables.py`.
5. Report inputs: `run_facts.json` (23 keys), `loss_curves.csv`, `samples.csv` emitted from runs; validated by the builder's own loader.
6. Split manifest: version-1 format; the path is an argument (`--corpus-manifest`, `--manifest`); test is read only through the ledger.
7. Banner: SIMULATED or MOCK label; off only with `--real`, which the mock pipeline refuses.

**Probe counts per fact (measured, `reports/integration/mock_tables_summary.json`):** val 2 = 1 canonical + 1 novel; test 3 = 1 canonical + 2 novel. Fact-level rule for 3 test probes: stored on at least 2 of 3 ("at least half" equals "more than half" for odd counts; for an even count the code is strict: 2 of 4 is not stored; tested for n = 3, 4, 5). The analysis reads the count from the table (`apply_rule` on `mean(stored)`). The canonical prefix text is shared by val and test.

## 4. Mock end-to-end (MOCK banner; `scripts/run_all_mock.py --limit 40`, 2 seeds x 8 epochs)
| stage | seconds |
|---|---|
| tokenizer_train | 0.22 |
| token_cache | 0.16 |
| pretrain_2_seeds | 10.27 |
| probes_modelscorer (init + 5 checkpoints x 2 seeds, 120 facts x 5 probes each) | 8.57 |
| sft_2_seeds | 8.01 |
| qa_eval_3_variants (40 questions per set x 3 sets x 3 variants x 2 seeds) | 96.09 |
| build_analysis_tables | 3.31 |
| run_analysis (+ sensitivity) | 10.63 |
| report_inputs | 2.45 |
| build_report | 5.29 |
| **total** | **145.00** |

Report build output: `backend: chrome; pages: 5; banner: True` (page gate 5-7). The banner reads "MOCK DATA - NOT RESULTS" on every page and figure; `--real` is refused with exit 2 (tested). Outputs: `reports/integration/mock_report.pdf`, `mock_report.md`, `mock_run.json`. QA exact match is 0.0 everywhere and the stored rate is at chance level (0.08-0.10, init 0.09), as expected for models trained for seconds on 200 toy documents; H3 and H4 are degenerate (estimate 0).

## 5. Deviations from DESIGN v1.2 (docs/DESIGN_CHANGES_v1.3.md, 37 rows; DESIGN.md not edited)
1. Sentence-bank architecture (documents never write fact sentences) - D-065..D-070.
2. A1 amendment (eligibility rule) - D-053. 3. A2, A2b (judge NO reported), A2c (reuse, (d) = 0.8 x min(need,25)) - D-070/D-074/D-089. 4. Stage-1 gate waived - D-064.
5. Six entities per family, Latin square - D-015. 6. Entity-level balance, co-occurrence cap 6 - D-023/D-029.
7. Length band 0.6-1.4, documents over 512 tokens chunked - D-060/M-D015. 8. Numeral policy - D-017. 9. 2407-document plan with iid/novel val/test regimes - D-024. 10. Planned = measured exposure (unconfirmed) - D-025. 11. Validator v5, 5 attempts, stuck rule - D-067/D-069.
12. Weight decay: M02 excluded embeddings (M-D024), reverted to DESIGN's all-2-D rule (M-D035); net matches DESIGN, the position table decays too.
13. Single analysed/final checkpoint, release seed by val loss - A-D025/M-D047 (DESIGN: val-probe selection rule).
14. No 12M-vs-25M sizing check yet (the sweep is lr x dropout only) - M-D034, open.
15. Probe frames (`probe_frame`; canonical shared by val and test; 2 val / 3 test) - E-D010/E-D014. 16. Token-normalised secondary outcome - E-D015. 17. Permutation null / chance baseline - E-D012.
18. Primary metric exact_value_match (+ contains_gold, sentence_exact) - M-D043. 19. 2-shot exemplars from SFT-val facts - M-D044. 20. Test-access ledger - M-D041.
21. GEE instead of a mixed model (seed fixed, template dummies) - A-D001..D003. 22. H4 secondary - A-D020/D022. 23. Holm over H1-H3 (m = 3) - PREREG D2.
24. Fact-level rules (majority; any/all sensitivity; comparator base_2shot) - A-D014/D023/D024. 25. Exposure coding log3 mentions - A-D019. 26. Realized-diversity covariate (sensitivity) - A-D026. 27. Sensitivity suite - A-D028. 28. PREREG not frozen, margins are placeholders - A-D018.
29. Report from a macro template to a Chrome PDF, no LaTeX - A-D029. 30. Spec PDF and compliance file missing - A-D030. 31. Bundle and `generate.py` instead of `release/` and `slm.generate` - M-D046..D049. 32. Hash-verified split manifest and token cache - M-D021..D023. 33. SFT free parameters, no replay - M-D036..D038. 34. Generator model gpt-5.4-mini - D-091. 35-37. Integration items (single conftest, MOCK banner, step-valued checkpoint).

## 6. Decisions, deviations, unsure (journal/integration/DECISIONS_I.md, I-D001..I-D015)
- I-D001 separate venv (main's venv untouched); I-F001 the stray system-Python `pip install` I had to stop.
- I-D004 I edited eval-stream code (`probes.prefetch`) for batched scoring; a scorer without `score_details` behaves as before.
- I-D005 `exact_value_match` is aliased to the analysis's `exact_match`.
- I-D006 the MOCK banner label touches the analysis stream's banner plumbing (figures, report markup/pdf/build, two CLIs).
- Unsure: (a) I-D007 the realized-diversity mapping (`mean_pair_skeleton_jaccard` -> `mean_pairwise_jaccard`) needs the bank owner; (b) I-D008 the mock QA file's fact split differs from the KB's `sft_split`, so a real run must say which split the SFT data used; (c) I-D010 "at least half" vs "more than half" differ only for even counts; (d) exposure for the mock is planned, not measured, the real corpus will show whether planned equals measured; (e) the model stream's exemplar ids are mock-split ids; (f) the real manifest and `sft_split` arrive with main's P02c, then merge main into `integration` and rerun `build_analysis_tables.py --manifest data/corpus/manifest.json`; (g) the fresh-clone test and `make_bundle` were not rerun by me (the model-stream tests cover them and passed in the full suite).

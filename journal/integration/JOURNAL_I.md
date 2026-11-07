# Integration journal

## I01 (2026-11-05) merge streams, interfaces, end-to-end mock
- **Goal:** one branch (`integration`, worktree `slm-integration`) holding model, eval and analysis streams with reconciled interfaces and a working mock pipeline from tokenizer to report.
- **Done:** merged model-stream, eval-stream, analysis-stream (conflicts only in AI_USE.md and tests/conftest.py); unified conftest; separate venv with an editable install (I-D001, I-F001); ModelScorer now implements `score_detailed`, probe harness prefetches batched scores (I-D004); `slm.integration` (probing, tables, report_inputs), `scripts/build_analysis_tables.py`, `scripts/run_all_mock.py`; MOCK banner label (I-D006); docs/INTERFACES.md, docs/DESIGN_CHANGES_v1.3.md; 25 integration tests (3 files), one of them an end-to-end run marked `slow`.
- **Decisions:** I-D001 to I-D015. **Failures:** I-F001. **Experiments:** I-E001.
- **Results:** mock run in about 100 s (see reports/integration/mock_run.json); probe counts per fact 2 val + 3 test (1 canonical + 2 novel in test); report 5 pages with MOCK banner. All model outputs are meaningless by design.
- **Problems:** `docs/Term_Project.pdf` and `docs/SPEC_COMPLIANCE.md` do not exist anywhere (I-D012). The real corpus manifest and measured exposure arrive with main's P02c; the real `sft_split` source must be fixed then (I-D008). Realized-diversity column meaning needs the bank owner's confirmation (I-D007).
- **Next:** when main's P02c finishes, merge main into `integration`, run `build_analysis_tables.py --manifest data/corpus/manifest.json`, then P05 (sweep, 3 seeds) with the same scripts.

## R00 - real-run preparation (2026-11-05)
- **Goal:** everything the real run needs that does not need the corpus: clean probe prompts, real SFT/QA files, a resumable orchestrator with a freeze step, and a full dry run on the toy corpus.
- **Done:** probe rendering audit (480 prompts, 0 mechanical problems, 2 wording fixes found by reading; a/an helper; I-D016, I-D017); `data/sft` + `data/eval` from the KB split with 14 assertions and hashes (I-D018); `scripts/run_real.py` (12 stages), `configs/real.yaml`, `configs/real_mock.yaml`, `scripts/freeze_prereg.py`, `slm.integration.freeze`, `slm.guard.record_test_use` (I-D019 to I-D025); 3 new test files; mock run reads the same SFT files as the real run.
- **Dry run (MOCK, toy corpus, 3 seeds, sweep 9 configs x 8 epochs + one 27.6M run):** all 12 stages ok, 454 s in two invocations (the first stopped at `probes` on a syntax error I had introduced in the ledger module, the second resumed from the stage files: 6 stages skipped); the freeze refused a fresh PREREG copy after the test reads and froze an empty run directory.
- **Problems:** a CRLF/newline slip in `guard/ledger.py` broke the import once (fixed with Edit); the first sizing result picks the large model on toy data, which means nothing.
- **Next:** merge main when P02c finishes, set the PREREG equivalence margins (they are placeholders and the freeze records the file as it stands), then `python scripts/run_real.py --config configs/real.yaml`.

## R01 - taxonomy, ranking accuracy, exemplars, samples, README (2026-11-05)
- **Goal:** keep successes AND failures visible (spec 6/R19), evaluate base and SFT on the same questions (risk 3), and give a README that runs the model without retraining (9(g)).
- **Spec files were not in the repo** (step 0 skipped on instruction; points relayed by the user, not read).
- **Done:** I-D026 to I-D033: `slm.sft_eval.taxonomy` / `ranking`, `error_class` and rank columns, `error_taxonomy.csv` / `ranking_accuracy.csv`, exemplar tests on the real files, `scripts/sample_checkpoints.py` + stage `samples`, `docs/README.md` + `tests/test_r01_readme.py`, `docs/ERROR_TAXONOMY.md`.
- **Found by tests:** `generate.py` crashed on a cp1252 console when a model emitted undecodable bytes (fixed, I-D032).
- **Next:** merge main when P02c finishes, set the PREREG margins, run `scripts/run_real.py --config configs/real.yaml`; fill the README `<...>` numbers from the real run.

## R02 - merge main, partial-corpus dry run (2026-11-06)
- **Done:** merged main 0cfabdc (conflicts only in `AI_USE.md`, `track.txt`); ran tokenizer, token cache and a 2-config sweep on the 135-document partial train split in `runs/partial_dryrun/`; probe-overlap check; 12 samples; I-D034 to I-D038.
- **No test data touched:** `data/corpus/test.jsonl` was not opened, not copied, not listed; the ledger file was not created.
- **Next:** when P02c3 finishes and `data/corpus/manifest.json` exists, merge main again and run `scripts/run_real.py --config configs/real.yaml`.

## R03 - E* rule, warmup scaling, PREREG v4 (2026-11-06)
- **Done:** I-D039 to I-D046: validation-probe budget rule (`slm.train.budget`, `slm.integration.budget_sweep`), sweep and sizing stages on it, final runs to 2E* with the primary analysis at E*, SFT from E*, secondary 2E* analysis, step-scaled warmup/logging (`TrainConfig.resolve`), PREREG v4, freeze record with config hash and E*, mock dry run (13 stages, 319 s), `tests/test_r03_*.py` (35 tests).
- **Found:** a first full-suite run failed one stale R00 assertion (the old sweep grid in `test_r00_freeze.py`); fixed, whole suite rerun.
- **Concerns written down:** val and test canonical probes share the prompt; 240 val probes are noisier than the 0.01 tolerance; the sweep and final cosine schedules differ.
- **Next:** merge main when P02c3 lands; run the real sweep; read the decision table (and its chance WARNING) before accepting E*; set nothing else in PREREG before the freeze.

## R04 (2026-11-06): E* rule v2, sweep seed 100, identical schedule, two-stage sweep, PREREG v5
- **Done:** `slm.train.budget` rewritten (3-checkpoint smoothing, fact-clustered SE, 1-SE near-ties and E*, chance guard with `no_val_storage`); `budget_sweep` two-stage with ETA/abort and seed 100; final runs use the sweep's schedule (no 2E*); PREREG v5 (unfrozen); freeze records sweep seed/E*/guard/schedule hash and refuses a dirty tree; `build_report --real` needs a verified freeze; QA cost measured (about 16 min projected, no batched decoder).
- **Mock dry run (13 stages, all ok):** the guard fired (best smoothed 0.098 vs init 0.100, threshold 0.145), E* = 12 = the val-loss optimum, 7 near-ties because every SE is ~0.02 at chance. R03 had picked E*=1 on noise.
- **Path test:** real-mode report refused without a freeze, built (banner off) after a valid freeze on a clean scratch repo, refused after PREREG was edited. Mock content, not results.
- **Concerns written down:** the ETA assumes equal cost per run; the large-model factor is the parameter ratio; the smoothed SE averages correlated checkpoints (conservative); the guard compares to the init rate of the same config only; the sweep still has one seed; real sweep not run (corpus manifest absent).

## R05 (2026-11-06)
Merged main cd17f63 (conflicts: AI_USE, track, DESIGN_CHANGES kept both sides). manifest sha256 failed on CRLF checkout; fixed with `data/corpus/** -text`. Tokenizer V=4096, train 687,060 tokens. Sweep + size check done; STOP (c) hit; not frozen. See reports/integration/REPORT_BACK_R05.md.

## R06 (2026-11-06)
Overrode R05 STOP (c) (I-D055). PREREG sensitivity paragraph, frozen at e1dce48 (E*=30). 3 seeds x 60 epochs, probes, SFT from E*, QA, tables, analysis, real report (6 pages). H1/H2 significant in the reversed direction; H3 null. See reports/integration/REPORT_BACK_R06.md.

## R07 (2026-11-07)
Result audit. Found the H1/H2 sign bug (bool outcome in the GEE), fixed it on synthetic evidence; SFT eval consistent, early stopping explains low QA; init stored rate is a value-length confound. No retraining, no test decode. See reports/integration/REPORT_BACK_R07.md.

## R08 (2026-11-07)
Freeze addendum, value-length check (existing tables), post-hoc fixed 3-epoch SFT (ledgered once), taxonomy split, report appendix (7 pages). See reports/integration/REPORT_BACK_R08.md.

## R09 (2026-11-07)
Submission deliverables: generate.py --qa/--compare, release bundle (3 models + MANIFEST), demo transcript and shot list, README, fresh-clone test (pass), secrets scan (clean), statements. See reports/integration/REPORT_BACK_R09.md.

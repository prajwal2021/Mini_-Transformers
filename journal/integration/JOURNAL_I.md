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

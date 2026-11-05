# Integration journal

## I01 (2026-11-05) merge streams, interfaces, end-to-end mock
- **Goal:** one branch (`integration`, worktree `slm-integration`) holding model, eval and analysis streams with reconciled interfaces and a working mock pipeline from tokenizer to report.
- **Done:** merged model-stream, eval-stream, analysis-stream (conflicts only in AI_USE.md and tests/conftest.py); unified conftest; separate venv with an editable install (I-D001, I-F001); ModelScorer now implements `score_detailed`, probe harness prefetches batched scores (I-D004); `slm.integration` (probing, tables, report_inputs), `scripts/build_analysis_tables.py`, `scripts/run_all_mock.py`; MOCK banner label (I-D006); docs/INTERFACES.md, docs/DESIGN_CHANGES_v1.3.md; 25 integration tests (3 files), one of them an end-to-end run marked `slow`.
- **Decisions:** I-D001 to I-D015. **Failures:** I-F001. **Experiments:** I-E001.
- **Results:** mock run in about 100 s (see reports/integration/mock_run.json); probe counts per fact 2 val + 3 test (1 canonical + 2 novel in test); report 5 pages with MOCK banner. All model outputs are meaningless by design.
- **Problems:** `docs/Term_Project.pdf` and `docs/SPEC_COMPLIANCE.md` do not exist anywhere (I-D012). The real corpus manifest and measured exposure arrive with main's P02c; the real `sft_split` source must be fixed then (I-D008). Realized-diversity column meaning needs the bank owner's confirmation (I-D007).
- **Next:** when main's P02c finishes, merge main into `integration`, run `build_analysis_tables.py --manifest data/corpus/manifest.json`, then P05 (sweep, 3 seeds) with the same scripts.

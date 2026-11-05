# Journal (eval stream)

## [2026-11-05] E01 - Probe harness, scorer interface, SFT builder
**Goal:** Model-independent probe harness and template-only SFT data builder.
**Done:** `slm.eval.{interface,probes,mock}`, `slm.sft.{templates,build}`, `scripts/run_probes.py`, `scripts/build_sft_mock.py`, tests, data/sft_mock/.
**Decisions:** E-D001 to E-D009. **Failures:** E-F001 to E-F003.
**Next:** real Scorer once a tokenizer and checkpoints exist; verify novel templates share no 8-gram with the train corpus (`has_ngram_overlap`).

## [2026-11-05] E02 - Chance baseline, probe_frame, hypothesis map, wording, doc loss
**Goal:** Make the probe outcome interpretable against chance and map every hypothesis to table columns.
**Done:** probe_frame rename; group scoring with permutation null, `init` checkpoint support, `chance_report`; optional `score_detailed` with token-normalised outcome; hand-written wording (20 x 1 canonical + 3 novel); `check_probe_overlap.py`; `doc_loss_by_regime`; docs/EVAL_COLUMNS.md and docs/HYPOTHESIS_MAP.md; reports/eval/REPORT_BACK_E02.md.
**Decisions:** E-D010 to E-D018. **Results:** E-E003.
**Next:** real Scorer; run `check_probe_overlap.py` once the train corpus exists; decide the fact-level stored rule and add exposure columns.
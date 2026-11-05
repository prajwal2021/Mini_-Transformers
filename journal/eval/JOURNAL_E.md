# Journal (eval stream)

## [2026-11-05] E01 - Probe harness, scorer interface, SFT builder
**Goal:** Model-independent probe harness and template-only SFT data builder.
**Done:** `slm.eval.{interface,probes,mock}`, `slm.sft.{templates,build}`, `scripts/run_probes.py`, `scripts/build_sft_mock.py`, tests, data/sft_mock/.
**Decisions:** E-D001 to E-D009. **Failures:** E-F001 to E-F003.
**Next:** real Scorer once a tokenizer and checkpoints exist; verify novel templates share no 8-gram with the train corpus (`has_ngram_overlap`).
# Model-stream journal

## M01 (2026-11-05) tokenizer, model, packing, GPU smoke test
- **Goal:** everything on the model side that needs no corpus (branch `model-stream`, worktree `slm-model`).
- **Done:** from-scratch byte-level BPE with train-only guard and calibration (`src/slm/tokenizer/`); 12.4M-parameter decoder-only Transformer with explicit attention and document masking (`src/slm/model/`, `configs/model.yaml`); document-aware packing (`src/slm/data_loading/`); synthetic mock corpus (`tests/fixtures/`); 35 tests in `tests/model_stream/` (3 need a GPU); `scripts/gpu_smoke.py`.
- **Decisions:** M-D001 to M-D020. **Experiments:** M-E001, M-E002. **Failures:** M-F001, M-F002.
- **Results:** 12,417,024 parameters; mock tokenizer reaches vocab 4096; 180k positions/s at batch 32 using 4.6 GB; about 2 minutes for 1M tokens x 20 epochs.
- **Problems:** spec PDF not in the repo (rules taken from DESIGN.md); `torch.compile` unavailable; mock text too small for 4096 merges at min_frequency 2.
- **Next:** wire the real train split into `train_tokenizer` once the data stream fixes a file format (M-D009), run the vocab-size study, then the real training loop (P05).

## M02 (2026-11-05) training loop, ModelScorer, manifest guard, hyper-parameter protocol
- **Goal:** everything needed to train and score on a corpus, tested on the mock corpus only.
- **Done:** split-manifest guard (`slm/split_manifest.py`, docs/SPLIT_MANIFEST.md) replacing the file-name check; token cache with statistics; training loop with seeds, schedule, weight-decay groups, checkpoints, resume, NaN guard (`slm/train/`, configs/train.yaml, scripts/pretrain.py); `ModelScorer` (`slm/eval_adapter/`); sweep (`slm/train/sweep.py`, scripts/sweep.py, docs/HPARAM_PROTOCOL.md); dry run (scripts/m02_dry_run.py).
- **Decisions:** M-D021 to M-D034. **Experiments:** M-E003, M-E004. **Failures:** M-F003, M-F004.
- **Results:** 63 tests pass in 14 s including 4 GPU tests; the mock dry run trains 2 seeds x 8 epochs in about 5 s each; resume is bit-identical on CPU, and also observed on the GPU.
- **Open:** `label_eos` semantics (M-D030) need a yes/no from the owner; the spec PDF is still absent, so the from-scratch rules still come from DESIGN.md.
- **Next:** point the manifest at the real train/val files, calibrate on the real train split, vocab-size study, then the real sweep (P05).

## [2026-11-05] M03 - SFT trainer, decoder, exact-match evaluator, test-access ledger
- **Goal:** fine-tune on QA pairs, decode, score exact match, and make test access auditable.
- **Done:** weight-decay fix (flag kept); `slm.sft_train` (data, trainer, per-seed runner, configs/sft.yaml); `slm.generation` (greedy plus seeded sampling); `slm.sft_eval` (exact match, contains, before/after table); `slm.guard` ledger and the manifest refusal; HPARAM_PROTOCOL sections 6 and 7; scripts/m03_dry_run.py.
- **Decisions:** M-D035 to M-D042. **Experiments:** M-E005. **Failures:** M-F005.
- **Open:** exact-match definition (sentence vs value) needs the owner's yes; the 7b scope came through a peer session.
- **Next:** real corpus, real SFT, base zero-shot and 2-shot prompts (DESIGN 7.2).

## [2026-11-05] M04 - Value-match metric, base prompts, generate CLI, bundle, fresh-clone test
- **Goal:** the demo and release pieces the course needs, runnable from a clean machine.
- **Done:** `exact_value_match` primary metric (KB-based exclusivity); base zero-shot and 2-shot prompts with exemplars outside E0/E1/E2; before/after table of three variants; `slm.bundle`, `scripts/make_bundle.py`, `scripts/generate.py` (one-shot, interactive, sampling), `scripts/fresh_clone_test.py`; `docs/README_TEMPLATE.md`; `scripts/m04_dry_run.py`.
- **Decisions:** M-D043 to M-D050. **Experiments:** M-E006.
- **Open:** no SFT training CLI; seed rule is by validation loss, not the val-probe rule; exemplar ids belong to the mock split; spec PDF absent.
- **Next:** real corpus and runs, then the real bundle.
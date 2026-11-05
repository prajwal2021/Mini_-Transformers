# Model-stream journal

## M01 (2026-11-05) tokenizer, model, packing, GPU smoke test
- **Goal:** everything on the model side that needs no corpus (branch `model-stream`, worktree `slm-model`).
- **Done:** from-scratch byte-level BPE with train-only guard and calibration (`src/slm/tokenizer/`); 12.4M-parameter decoder-only Transformer with explicit attention and document masking (`src/slm/model/`, `configs/model.yaml`); document-aware packing (`src/slm/data_loading/`); synthetic mock corpus (`tests/fixtures/`); 35 tests in `tests/model_stream/` (3 need a GPU); `scripts/gpu_smoke.py`.
- **Decisions:** M-D001 to M-D020. **Experiments:** M-E001, M-E002. **Failures:** M-F001, M-F002.
- **Results:** 12,417,024 parameters; mock tokenizer reaches vocab 4096; 180k positions/s at batch 32 using 4.6 GB; about 2 minutes for 1M tokens x 20 epochs.
- **Problems:** spec PDF not in the repo (rules taken from DESIGN.md); `torch.compile` unavailable; mock text too small for 4096 merges at min_frequency 2.
- **Next:** wire the real train split into `train_tokenizer` once the data stream fixes a file format (M-D009), run the vocab-size study, then the real training loop (P05).

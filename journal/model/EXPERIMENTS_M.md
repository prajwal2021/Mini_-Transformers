# Model-stream experiments (M-E###)

## M-E001 GPU smoke test (M01)
- Command: `python scripts/gpu_smoke.py --json reports/model/gpu_smoke.json`
- Machine: NVIDIA GeForce RTX 5080 Laptop GPU (15.9 GB), torch 2.11.0+cu128, CUDA 12.8, bf16 autocast, TF32 on, fused AdamW.
- Data: mock corpus (200 documents), tokenizer trained on it (vocab 4096), 97 packed sequences of 512, packing efficiency 98.4%.
- Eager, batch 32, 300 steps: 180,200 positions/s (177,400 real tokens/s), 90.9 ms/step, peak memory 4.60 GB.
- Loss: 8.367 at step 0 (ln 4096 = 8.318), 0.074 at step 300. The mock set has only 97 sequences, so this is memorisation, not generalisation.
- `torch.compile`: not available (M-F001).
- Estimate, 1M tokens x 20 epochs = 20M real tokens: 1.9 min at the mock packing efficiency, 2.1 min at 90% efficiency (compute only, excludes evaluation and checkpoint I/O).
- Batch-size probe (peak memory): 16 -> 2.4 GB, 32 -> 4.6 GB, 64 -> 9.0 GB, 96 -> 13.4 GB.
- Verdict: pipeline works end to end on GPU; throughput is far above what P05 needs.

## M-E002 Mock-corpus calibration
- Tokenizer vocab 4096 (min_frequency 1). 200 documents, 41,916 words, 48,692 tokens.
- tokens_per_word 1.162; share of documents over 512 tokens (with eos) 4.0%; mean 243 tokens per document, max 829.
- The mock is synthetic. The real figures must be recomputed with `slm.tokenizer.calibrate` on the real train split.

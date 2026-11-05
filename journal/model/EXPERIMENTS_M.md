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

## M-E003 M02 dry run on the mock corpus (reports/model/m02_dry_run.json)
- Pipeline: manifest -> tokenizer (vocab 4096, min_frequency 1) -> token cache -> 2 seeds x 8 epochs, batch 8 (13 steps/epoch, 104 steps), warmup 20, GPU bf16 -> checkpoint -> ModelScorer.
- Phases (s): manifest 0.04, tokenizer train 0.17, tokenize + pack 0.09 (cache hit 0.04), training both seeds 10.2, sweep of 4 configs x 3 epochs 6.6.
- Per seed: 5.9 s and 4.2 s wall (4.4 s and 4.1 s training); train loss 7.22 -> 1.74 (seed 0) and 7.20 -> 1.79 (seed 1); val loss 5.56 at epoch 1, minimum 2.65 around epoch 5, 2.68 / 2.65 at epoch 8 (the mock set is tiny, so the val loss turns up slightly).
- Checkpoint sizes: epoch_*.pt 47.4 MB each (5 per seed), last.pt 142.2 MB.
- ModelScorer toy pair: the natural continuation " before the doors open." scores -7.86; the nonsense " zzqx wiggle plonk." scores -152.5.
- Sweep plumbing: chosen lr 1e-3, dropout 0.0, best epoch 3, val 2.742. Not a tuning result.
- Mock-split statistics: train tokens_per_word 1.162, 4.0% of documents over 512 tokens; val 1.293 and 6.7%.

## M-E004 GPU determinism check (scratch script, not committed)
- RTX 5080 laptop, 3 epochs of the real model on the mock set, batch 8, bf16, same seed. Rerun vs rerun: max |dW| = 0 with and without `deterministic`. Interrupted at epoch 1 and resumed vs uninterrupted: max |dW| = 0 in both settings. One machine and a short run, so an observation only (see docs/HPARAM_PROTOCOL.md section 5).

## M-E005 M03 mock dry run (plumbing only)
- 2 seeds pretrained 8 epochs (about 9.5 s for both), SFT on sft_mock/sft_train 6 epochs each (7 s for both, best epoch 6, sft_val loss 3.47 and 3.41, still falling), then greedy decoding on E0 336 / E1 144 / E2 180 questions for the pretrained and the SFT checkpoint of each seed (144 s per seed for both checkpoints). Exact match and contains-gold were 0.000 everywhere for both checkpoints, as expected for a model that saw 200 mock documents and 6 SFT epochs; its answers look like "The pets is." Ledger: 1 line. No prompt was truncated.
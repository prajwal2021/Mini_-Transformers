# M02 report back

## 1. Checks
- **Fast tests** (`tests/model_stream -m "not gpu"`): `59 passed, 4 deselected in 7.85s`
- **GPU tests** (`-m gpu`, RTX 5080 Laptop): `4 passed, 59 deselected in 9.83s` (bf16 forward, real 12M model overfits 16 sequences, smoke train, real-model train + checkpoint + ModelScorer on cuda)
- **Whole repo** (includes the data stream's existing tests): `265 passed in 187.12s (0:03:07)`
- **Ruff** (all model-stream files): `All checks passed!`
- No test of mine exceeds 30 s (slowest 3.8 s), so no `slow` marks were needed.
- `git log --oneline -3` and `git status --short`: see the end of this file (filled in after the commit).

## 2. Manifest format and the scorer's boundary decision
**Manifest** (docs/SPLIT_MANIFEST.md): JSON `{"version": 1, "files": {"<path relative to the manifest>": {"split": "train|val|test", "sha256": "<hex of raw bytes>"}}}`. The tokenizer trainer takes `train` only; the token cache and the training loop take `train` and `val`; `test` is refused everywhere. A file is refused if it is unlisted, listed under another split, or its hash differs. File names are no longer inspected: a val file called `part2.txt` is refused (test), and a tampered train file is refused (test). Content format stays provisional: `.jsonl` with `{"text": ...}` or `.txt` with form-feed-separated documents.

**ModelScorer boundary** (M-D032): prompt and continuation are tokenised **separately** and the ids concatenated, after moving one trailing prompt space onto the continuation (`"is " + "Caldreth"` becomes `"is" + " Caldreth"`).
- Why separate: the context must not depend on the continuation being scored, and the same value string must give identical tokens under every prompt (needed for ranking values across entities and for the binding score). Joint tokenisation can merge across the boundary and leak the continuation into the context.
- Why the space shift: the GPT-2 pre-tokeniser glues a space to the following word, so a bare trailing-space prompt would otherwise create an off-distribution token `" "` followed by an unspaced word. After the shift the ids equal the joint tokenisation of the full sentence (tested).
- Tests: equals a manual log-softmax computation (1e-4), batched equals single in any order, chain rule `score(p, a+b) = score(p, a) + score(p+a, b)`, first continuation token scored from prompt-only logits, prompt ids unchanged by the continuation, no eos appended, edge cases (empty prompt raises, empty continuation is 0.0, long prompt trimmed from the left, over-long continuation raises).

## 3. Dry-run numbers (mock corpus, `reports/model/m02_dry_run.json`)
2 seeds x 8 epochs, real 12.4M model, GPU bf16, batch 8 (13 steps per epoch, 104 steps), warmup 20.
| Item | Value |
|---|---|
| Seconds per seed run | 5.9 (seed 0, includes CUDA warm-up) and 4.2 (seed 1); training part 4.4 and 4.1 |
| Phases | manifest 0.04 s, tokenizer training 0.17 s, tokenise + pack 0.09 s (cache hit 0.04 s), both seeds 10.2 s, 4-config sweep (3 epochs each) 6.6 s |
| Train loss start -> end | 7.22 -> 1.74 (seed 0), 7.20 -> 1.79 (seed 1) |
| Val loss | epoch 1: 5.56; minimum about 2.65 near epoch 5; epoch 8: 2.68 / 2.65 (tiny set, slight overfit) |
| Checkpoint sizes | `epoch_NNN.pt` 47.4 MB each (epochs 1, 2, 3, 5, 8); `last.pt` (with optimizer) 142.2 MB |
| ModelScorer toy pair | " before the doors open." -> -7.86; " zzqx wiggle plonk." -> -152.5 |
| Sweep (plumbing only) | chosen lr 1e-3, dropout 0.0, best epoch 3 |
| Mock split stats | train 1.162 tokens/word, 4.0% of docs over 512; val 1.293, 6.7% |

Extrapolation: at the M01 speed the real run (1M tokens x 20 epochs) is about 2 minutes per seed, so the 9-run sweep plus 3 final seeds is on the order of 25 to 30 minutes of GPU time.

## 4. Remaining non-determinism and the resume test
- **Resume test (CPU, in the suite):** 4 epochs straight vs 2 epochs + resume + 2 epochs gives bit-identical weights and identical loss.csv rows (dropout 0.1 included, because the RNG state is saved). A second test checks that rows left by a crashed partial epoch are dropped on resume.
- **GPU observation** (M-E004, scratch script): same-seed rerun and interrupted-then-resumed run were both bit-identical (max |dW| = 0), with and without `deterministic`, on this machine for a 3-epoch run. That is an observation, not a guarantee.
- **Still not guaranteed** (docs/HPARAM_PROTOCOL.md section 5): CUDA atomics in embedding backward and some reductions; cuBLAS/cuDNN algorithm choice and TF32/bf16 accumulation order across GPUs, drivers and torch builds; resuming on another device type, torch version or thread count; thermal wall-clock variation. Resume only works at epoch boundaries.

## 5. Decisions, deviations, doubts
Decisions M-D021 to M-D034 (journal/model/DECISIONS_M.md):
021 manifest format; 022 manifest guard replaces the name guard (supersedes M-D008); 023 token cache format and key; 024 weight decay on Linear weights only; 025 warmup + cosine schedule; 026 run-directory layout; 027 checkpoint schedule and contents; 028 epoch-boundary resume; 029 NaN/inf abort; 030 `label_eos` meaning; 031 fp32 token-weighted validation; 032 scorer boundary tokenisation; 033 scorer details (no bos/eos, empty prompt raises, left truncation); 034 sweep grid and selection.

Deviations and open points:
1. **`label_eos` (please confirm).** "eos unlabeled as in M01" is ambiguous. In M01, `<|eos|>` is a *target* (the model learns to end documents) while the label *at* the eos position is masked. I made `label_eos: true` (default) keep that behaviour and `false` mask the eos target. If you meant that eos must never be predicted in pretraining, set `label_eos: false`. SFT needs `true`.
2. **Weight decay** now excludes embeddings (as asked), which differs from DESIGN section 5 (decay on all 2-D matrices including the tied embedding). Logged as M-D024.
3. **Spec PDF:** `docs/Term_Project.pdf` still does not exist in the repo (also searched `Documents`), so the from-scratch rules still come from DESIGN.md; no difference could be checked.
4. **Mock-only:** nothing here is a tuning or modelling result. The sweep winner (lr 1e-3, dropout 0) comes from 97 sequences and means nothing.
5. **Test-split protection** is by manifest; nothing stops a caller from reading a `test` file directly with pandas. The loaders refuse it, but that is the limit.
6. **Existing M01 API changes:** `train_tokenizer` now takes a manifest (not paths); `read_documents` and `assert_train_only` were removed; `calibrate` takes documents. `gpu_smoke.py` and the M01 tests were updated accordingly.
7. `runs/m02_dry_run/` (mock checkpoints, about 0.6 GB) is left out of the commit.

## git (after commit)
```n4dffffa M02: training loop, ModelScorer, manifest guard, hparam protocol
ed78f3c M01: tokenizer, model, packing, GPU smoke test
c092070 P02b7f: duplicate-aware refill, F008 refill (G1 not met)

git status --short:
?? runs/m02_dry_run/
```

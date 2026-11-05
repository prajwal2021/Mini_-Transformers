# Hyper-parameter protocol

Status: plumbing verified on the mock corpus. **Real tuning waits for the real corpus.**

## 1. Rule
Hyper-parameters are chosen by **validation loss only**, computed on the val split of the split
manifest (documents the tokenizer and the model never train on). Probe accuracy, test loss, and
test probes are never used. `slm.train.sweep.select_best` reads nothing but `val_by_epoch`, and a
unit test puts conflicting probe and test numbers in the rows to prove it.

## 2. Grid
| Parameter | Values | Why |
|---|---|---|
| peak learning rate | 3e-4, 6e-4, 1e-3 | brackets the DESIGN default 6e-4 |
| dropout | 0.0, 0.1, 0.2 | small data, many epochs: overfitting is the main risk |
| epochs | via the checkpoint schedule {1,2,3,5,8,12,16,20} | one 20-epoch run evaluates all of them |

Fixed during the sweep: AdamW betas (0.9, 0.95), weight decay 0.1 on linear weight matrices,
grad clip 1.0, warmup 200 steps (scale it down if an epoch has fewer than ~100 steps), cosine to
10% of peak, batch 32, architecture from `configs/model.yaml`. The grid is 9 runs, at most about 2
minutes each on the RTX 5080 (M-E001), so it is cheap. Widen it only by logging a new decision.

## 3. Procedure
1. `python scripts/sweep.py --manifest <splits.json> --tokenizer <tokenizer.json> --name <run>`
2. Sweep: one seed (seed 0) per grid point, full `epochs`, every configuration recorded in
   `runs/<run>/sweep/results.json` (status, val loss at each scheduled epoch, seconds). Aborted runs
   (non-finite loss) stay in the file with their message and are excluded from selection.
3. Selection: for each run take its lowest val loss over the scheduled epochs; the run with the
   lowest value wins; ties go to the earlier row. `chosen.json` stores lr, dropout, best epoch.
4. Final: 3 seeds (0, 1, 2) with the chosen lr and dropout, full 20 epochs, into
   `runs/<run>/final/seed<k>/`. Everything else is unchanged.
5. The checkpoint that is *released* is chosen later by the pre-registered probe rule in DESIGN
   section 5 (val probes), not by this protocol. The "best epoch" here is informational and tells us
   where validation loss bottoms out.

## 4. Records
Each run directory holds `config.yaml`, `meta.json` (git commit, tokenizer hash, tokenized-data
hash, torch/CUDA versions, device), `loss.csv` and checkpoints. Every sweep configuration is logged
as an M-E record.

## 5. Remaining non-determinism
Seeds fix model initialisation, dropout masks (global torch RNG, saved and restored on resume), and
epoch order (a separate generator keyed by seed and epoch). Still not guaranteed bit-for-bit:
- CUDA kernels that use atomics (embedding backward, some reductions), cuBLAS algorithm choice, and
  TF32/bf16 accumulation order can differ between GPU models, drivers, and torch builds.
  `deterministic: true` switches on `torch.use_deterministic_algorithms(warn_only=True)`; it costs
  speed and still gives no promise across hardware.
- A resumed run replays from an epoch boundary. On CPU it is bit-identical to an uninterrupted run
  (tested). On the RTX 5080 laptop a 3-epoch check was also bit-identical for both rerun and resume
  (M-E004), but that is an observation on one machine, not a guarantee.
- Resuming on a different device type, torch version, or thread count can change low-order bits.
- Val loss is computed in fp32 with dropout off, training in bf16 autocast, so a val number is not
  reproducible from a checkpoint trained under a different dtype setting.
- Wall-clock figures vary with laptop thermals.

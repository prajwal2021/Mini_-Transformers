# Checkpoints in this bundle

All three come from **seed 0** of the final runs (three seeds were trained; the others are not bundled). Weights only; no optimizer state.

| directory | kind | variant | parameters | size | what it is |
|---|---|---|---|---|---|
| `pretrained/` | pretrained | - | 12,417,024 | 47.4 MiB | pretrained from scratch, seed 0, epoch 30 = E* (the primary analysis checkpoint) |
| `sft_early_stopped/` | sft | early_stopped_primary | 12,417,024 | 47.4 MiB | PRE-SPECIFIED primary SFT, seed 0: best epoch by SFT-validation loss (epoch 1), from the E*=30 pretrained checkpoint |
| `sft_fixed3/` | sft | fixed3_posthoc | 12,417,024 | 47.4 MiB | POST-HOC secondary SFT, seed 0: fixed 3 epochs, no early stopping, from the E*=30 pretrained checkpoint |

**Which SFT is which.** `sft_early_stopped` is the **pre-specified primary** SFT: early stopping on the loss of a 12-fact SFT-validation set, which
selected epoch 1 for seed 0 (so it is a lightly trained model). `sft_fixed3` is a **post-hoc secondary** SFT added after the results were seen
(fixed 3 epochs, no early stopping, otherwise the same configuration); it answers the training facts far better but is not the pre-specified result.
The report's primary numbers are for `sft_early_stopped`; the fixed-3 numbers are labelled post-hoc.

Each directory has `model.pt`, `tokenizer.json` (the same file in all three), `model_config.json` and `bundle_manifest.json` (sha256 of the three
files, git commit, parameter count). `MANIFEST.json` at the top lists the sha256 of every file in the bundle; `scripts/make_bundle.py --verify bundle`
re-checks it, and `scripts/generate.py` checks the per-model hashes at every load.

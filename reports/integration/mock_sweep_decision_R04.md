# Sweep decision (validation probes)

**MOCK RUN: toy corpus. NOTHING HERE IS A RESULT.**

Rule v2: stored rate smoothed over 3 checkpoints; config score = best smoothed rate; near-ties (within 1 SE) go to the lower validation loss; **E\*** = earliest checkpoint whose smoothed rate is within 1 SE of the chosen config's best. Chance guard: if that best is not above `init` by more than 2 SE, **E\*** = the epoch of minimum validation loss and the result is flagged `no_val_storage`. Validation probes only (no test probe is scored).

- chosen config: `cfg04_lr0.001_dropout0.0_batch_size32`; **E\* = 12** (min validation loss (chance guard); raw stored rate 0.046, smoothed 0.054)
- config best smoothed rate 0.098 (SE 0.022, raw best 0.104) at epoch 1; `init` 0.100; guard threshold (init + 2 SE) 0.145
- `no_val_storage`: **true**
- validation-loss-optimal epoch of the same config: **12** (val loss 2.6870, stored rate there 0.046); val loss at E\*: 2.6870
- near-ties considered (7): `cfg00_lr0.0003_dropout0.0_batch_size32`, `cfg01_lr0.0003_dropout0.1_batch_size32`, `cfg02_lr0.0006_dropout0.0_batch_size32`, `cfg03_lr0.0006_dropout0.1_batch_size32`, `cfg04_lr0.001_dropout0.0_batch_size32`, `cfg05_lr0.001_dropout0.1_batch_size32`, `cfg06_lr0.001_dropout0.0_batch_size16`
- `init` (untrained, per config): stored rate 0.100; null_stored_rate 0.102
- **WARNING: no storage is detectable on validation (best smoothed rate 0.098 is not above `init` 0.100 by more than 2 SE = 0.045). The chance guard set E\* to the epoch of minimum validation loss; the sweep cannot tune lr/dropout/batch size by storage and must not be read as a result.**

Cells are `raw stored rate / val loss`; `*` marks the config's best SMOOTHED checkpoint, `E` marks E* of the chosen config.

| config | 1 | 2 | 3 | 5 | 8 | 12 |
|---|---|---|---|---|---|---|
| cfg00_lr0.0003_dropout0.0_batch_size32 | 0.108 / 7.30 | 0.083 / 6.47 | 0.067 / 5.73 | 0.075 / 4.52 | 0.096 / 3.65 | 0.096 / 3.38* |
| cfg01_lr0.0003_dropout0.1_batch_size32 | 0.104 / 7.33* | 0.096 / 6.56 | 0.092 / 5.86 | 0.071 / 4.62 | 0.075 / 3.73 | 0.092 / 3.44 |
| cfg02_lr0.0006_dropout0.0_batch_size32 | 0.108 / 7.04* | 0.087 / 6.10 | 0.083 / 5.30 | 0.071 / 3.77 | 0.083 / 3.03 | 0.087 / 2.86 |
| cfg03_lr0.0006_dropout0.1_batch_size32 | 0.104 / 7.13 | 0.087 / 6.08 | 0.083 / 5.30 | 0.071 / 3.90 | 0.096 / 3.08 | 0.096 / 2.88* |
| **cfg04_lr0.001_dropout0.0_batch_size32** | 0.104 / 7.04* | 0.092 / 6.08 | 0.083 / 4.79 | 0.067 / 3.38 | 0.062 / 2.75 | 0.046 / 2.69E |
| cfg05_lr0.001_dropout0.1_batch_size32 | 0.096 / 6.87 | 0.075 / 5.98* | 0.087 / 4.96 | 0.062 / 3.59 | 0.087 / 2.86 | 0.079 / 2.73 |
| cfg06_lr0.001_dropout0.0_batch_size16 | 0.079 / 6.25* | 0.108 / 4.33 | 0.079 / 3.27 | 0.067 / 2.72 | 0.092 / 2.73 | 0.096 / 2.69 |

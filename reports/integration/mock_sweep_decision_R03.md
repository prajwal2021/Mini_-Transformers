# Sweep decision (validation probes)

**MOCK RUN: toy corpus. NOTHING HERE IS A RESULT.**

Rule: config score = best val-probe stored rate over the schedule; near-ties within 0.01 go to the lower validation loss; **E\*** = earliest checkpoint within the tolerance of the chosen config's best rate. Validation probes only (no test probe is scored); chance reference = the untrained model (`init`).

- chosen config: `cfg04_lr0.0006_dropout0.0_batch_size16`; **E\* = 1** (stored rate 0.113; config best 0.113 at epoch 1)
- validation-loss-optimal epoch of the same config: **8** (val loss 2.6938, stored rate there 0.100); val loss at E\*: 7.5084
- near-ties considered (5): `cfg00_lr0.0003_dropout0.0_batch_size16`, `cfg03_lr0.0003_dropout0.1_batch_size32`, `cfg04_lr0.0006_dropout0.0_batch_size16`, `cfg07_lr0.0006_dropout0.1_batch_size32`, `cfg09_lr0.001_dropout0.0_batch_size32`
- `init` (untrained, per config): stored rate 0.108; null_stored_rate 0.100
- **WARNING: the chosen config's best stored rate (0.113) is not above chance (0.108 = the larger of `init` and `null_stored_rate`) by more than the tolerance: no storage is detected, so E\* only picks the noisiest early checkpoint and must not be used for a real run.**

Cells are `stored rate / val loss`; `*` marks the config's best stored rate, `E` marks E* of the chosen config.

| config | 1 | 2 | 3 | 5 | 8 | 12 |
|---|---|---|---|---|---|---|
| cfg00_lr0.0003_dropout0.0_batch_size16 | 0.071 / 6.83 | 0.067 / 5.29 | 0.079 / 4.35 | 0.092 / 3.33 | 0.108 / 2.93* | 0.096 / 2.86 |
| cfg01_lr0.0003_dropout0.0_batch_size32 | 0.058 / 7.34 | 0.075 / 6.54 | 0.087 / 5.74 | 0.087 / 4.55 | 0.092 / 3.67 | 0.104 / 3.40* |
| cfg02_lr0.0003_dropout0.1_batch_size16 | 0.071 / 6.75 | 0.075 / 5.37 | 0.083 / 4.39 | 0.096 / 3.36 | 0.087 / 2.94 | 0.104 / 2.85* |
| cfg03_lr0.0003_dropout0.1_batch_size32 | 0.079 / 7.38 | 0.067 / 6.48 | 0.117 / 5.74* | 0.092 / 4.57 | 0.087 / 3.69 | 0.083 / 3.42 |
| **cfg04_lr0.0006_dropout0.0_batch_size16** | 0.113 / 7.51*E | 0.067 / 4.75 | 0.087 / 3.56 | 0.092 / 2.81 | 0.100 / 2.69 | 0.113 / 2.70* |
| cfg05_lr0.0006_dropout0.0_batch_size32 | 0.092 / 7.23 | 0.087 / 6.28 | 0.083 / 5.30 | 0.092 / 3.80 | 0.100 / 3.01* | 0.096 / 2.85 |
| cfg06_lr0.0006_dropout0.1_batch_size16 | 0.075 / 6.47 | 0.079 / 4.76 | 0.075 / 3.59 | 0.104 / 2.83* | 0.067 / 2.70 | 0.058 / 2.69 |
| cfg07_lr0.0006_dropout0.1_batch_size32 | 0.075 / 7.16 | 0.087 / 6.17 | 0.096 / 5.19 | 0.087 / 3.77 | 0.108 / 3.01* | 0.108 / 2.86* |
| cfg08_lr0.001_dropout0.0_batch_size16 | 0.071 / 6.19 | 0.075 / 4.32 | 0.096 / 3.17* | 0.092 / 2.72 | 0.071 / 2.69 | 0.092 / 2.70 |
| cfg09_lr0.001_dropout0.0_batch_size32 | 0.108 / 7.92* | 0.092 / 5.84 | 0.096 / 4.90 | 0.087 / 3.29 | 0.092 / 2.75 | 0.104 / 2.72 |
| cfg10_lr0.001_dropout0.1_batch_size16 | 0.075 / 6.28 | 0.083 / 4.59* | 0.075 / 3.26 | 0.083 / 2.68* | 0.062 / 2.71 | 0.058 / 2.70 |
| cfg11_lr0.001_dropout0.1_batch_size32 | 0.092 / 7.71 | 0.079 / 5.93 | 0.067 / 4.75 | 0.100 / 3.39* | 0.092 / 2.79 | 0.075 / 2.69 |

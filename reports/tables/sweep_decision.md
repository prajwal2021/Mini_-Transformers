# Sweep decision (validation probes)

Rule: config score = best val-probe stored rate over the schedule; near-ties within 0.01 go to the lower validation loss; **E\*** = earliest checkpoint within the tolerance of the chosen config's best rate. Validation probes only (no test probe is scored); chance reference = the untrained model (`init`).

- chosen config: `cfg01_lr0.001_dropout0.1`; **E\* = 1** (stored rate 0.087; config best 0.087 at epoch 1)
- validation-loss-optimal epoch of the same config: **3** (val loss 5.3593, stored rate there 0.083); val loss at E\*: 5.9674
- near-ties considered (2): `cfg00_lr0.0003_dropout0.1`, `cfg01_lr0.001_dropout0.1`
- `init` (untrained, per config): stored rate 0.079; null_stored_rate 0.093
- **WARNING: the chosen config's best stored rate (0.087) is not above chance (0.093 = the larger of `init` and `null_stored_rate`) by more than the tolerance: no storage is detected, so E\* only picks the noisiest early checkpoint and must not be used for a real run.**

Cells are `stored rate / val loss`; `*` marks the config's best stored rate, `E` marks E* of the chosen config.

| config | 1 | 2 | 3 |
|---|---|---|---|
| cfg00_lr0.0003_dropout0.1 | 0.075 / 6.60 | 0.071 / 5.89 | 0.079 / 5.74* |
| **cfg01_lr0.001_dropout0.1** | 0.087 / 5.97*E | 0.079 / 5.52 | 0.083 / 5.36 |

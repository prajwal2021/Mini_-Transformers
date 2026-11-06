# Sweep decision (validation probes)

Rule v2: stored rate smoothed over 3 checkpoints; config score = best smoothed rate; near-ties (within 1 SE) go to the lower validation loss; **E\*** = earliest checkpoint whose smoothed rate is within 1 SE of the chosen config's best. Chance guard: if that best is not above `init` by more than 2 SE, **E\*** = the epoch of minimum validation loss and the result is flagged `no_val_storage`. Validation probes only (no test probe is scored).

- chosen config: `cfg06_lr0.001_dropout0.1_batch_size16`; **E\* = 30** (earliest smoothed rate within 1 SE of the best; raw stored rate 0.242, smoothed 0.251)
- config best smoothed rate 0.273 (SE 0.032, raw best 0.275) at epoch 60; `init` 0.100; guard threshold (init + 2 SE) 0.164
- `no_val_storage`: **false**
- validation-loss-optimal epoch of the same config: **12** (val loss 2.7325, stored rate there 0.171); val loss at E\*: 3.6842
- near-ties considered (2): `cfg05_lr0.001_dropout0.1_batch_size32`, `cfg06_lr0.001_dropout0.1_batch_size16`
- `init` (untrained, per config): stored rate 0.100; null_stored_rate 0.087

Cells are `raw stored rate / val loss`; `*` marks the config's best SMOOTHED checkpoint, `E` marks E* of the chosen config.

| config | 1 | 2 | 3 | 5 | 8 | 12 | 16 | 20 | 25 | 30 | 40 | 50 | 60 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| cfg00_lr0.0003_dropout0.0_batch_size32 | 0.096 / 6.35 | 0.092 / 5.10 | 0.079 / 4.53 | 0.087 / 3.94 | 0.104 / 3.44 | 0.142 / 3.10 | 0.133 / 3.09 | 0.125 / 3.35 | 0.138 / 3.77 | 0.138 / 4.18 | 0.146 / 4.74 | 0.154 / 5.07 | 0.163 / 5.27* |
| cfg01_lr0.0003_dropout0.1_batch_size32 | 0.092 / 6.39 | 0.104 / 5.16 | 0.108 / 4.56 | 0.079 / 3.98 | 0.079 / 3.53 | 0.121 / 3.06 | 0.146 / 2.84 | 0.150 / 2.73 | 0.154 / 2.71 | 0.167 / 2.74 | 0.208 / 2.87 | 0.208 / 2.98 | 0.212 / 3.05* |
| cfg02_lr0.0006_dropout0.0_batch_size32 | 0.100 / 5.78 | 0.096 / 4.65 | 0.092 / 4.16 | 0.092 / 3.61 | 0.117 / 3.11 | 0.108 / 2.95 | 0.133 / 3.27 | 0.108 / 3.80 | 0.125 / 4.39 | 0.108 / 4.75 | 0.138 / 5.27 | 0.154 / 5.58 | 0.158 / 5.78* |
| cfg03_lr0.0006_dropout0.1_batch_size32 | 0.100 / 5.83 | 0.125 / 4.71 | 0.092 / 4.22 | 0.075 / 3.70 | 0.113 / 3.15 | 0.142 / 2.81 | 0.188 / 2.72 | 0.208 / 2.75 | 0.192 / 2.89 | 0.212 / 3.06 | 0.200 / 3.41 | 0.208 / 3.63 | 0.221 / 3.76* |
| cfg04_lr0.001_dropout0.0_batch_size32 | 0.075 / 5.40 | 0.083 / 4.39 | 0.117 / 3.95 | 0.108 / 3.43 | 0.113 / 3.02 | 0.150 / 3.04 | 0.133 / 3.63 | 0.129 / 4.27 | 0.146 / 4.83 | 0.146 / 5.23 | 0.146 / 5.75 | 0.163 / 6.06 | 0.188 / 6.23* |
| cfg05_lr0.001_dropout0.1_batch_size32 | 0.087 / 5.47 | 0.104 / 4.44 | 0.113 / 4.01 | 0.087 / 3.50 | 0.154 / 3.00 | 0.225 / 2.74 | 0.308 / 2.76 | 0.283 / 2.92 | 0.308 / 3.19 | 0.292 / 3.43 | 0.308 / 3.91 | 0.292 / 4.17* | 0.312 / 4.32 |
| **cfg06_lr0.001_dropout0.1_batch_size16** | 0.087 / 4.96 | 0.104 / 4.15 | 0.092 / 3.76 | 0.121 / 3.15 | 0.183 / 2.80 | 0.171 / 2.73 | 0.229 / 2.87 | 0.221 / 3.07 | 0.242 / 3.39 | 0.242 / 3.68E | 0.271 / 4.18 | 0.271 / 4.44 | 0.275 / 4.60* |

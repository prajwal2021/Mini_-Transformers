# Analysis input contract: the long-format probe table

`scripts/run_analysis.py --input <table> --out reports/` reads one **long-format probe table**
(CSV or Parquet). One row = one probe outcome for one fact, from one trained model (seed) at one
checkpoint, under one regime and one prompt variant. The producer is the probe/eval stream (P06);
until real probes exist the table comes from `slm.analysis.simulate`. Validation lives in
`slm.analysis.schema.validate_table` and fails loudly on any violation.

## Required columns

| column | type | meaning |
|---|---|---|
| `fact_id` | str | measured-fact id (the cluster unit; the random-effect / bootstrap unit) |
| `seed` | int | model seed (0, 1, 2); model-init + data-order seed, same corpus |
| `checkpoint` | int | training step of the checkpoint (log-spaced, ~15 per seed) |
| `regime` | `iid` \| `novel` | probe regime: `iid` = wording drawn from the training frame distribution, `novel` = held-out wording (verified no shared 8-gram with training text) |
| `freq_bin` | `low` \| `mid` \| `high` | assigned exposure bin (~5 / ~15 / ~45 train documents); constant within a fact |
| `div_bin` | `templated` \| `paraphrased` | assigned diversity condition; constant within a fact |
| `prompt_variant` | str | test-template label (`v1`..`v3`); the same labels are used in both regimes |
| `rank` | int 1..6 | rank of the correct value by log p(value \| prompt) among the 6 same-attribute values |
| `binding_score` | float | log p(v \| correct entity) - mean log p(v \| other entities of the same type) |
| `stored` | 0/1 | `rank == 1 and binding_score > 0` (DESIGN.md section 6); validated against the other two columns |

Uniqueness: `(fact_id, seed, checkpoint, regime, prompt_variant)` must be unique. Test probes
only: validation probes (checkpoint selection) must never be in this table.

## Optional covariates (used when present)

| column | type | use |
|---|---|---|
| `attr_type` | str | categorical covariate |
| `value_len` | int | value token length; standardised |
| `entity_freq` | float | entity mention count (log scale preferred); standardised |

These are the DESIGN.md covariates `value_len + entity_freq + attr_type`. They are constant
within a fact. Any other columns are ignored.

## Design assumptions the analysis relies on

- 6 cells (3 `freq_bin` x 2 `div_bin`), balanced by design (about 20 facts per cell); the
  validator warns if a cell has less than half the facts of the largest.
- Every seed has the primary checkpoint (the largest checkpoint present in all seeds, or
  `--checkpoint N`). Earlier checkpoints are used only for learning curves and acquisition steps.
- Exposure enters the model as the bin code `freq_c` in {-1, 0, +1}. Because the bins are about
  5/15/45 documents (a factor of 3 apart), this is log-linear in exposure with one unit = one
  tripling. If the P03 string-match counts show the bins are not evenly spaced on the log scale,
  add a numeric `log_exposure` column and revisit this in the PREREG before freezing.

## Simulated tables

```python
from slm.analysis.simulate import SimParams, simulate_probe_table
df = simulate_probe_table(SimParams(), seed=0)          # all 15 checkpoints, 32,400 rows
df.to_csv("sim_probe_table.csv", index=False)
```

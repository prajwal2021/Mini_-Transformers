# Analysis input contracts

`scripts/run_analysis.py --input <probe table> [--qa-input <QA table>] --out reports/` reads two
long-format tables (CSV or Parquet). Both are validated by `slm.analysis.schema` and fail loudly
on any violation. Hypotheses and tests: docs/ANALYSIS_HYPOTHESES.md.

## 1. Probe table (H1, H2)

One row = one probe outcome for one fact, one seed, one checkpoint, one prompt variant. This is
the eval stream's probe table (`slm.eval.probes.TABLE_COLUMNS`, docs/EVAL_COLUMNS.md); extra
columns are ignored.

| column | type | meaning |
|---|---|---|
| `fact_id` | str | measured fact; the cluster and bootstrap unit |
| `seed` | int | model seed (0, 1, 2) |
| `checkpoint` | int or `init` | training step; `init` (untrained model) is read as step 0 and is never the primary checkpoint |
| `probe_frame` | `canonical` \| `novel` | the prompt's frame (DESIGN section 6): canonical = KB canonical-sentence prefix, novel = new wording. This is the "frame" of H2 |
| `freq_bin` | `low` \| `mid` \| `high` | design cell (about 5 / 15 / 45 train documents); constant within a fact |
| `div_bin` | `templated` \| `paraphrased` | design cell; constant within a fact |
| `prompt_variant` | str | template label (`test-canon`, `test-n1..n3`, `val-...`); each variant belongs to exactly one frame |
| `rank` | int 1..6 | rank of the true value among the six same-attribute values |
| `binding_score` | float | log p(v given true entity) - mean log p(v given the other entities) |
| `stored` | 0/1 | `rank == 1 and binding_score > 0`; checked against the two columns |
| `split` | `val` \| `test` | `val` is for checkpoint selection only; the analysis uses `test` rows and refuses a table with none |
| `attribute_id` | str | the attribute; used as the `attr_type` categorical covariate; constant within a fact |
| `true_logprob`, `baseline_logprob` | float | the two terms of the binding score; `binding_score = true - baseline` (tolerance 0.005, checked) |

Optional fact-level columns (used when present; aliases accepted): `train_mentions` (measured
string-match train count; when present `freq_c` = log3(mentions) centred on its mean, otherwise
the bin code -1/0/+1), `value_len` (alias `value_len_tokens`), `entity_freq` (alias
`entity_mentions`; log scale preferred). `n_ties`, `null_stored_rate`, `*_tokennorm` and
`norm_unit` are ignored by the confirmatory analysis.

Uniqueness: `(fact_id, seed, checkpoint, split, prompt_variant)`.

**Document-level `regime` (iid / novel) is not part of this table.** DESIGN.md does not use it in
any hypothesis; it is the corpus-plan field `style_regime` and belongs to the eval stream's
`doc_loss_by_regime` output only. A01's `regime` moderator was a mislabelled stand-in for
`probe_frame` and has been removed (A-F001).

## 2. SFT QA table (H3, H4)

One row = one question for one fact under one model. DESIGN section 7: E0 = SFT-train facts with
train question templates (sanity), E1 = SFT-train facts with unseen test templates, E2 =
held-out facts (never in SFT) with unseen test templates. Facts are split 40% SFT-train / 10%
SFT-val / 50% held-out within each of the 6 cells; SFT-val facts are not evaluated.

| column | type | meaning |
|---|---|---|
| `fact_id` | str | fact |
| `seed` | int | model seed |
| `eval_set` | `E0` \| `E1` \| `E2` | evaluation set (alias `subset`) |
| `question_id` | str | the item; identical across models so items are paired |
| `model` | `base_0shot` \| `base_2shot` \| `sft` | zero-shot and fixed 2-shot pretrained model, and the SFT model (DESIGN section 7.2) |
| `exact_match` | 0/1 | exact value match (alias `correct`) |
| `stored_pretrain` | 0/1 | whether this fact was stored by the pretrained checkpoint that the SFT started from, same seed; the producer fixes the aggregation over probes (eval stream proposes >= 2 of 3 test probes) |
| `freq_bin`, `div_bin` | str | design cell of the fact |
| `sft_split` | `train` \| `heldout` | the fact's SFT split; checked: E0/E1 rows are `train`, E2 rows are `heldout`, and no fact is in both |

Uniqueness: `(fact_id, seed, eval_set, question_id, model)`. Every E2 question should be scored by
both the comparator (`base_2shot`) and `sft`. Optional `contains_match` is ignored.

The eval stream's frozen question file (`qa_test.jsonl`: `subset`, `fact_id`, `template_set`, ...)
matches these definitions (E2 = 60 held-out facts x 3 test templates in the mock); its result table
(`fact_id, model, subset, correct`) needs the extra columns `seed`, `question_id`, `stored_pretrain`,
`freq_bin`, `div_bin`, `sft_split`.

## Design assumptions the analysis relies on

- 6 cells (3 x 2), about 20 facts per cell; a warning is raised if a cell has under half the facts
  of the largest.
- The primary checkpoint is the largest test checkpoint present in every seed (or `--checkpoint N`).
  Earlier checkpoints feed only learning curves and acquisition steps.
- Exposure enters as `freq_c`: bin code now, log3(`train_mentions`) when P03 counts exist.

## Simulated tables

```python
from slm.analysis.simulate import SimParams, simulate_probe_table, simulate_qa_table
probe = simulate_probe_table(SimParams(), seed=0, include_val=True)
qa = simulate_qa_table(SimParams(), probe[probe["split"] == "test"], seed=1)
```

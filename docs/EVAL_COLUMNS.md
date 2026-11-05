# Evaluation table columns

Two different things used to be called "regime". They are now separate.

| name | level | values | meaning |
|---|---|---|---|
| `probe_frame` | probe (a prompt wording) | `canonical`, `novel` | `canonical` = the KB canonical sentence up to the value (the templated corpus phrasing). `novel` = hand-written natural question or statement that does not reuse that sentence frame. This is the "frame" of H2. |
| `regime` | document (val/test documents of the corpus plan) | `iid`, `novel` | Plan field `style_regime` (D-024). `iid`: style cards from the train marginals. `novel`: at least one held-out author_role (quality auditor, route editor) or tone (apologetic). Used only by `doc_loss_by_regime`. |

The probe table has NO `regime` column.

## Probe table (`slm.eval.probes.TABLE_COLUMNS`), one row per fact x prompt variant x checkpoint x seed

| column | meaning |
|---|---|
| `fact_id`, `attribute_id` | fact and its attribute (the six same-attribute values are the candidates) |
| `seed`, `checkpoint` | model seed and checkpoint id; `init` is the untrained model (epoch 0) |
| `split` | `val` (checkpoint selection only) or `test` (reported) |
| `probe_frame` | see above |
| `prompt_variant` | `<split>-canon` or `<split>-n1/n2/n3`; the template factor `(1 | template)` |
| `freq_bin`, `div_bin` | KB design cell (low/mid/high; templated/paraphrased) |
| `rank` | 1 + number of other candidates scoring >= the true value (ties count against the fact) |
| `binding_score` | log p(v given the true entity) - mean log p(v given each of the 5 other entities), summed log-probs |
| `stored` | `rank == 1 and binding_score > 0` (DESIGN section 6) |
| `true_logprob`, `baseline_logprob` | the two terms of the binding score |
| `n_ties` | other candidates with exactly the true score |
| `null_stored_rate` | permutation null: mean over the 5 other entities' values taken as pseudo-truth, same prompt and procedure, of `stored` (chance level for this row) |
| `rank_tokennorm`, `stored_tokennorm` | secondary sensitivity outcome: rank and stored on score / n_tokens |
| `norm_unit` | `token` if the scorer has `score_detailed`, else `char` (score per character of the continuation) |

## Other outputs
- `chance_report(table, by=("probe_frame","freq_bin","div_bin"))`: `n_probes, stored_rate, null_rate, diff`.
- `fact_level(table)`: per fact x checkpoint x seed, `stored_rate` (share of probes stored) and `null_stored_rate`.
- `checkpoint_summary(table)`: the chance report by checkpoint x seed.
- `doc_loss_by_regime`: `split, regime, group_by (all|author_role|tone|held_out_style), group, n_docs, n_tokens, mean_nll`.
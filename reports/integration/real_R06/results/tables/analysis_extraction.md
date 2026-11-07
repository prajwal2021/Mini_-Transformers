# Extraction tests: H3 (confirmatory) and H4 (secondary), E2 held-out facts

QA table: `qa.csv`; facts 60. Unit = fact (stored / correct on >= 2 of 3 items within a seed, majority of seeds); comparator = base_2shot.

## Tests and effect sizes (95% stratified fact-bootstrap CIs)

| component | test | scale | estimate | ci_low | ci_high | p_raw | direction_ok | detail |
|---|---|---|---|---|---|---|---|---|
| H3a | McNemar exact, base vs SFT (E2) | risk diff | 0 | 0 | 0 | 1 | False | base-only correct 0, SFT-only correct 0 |
| H3b | Fisher exact, stored x correct (SFT, E2) | risk diff | 0 | 0 | 0 | 1 | False | odds ratio nan |
| H4 | permutation, gain(paraphrased) - gain(templated) | risk diff | 0 | 0 | 0 | 1 | False | gain paraphrased 0.000, templated 0.000 |

## McNemar (base vs SFT) and Fisher (stored x correct) per diversity condition

| div_bin | n_facts | acc_base | acc_sft | gain | mcnemar_p | fisher_p_stored_x_correct |
|---|---|---|---|---|---|---|
| templated | 30 | 0.000 | 0.000 | 0.000 | 1.000 | 1.000 |
| paraphrased | 30 | 0.000 | 0.000 | 0.000 | 1.000 | 1.000 |

## 2x2 counts: stored x QA-correct (SFT model) per diversity condition

| div_bin | stored | n_correct | n_wrong |
|---|---|---|---|
| templated | stored | 0 | 1 |
| templated | not stored | 0 | 29 |
| paraphrased | stored | 0 | 6 |
| paraphrased | not stored | 0 | 24 |

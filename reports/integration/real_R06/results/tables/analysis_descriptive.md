# Descriptive tables

## Stored rate by cell at checkpoint 2970 (test probes, 95% fact-bootstrap CI)

| freq_bin | div_bin | probe_frame | n_facts | stored_rate | ci_low | ci_high |
|---|---|---|---|---|---|---|
| low | templated | canonical | 20 | 0.033 | 0.000 | 0.083 |
| low | templated | novel | 20 | 0.025 | 0.000 | 0.050 |
| low | paraphrased | canonical | 20 | 0.000 | 0.000 | 0.000 |
| low | paraphrased | novel | 20 | 0.025 | 0.000 | 0.050 |
| mid | templated | canonical | 20 | 0.217 | 0.117 | 0.333 |
| mid | templated | novel | 20 | 0.092 | 0.042 | 0.142 |
| mid | paraphrased | canonical | 20 | 0.100 | 0.033 | 0.183 |
| mid | paraphrased | novel | 20 | 0.175 | 0.108 | 0.258 |
| high | templated | canonical | 20 | 0.617 | 0.483 | 0.750 |
| high | templated | novel | 20 | 0.300 | 0.183 | 0.433 |
| high | paraphrased | canonical | 20 | 0.350 | 0.233 | 0.483 |
| high | paraphrased | novel | 20 | 0.517 | 0.408 | 0.625 |

## Acquisition (first checkpoint with >= half of a fact-seed's probes stored)

| freq_bin | div_bin | n_fact_seeds | never_acquired | median_acq_step |
|---|---|---|---|---|
| low | paraphrased | 60 | 1.000 | nan |
| low | templated | 60 | 0.967 | 2475.000 |
| mid | paraphrased | 60 | 0.733 | 1584.000 |
| mid | templated | 60 | 0.800 | 1584.000 |
| high | paraphrased | 60 | 0.050 | 495.000 |
| high | templated | 60 | 0.183 | 297.000 |

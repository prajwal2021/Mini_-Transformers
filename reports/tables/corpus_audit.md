# Corpus audit

## (d) Documents, words and estimated tokens (words x 1.35)

| split | docs planned | docs in corpus | words | est. tokens | mean words/doc |
| --- | ---: | ---: | ---: | ---: | ---: |
| train | 2167 | 2165 | 561395 | 757883 | 259.3 |
| val | 120 | 120 | 30623 | 41341 | 255.2 |
| test | 120 | 120 | 30785 | 41560 | 256.5 |
| all | 2407 | 2405 | 622803 | 840784 | 259.0 |

| doc type | train | val | test |
| --- | ---: | ---: | ---: |
| complaint letter + reply | 114 | 6 | 6 |
| customer notice | 227 | 12 | 13 |
| employee email | 292 | 12 | 13 |
| help-center article | 228 | 12 | 14 |
| incident report | 114 | 6 | 5 |
| internal chat thread | 225 | 12 | 12 |
| meeting minutes | 174 | 12 | 10 |
| monthly ops report | 128 | 12 | 11 |
| newsletter blurb | 179 | 12 | 11 |
| policy manual section | 257 | 12 | 13 |
| training handbook page | 227 | 12 | 12 |

Documents by split and mode: test/paraphrased 120, train/mixed 566, train/none 867, train/paraphrased 369, train/templated 363, val/paraphrased 120

## (h) Opening-5-gram duplicate share on the final corpus (Gate A metric)

Overall 0.75% over 2405 documents (limit 5%).

| group | docs | duplicate share |
| --- | ---: | ---: |
| type: complaint letter + reply | 126 | 0.79% |
| type: customer notice | 252 | 0.00% |
| type: employee email | 317 | 0.32% |
| type: help-center article | 254 | 1.18% |
| type: incident report | 125 | 0.00% |
| type: internal chat thread | 249 | 0.80% |
| type: meeting minutes | 196 | 0.00% |
| type: monthly ops report | 151 | 0.00% |
| type: newsletter blurb | 202 | 0.50% |
| type: policy manual section | 282 | 1.42% |
| type: training handbook page | 251 | 1.99% |
| split: train | 2165 | 0.74% |
| split: val | 120 | 0.00% |
| split: test | 120 | 0.00% |

Ten most common openings (first five words): 'morning rules for the evening' x2; 'desk cover on a spirited' x2; 'basic rules for paperwork queues' x2; 'last week late winter greetings' x2; 'rewarding start rules for the' x2; 'clear signage explained for anyone' x2; 'this afternoon clear rules for' x2; 'shift quiet corners rules new' x2; 'spare blankets explained for anyone' x2; 'practice for the spirited night' x2
Documents whose first five words equal the assigned opener of round 0, 1 or 2: 2294 of 2405 (95.4%; informational, not a gate).

## (i) Artifact rate and marker placements on the final corpus

Artifact rate (detector in slm/data/artifacts.py) 0.13% = 2 of 1538 mention-bearing documents (gate limit 2%).

| doc type | mention-bearing docs | with artifact | rate |
| --- | ---: | ---: | ---: |
| complaint letter + reply | 48 | 0 | 0.0% |
| customer notice | 173 | 0 | 0.0% |
| employee email | 238 | 0 | 0.0% |
| help-center article | 175 | 1 | 0.6% |
| incident report | 46 | 0 | 0.0% |
| internal chat thread | 170 | 0 | 0.0% |
| meeting minutes | 117 | 0 | 0.0% |
| monthly ops report | 72 | 0 | 0.0% |
| newsletter blurb | 124 | 0 | 0.0% |
| policy manual section | 203 | 1 | 0.5% |
| training handbook page | 172 | 0 | 0.0% |

Placement counts per mention in the accepted attempt:

| doc type | model | repaired_missing | repaired_mid_v2 | repaired_dup |
| --- | ---: | ---: | ---: | ---: |
| complaint letter + reply | 69 | 3 | 6 | 0 |
| customer notice | 258 | 6 | 72 | 0 |
| employee email | 385 | 11 | 112 | 0 |
| help-center article | 289 | 2 | 76 | 0 |
| incident report | 67 | 1 | 6 | 0 |
| internal chat thread | 293 | 0 | 47 | 0 |
| meeting minutes | 175 | 7 | 36 | 0 |
| monthly ops report | 131 | 1 | 8 | 0 |
| newsletter blurb | 217 | 5 | 26 | 0 |
| policy manual section | 321 | 3 | 88 | 0 |
| training handbook page | 323 | 3 | 29 | 0 |

All types: {'model': 2528, 'repaired_mid_v2': 506, 'repaired_missing': 42}.

## (j) Provenance: prompt version of the accepted attempt

Documents by prompt version: v7 138, v8 193, v9 2074.

| doc type | v7 | v8 | v9 |
| --- | ---: | ---: | ---: |
| complaint letter + reply | 3 | 12 | 111 |
| customer notice | 12 | 17 | 223 |
| employee email | 17 | 26 | 274 |
| help-center article | 16 | 15 | 223 |
| incident report | 8 | 10 | 107 |
| internal chat thread | 15 | 29 | 205 |
| meeting minutes | 10 | 17 | 169 |
| monthly ops report | 18 | 12 | 121 |
| newsletter blurb | 9 | 13 | 180 |
| policy manual section | 17 | 28 | 237 |
| training handbook page | 13 | 14 | 224 |

Documents accepted only after a re-plan or regeneration round (type, round): complaint letter + reply r4 x6, customer notice r3 x1, customer notice r4 x7, customer notice r5 x1, employee email r1 x2, employee email r4 x13, employee email r5 x1, employee email r6 x1, help-center article r1 x1, help-center article r4 x10, help-center article r5 x4, help-center article r6 x3, incident report r1 x1, incident report r4 x1, internal chat thread r1 x2, meeting minutes r4 x2, monthly ops report r4 x5, monthly ops report r5 x1, newsletter blurb r1 x7, newsletter blurb r4 x4, policy manual section r1 x2, policy manual section r4 x9, policy manual section r5 x5, policy manual section r6 x8, training handbook page r1 x3, training handbook page r4 x12, training handbook page r5 x4, training handbook page r6 x5.

## (a) Train exposure: planned vs measured mentions per fact (data/corpus/exposure.csv)

Planned train mentions 2600 (templated 1300, paraphrased 1300); measured 2596 (templated 1297, paraphrased 1299). Facts with measured != planned: 4 of 120.

| fact | planned T/P | measured T/P |
| --- | --- | --- |
| F003 | 15/0 | 14/0 |
| F018 | 15/0 | 14/0 |
| F027 | 45/0 | 44/0 |
| F082 | 0/45 | 0/44 |

Train documents unaccepted after re-planning: 3 ['train-0676', 'train-0908', 'test-0004']. Dropped documents (near-duplicates or P02c5 decisions): 2 ['train-0908', 'train-0192'].

## (b) Val/test paraphrased mentions per fact (must be exactly 2 + 2)

Facts with exactly 2 val and 2 test paraphrased mentions: 120 of 120.

## (c) Bank sentences in more than one split

0 (must be 0): []

## (e) Validator v5 regression over the final texts

0 failures of 2405 (must be 0). []

## (f) 13-gram leakage (after validator normalisation)

Val/test documents sharing at least one 13-gram with train: 12 (total shared 39); must be 0. {'val-0031': 4, 'val-0047': 3, 'val-0070': 5, 'val-0085': 2, 'val-0112': 1, 'test-0021': 8, 'test-0041': 2, 'test-0043': 1, 'test-0053': 7, 'test-0079': 1, 'test-0082': 2, 'test-0095': 3}
Train near-duplicate pairs (13-gram Jaccard > 0.5): 0. []

Leakage without exemption: 12 docs; with the sign-off exemption (grams entirely inside a sign-off line, docs/DESIGN_CHANGES_v1.3.md): 12 docs. Gram classes: i 0, i-b 0, ii 2, iii 33.

## (g) Exact duplicate documents across all splits

0 (must be 0): []

## (k) Meta-talk scan (prompt leaks)

Broad patterns (raw substring hits, informational): 'inserted sentence' 0, 'fact sentence' 0, 'marker' 9, '<<' 0, 'FACT' 296, 'the prompt' 4, 'instruction' 619, 'as requested' 3, 'as asked' 27, 'your own commentary' 0, 'keep your' 542, 'use the inserted' 0, 'word count' 0, 'sentences long' 0, 'the brief' 19, 'as an AI' 0, 'the model' 0, 'placeholder' 0.
Genuine prompt-leak documents (slm/data/metatalk.py GENUINE, gate target 0): 1 ['val-0047']

## Cost and attempts (raw records)

Cost of all attempts $5.1310; attempts per document (all rounds): {1: 2180, 2: 167, 3: 32, 4: 21, 5: 4, 8: 2, 10: 1}; mean 1.138.

## Disclosed exceptions (data/corpus/flags.json, listed in docs/DATA_CARD.md)

13: ['leak test-0021', 'leak test-0041', 'leak test-0043', 'leak test-0053', 'leak test-0079', 'leak test-0082', 'leak test-0095', 'leak val-0031', 'leak val-0047', 'leak val-0070', 'leak val-0085', 'leak val-0112', 'meta-talk val-0047']
Unflagged failures: 0 []

Result: PASS; 13 disclosed exceptions

# Corpus audit

## (d) Documents, words and estimated tokens (words x 1.35)

| split | docs planned | docs in corpus | words | est. tokens | mean words/doc |
| --- | ---: | ---: | ---: | ---: | ---: |
| train | 2167 | 2165 | 561821 | 758458 | 259.5 |
| val | 120 | 120 | 30614 | 41329 | 255.1 |
| test | 120 | 119 | 30721 | 41473 | 258.2 |
| all | 2407 | 2404 | 623156 | 841261 | 259.2 |

| doc type | train | val | test |
| --- | ---: | ---: | ---: |
| complaint letter + reply | 114 | 6 | 6 |
| customer notice | 226 | 12 | 13 |
| employee email | 292 | 12 | 12 |
| help-center article | 228 | 12 | 14 |
| incident report | 114 | 6 | 5 |
| internal chat thread | 225 | 12 | 12 |
| meeting minutes | 174 | 12 | 10 |
| monthly ops report | 128 | 12 | 11 |
| newsletter blurb | 179 | 12 | 11 |
| policy manual section | 258 | 12 | 13 |
| training handbook page | 227 | 12 | 12 |

Documents by split and mode: test/paraphrased 119, train/mixed 565, train/none 867, train/paraphrased 369, train/templated 364, val/paraphrased 120

## (h) Opening-5-gram duplicate share on the final corpus (Gate A metric)

Overall 0.75% over 2404 documents (limit 5%).

| group | docs | duplicate share |
| --- | ---: | ---: |
| type: complaint letter + reply | 126 | 0.79% |
| type: customer notice | 251 | 0.00% |
| type: employee email | 316 | 0.32% |
| type: help-center article | 254 | 1.18% |
| type: incident report | 125 | 0.00% |
| type: internal chat thread | 249 | 0.80% |
| type: meeting minutes | 196 | 0.00% |
| type: monthly ops report | 151 | 0.66% |
| type: newsletter blurb | 202 | 0.50% |
| type: policy manual section | 283 | 1.06% |
| type: training handbook page | 251 | 1.99% |
| split: train | 2165 | 0.74% |
| split: val | 120 | 0.00% |
| split: test | 119 | 0.00% |

Ten most common openings (first five words): 'desk cover on a spirited' x2; 'basic rules for paperwork queues' x2; 'last week late winter greetings' x2; 'rewarding start rules for the' x2; 'clear signage explained for anyone' x2; 'this afternoon clear rules for' x2; 'shift quiet corners rules new' x2; 'spare blankets explained for anyone' x2; 'practice for the spirited night' x2; 'a quick look at traveler' x2
Documents whose first five words equal the assigned opener of round 0, 1 or 2: 2396 of 2404 (99.7%; informational, not a gate).

## (i) Artifact rate and marker placements on the final corpus

Artifact rate (detector in slm/data/artifacts.py) 0.13% = 2 of 1537 mention-bearing documents (gate limit 2%).

| doc type | mention-bearing docs | with artifact | rate |
| --- | ---: | ---: | ---: |
| complaint letter + reply | 48 | 0 | 0.0% |
| customer notice | 172 | 0 | 0.0% |
| employee email | 237 | 0 | 0.0% |
| help-center article | 175 | 1 | 0.6% |
| incident report | 46 | 0 | 0.0% |
| internal chat thread | 170 | 0 | 0.0% |
| meeting minutes | 117 | 0 | 0.0% |
| monthly ops report | 72 | 0 | 0.0% |
| newsletter blurb | 124 | 0 | 0.0% |
| policy manual section | 204 | 1 | 0.5% |
| training handbook page | 172 | 0 | 0.0% |

Placement counts per mention in the accepted attempt:

| doc type | model | repaired_missing | repaired_mid_v2 | repaired_dup |
| --- | ---: | ---: | ---: | ---: |
| complaint letter + reply | 71 | 0 | 7 | 0 |
| customer notice | 256 | 6 | 72 | 0 |
| employee email | 381 | 11 | 114 | 0 |
| help-center article | 290 | 2 | 75 | 0 |
| incident report | 67 | 1 | 6 | 0 |
| internal chat thread | 293 | 0 | 47 | 0 |
| meeting minutes | 175 | 7 | 36 | 0 |
| monthly ops report | 131 | 1 | 8 | 0 |
| newsletter blurb | 216 | 6 | 26 | 0 |
| policy manual section | 330 | 2 | 83 | 0 |
| training handbook page | 316 | 1 | 38 | 0 |

All types: {'model': 2526, 'repaired_mid_v2': 512, 'repaired_missing': 37}.

## (j) Provenance: prompt version of the accepted attempt

Documents by prompt version: v7 146, v8 199, v9 2059.

| doc type | v7 | v8 | v9 |
| --- | ---: | ---: | ---: |
| complaint letter + reply | 3 | 14 | 109 |
| customer notice | 13 | 17 | 221 |
| employee email | 18 | 26 | 272 |
| help-center article | 19 | 16 | 219 |
| incident report | 8 | 10 | 107 |
| internal chat thread | 15 | 29 | 205 |
| meeting minutes | 10 | 17 | 169 |
| monthly ops report | 19 | 12 | 120 |
| newsletter blurb | 9 | 13 | 180 |
| policy manual section | 17 | 30 | 236 |
| training handbook page | 15 | 15 | 221 |

Documents accepted only after a re-plan or regeneration round (type, round): employee email r1 x2, help-center article r1 x1, incident report r1 x1, internal chat thread r1 x2, newsletter blurb r1 x7, policy manual section r1 x2, training handbook page r1 x3.

## (a) Train exposure: planned vs measured mentions per fact (data/corpus/exposure.csv)

Planned train mentions 2600 (templated 1300, paraphrased 1300); measured 2597 (templated 1299, paraphrased 1298). Facts with measured != planned: 3 of 120.

| fact | planned T/P | measured T/P |
| --- | --- | --- |
| F057 | 0/45 | 0/44 |
| F072 | 5/0 | 4/0 |
| F082 | 0/45 | 0/44 |

Train documents unaccepted after re-planning: 3 ['train-0676', 'train-0908', 'test-0004']. Dropped as near-duplicates: 0 [].

## (b) Val/test paraphrased mentions per fact (must be exactly 2 + 2)

Facts with exactly 2 val and 2 test paraphrased mentions: 118 of 120. Violations: [('F036', 2, 1), ('F037', 2, 1)]

## (c) Bank sentences in more than one split

0 (must be 0): []

## (e) Validator v5 regression over the final texts

0 failures of 2404 (must be 0). []

## (f) 13-gram leakage (after validator normalisation)

Val/test documents sharing at least one 13-gram with train: 70 (total shared 197); must be 0. {'val-0009': 2, 'val-0018': 2, 'val-0020': 4, 'val-0025': 1, 'val-0031': 1, 'val-0034': 2, 'val-0035': 1, 'val-0037': 1, 'val-0038': 4, 'val-0039': 5, 'val-0047': 1, 'val-0049': 2, 'val-0050': 1, 'val-0052': 1, 'val-0063': 9, 'val-0064': 1, 'val-0070': 2, 'val-0080': 5, 'val-0082': 1, 'val-0085': 3, 'val-0086': 1, 'val-0090': 4, 'val-0096': 2, 'val-0099': 7, 'val-0106': 2, 'val-0108': 2, 'val-0110': 3, 'val-0111': 2, 'val-0112': 3, 'val-0113': 3, 'val-0114': 2, 'test-0001': 6, 'test-0005': 2, 'test-0009': 1, 'test-0011': 1, 'test-0013': 1, 'test-0015': 1, 'test-0021': 2, 'test-0022': 4, 'test-0023': 1, 'test-0024': 1, 'test-0029': 1, 'test-0036': 4, 'test-0039': 3, 'test-0040': 2, 'test-0041': 4, 'test-0043': 3, 'test-0044': 2, 'test-0048': 2, 'test-0053': 3, 'test-0059': 6, 'test-0060': 4, 'test-0066': 4, 'test-0071': 8, 'test-0074': 1, 'test-0079': 4, 'test-0080': 1, 'test-0081': 1, 'test-0082': 9, 'test-0088': 10, 'test-0092': 2, 'test-0093': 6, 'test-0095': 2, 'test-0098': 3, 'test-0100': 1, 'test-0108': 1, 'test-0110': 6, 'test-0113': 1, 'test-0117': 2, 'test-0119': 1}
Train near-duplicate pairs (13-gram Jaccard > 0.5): 0. []

## (g) Exact duplicate documents across all splits

0 (must be 0): []

## Cost and attempts (raw records)

Cost of all attempts $4.7872; attempts per document (all rounds): {1: 2280, 2: 104, 3: 15, 4: 4, 5: 1, 6: 2, 7: 1}; mean 1.069.

Result: FAIL (72 problems)

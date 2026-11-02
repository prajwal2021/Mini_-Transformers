# Plan statistics

Total docs: 2407
Train docs: 2167 (1300 measured, 867 background)
tokens_per_word: 1.35 (pending calibration against the real tokenizer in P03)

## Document length

Expected tokens are computed as target_words x tokens_per_word per document.

| split | docs | mean words | mean tokens | total tokens |
| --- | ---: | ---: | ---: | ---: |
| train | 2167 | 255.0 | 344.2 | 745,844 |
| val | 120 | 255.2 | 344.5 | 41,340 |
| test | 120 | 255.6 | 345.0 | 41,403 |
| val/iid | 60 | 254.9 | 344.1 | 20,648 |
| val/novel | 60 | 255.4 | 344.9 | 20,691 |
| test/iid | 60 | 255.2 | 344.6 | 20,675 |
| test/novel | 60 | 255.9 | 345.5 | 20,728 |

Train mean tokens 344.2 vs target 350: within 10% (1.7% off) - ASSERTED.
Train mean words 255.0 (target 260 +/- 5%: PASS).

## Doc type targets

| doc type | base words | train docs | mean target words |
| --- | ---: | ---: | ---: |
| policy manual section | 260 | 258 | 287.5 |
| employee email | 200 | 292 | 229.4 |
| internal chat thread | 190 | 225 | 216.6 |
| incident report | 250 | 114 | 288.8 |
| monthly ops report | 270 | 128 | 294.0 |
| customer notice | 170 | 228 | 194.6 |
| help-center article | 260 | 228 | 292.6 |
| training handbook page | 270 | 227 | 300.1 |
| meeting minutes | 240 | 174 | 274.3 |
| complaint letter + reply | 290 | 114 | 304.8 |
| newsletter blurb | 150 | 179 | 169.6 |

## Mentions per fact

All train planned mentions equal: yes
val/iid mentions per fact: {1: 120} over 60 docs
val/novel mentions per fact: {1: 120} over 60 docs
test/iid mentions per fact: {1: 120} over 60 docs
test/novel mentions per fact: {1: 120} over 60 docs

## Docs per split/type/family

| split | doc type | primary family | docs |
| --- | ---: | ---: | ---: |
| test | complaint letter + reply | compensation | 6 |
| test | customer notice | skyport | 6 |
| test | customer notice | species | 7 |
| test | employee email | airship | 2 |
| test | employee email | procedure | 2 |
| test | employee email | species | 8 |
| test | help-center article | procedure | 5 |
| test | help-center article | skyport | 5 |
| test | help-center article | species | 4 |
| test | incident report | compensation | 5 |
| test | internal chat thread | airship | 1 |
| test | internal chat thread | procedure | 4 |
| test | internal chat thread | skyport | 7 |
| test | meeting minutes | airship | 5 |
| test | meeting minutes | procedure | 5 |
| test | monthly ops report | airship | 11 |
| test | newsletter blurb | airship | 4 |
| test | newsletter blurb | skyport | 8 |
| test | policy manual section | compensation | 1 |
| test | policy manual section | procedure | 4 |
| test | policy manual section | skyport | 4 |
| test | policy manual section | species | 4 |
| test | training handbook page | airship | 1 |
| test | training handbook page | procedure | 4 |
| test | training handbook page | species | 7 |
| train | complaint letter + reply | background | 78 |
| train | complaint letter + reply | compensation | 36 |
| train | customer notice | background | 79 |
| train | customer notice | compensation | 31 |
| train | customer notice | skyport | 51 |
| train | customer notice | species | 67 |
| train | employee email | airship | 36 |
| train | employee email | background | 79 |
| train | employee email | compensation | 27 |
| train | employee email | procedure | 39 |
| train | employee email | skyport | 49 |
| train | employee email | species | 62 |
| train | help-center article | background | 79 |
| train | help-center article | procedure | 40 |
| train | help-center article | skyport | 48 |
| train | help-center article | species | 61 |
| train | incident report | background | 79 |
| train | incident report | compensation | 35 |
| train | internal chat thread | airship | 41 |
| train | internal chat thread | background | 79 |
| train | internal chat thread | procedure | 45 |
| train | internal chat thread | skyport | 60 |
| train | meeting minutes | airship | 43 |
| train | meeting minutes | background | 79 |
| train | meeting minutes | procedure | 52 |
| train | monthly ops report | airship | 49 |
| train | monthly ops report | background | 79 |
| train | newsletter blurb | airship | 39 |
| train | newsletter blurb | background | 78 |
| train | newsletter blurb | skyport | 62 |
| train | policy manual section | background | 79 |
| train | policy manual section | compensation | 29 |
| train | policy manual section | procedure | 41 |
| train | policy manual section | skyport | 45 |
| train | policy manual section | species | 64 |
| train | training handbook page | airship | 39 |
| train | training handbook page | background | 79 |
| train | training handbook page | procedure | 44 |
| train | training handbook page | species | 65 |
| val | complaint letter + reply | compensation | 6 |
| val | customer notice | skyport | 3 |
| val | customer notice | species | 9 |
| val | employee email | airship | 3 |
| val | employee email | procedure | 5 |
| val | employee email | skyport | 4 |
| val | help-center article | skyport | 3 |
| val | help-center article | species | 9 |
| val | incident report | compensation | 6 |
| val | internal chat thread | airship | 2 |
| val | internal chat thread | procedure | 6 |
| val | internal chat thread | skyport | 4 |
| val | meeting minutes | airship | 3 |
| val | meeting minutes | procedure | 9 |
| val | monthly ops report | airship | 12 |
| val | newsletter blurb | airship | 3 |
| val | newsletter blurb | skyport | 9 |
| val | policy manual section | procedure | 1 |
| val | policy manual section | skyport | 7 |
| val | policy manual section | species | 4 |
| val | training handbook page | airship | 1 |
| val | training handbook page | procedure | 3 |
| val | training handbook page | species | 8 |

## k distribution

| split | k | docs |
| --- | ---: | ---: |
| test | 2 | 120 |
| train | 0 | 867 |
| train | 1 | 325 |
| train | 2 | 650 |
| train | 3 | 325 |
| val | 2 | 120 |

## Co-occurrence (P3': maximum train pair count <= 6)

Cross-family docs: 65 of 1300 measured train docs (5.0%; allowed up to 35%)
Multi-fact docs: 975; distinct pairs used: 953
Maximum train pair count: 6 (cap 6: MET)
Pairs above 3: 30
Sum of squared pair counts: 3779

Pair-count histogram (pair count -> number of fact pairs):

| pair count | fact pairs |
| --- | ---: |
| 1 | 550 |
| 2 | 209 |
| 3 | 164 |
| 4 | 1 |
| 5 | 13 |
| 6 | 16 |

### Cross-family escalation (smallest allowance that meets both targets)

| cross allowed | cross used | max pair | pairs>3 | sum sq | ratio min | ratio max | targets met |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 0% | 0 | 9 | 55 | 4733 | 0.805 | 1.127 | no |
| 5% | 65 | 6 | 30 | 3779 | 0.795 | 1.133 | yes |

### Objective trace of the accepted run

| phase | step | max pair | pairs>3 | sum sq | cross docs | ratio min | ratio max |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 1 | 18 | 146 | 8081 | 0 | 0.778 | 1.129 |
| 1 | 60000 | 6 | 62 | 4297 | 65 | 0.338 | 1.273 |
| 1 | 120000 | 6 | 42 | 4085 | 65 | 0.254 | 1.266 |
| 1 | 180000 | 6 | 40 | 3961 | 65 | 0.18 | 1.252 |
| 1 | 240000 | 6 | 38 | 3901 | 65 | 0.354 | 1.225 |
| 1 | 300000 | 6 | 36 | 3873 | 65 | 0.122 | 1.249 |
| 2 | 1 | 6 | 36 | 3873 | 65 | 0.122 | 1.249 |
| 2 | 100000 | 6 | 37 | 4017 | 65 | 0.8 | 1.124 |
| 2 | 200000 | 6 | 34 | 3957 | 65 | 0.829 | 1.099 |
| 2 | 300000 | 6 | 32 | 3865 | 65 | 0.79 | 1.125 |
| 2 | 400000 | 6 | 31 | 3831 | 65 | 0.794 | 1.134 |
| 2 | 500000 | 6 | 30 | 3779 | 65 | 0.795 | 1.133 |

### Bin independence (frequency bin of fact A x bin of fact B)

Expected = total pairs x share(A) x share(B) (x2 for unlike bins), where share is the bin's fraction of partner slots (a fact in a k-fact doc has k-1 partners). Target: every ratio within 0.75-1.25.

| bins | observed | expected | obs/exp | in range | cap-6 capacity (within family) | cap-6 capacity (cross-family) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| high x high | 567 | 591.0 | 0.959 | yes | 792 | 4560 |
| high x mid | 589 | 568.7 | 1.036 | yes | 1584 | 9120 |
| high x low | 237 | 209.3 | 1.133 | yes | 1584 | 9120 |
| mid x mid | 137 | 136.8 | 1.001 | yes | 792 | 4560 |
| mid x low | 80 | 100.7 | 0.795 | yes | 1584 | 9120 |
| low x low | 15 | 18.5 | 0.81 | yes | 792 | 4560 |

Targets met: yes. Capacity argument: independence puts about 591 pair incidences in the high x high cell. Inside families only 792 incidences fit (admissible high-frequency pairs x cap 6), i.e. the cell would have to be 75% full with no slack. With no cross-family docs the search ended at max pair 9 (cap 6 missed). Cross-family docs raise the cap-6 capacity to 4560; the accepted run needed only 65 such docs.

## Distinct (doc_type, style) ratio

Minimum: 1.000
Mean: 1.000

## Style-card marginals

| split/regime | axis | value | count |
| --- | ---: | ---: | ---: |
| train | formality | casual | 754 |
| train | formality | formal | 697 |
| train | formality | neutral | 716 |
| train | author_role | communications aide | 278 |
| train | author_role | customer advocate | 267 |
| train | author_role | operations planner | 288 |
| train | author_role | records aide | 250 |
| train | author_role | safety reviewer | 267 |
| train | author_role | service writer | 284 |
| train | author_role | shift coordinator | 254 |
| train | author_role | training editor | 279 |
| train | tone | brisk | 458 |
| train | tone | instructional | 433 |
| train | tone | reassuring | 459 |
| train | tone | urgent | 373 |
| train | tone | warm | 444 |
| train | length_bucket | long | 1192 |
| train | length_bucket | medium | 802 |
| train | length_bucket | short | 173 |
| val/iid | formality | casual | 21 |
| val/iid | formality | formal | 21 |
| val/iid | formality | neutral | 18 |
| val/iid | author_role | communications aide | 8 |
| val/iid | author_role | customer advocate | 4 |
| val/iid | author_role | operations planner | 10 |
| val/iid | author_role | records aide | 6 |
| val/iid | author_role | safety reviewer | 7 |
| val/iid | author_role | service writer | 4 |
| val/iid | author_role | shift coordinator | 12 |
| val/iid | author_role | training editor | 9 |
| val/iid | tone | brisk | 14 |
| val/iid | tone | instructional | 10 |
| val/iid | tone | reassuring | 15 |
| val/iid | tone | urgent | 8 |
| val/iid | tone | warm | 13 |
| val/iid | length_bucket | long | 33 |
| val/iid | length_bucket | medium | 22 |
| val/iid | length_bucket | short | 5 |
| val/novel | formality | casual | 22 |
| val/novel | formality | formal | 22 |
| val/novel | formality | neutral | 16 |
| val/novel | author_role | communications aide | 4 |
| val/novel | author_role | customer advocate | 4 |
| val/novel | author_role | operations planner | 1 |
| val/novel | author_role | quality auditor | 24 |
| val/novel | author_role | records aide | 1 |
| val/novel | author_role | route editor | 17 |
| val/novel | author_role | safety reviewer | 2 |
| val/novel | author_role | service writer | 1 |
| val/novel | author_role | shift coordinator | 3 |
| val/novel | author_role | training editor | 3 |
| val/novel | tone | apologetic | 42 |
| val/novel | tone | brisk | 5 |
| val/novel | tone | instructional | 3 |
| val/novel | tone | reassuring | 3 |
| val/novel | tone | urgent | 1 |
| val/novel | tone | warm | 6 |
| val/novel | length_bucket | long | 33 |
| val/novel | length_bucket | medium | 22 |
| val/novel | length_bucket | short | 5 |
| test/iid | formality | casual | 21 |
| test/iid | formality | formal | 19 |
| test/iid | formality | neutral | 20 |
| test/iid | author_role | communications aide | 8 |
| test/iid | author_role | customer advocate | 8 |
| test/iid | author_role | operations planner | 16 |
| test/iid | author_role | records aide | 9 |
| test/iid | author_role | safety reviewer | 3 |
| test/iid | author_role | service writer | 6 |
| test/iid | author_role | shift coordinator | 6 |
| test/iid | author_role | training editor | 4 |
| test/iid | tone | brisk | 15 |
| test/iid | tone | instructional | 10 |
| test/iid | tone | reassuring | 12 |
| test/iid | tone | urgent | 8 |
| test/iid | tone | warm | 15 |
| test/iid | length_bucket | long | 33 |
| test/iid | length_bucket | medium | 22 |
| test/iid | length_bucket | short | 5 |
| test/novel | formality | casual | 18 |
| test/novel | formality | formal | 24 |
| test/novel | formality | neutral | 18 |
| test/novel | author_role | communications aide | 4 |
| test/novel | author_role | customer advocate | 6 |
| test/novel | author_role | operations planner | 1 |
| test/novel | author_role | quality auditor | 17 |
| test/novel | author_role | route editor | 14 |
| test/novel | author_role | safety reviewer | 5 |
| test/novel | author_role | service writer | 2 |
| test/novel | author_role | shift coordinator | 7 |
| test/novel | author_role | training editor | 4 |
| test/novel | tone | apologetic | 40 |
| test/novel | tone | brisk | 4 |
| test/novel | tone | instructional | 7 |
| test/novel | tone | reassuring | 4 |
| test/novel | tone | urgent | 3 |
| test/novel | tone | warm | 2 |
| test/novel | length_bucket | long | 33 |
| test/novel | length_bucket | medium | 22 |
| test/novel | length_bucket | short | 5 |

Held-out values (roles quality auditor / route editor, tone apologetic):

| split/regime | docs | docs with a held-out value |
| --- | ---: | ---: |
| train | 2167 | 0 |
| val/iid | 60 | 0 |
| val/novel | 60 | 60 |
| test/iid | 60 | 0 |
| test/novel | 60 | 60 |

## Core-fact usage (docs using each core fact, all splits)

Mean 289.7; min 289, max 291; within +/-30% of mean: yes

| core id | docs | train | val | test | bar |
| --- | ---: | ---: | ---: | ---: | ---: |
| C01 | 290 | 261 | 14 | 15 | #################### |
| C02 | 289 | 260 | 14 | 15 | #################### |
| C03 | 289 | 261 | 14 | 14 | #################### |
| C04 | 290 | 260 | 15 | 15 | #################### |
| C05 | 289 | 260 | 14 | 15 | #################### |
| C06 | 289 | 260 | 14 | 15 | #################### |
| C07 | 289 | 260 | 14 | 15 | #################### |
| C08 | 291 | 261 | 15 | 15 | #################### |
| C09 | 289 | 260 | 14 | 15 | #################### |
| C10 | 291 | 261 | 15 | 15 | #################### |
| C12 | 290 | 260 | 15 | 15 | #################### |
| C13 | 290 | 260 | 15 | 15 | #################### |
| C14 | 290 | 260 | 15 | 15 | #################### |
| C15 | 289 | 260 | 14 | 15 | #################### |
| C16 | 290 | 260 | 15 | 15 | #################### |
| C17 | 289 | 260 | 14 | 15 | #################### |
| C18 | 290 | 260 | 15 | 15 | #################### |
| C19 | 290 | 260 | 15 | 15 | #################### |
| C20 | 289 | 260 | 14 | 15 | #################### |
| C21 | 291 | 261 | 15 | 15 | #################### |
| C22 | 290 | 261 | 14 | 15 | #################### |
| C26 | 289 | 260 | 14 | 15 | #################### |
| C27 | 289 | 260 | 14 | 15 | #################### |
| C28 | 289 | 260 | 14 | 15 | #################### |
| C29 | 291 | 261 | 15 | 15 | #################### |

## Generation cost estimate

Input tokens = chars/4 of every rendered v2 prompt. Expected output = target_words x tokens_per_word, times (1 + reasoning overhead). Worst case = max_output_tokens per doc (the cap already covers reasoning tokens). Costs include the 1.5 attempts factor; batch is x0.5. Budget guard: $10.

| model | tier | reasoning overhead | input tokens | expected output tokens | worst-case output tokens | expected cost (USD) | worst-case cost (USD) | flag > $10 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| gpt-5.4-nano | standard | +0% | 1,225,014 | 828,587 | 2,166,300 | $1.92 | $4.43 | ok |
| gpt-5.4-nano | standard | +50% | 1,225,014 | 1,242,880 | 2,166,300 | $2.70 | $4.43 | ok |
| gpt-5.4-nano | standard | +100% | 1,225,014 | 1,657,174 | 2,166,300 | $3.47 | $4.43 | ok |
| gpt-5.4-nano | batch | +0% | 1,225,014 | 828,587 | 2,166,300 | $0.96 | $2.21 | ok |
| gpt-5.4-nano | batch | +50% | 1,225,014 | 1,242,880 | 2,166,300 | $1.35 | $2.21 | ok |
| gpt-5.4-nano | batch | +100% | 1,225,014 | 1,657,174 | 2,166,300 | $1.74 | $2.21 | ok |
| gpt-5.4-mini | standard | +0% | 1,225,014 | 828,587 | 2,166,300 | $6.97 | $16.00 | OVER BUDGET |
| gpt-5.4-mini | standard | +50% | 1,225,014 | 1,242,880 | 2,166,300 | $9.77 | $16.00 | OVER BUDGET |
| gpt-5.4-mini | standard | +100% | 1,225,014 | 1,657,174 | 2,166,300 | $12.56 | $16.00 | OVER BUDGET |
| gpt-5.4-mini | batch | +0% | 1,225,014 | 828,587 | 2,166,300 | $3.49 | $8.00 | ok |
| gpt-5.4-mini | batch | +50% | 1,225,014 | 1,242,880 | 2,166,300 | $4.88 | $8.00 | ok |
| gpt-5.4-mini | batch | +100% | 1,225,014 | 1,657,174 | 2,166,300 | $6.28 | $8.00 | ok |

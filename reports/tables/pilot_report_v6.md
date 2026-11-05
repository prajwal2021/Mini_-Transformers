Client: openai

# Pilot report

Template: P02b7-template-v6 (52c2ae4696c5); validator v5. Generated 2026-11-05 21:07 UTC.
Global spend so far: $2.7403 of $10.00; pilot spend: $0.9149 of $1.60.

| metric | gpt-5.4-nano | gpt-5.4-mini |
| --- | ---: | ---: |
| docs | 40 | 40 |
| first-attempt pass rate | 85.0% | 95.0% |
| accepted within 3 attempts | 92.5% | 100.0% |
| mean attempts per doc | 1.38 | 1.05 |
| mean input tokens / call | 657 | 650 |
| mean output tokens / call | 334 | 316 |
| mean reasoning tokens / call | 0 | 0 |
| total cost (USD) | $0.0252 | $0.0802 |
| cost per accepted doc (USD) | $0.00068 | $0.00201 |
| projected full run, 2407 docs (USD) | $1.64 | $4.83 |
| mean actual/target words | 1.025 | 0.998 |
| docs within +/-15% of target | 83.8% | 87.5% |
| mean latency (s) | 2.84 | 2.65 |
| distinct-2gram ratio | 0.681 | 0.612 |
| opening-5-gram duplicate rate | 2.7% | 5.0% |
| mean capitalized-token flags / doc | 0.19 | 0.15 |

## Validator reason histogram (failed attempts, by rule)

| rule | gpt-5.4-nano | gpt-5.4-mini |
| --- | ---: | ---: |
| V12 | 3 | 2 |
| V16 | 1 | 0 |
| V18 | 1 | 0 |
| V7 | 2 | 0 |
| V8 | 2 | 0 |

## Selection criteria (docs/GENERATION_DECISION.md)

| criterion | gpt-5.4-nano | gpt-5.4-mini |
| --- | --- | --- |
| C1: accepted within 3 attempts >= 95% | FAIL | PASS |
| C2: first-attempt pass >= 60% | PASS | PASS |
| C3: projected full-run cost <= $6.00 | PASS | PASS |
| C4: >= 80% of accepted docs within +/-15% of target words | PASS | PASS |
| C5: opening-5-gram duplicate rate <= 10% | PASS | PASS |
| C6: human read-through of printed samples | pending human | pending human |

## Additional measures

| measure | gpt-5.4-nano | gpt-5.4-mini |
| --- | ---: | ---: |
| empty responses (expected 0) | 0 | 0 |
| E1 API events (empty or length) | 0 | 0 |
| docs lost to E1 after retries | 0 | 0 |
| mean reasoning tokens / call (expected 0) | 0 | 0 |
| attempts made | 46 | 42 |
| mean attempts per doc | 1.38 | 1.05 |
| cost per doc (USD) | $0.00063 | $0.00201 |
| projected full run at observed attempts/doc (USD) | $1.52 | $4.83 |
| projected full run at 1.4 attempts/doc (USD) | $1.85 | $6.44 |

First-attempt pass by mode:

| measure | gpt-5.4-nano | gpt-5.4-mini |
| --- | ---: | ---: |
| none | 3/3 (100%) | 3/3 (100%) |
| paraphrased | 16/19 (84%) | 18/19 (95%) |
| templated | 15/18 (83%) | 17/18 (94%) |

First-attempt pass by doc type:

| measure | gpt-5.4-nano | gpt-5.4-mini |
| --- | ---: | ---: |
| complaint letter + reply | 4/5 (80%) | 5/5 (100%) |
| customer notice | 2/2 (100%) | 2/2 (100%) |
| employee email | 5/5 (100%) | 5/5 (100%) |
| help-center article | 2/2 (100%) | 2/2 (100%) |
| incident report | 2/2 (100%) | 2/2 (100%) |
| internal chat thread | 2/2 (100%) | 2/2 (100%) |
| meeting minutes | 5/6 (83%) | 6/6 (100%) |
| monthly ops report | 1/2 (50%) | 2/2 (100%) |
| newsletter blurb | 2/2 (100%) | 2/2 (100%) |
| policy manual section | 6/6 (100%) | 5/6 (83%) |
| training handbook page | 3/6 (50%) | 5/6 (83%) |

## C1 at 3 and at 5 attempts, other original criteria

| model | accepted within 3 (C1) | accepted within 5 | first-attempt pass (C2) | projected full run (C3, $6.00) | within +/-15% (C4) | opening-5-gram dup (C5) |
| --- | --- | --- | --- | --- | --- | --- |
| gpt-5.4-nano | 92.5% FAIL | 92.5% | 85.0% PASS | $1.64 PASS | 83.8% PASS | 2.7% PASS |
| gpt-5.4-mini | 100.0% PASS | 100.0% | 95.0% PASS | $4.83 PASS | 87.5% PASS | 5.0% PASS |

## Acceptance within 5 attempts by doc type

| doc type | gpt-5.4-nano | gpt-5.4-mini |
| --- | ---: | ---: |
| complaint letter + reply | 4/5 (80%) | 5/5 (100%) |
| customer notice | 2/2 (100%) | 2/2 (100%) |
| employee email | 5/5 (100%) | 5/5 (100%) |
| help-center article | 2/2 (100%) | 2/2 (100%) |
| incident report | 2/2 (100%) | 2/2 (100%) |
| internal chat thread | 2/2 (100%) | 2/2 (100%) |
| meeting minutes | 6/6 (100%) | 6/6 (100%) |
| monthly ops report | 2/2 (100%) | 2/2 (100%) |
| newsletter blurb | 2/2 (100%) | 2/2 (100%) |
| policy manual section | 6/6 (100%) | 6/6 (100%) |
| training handbook page | 4/6 (67%) | 6/6 (100%) |

## Amendment A1 eligibility (docs/GENERATION_DECISION.md)

| criterion | gpt-5.4-nano | gpt-5.4-mini |
| --- | --- | --- |
| (a) accepted within 5 >= 97%, every type >= 1, no type < 50% | 92.5%; lowest type 67% FAIL | 100.0%; lowest type 100% PASS |
| (b) first-attempt pass >= 60% | 85.0% PASS | 95.0% PASS |
| (c) projected full run at observed attempts/doc <= $7.00 | $1.52 PASS | $4.83 PASS |
| (d) opening-5-gram duplicates <= 10% | 2.7% PASS | 5.0% PASS |
| eligible under A1 | NO | YES |

## Mean actual/target words by doc type (all non-empty attempts)

| doc type | gpt-5.4-nano | gpt-5.4-mini |
| --- | ---: | ---: |
| complaint letter + reply | 0.980 (n=6) | 0.996 (n=5) |
| customer notice | 0.912 (n=2) | 0.903 (n=2) |
| employee email | 0.951 (n=5) | 1.006 (n=5) |
| help-center article | 0.950 (n=2) | 1.036 (n=2) |
| incident report | 1.034 (n=2) | 0.957 (n=2) |
| internal chat thread | 1.132 (n=2) | 0.986 (n=2) |
| meeting minutes | 1.112 (n=7) | 1.007 (n=6) |
| monthly ops report | 0.979 (n=3) | 0.973 (n=2) |
| newsletter blurb | 1.102 (n=2) | 0.933 (n=2) |
| policy manual section | 1.028 (n=6) | 1.003 (n=7) |
| training handbook page | 1.058 (n=9) | 1.019 (n=7) |
| all types | 1.025 (accepted only) | 0.998 (accepted only) |

## Validator reason lines (failed attempts)

| rule | gpt-5.4-nano | gpt-5.4-mini |
| --- | ---: | ---: |
| V18 | 1 | 0 |
| V15 | 0 | 0 |
| V11 | 0 | 0 |
| V1p | 0 | 0 |

## Confound audit: fact sentences alone on their line, accepted documents

| model | templated (code-inserted) | paraphrased (model-written) |
| --- | --- | --- |
| gpt-5.4-nano | 1/27 (4%) | 4/26 (15%) |
| gpt-5.4-mini | 0/29 (0%) | 0/28 (0%) |

## Placement counts of the accepted documents (model / repaired_*)

| mode | placement | gpt-5.4-nano | gpt-5.4-mini |
| --- | --- | ---: | ---: |
| paraphrased | model | 15 | 21 |
| paraphrased | repaired_dup | 1 | 0 |
| paraphrased | repaired_mid | 9 | 7 |
| paraphrased | repaired_missing | 1 | 0 |
| templated | model | 19 | 23 |
| templated | repaired_mid | 7 | 6 |
| templated | repaired_missing | 1 | 0 |

## Stuck documents (two consecutive attempts failed with the identical rule set)

- gpt-5.4-nano: train-0422 stopped at attempt 2 (complaint letter + reply); rules V7
- gpt-5.4-nano: train-0953 stopped at attempt 2 (training handbook page); rules V8
- gpt-5.4-nano: train-1267 stopped at attempt 2 (training handbook page); rules V12

## Projected totals against the global budget

| model | spent before bank and pilot | bank | documents (full run) | total | limit |
| --- | ---: | ---: | ---: | ---: | ---: |
| gpt-5.4-nano at observed attempts/doc | $1.26 | $1.38 | $1.52 | $4.15 | $9.00 |
| gpt-5.4-nano at 1.4 attempts/doc | $1.26 | $1.38 | $1.85 | $4.48 | $9.00 |
| gpt-5.4-mini at observed attempts/doc | $1.26 | $1.38 | $4.83 | $7.46 | $9.00 |
| gpt-5.4-mini at 1.4 attempts/doc | $1.26 | $1.38 | $6.44 | $9.07 | $9.00 |

## Manipulation check: paraphrase diversity of the inserted sentences (accepted documents)

| model | inserted | distinct sentences | equal to canonical | starts 'For <entity>,' | distinct 3-token prefixes | mean pairwise skeleton Jaccard per fact (facts with 2+ uses) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| gpt-5.4-nano | 26 | 26/26 | 0 | 0 | 19 | 0.141 (5 pairs) |
| gpt-5.4-mini | 28 | 28/28 | 0 | 0 | 21 | 0.167 (8 pairs) |

**Recommendation:** Eligible under A1: gpt-5.4-mini. Among eligible models the choice is by C6 (naturalness, no prompt or meta language; read pilot_samples_v6.md) and then by cost; no model is chosen here.

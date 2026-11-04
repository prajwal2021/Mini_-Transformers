Client: openai

# Pilot report

Template: P02b6-template-v5 (a2ee4ded4066); validator v4. Generated 2026-11-04 17:31 UTC.
Global spend so far: $0.8094 of $10.00; pilot spend: $0.8094 of $1.50.

| metric | gpt-5.4-nano | gpt-5.4-mini |
| --- | ---: | ---: |
| docs | 40 | 40 |
| first-attempt pass rate | 62.5% | 72.5% |
| accepted within 3 attempts | 87.5% | 80.0% |
| mean attempts per doc | 1.77 | 1.90 |
| mean input tokens / call | 693 | 712 |
| mean output tokens / call | 308 | 330 |
| mean reasoning tokens / call | 0 | 0 |
| total cost (USD) | $0.0314 | $0.1190 |
| cost per accepted doc (USD) | $0.00090 | $0.00372 |
| projected full run, 2407 docs (USD) | $2.16 | $8.95 |
| mean actual/target words | 0.958 | 0.996 |
| docs within +/-15% of target | 77.1% | 65.6% |
| mean latency (s) | 2.92 | 3.26 |
| distinct-2gram ratio | 0.692 | 0.659 |
| opening-5-gram duplicate rate | 2.9% | 3.1% |
| mean capitalized-token flags / doc | 0.17 | 0.00 |

## Validator reason histogram (failed attempts, by rule)

| rule | gpt-5.4-nano | gpt-5.4-mini |
| --- | ---: | ---: |
| V12 | 3 | 0 |
| V15 | 13 | 39 |
| V16 | 1 | 0 |
| V1p | 19 | 19 |
| V2b | 6 | 0 |
| V5 | 3 | 0 |
| V7 | 5 | 1 |

## Selection criteria (docs/GENERATION_DECISION.md)

| criterion | gpt-5.4-nano | gpt-5.4-mini |
| --- | --- | --- |
| C1: accepted within 3 attempts >= 95% | FAIL | FAIL |
| C2: first-attempt pass >= 60% | PASS | PASS |
| C3: projected full-run cost <= $6.00 | PASS | FAIL |
| C4: >= 80% of accepted docs within +/-15% of target words | FAIL | FAIL |
| C5: opening-5-gram duplicate rate <= 10% | PASS | PASS |
| C6: human read-through of printed samples | pending human | pending human |

## Additional measures

| measure | gpt-5.4-nano | gpt-5.4-mini |
| --- | ---: | ---: |
| empty responses (expected 0) | 0 | 0 |
| E1 API events (empty or length) | 0 | 0 |
| docs lost to E1 after retries | 0 | 0 |
| mean reasoning tokens / call (expected 0) | 0 | 0 |
| attempts made | 71 | 76 |
| mean attempts per doc | 1.77 | 1.90 |
| cost per doc (USD) | $0.00079 | $0.00298 |
| projected full run at observed attempts/doc (USD) | $1.89 | $7.16 |
| projected full run at 1.4 attempts/doc (USD) | $1.49 | $5.28 |

First-attempt pass by mode:

| measure | gpt-5.4-nano | gpt-5.4-mini |
| --- | ---: | ---: |
| none | 3/3 (100%) | 3/3 (100%) |
| paraphrased | 12/19 (63%) | 13/19 (68%) |
| templated | 10/18 (56%) | 13/18 (72%) |

First-attempt pass by doc type:

| measure | gpt-5.4-nano | gpt-5.4-mini |
| --- | ---: | ---: |
| complaint letter + reply | 2/5 (40%) | 5/5 (100%) |
| customer notice | 2/2 (100%) | 2/2 (100%) |
| employee email | 4/5 (80%) | 5/5 (100%) |
| help-center article | 2/2 (100%) | 2/2 (100%) |
| incident report | 2/2 (100%) | 2/2 (100%) |
| internal chat thread | 1/2 (50%) | 2/2 (100%) |
| meeting minutes | 5/6 (83%) | 4/6 (67%) |
| monthly ops report | 0/2 (0%) | 0/2 (0%) |
| newsletter blurb | 1/2 (50%) | 2/2 (100%) |
| policy manual section | 2/6 (33%) | 3/6 (50%) |
| training handbook page | 4/6 (67%) | 2/6 (33%) |

## C1 at 3 and at 5 attempts, other original criteria

| model | accepted within 3 (C1) | accepted within 5 | first-attempt pass (C2) | projected full run (C3, $6.00) | within +/-15% (C4) | opening-5-gram dup (C5) |
| --- | --- | --- | --- | --- | --- | --- |
| gpt-5.4-nano | 87.5% FAIL | 87.5% | 62.5% PASS | $2.16 PASS | 77.1% FAIL | 2.9% PASS |
| gpt-5.4-mini | 80.0% FAIL | 80.0% | 72.5% PASS | $8.95 FAIL | 65.6% FAIL | 3.1% PASS |

## Acceptance within 5 attempts by doc type

| doc type | gpt-5.4-nano | gpt-5.4-mini |
| --- | ---: | ---: |
| complaint letter + reply | 4/5 (80%) | 5/5 (100%) |
| customer notice | 2/2 (100%) | 2/2 (100%) |
| employee email | 5/5 (100%) | 5/5 (100%) |
| help-center article | 2/2 (100%) | 2/2 (100%) |
| incident report | 2/2 (100%) | 2/2 (100%) |
| internal chat thread | 2/2 (100%) | 2/2 (100%) |
| meeting minutes | 6/6 (100%) | 4/6 (67%) |
| monthly ops report | 2/2 (100%) | 1/2 (50%) |
| newsletter blurb | 2/2 (100%) | 2/2 (100%) |
| policy manual section | 3/6 (50%) | 3/6 (50%) |
| training handbook page | 5/6 (83%) | 4/6 (67%) |

## Amendment A1 eligibility (docs/GENERATION_DECISION.md)

| criterion | gpt-5.4-nano | gpt-5.4-mini |
| --- | --- | --- |
| (a) accepted within 5 >= 97%, every type >= 1, no type < 50% | 87.5%; lowest type 50% FAIL | 80.0%; lowest type 50% FAIL |
| (b) first-attempt pass >= 60% | 62.5% PASS | 72.5% PASS |
| (c) projected full run at observed attempts/doc <= $7.00 | $1.89 PASS | $7.16 FAIL |
| (d) opening-5-gram duplicates <= 10% | 2.9% PASS | 3.1% PASS |
| eligible under A1 | NO | NO |

## Mean actual/target words by doc type (all non-empty attempts)

| doc type | gpt-5.4-nano | gpt-5.4-mini |
| --- | ---: | ---: |
| complaint letter + reply | 0.909 (n=11) | 0.927 (n=5) |
| customer notice | 0.998 (n=2) | 0.941 (n=2) |
| employee email | 0.825 (n=6) | 0.911 (n=5) |
| help-center article | 0.869 (n=2) | 1.070 (n=2) |
| incident report | 0.989 (n=2) | 1.065 (n=2) |
| internal chat thread | 1.056 (n=3) | 0.958 (n=2) |
| meeting minutes | 1.023 (n=7) | 0.989 (n=14) |
| monthly ops report | 0.984 (n=4) | 1.034 (n=7) |
| newsletter blurb | 1.064 (n=3) | 1.150 (n=2) |
| policy manual section | 0.950 (n=19) | 0.986 (n=18) |
| training handbook page | 0.941 (n=12) | 0.970 (n=17) |
| all types | 0.958 (accepted only) | 0.996 (accepted only) |

## Validator reason lines (failed attempts)

| rule | gpt-5.4-nano | gpt-5.4-mini |
| --- | ---: | ---: |
| V18 | 0 | 0 |
| V15 | 13 | 39 |
| V11 | 0 | 0 |
| V1p | 19 | 19 |

## Confound audit: fact sentences alone on their line, accepted documents

| model | templated (code-inserted) | paraphrased (model-written) |
| --- | --- | --- |
| gpt-5.4-nano | 3/26 (12%) | 8/24 (33%) |
| gpt-5.4-mini | 0/26 (0%) | 3/16 (19%) |

**Recommendation:** Neither model is eligible under A1; stop and report. No model is named.

Client: openai

# Pilot report

Template: P02b4-template-v3 (f55866b3910d); validator v2. Generated 2026-11-02 21:21 UTC.
Global spend so far: $0.3859 of $10.00; pilot spend: $0.3859 of $1.00.

| metric | gpt-5.4-nano | gpt-5.4-mini |
| --- | ---: | ---: |
| docs | 30 | 30 |
| first-attempt pass rate | 46.7% | 50.0% |
| accepted within 3 attempts | 70.0% | 80.0% |
| mean attempts per doc | 1.93 | 1.87 |
| mean input tokens / call | 633 | 612 |
| mean output tokens / call | 230 | 212 |
| mean reasoning tokens / call | 0 | 0 |
| total cost (USD) | $0.0240 | $0.0793 |
| cost per accepted doc (USD) | $0.00114 | $0.00330 |
| projected full run, 2407 docs (USD) | $2.75 | $7.95 |
| mean actual/target words | 0.792 | 0.790 |
| docs within +/-15% of target | 23.8% | 16.7% |
| mean latency (s) | 2.08 | 1.68 |
| distinct-2gram ratio | 0.783 | 0.723 |
| opening-5-gram duplicate rate | 9.5% | 4.2% |
| mean capitalized-token flags / doc | 0.05 | 0.08 |

## Validator reason histogram (failed attempts, by rule)

| rule | gpt-5.4-nano | gpt-5.4-mini |
| --- | ---: | ---: |
| V1 | 14 | 4 |
| V11 | 5 | 1 |
| V12 | 4 | 4 |
| V15 | 2 | 6 |
| V2 | 2 | 1 |
| V5 | 10 | 1 |
| V7 | 2 | 1 |
| V8 | 24 | 27 |

## Selection criteria (docs/GENERATION_DECISION.md)

| criterion | gpt-5.4-nano | gpt-5.4-mini |
| --- | --- | --- |
| C1: accepted within 3 attempts >= 95% | FAIL | FAIL |
| C2: first-attempt pass >= 60% | FAIL | FAIL |
| C3: projected full-run cost <= $6.00 | PASS | FAIL |
| C4: >= 80% of accepted docs within +/-15% of target words | FAIL | FAIL |
| C5: opening-5-gram duplicate rate <= 10% | PASS | PASS |
| C6: human read-through of printed samples | pending human | pending human |

## Additional measures (prompt v3 / validator v2 rerun)

| measure | gpt-5.4-nano | gpt-5.4-mini |
| --- | ---: | ---: |
| empty responses (expected 0) | 0 | 0 |
| E1 API events (empty or length) | 0 | 0 |
| docs lost to E1 after retries | 0 | 0 |
| mean reasoning tokens / call (expected 0) | 0 | 0 |
| attempts made | 58 | 56 |
| mean attempts per doc | 1.93 | 1.87 |
| cost per doc (USD) | $0.00080 | $0.00264 |
| projected full run at observed attempts/doc (USD) | $1.93 | $6.36 |
| projected full run at 1.4 attempts/doc (USD) | $1.40 | $4.77 |

First-attempt pass by mode:

| measure | gpt-5.4-nano | gpt-5.4-mini |
| --- | ---: | ---: |
| none | 4/4 (100%) | 3/4 (75%) |
| paraphrased | 5/16 (31%) | 7/16 (44%) |
| templated | 5/10 (50%) | 5/10 (50%) |

First-attempt pass by doc type:

| measure | gpt-5.4-nano | gpt-5.4-mini |
| --- | ---: | ---: |
| complaint letter + reply | 2/3 (67%) | 2/3 (67%) |
| customer notice | 1/2 (50%) | 0/2 (0%) |
| employee email | 1/4 (25%) | 0/4 (0%) |
| help-center article | 2/2 (100%) | 1/2 (50%) |
| incident report | 2/3 (67%) | 3/3 (100%) |
| internal chat thread | 1/3 (33%) | 1/3 (33%) |
| meeting minutes | 0/3 (0%) | 1/3 (33%) |
| monthly ops report | 0/1 (0%) | 1/1 (100%) |
| newsletter blurb | 1/3 (33%) | 1/3 (33%) |
| policy manual section | 2/3 (67%) | 2/3 (67%) |
| training handbook page | 2/3 (67%) | 3/3 (100%) |

**Recommended model:** No model passes C1 or C2: iterate the prompt (template v3) using the reason histogram, within the remaining pilot budget.

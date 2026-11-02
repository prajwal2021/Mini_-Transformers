Client: openai

# Pilot report

Template: P02b5-template-v4 (516065c99bb3); validator v3. Generated 2026-11-02 22:10 UTC.
Global spend so far: $0.6590 of $10.00; pilot spend: $0.6590 of $1.00.

| metric | gpt-5.4-nano | gpt-5.4-mini |
| --- | ---: | ---: |
| docs | 50 | 50 |
| first-attempt pass rate | 46.0% | 48.0% |
| accepted within 3 attempts | 66.0% | 66.0% |
| mean attempts per doc | 1.94 | 1.90 |
| mean input tokens / call | 692 | 684 |
| mean output tokens / call | 366 | 393 |
| mean reasoning tokens / call | 0 | 0 |
| total cost (USD) | $0.0566 | $0.2166 |
| cost per accepted doc (USD) | $0.00171 | $0.00656 |
| projected full run, 2407 docs (USD) | $4.12 | $15.80 |
| mean actual/target words | 1.069 | 1.128 |
| docs within +/-15% of target | 69.7% | 54.5% |
| mean latency (s) | 2.76 | 2.58 |
| distinct-2gram ratio | 0.704 | 0.665 |
| opening-5-gram duplicate rate | 12.1% | 6.1% |
| mean capitalized-token flags / doc | 0.00 | 0.00 |

## Validator reason histogram (failed attempts, by rule)

| rule | gpt-5.4-nano | gpt-5.4-mini |
| --- | ---: | ---: |
| V1 | 12 | 2 |
| V11 | 18 | 5 |
| V12 | 9 | 6 |
| V15 | 9 | 13 |
| V1p | 18 | 8 |
| V2 | 1 | 3 |
| V5 | 6 | 1 |
| V7 | 3 | 1 |
| V8 | 21 | 50 |

## Selection criteria (docs/GENERATION_DECISION.md)

| criterion | gpt-5.4-nano | gpt-5.4-mini |
| --- | --- | --- |
| C1: accepted within 3 attempts >= 95% | FAIL | FAIL |
| C2: first-attempt pass >= 60% | FAIL | FAIL |
| C3: projected full-run cost <= $6.00 | PASS | FAIL |
| C4: >= 80% of accepted docs within +/-15% of target words | FAIL | FAIL |
| C5: opening-5-gram duplicate rate <= 10% | FAIL | PASS |
| C6: human read-through of printed samples | pending human | pending human |

## Additional measures (prompt v3 / validator v2 rerun)

| measure | gpt-5.4-nano | gpt-5.4-mini |
| --- | ---: | ---: |
| empty responses (expected 0) | 0 | 0 |
| E1 API events (empty or length) | 0 | 0 |
| docs lost to E1 after retries | 0 | 0 |
| mean reasoning tokens / call (expected 0) | 0 | 0 |
| attempts made | 97 | 95 |
| mean attempts per doc | 1.94 | 1.90 |
| cost per doc (USD) | $0.00113 | $0.00433 |
| projected full run at observed attempts/doc (USD) | $2.72 | $10.43 |
| projected full run at 1.4 attempts/doc (USD) | $1.96 | $7.68 |

First-attempt pass by mode:

| measure | gpt-5.4-nano | gpt-5.4-mini |
| --- | ---: | ---: |
| none | 2/4 (50%) | 3/4 (75%) |
| paraphrased | 12/26 (46%) | 13/26 (50%) |
| templated | 9/20 (45%) | 8/20 (40%) |

First-attempt pass by doc type:

| measure | gpt-5.4-nano | gpt-5.4-mini |
| --- | ---: | ---: |
| complaint letter + reply | 1/7 (14%) | 4/7 (57%) |
| customer notice | 0/2 (0%) | 1/2 (50%) |
| employee email | 8/8 (100%) | 7/8 (88%) |
| help-center article | 1/2 (50%) | 2/2 (100%) |
| incident report | 2/3 (67%) | 3/3 (100%) |
| internal chat thread | 2/3 (67%) | 2/3 (67%) |
| meeting minutes | 0/7 (0%) | 1/7 (14%) |
| monthly ops report | 1/1 (100%) | 1/1 (100%) |
| newsletter blurb | 3/3 (100%) | 2/3 (67%) |
| policy manual section | 4/7 (57%) | 0/7 (0%) |
| training handbook page | 1/7 (14%) | 1/7 (14%) |

## Criteria by cohort (same thresholds as GENERATION_DECISION.md)

| model | cohort | docs | C1 accepted within 3 | C2 first-attempt pass | C3 projected full run | C4 within +/-15% | C5 opening-5-gram dup |
| --- | --- | ---: | --- | --- | --- | --- | --- |
| gpt-5.4-nano | combined 50 | 50 | 66.0% FAIL | 46.0% FAIL | $4.12 PASS | 69.7% FAIL | 12.1% FAIL |
| gpt-5.4-nano | same 30 | 30 | 76.7% FAIL | 50.0% FAIL | $3.26 PASS | 78.3% FAIL | 13.0% FAIL |
| gpt-5.4-nano | fresh 20 | 20 | 50.0% FAIL | 40.0% FAIL | $6.13 FAIL | 50.0% FAIL | 0.0% PASS |
| gpt-5.4-mini | combined 50 | 50 | 66.0% FAIL | 48.0% FAIL | $15.80 FAIL | 54.5% FAIL | 6.1% PASS |
| gpt-5.4-mini | same 30 | 30 | 70.0% FAIL | 56.7% FAIL | $13.25 FAIL | 71.4% FAIL | 0.0% PASS |
| gpt-5.4-mini | fresh 20 | 20 | 60.0% FAIL | 35.0% FAIL | $20.25 FAIL | 25.0% FAIL | 8.3% PASS |

## Mean actual/target words by doc type (all non-empty attempts, after calibration)

| doc type | gpt-5.4-nano | gpt-5.4-mini |
| --- | ---: | ---: |
| complaint letter + reply | 1.135 (n=16) | 1.142 (n=13) |
| customer notice | 1.061 (n=5) | 1.166 (n=3) |
| employee email | 0.998 (n=8) | 1.147 (n=9) |
| help-center article | 0.964 (n=3) | 1.112 (n=2) |
| incident report | 1.080 (n=4) | 1.052 (n=3) |
| internal chat thread | 1.304 (n=5) | 1.416 (n=5) |
| meeting minutes | 1.069 (n=21) | 1.235 (n=17) |
| monthly ops report | 1.074 (n=1) | 1.252 (n=1) |
| newsletter blurb | 1.081 (n=3) | 1.020 (n=4) |
| policy manual section | 1.126 (n=13) | 1.229 (n=19) |
| training handbook page | 1.144 (n=18) | 1.175 (n=19) |
| all types | 1.105 (n=97) | 1.191 (n=95) |

## Validator reason lines for the new and fidelity rules (failed attempts)

| rule | gpt-5.4-nano | gpt-5.4-mini |
| --- | ---: | ---: |
| V1p | 18 | 8 |
| V17 | 0 | 0 |
| V15 | 9 | 13 |

## Confound audit: fact sentences alone on their line, accepted documents

| model | templated (code-inserted) | paraphrased (model-written) |
| --- | --- | --- |
| gpt-5.4-nano | 3/18 (17%) | 2/36 (6%) |
| gpt-5.4-mini | 1/20 (5%) | 1/33 (3%) |

**Recommended model:** No model passes C1 or C2: iterate the prompt (template v3) using the reason histogram, within the remaining pilot budget.

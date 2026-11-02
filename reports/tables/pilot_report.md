Client: openai

# Pilot report

Template: P02a2-template-v2 (34de5d64b2c2). Generated 2026-11-02 20:38 UTC.
Global spend so far: $0.2826 of $10.00; pilot spend: $0.2826 of $1.00.

| metric | gpt-5.4-nano | gpt-5.4-mini |
| --- | ---: | ---: |
| docs | 30 | 30 |
| first-attempt pass rate | 16.7% | 23.3% |
| accepted within 3 attempts | 40.0% | 53.3% |
| mean attempts per doc | 2.57 | 2.37 |
| mean input tokens / call | 476 | 472 |
| mean output tokens / call | 681 | 587 |
| mean reasoning tokens / call | 415 | 308 |
| total cost (USD) | $0.0729 | $0.2096 |
| cost per accepted doc (USD) | $0.00608 | $0.01310 |
| projected full run, 2407 docs (USD) | $14.63 | $31.53 |
| mean actual/target words | 0.944 | 0.943 |
| docs within +/-15% of target | 66.7% | 87.5% |
| mean latency (s) | 4.53 | 2.94 |
| distinct-2gram ratio | 0.835 | 0.783 |
| opening-5-gram duplicate rate | 0.0% | 0.0% |
| mean capitalized-token flags / doc | 0.67 | 1.19 |

## Validator reason histogram (failed attempts, by rule)

| rule | gpt-5.4-nano | gpt-5.4-mini |
| --- | ---: | ---: |
| V1 | 68 | 43 |
| V2 | 42 | 36 |
| V5 | 31 | 21 |
| V6 | 2 | 12 |
| V7 | 1 | 0 |
| V8 | 28 | 25 |

## Selection criteria (docs/GENERATION_DECISION.md)

| criterion | gpt-5.4-nano | gpt-5.4-mini |
| --- | --- | --- |
| C1: accepted within 3 attempts >= 95% | FAIL | FAIL |
| C2: first-attempt pass >= 60% | FAIL | FAIL |
| C3: projected full-run cost <= $6.00 | FAIL | FAIL |
| C4: >= 80% of accepted docs within +/-15% of target words | FAIL | PASS |
| C5: opening-5-gram duplicate rate <= 10% | PASS | PASS |
| C6: human read-through of printed samples | pending human | pending human |

**Recommended model:** No model passes C1 or C2: iterate the prompt (template v3) using the reason histogram, within the remaining pilot budget.

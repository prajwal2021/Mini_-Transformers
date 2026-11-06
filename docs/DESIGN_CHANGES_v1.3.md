# Design changes v1.3 (corpus stream, NNP branch)

This file is created on the corpus branch; the integration branch carries its own copy with rows 1-42. Merge by appending the rows below.

| # | change | where | reason |
| --- | --- | --- | --- |
| C-1 (P02c5) | **13-gram leak rule exemption for sign-off lines.** 13-grams that lie entirely inside a code-inserted or fixed sign-off line are exempt from the zero-leak rule; every other shared 13-gram keeps the original rule. Reported with and without the exemption (audit section f). | slm/data/leakclass.py, scripts/audit_corpus.py | Architect decision in P02c5. **Effect: none.** In this corpus sign-offs are model-written lines of at most 8 words, shorter than a 13-gram, so no shared 13-gram lies entirely inside one (classes i and i-b both 0 of 187 distinct grams). Leakage with and without the exemption is identical. |
| C-2 (P02c5) | **test-0004 re-planned as another document type.** After 3 rounds as a newsletter blurb failed V12, the document was generated once as an "employee email" with the same facts and split (data/corpus/plan_overrides.json, round 6). | scripts/close_corpus.py, corpus.apply_plan_overrides | Keeps the 2+2 val/test mentions of F036 and F037. |
| C-3 (P02c5) | **Meta-talk scan is a gate metric** (slm/data/metatalk.py GENUINE, target 0), not a validator; validators v1-v5 stay frozen. | audit_corpus.py | 33 documents talked about the "inserted" sentence. |

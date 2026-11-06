# Reprocessing of the run-2 raw outputs with marker repair v2 (no API calls)

Documents: 350; attempts before 377, after 376 (dropped 1 attempts that followed the first accepted one).
Accepted documents whose text changed: 15.
Documents accepted now but not before: 0 [].
Documents accepted before but failing now: 0 [] (their attempts are removed from attempts.jsonl and the documents are regenerated with prompt v8 on resume).
Mention-bearing accepted documents with an artifact: before 2, after 2 (of 212 before).

| doc type | model | repaired_missing | repaired_mid_v2 | repaired_dup |
| --- | ---: | ---: | ---: | ---: |
| complaint letter + reply | 13 | 0 | 1 | 0 |
| customer notice | 29 | 1 | 10 | 0 |
| employee email | 42 | 4 | 23 | 0 |
| help-center article | 36 | 0 | 8 | 0 |
| incident report | 4 | 0 | 4 | 0 |
| internal chat thread | 54 | 0 | 5 | 0 |
| meeting minutes | 23 | 3 | 14 | 0 |
| monthly ops report | 19 | 0 | 1 | 0 |
| newsletter blurb | 16 | 0 | 6 | 0 |
| policy manual section | 56 | 1 | 16 | 0 |
| training handbook page | 33 | 0 | 9 | 0 |

# Reprocessing of the run-2 raw outputs with marker repair v2 (no API calls)

Documents: 150; attempts before 167, after 161 (dropped 2 attempts that followed the first accepted one).
Accepted documents whose text changed: 27.
Documents accepted now but not before: 0 [].
Documents accepted before but failing now: 2 ['train-0257', 'train-0487'] (their attempts are removed from attempts.jsonl and the documents are regenerated with prompt v8 on resume).
Mention-bearing accepted documents with an artifact: before 12, after 0 (of 91 before).

| doc type | model | repaired_missing | repaired_mid_v2 | repaired_dup |
| --- | ---: | ---: | ---: | ---: |
| customer notice | 14 | 0 | 4 | 0 |
| employee email | 11 | 3 | 11 | 0 |
| help-center article | 27 | 0 | 4 | 0 |
| incident report | 2 | 0 | 4 | 0 |
| internal chat thread | 22 | 0 | 0 | 0 |
| meeting minutes | 9 | 3 | 9 | 0 |
| monthly ops report | 13 | 0 | 0 | 0 |
| newsletter blurb | 4 | 0 | 2 | 0 |
| policy manual section | 15 | 0 | 7 | 0 |
| training handbook page | 16 | 0 | 4 | 0 |

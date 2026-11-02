# Experiments

| E-### | date | run_id | purpose | config_hash | git commit | data hash | key metrics | verdict |
|---|---|---|---|---|---|---|---|---|
| E-001 | 2026-11-02 | replay-v1-v2 | Replay the 148 stored P02b2 pilot attempts through validator v1 and v2 (offline, no API) | cfg 4a26538a52f9 | local commit "P02b4a" | pilot attempts 32b6bc6b339f | mini accepted attempts 15 -> 36, first-attempt pass on non-empty 20.0% -> 60.0%; nano 10 -> 21, 17.2% -> 41.4%; pass->fail flips mini 2, nano 4 (V15 x5, V16 x2, V2 x1) | v2 admits documents v1 wrongly rejected and rejects 6 that lose meaning or casing; reports/tables/pilot_replay.md |
| E-002 | 2026-11-02 | pilot-v3-rerun | Rerun the same 30 pilot documents with prompt v3, validator v2, reasoning none, max 700 output tokens, both models | cfg 4a26538a52f9 | local commit "P02b4b" | pilot_v3 attempts f3c85bc0b0ee | nano: first pass 46.7%, accepted 70.0%, projected $2.75, 23.8% within +/-15% of target; mini: 50.0%, 80.0%, $7.95, 16.7%; empty responses 0, reasoning tokens 0; spend $0.1033 | C1, C2 fail for both; C3 passes for nano only; C4 fails for both (mean length ratio 0.79); no model chosen; reports/tables/pilot_report_v3.md |

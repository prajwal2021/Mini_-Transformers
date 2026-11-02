# Experiments

| E-### | date | run_id | purpose | config_hash | git commit | data hash | key metrics | verdict |
|---|---|---|---|---|---|---|---|---|
| E-001 | 2026-11-02 | replay-v1-v2 | Replay the 148 stored P02b2 pilot attempts through validator v1 and v2 (offline, no API) | cfg 4a26538a52f9 | local commit "P02b4a" | pilot attempts 32b6bc6b339f | mini accepted attempts 15 -> 36, first-attempt pass on non-empty 20.0% -> 60.0%; nano 10 -> 21, 17.2% -> 41.4%; pass->fail flips mini 2, nano 4 (V15 x5, V16 x2, V2 x1) | v2 admits documents v1 wrongly rejected and rejects 6 that lose meaning or casing; reports/tables/pilot_replay.md |

# REPORT BACK P02c4

Status: prompt v9 fixed the newsletter problem; all 2407 rows generated, every rolling gate passed; STOPPED at the re-plan stage because val/test doc test-0004 (newsletter) is unaccepted after 2 re-plans (rule: stop). Leak stage, final audit PASS, manifest and data card NOT done. Nothing pushed.

a) pytest 262 passed, 1 skipped in 205.81s; ruff all checks passed; git log: f792970 P02c4-b, 2d9fc67 P02c4-a, 0dd195b, 2fd6cae, 49ca725; git status: only data/pilot_mock_v6/ untracked.

b) 5 newsletters (train-0243, train-0301, train-bg-0154, train-bg-0506, test-0116): all accepted on the first v9 attempt (round 1), sentence-case headlines. Gate at 350 re-evaluated: 100.0%, 1.11, $4.87, dup 0.3%, lowest type 100%, artifact 0/215 -> PASS.
Gate table: see reports/tables/corpus_progress.md (450..2407 all PASS). Final: accepted within 5 99.3%, attempts 1.08, projected $4.77, opening dup 0.7%, lowest type 98%, artifact 0.1% (2/1528).
Re-plans: 16 docs in round 1; 3 unaccepted after round 2: train-0676, train-0908 (policy/other, V12), test-0004 (newsletter, V12; V12 = 1 of 7-9 sentences starts lowercase, 11-14% vs 10%). Accepted only after a re-plan: employee email 2, help-center 1, incident report 1, chat thread 2, newsletter 7, policy manual 2, handbook 3.

c) Spend: this prompt $4.0847; corpus ledger $4.8031 (cap $6.00); global $7.8387 of $9.00.

d) Audit (reports/tables/corpus_audit.md, on 2404 docs): exposure measured != planned for 3 facts (F057 44 vs 45, F072 4 vs 5, F082 44 vs 45: the 3 unaccepted train/test docs). Val/test 2+2: 118 of 120 facts; F036, F037 have 1 test mention (test-0004). Leakage: 70 val/test docs share a 13-gram with train (197 shared) - the leak stage (rounds 3-4) has not run. Near-duplicates 0, exact duplicates 0, bank sentences across splits 0, validator v5 regression 0 failures. Counts: train 2165, val 120, test 119; 623,156 words, ~841,261 est. tokens. Opening-5-gram dup 0.75% overall (type max 1.99% handbook; train 0.74%, val 0, test 0). Artifact rate 0.13% (2/1537). Placements (all types): model 2526, repaired_mid_v2 512, repaired_missing 37, repaired_dup 0 (about 17% of mentions repaired). Provenance (accepted attempt prompt version): v7 146, v8 199, v9 2059. Known bank defect rate ~3% (60-sentence sample, P02b7h; not re-measured).

e) Samples and neighbourhoods: reports/tables/p02c4_samples.md (8 docs incl. 2 newsletters, 15 neighbourhoods).

f) Deviations/unsure: (1) gate counting of re-planned docs: replan attempts numbered 5, cost included. (2) The v9 sentence is appended to the Structure line of newsletter prompts. (3) Meta-talk leakage seen in samples: train-0251 "Keep your own commentary brief after the inserted sentence", train-1000 "Use the inserted sentence as a complete sentence" - not caught by validators v1-v5; not measured corpus-wide. (4) 'Companion Animal Travel Desk' sign-off line and bank phrases ("as the desk records it") are repetitive. (5) Run was one process from redo to replan stage; no data card written.

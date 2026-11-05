# Experiments (eval stream)

| id | date | name | result |
|---|---|---|---|
| E-E001 | 2026-11-05 | mock-ground-truth recovery | 3 random ground truths x 1440 probe items (ties, zero bindings, frequency-prior cases present): rank, binding and stored recovered exactly; noise 0.1 leaves all non-tie outcomes unchanged |
| E-E002 | 2026-11-05 | sft-mock-build | split 8/2/10 per cell; rows sft_train 336, sft_val 24, E0 336, E1 144, E2 180; qa_test.jsonl sha256 in data/sft_mock/manifest.json |
| E-E003 | 2026-11-05 | chance-baseline-mock | Value prior + noise 3.0 (no entity binding), 3 seeds: stored 0.113/0.138/0.155 vs null 0.146/0.144/0.141. Pure value prior: stored 0, null 0. Planted binding on all facts: stored 1.000, null 0.000. Binding on half the facts: planted stored 1.000, unplanted 0.133, null overall 0.083 |
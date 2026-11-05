# Experiments (eval stream)

| id | date | name | result |
|---|---|---|---|
| E-E001 | 2026-11-05 | mock-ground-truth recovery | 3 random ground truths x 1440 probe items (ties, zero bindings, frequency-prior cases present): rank, binding and stored recovered exactly; noise 0.1 leaves all non-tie outcomes unchanged |
| E-E002 | 2026-11-05 | sft-mock-build | split 8/2/10 per cell; rows sft_train 336, sft_val 24, E0 336, E1 144, E2 180; qa_test.jsonl sha256 in data/sft_mock/manifest.json |
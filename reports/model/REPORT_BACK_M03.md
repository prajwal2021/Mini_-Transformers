# REPORT BACK M03

## 1. Checks
- pytest: model-stream fast `99 passed, 4 deselected in 15.90s`; GPU `4 passed, 99 deselected in 11.43s`; whole repo `305 passed in 292.25s (0:04:52)`. Slowest tests are existing P02 ones (39-55 s, not mine; mine are under 5 s).
- ruff: `All checks passed!`
- git log --oneline -3 and git status --short: in the message.

## 2. Template and normalisation
- Template (DESIGN 7.1: "Format (identical for base and SFT evaluation): `Question: <q>\nAnswer: <one sentence containing the value><|eos|>`"): prompt `Question: <q>\nAnswer:`, completion ` <answer sentence><|eos|>`. Loss on answer tokens and eos only (DESIGN 7.1 "Loss on answer tokens only"; eos as a target is my reading, M-D037).
- Decoding (DESIGN 7.2: "Greedy decoding, stop at `<|eos|>` or newline, max 48 tokens").
- Normalisation: DESIGN names none (it says "normalized value" in section 6 without a definition; 7.4 lists "Exact value match, contains-match"). Rule used: cut at first newline, strip, collapse whitespace, case-sensitive (M-D040).
- exact_match = normalised prediction equals the normalised gold answer SENTENCE. contains_value / contains_gold = the value string occurs in the prediction, a separate column.

## 3. Dry run (mock; numbers mean nothing)
| phase | seconds |
|---|---|
| tokenizer | 0.1 |
| pretrain 2 seeds x 8 epochs | 9.5 |
| SFT 2 seeds x 6 epochs | 7.0 |
| decode + score, seed 0, both checkpoints (660 questions each) | 144 |
| same, seed 1 | 144 |

Before/after, mean over 2 seeds, same questions, template and decoding (checkpoint | eval_set | n | exact_match | contains_gold): pretrained and SFT, E0 672 / E1 288 / E2 360, all 0.000. SFT sft_val loss 3.47 and 3.41, still falling at epoch 6 (no early stop). Answers look like "The pets is." Plumbing works end to end; ledger wrote 1 line; 0 prompts truncated. Seeded sample (T 0.8, top-k 20): " The petets is."

## 4. Ledger
`slm.guard.open_split(manifest, split, purpose)` returns the verified bytes. For `test` it first appends one JSON line (UTC time, split, purpose, git commit + dirty flag, caller, manifest, file hashes) to `reports/test_access_log.jsonl`, then reads with a context variable set; `SplitManifest.read_verified` refuses test files unless that variable is set, so every manifest-based reader (tokenizer, token cache, trainer, `read_split` even with widened `allowed`) refuses test. Train/val are verified but not logged; unlisted, wrong-split or hash-mismatched files are refused. Covered: `load_qa_rows` (the evaluator). Not covered: code that opens a path with `open()` directly; a static test checks only the guard and the manifest use the permission flag. Rule in docs/HPARAM_PROTOCOL.md section 6. The dry run wrote its ledger inside runs/m03_dry_run/ so the real log is untouched.

## 5. Decisions, deviations, doubts
M-D035 to M-D042 (journal/model/DECISIONS_M.md).
- 7b (before/after table, same-question test, seeded temperature/top-k) is NOT in my copy of the prompt. The M01 session relayed it twice, the second time saying the user had confirmed it there. I could not verify that myself; the work is additive and easy to remove. Please confirm.
- M-D035 also decays the learned position table (2-D), following DESIGN literally.
- Exact match as sentence equality is my reading of "exact value match"; please confirm or ask for value extraction.
- SFT batch size 16, warmup 20 and patience 2 are my choices (DESIGN fixes only LR 1e-4, short warmup, at most 6 epochs).
- Base zero-shot and 2-shot prompts (DESIGN 7.2) are not built.
- Bash was flaky earlier; PowerShell used. runs/m03_dry_run/ (checkpoints, predictions) is left untracked.
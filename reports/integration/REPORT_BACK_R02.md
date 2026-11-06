# REPORT BACK R02 (merge main, partial-corpus dry run)

Branch `integration` (worktree `../slm-integration`), local only: nothing pushed, main untouched, no OpenAI call, `.env` never read. The partial corpus is `data/corpus/{train,val,test}.jsonl` of main at 0cfabdc: **train 135, val 4, test 9 documents**. The test file was **not opened, copied or listed**; the test-access ledger was not created (asserted by the dry-run script).

## 1. Checks
- pytest (whole merged repo, one invocation, no PYTHONPATH; it finished inside the 10 minute limit, run from a background shell and polled; no code changed while it ran): `644 passed, 1 skipped, 7 warnings in 491.29s (0:08:11)` (R01: 630). The skip is main's `tests/test_p02c.py:101` "corpus not generated yet" (it waits for the full corpus and its manifest). New: `tests/test_r02_partial.py` 4; main's `tests/test_p02c2.py` is included and passes.
- ruff: `All checks passed!`
- git log --oneline -4 and git status --short: 

```
4d15a63 R02: merge main, partial-corpus dry run
67c1f83 R02: merge main (P02c2) into integration
af30adf R01: taxonomy, ranking accuracy, exemplars, samples, README
0cfabdc P02c2-b: corpus generation run 2 (stopped at Gate A: every_type, opening duplicates 0.0%)
```
`git status --short`: empty after the commit. (The top hash is the commit before this block was added; the commit was amended once, local only, so the final hash differs. `67c1f83` is the merge commit; `0cfabdc` is main's tip at the merge.)

## 2. Merge of main (I-D034)
One-off merge of main 0cfabdc (P02b7i, P02c, P02c2-a, P02c2-b); Window 1's later commits are not included.

| file | conflict | resolution |
|---|---|---|
| `AI_USE.md` | main's P02c2 row vs my rows M01..R01 at the same place | kept every row |
| `track.txt` | main's current `NEXT STEP` line vs my copy of an older `NEXT STEP` plus the INTEGRATION block | kept the INTEGRATION block and main's current `NEXT STEP` ("Human decides how to treat the per-type gate at n=11 ..."), dropped my stale copy |
| everything else | none: 366 files from main (corpus `raw/` caches, `data/corpus*/`, `configs/openers_v2.yaml`, `tests/test_p02c2.py`, journals) are in paths I did not change | auto-merged |

`data/corpus/` has no `manifest.json` yet (P02c3). I built one for train + val only in `runs/partial_dryrun/data/splits.json` (`scripts/partial_manifest.py`).

## 3. Stats from the partial corpus (`runs/partial_dryrun/`, scripts `partial_manifest.py`, `partial_dryrun.py`, stages tokenizer / token_cache / sweep of `run_real.py`)
| item | train | val |
|---|---|---|
| documents | 135 | 4 |
| words | 36,777 | 884 |
| tokens (incl. `<|eos|>`) | 44,996 | 1,139 |
| **tokens per word (real text)** | **1.220** | 1.284 |
| **share of documents over 512 tokens** | **0.0%** | n/a (not recorded for val) |

(Provisional `tokens_per_word` in the sizing notes was 1.35; the real text gives 1.22 with a 3.7k vocabulary.)

Tokenizer (fit on the 135 train documents only, vocab 4096 requested, `min_frequency 2`): **vocab size 3715, merges 3456** (the merges ran out), 2737 distinct tokens occur in train. The 20 most common tokens in train (share of all train tokens): ` the` 5.7%, `,` 5.3%, `.` 4.4%, ` and` 3.6%, newline 3.3%, ` a` 1.7%, ` for` 1.2%, ` to` 1.2%, ` is` 1.1%, ` with` 0.9%, ` The` 0.9%, ` that` 0.9%, ` desk` 0.7%, ` in` 0.6%, `:` 0.6%, ` animal` 0.6%, ` pet` 0.6%, ` keep` 0.6%, ` Travel` 0.6%, ` Animal` 0.5%.

Stage timings (seconds, `runs/partial_dryrun/stages/*.json`): tokenizer **0.21**, token_cache **0.23**, sweep (2 configs x 3 epochs) **6.32**; total about 6.8 s wall including imports.

Sweep (1 seed, 3 epochs, batch 8, 14 steps per epoch, 42 steps; model 6 layers / d384, 12.4M parameters). Validation loss per epoch (4 validation documents, so noisy) and train loss every few steps:

| config | val ep 1 | val ep 2 | val ep 3 | train loss at steps 2, 10, 18, 26, 34, 42 | seconds | tokens/s |
|---|---|---|---|---|---|---|
| lr 3e-4, dropout 0.1 | 6.603 | 5.890 | 5.739 | 8.30, 7.10, 6.30, 5.95, 5.69, 5.71 | 4.7 | 29,018 (includes CUDA warm-up) |
| **lr 1e-3, dropout 0.1** (chosen, best val 5.359 at epoch 3) | 5.967 | 5.520 | 5.359 | 8.17, 6.42, 5.67, 5.56, 5.26, 5.31 | 1.6 | 85,579 |

Both curves fall monotonically; ln(vocab) = 8.3 is where they start. Tokens seen per config: 134,988 (3 epochs x 44,996). **GPU: RTX 5080 Laptop, peak allocated memory 1,360 MB** (batch 8 x 512 tokens, bf16 autocast, plus evaluation); the second config's 85.6k tokens/s is the steady-state figure for this small batch, the first is depressed by warm-up. No real throughput claim should be made from 3 epochs.

## 4. Probe-overlap check (`scripts/check_probe_overlap.py --split-manifest runs/partial_dryrun/data/splits.json`)
**OK: no novel probe prompt shares an 8-gram with the train text** (each novel prompt checked as prompt + " " + value, for all 120 facts; 39 canonical prompts share an 8-gram, as expected and informational). No offenders to print. The check ran on 135 train documents only (about 37k words) and must be repeated on the full corpus. The script now also reads the version-1 manifest and prints the shared 8-grams of any offender (tested with a planted offender).

## 5. Twelve samples (best sweep run, epoch-3 checkpoint, temperature 0.8, 40 new tokens; only to see that generation works)
Four prompts x three samples; all 12 are in `reports/integration/partial_dryrun_stats_R02.json` (copy of the gitignored `runs/partial_dryrun/partial_stats.json`). The model produces fluent-looking domain words (desk, traveler, crate, coordinator, "Companion Animal Travel Desk") and the document layout (blank lines, role headings), and no correct value; three examples:
- `How long is a health certificate good for when flying with a large dog? It stays valid for` -> ` a pet shared, and avoid, and keep a pet on your animal. The traveler was orderly. ...`
- `Passengers travelling with pets should` -> ` should check at support, carrier to the handoff, carrier coordinator\nCoordinator\n\nCompanion know document, since ...`
- `Passengers travelling with pets should` -> ` the missing without should your calm, and the booking to for the same pet and steady ...`
Not interpreted: 42 optimiser steps on 45k tokens.

## 6. Bugs found in the real pipeline on real text
None. The tokenizer, token cache, packing, training, evaluation and checkpoint writing ran on the real documents without error, and the test split was never touched. Observations that are not bugs: (a) the tokenizer ended at 3715 ids, so `model.vocab_size 4096` has 381 unused embedding rows until the full corpus fills the vocabulary; (b) 4 validation documents make validation loss, and so the sweep choice, noisy; (c) at the real batch of 32 an epoch of the partial corpus is only 3 steps, so the warmup and logging settings of `configs/train.yaml` are for the full corpus.

## 7. Decisions (I-D034 to I-D038), deviations, unsure
- I-D034 merge; I-D035 partial manifest without test; I-D036 dry-run config and in-process driver; I-D037 overlap script reads v1 manifests; I-D038 caveats on the numbers.
- Deviation: the dry run uses `mode: real` with a partial manifest instead of `configs/real.yaml`; the freeze, probes, SFT, QA test and report stages were not run (as instructed). `runs/partial_dryrun/` is gitignored.
- Unsure: (a) the figures come from 135 documents, the share over 512 tokens and the 8-gram check must be redone on the full corpus; (b) the chosen config (lr 1e-3) has no meaning beyond the plumbing; (c) I did not check the merged main code beyond the full test suite (P02c2 changed generation code that I do not own); (d) Window 1 will commit more to main (P02c3): this merge is a snapshot.

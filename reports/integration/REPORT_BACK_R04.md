# REPORT BACK R04 (E* rule v2)

## 1. Checks
- pytest (whole suite): `1 failed, 677 passed, 1 skipped, 7 warnings in 366.57s (0:06:06)`. The one failure was a stale R03 assertion in `tests/test_r00_freeze.py` (old sweep grid); I fixed the assertion and reran that file (9 passed). The whole suite was not rerun after that one-line fix. The skip is main's corpus test.
- ruff: all checks passed.
- git log / status: see the end of the printed report (filled after the commit).

## 2. The rule as implemented
Per config the validation-probe stored rate is smoothed with a centred 3-checkpoint moving average (shortened at the ends); its SE is the mean of the window's fact-clustered SEs (binomial from `n_probes` if no `se`). Config score = best smoothed rate; configs within 1 SE of the best are near-ties and the lowest validation loss wins; E* = earliest checkpoint of the winner within 1 SE of its best smoothed rate. Chance guard: if the winner's best smoothed rate is not above its `init` rate by more than 2 SE, E* = epoch of minimum validation loss, the table prints a WARNING and the result carries `no_val_storage`. Unit tests (all pass): (a) plateau curve picks the plateau start (E*=12, val-loss optimum 8); (b) a noisy at-chance curve fires the guard (E*=8=min val loss, not the noisy-best epoch 1); (c) the rule is deterministic, ignores extra keys and input order.

## 3. Mock decision table and guard (MOCK, nothing here is a result)
Full table: `reports/integration/mock_sweep_decision_R04.md`. Chosen `cfg04_lr0.001_dropout0.0_batch_size32`. **The guard fired**: best smoothed 0.098 (SE 0.022) vs init 0.100, threshold 0.145; E* = 12 = the val-loss optimum (R03 had picked E*=1 on noise). All 7 runs are near-ties because every SE is about 0.02 at chance. Sizing picked the small model. 13 stages ok; sweep 70.9 s, whole run about 5.6 min. Secondary (epoch 60) analysis is skipped in the mock because its last epoch equals E*.

## 4. Two-stage sweep and ETA
Runs (real config): stage 1 = lr {3e-4, 6e-4, 1e-3} x dropout {0, 0.1} at batch 32 (6 runs, seed 100, 60 epochs); stage 2 = the best stage-1 config (same rule) at batch 16 (1 run); `sizing` = the chosen config at 27.6M. Selection over the 7 sweep runs; sizing by the same rule. ETA: `first_run_seconds x (n_stage1 + n_stage2 + large_factor) / 3600`, large_factor = parameter ratio (2.22), printed and written to `sweep/eta.json`; `SweepTooLong` aborts above `sweep.max_hours` = 3 (tested with a stubbed run). Mock: first run 11.4 s, projection 0.03 h.

## 5. PREREG v5 and freeze
Changes: title v5; header training-budget row; D4 rewritten; Supersedes row; secondary analysis is epoch 60 (all 2E* wording removed, asserted by test); section 9 rewritten (identical 60-epoch schedule, seed 100, two stages, smoothed rule, chance guard, final runs, freeze incl. dirty-tree refusal). Still unfrozen, placeholders unchanged. Freeze records: config hash, sweep seed, E*, `no_val_storage`, schedule sha256, total epochs, size, lr, dropout, batch size, val-loss-optimal epoch, clean commit hash. It refuses on a dirty tracked tree (PREREG excepted) and on any test-split ledger entry / probe row / QA test predictions (earlier tests pass). Mock runs freeze with `require_clean=False` (the mock PREREG copy recorded `DIRTY` honestly).
- (b) Path test (`scripts/real_report_path_test.py`, PATH TEST, NOT RESULTS): no freeze -> exit 3; clean-tree freeze -> built, `banner: False`; PREREG edited -> exit 3 (hash mismatch). Fast version in `tests/test_r04_budget.py`.
- (c) QA cost (`reports/integration/qa_cost_R04.json`): 0.14-0.16 s per generated answer, 0.008 s per ranked question; 660 x 3 x 3 = 5,940 answers is about 16 min (< 40), so no batched decoder was added.

## 6. Decisions, deviations, unsure
Decisions I-D047..I-D053. Deviations: the guard compares to the same config's `init` only; tracked-only dirty check (untracked files are ignored). Unsure: (1) val and test canonical probes still share a prompt (seed now separate, prompt not); (2) ETA assumes equal cost per run and the large model at its parameter ratio; (3) the QA timing used a mock checkpoint (likely 48-token outputs, so an upper bound) and repeated 24 val questions; (4) the smoothed SE averages correlated checkpoints (conservative); (5) one sweep seed; large-model lr not retuned; (6) real sweep not run, corpus manifest absent; (7) the whole suite was not rerun after the one-line test fix.

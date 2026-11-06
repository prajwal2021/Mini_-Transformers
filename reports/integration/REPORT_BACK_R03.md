# REPORT BACK R03 (E* rule, warmup scaling, PREREG v4)

Branch `integration` (worktree `../slm-integration`), local only: nothing pushed, main untouched, no OpenAI call, `.env` never read. `docs/PREREG.md` is v4 and still **not frozen** (the dry run froze a mock copy only). The mock numbers below are from the toy corpus and mean nothing.

## 1. Checks
- pytest (whole repo, one invocation, no PYTHONPATH, background shell polled; no code changed while it ran): `665 passed, 1 skipped, 7 warnings in 561.67s (0:09:21)` (R02: 644). **The first full run had one failure** (`test_r00_freeze.py::test_orchestrator_stage_list_and_configs` still asserted the old sweep grid); I changed that assertion to the new grid and reran the whole suite, which is the line above. The skip is main's `tests/test_p02c.py:101` (waits for the full corpus). New: `test_r03_budget.py` 17, `test_r03_prereg.py` 4.
- ruff: `All checks passed!`
- git log --oneline -3 and git status --short: 

```
82a6c4a R03: E* rule, warmup scaling, PREREG v4
5b239a6 R02: merge main, partial-corpus dry run
67c1f83 R02: merge main (P02c2) into integration
```
`git status --short`: empty after the commit. (The top hash is the commit before this block was added; the commit was amended once, local only, so the final hash differs.)

## 2. The E* rule as implemented (`slm.train.budget`, `slm.integration.budget_sweep`, orchestrator stages `sweep` and `sizing`)
**Why (I-D039).** The full train split is about 0.75M tokens (about 45 optimiser steps per epoch at batch 32). On a corpus that small validation loss bottoms out early (overfitting) while fact storage keeps improving; DESIGN section 5 selects checkpoints by validation probes; PREREG v3 used validation loss.

**Sweep.** One seed (0), lr {3e-4, 6e-4, 1e-3} x dropout {0, 0.1} x batch size {16, 32} = 12 configs, up to 60 epochs, checkpoints at 1, 2, 3, 5, 8, 12, 16, 20, 25, 30, 40, 50, 60. After each run every checkpoint and the untrained model (`init`) are scored on the **validation probes only** (2 per fact, 240 rows; the probe set is built with `splits=("val",)` and asserted; nothing is written to the test ledger because no test probe exists in the set); the checkpoints are then deleted. Per checkpoint: validation loss, validation-probe stored rate (probe level), `null_stored_rate`.

**Rule (tolerance 0.01).**
1. config score = its best val-probe stored rate over the schedule;
2. near-ties = configs within 0.01 of the best score; the winner is the one with the **lowest validation loss** (minimum over its checkpoints) among them, the first in grid order on an exact tie;
3. **E\*** = the earliest checkpoint of the winner whose stored rate is within 0.01 of the winner's own best;
4. the sizing check (12M vs 27.6M) applies the same rule to the chosen config at both sizes and uses the winner's E\*;
5. the val-loss-optimal epoch of the winner is returned and printed beside E\*; the decision table lists every config at every checkpoint (`reports/tables/sweep_decision.md` for a real run).

**Final runs.** Seeds 0, 1, 2 train to 2E\* (cap 60) in one run, saving E\*, 2E\* and the schedule. Primary analysis, SFT start (`run_sft_seeds(pretrain_epoch=E*)`), QA base models and `stored_pretrain`: the checkpoint at E\* (the primary probe table is cut at the E\* step, so E\* is each seed's final checkpoint for the unchanged analysis code). Secondary analysis (H1/H2 at 2E\*, outside the Holm family): `results_secondary/`; learning curves use all checkpoints.

**Mock decision table** (`reports/integration/mock_sweep_decision_R03.md`; toy corpus, 12 epochs max, schedule 1,2,3,5,8,12; cells = val-probe stored rate / val loss; `*` = the config's best rate, `E` = E\*):

| config | 1 | 2 | 3 | 5 | 8 | 12 |
|---|---|---|---|---|---|---|
| cfg00 lr3e-4 d0.0 b16 | 0.071 / 6.83 | 0.067 / 5.29 | 0.079 / 4.35 | 0.092 / 3.33 | 0.108 / 2.93* | 0.096 / 2.86 |
| cfg01 lr3e-4 d0.0 b32 | 0.058 / 7.34 | 0.075 / 6.54 | 0.087 / 5.74 | 0.087 / 4.55 | 0.092 / 3.67 | 0.104 / 3.40* |
| cfg02 lr3e-4 d0.1 b16 | 0.071 / 6.75 | 0.075 / 5.37 | 0.083 / 4.39 | 0.096 / 3.36 | 0.087 / 2.94 | 0.104 / 2.85* |
| cfg03 lr3e-4 d0.1 b32 | 0.079 / 7.38 | 0.067 / 6.48 | 0.117 / 5.74* | 0.092 / 4.57 | 0.087 / 3.69 | 0.083 / 3.42 |
| **cfg04 lr6e-4 d0.0 b16** | 0.113 / 7.51 *E | 0.067 / 4.75 | 0.087 / 3.56 | 0.092 / 2.81 | 0.100 / 2.69 | 0.113 / 2.70* |
| cfg05 lr6e-4 d0.0 b32 | 0.092 / 7.23 | 0.087 / 6.28 | 0.083 / 5.30 | 0.092 / 3.80 | 0.100 / 3.01* | 0.096 / 2.85 |
| cfg06 lr6e-4 d0.1 b16 | 0.075 / 6.47 | 0.079 / 4.76 | 0.075 / 3.59 | 0.104 / 2.83* | 0.067 / 2.70 | 0.058 / 2.69 |
| cfg07 lr6e-4 d0.1 b32 | 0.075 / 7.16 | 0.087 / 6.17 | 0.096 / 5.19 | 0.087 / 3.77 | 0.108 / 3.01* | 0.108 / 2.86* |
| cfg08 lr1e-3 d0.0 b16 | 0.071 / 6.19 | 0.075 / 4.32 | 0.096 / 3.17* | 0.092 / 2.72 | 0.071 / 2.69 | 0.092 / 2.70 |
| cfg09 lr1e-3 d0.0 b32 | 0.108 / 7.92* | 0.092 / 5.84 | 0.096 / 4.90 | 0.087 / 3.29 | 0.092 / 2.75 | 0.104 / 2.72 |
| cfg10 lr1e-3 d0.1 b16 | 0.075 / 6.28 | 0.083 / 4.59* | 0.075 / 3.26 | 0.083 / 2.68* | 0.062 / 2.71 | 0.058 / 2.70 |
| cfg11 lr1e-3 d0.1 b32 | 0.092 / 7.71 | 0.079 / 5.93 | 0.067 / 4.75 | 0.100 / 3.39* | 0.092 / 2.79 | 0.075 / 2.69 |

Chosen: `cfg04` (best rate 0.113; 5 near-ties, lowest val loss among them), **E\* = 1**, **val-loss-optimal epoch = 8** (val loss 2.69, stored rate 0.100 there), final run 2 epochs, size small (27.6M model: best rate 0.100). `init` stored rate 0.108, `null_stored_rate` 0.100. **Every number is at chance** (0.058-0.117 around 0.108), so the rule picked the noisiest early checkpoint; the decision table now prints a WARNING when the chosen config's best rate is not above chance by more than the tolerance (tested), and the real run must not be accepted without checking it. The dry run went through all 13 stages (tokenizer 0.32 s, token cache 2.9, sweep 124.6, sizing 18.9, freeze 0.1, pretrain 4.8, probes 6.5, sft 12.5, qa_eval 68.9, samples 42.4, tables 12.8, analysis 17.2, report 7.5; total 319.5 s; report 6 pages, MOCK). The primary table holds checkpoints init and step 7 (E\*), the secondary one init, 7, 14.

## 3. Steps per epoch and total steps; warmup and logging
`spe = ceil(sequences / batch)`, `total = spe x epochs`; `warmup = min(max(10, round(0.05 x total)), total // 2)`, `val_every = max(1, total // 40)`, `log_every = max(1, total // 200)`; cosine to 10% of peak (`TrainConfig.resolve`, called in `train_run`; fields in `configs/train.yaml`: `warmup_frac 0.05`, `min_warmup_steps 10`, `val_evals_per_run 40`, `log_points_per_run 200`; null fields keep the old fixed values). The sweep stage prints the numbers from the real token cache, and each run's `summary.json` stores them.

| corpus | sequences (512 tokens) | batch | steps/epoch | total at 20 / 60 epochs | warmup at 20 / 60 | val_every at 20 / 60 | log_every at 20 / 60 |
|---|---|---|---|---|---|---|---|
| **partial (measured, 45.0k tokens)** | 105 | 8 | 14 | 280 / 840 | 14 / 42 | 7 / 21 | 1 / 4 |
| partial | 105 | 16 | 7 | 140 / 420 | 10 / 21 | 3 / 10 | 1 / 2 |
| partial | 105 | 32 | 4 | 80 / 240 | 10 / 12 | 2 / 6 | 1 / 1 |
| full-size estimate (0.75M tokens, 45 steps at batch 32) | about 1,440 | 16 | 90 | 1,800 / 5,400 | 90 / 270 | 45 / 135 | 9 / 27 |
| full-size estimate | about 1,440 | 32 | 45 | 900 / 2,700 | 45 / 135 | 22 / 67 | 4 / 13 |

(The partial rows at batch 16 and 32 and the full-size rows are computed with `resolve`; batch 8 follows the same formula. The partial corpus is 4 steps per epoch at the real batch, so the old fixed warmup of 200 steps would be 4.4 epochs at batch 32 on the full corpus and more than a whole 20-epoch run (80 steps) on the partial one.) `scripts/partial_dryrun.py` still runs with the new sweep (2 configs, 42 steps per config, warmup 10, no test read, ledger absent).

## 4. PREREG v4 changes and the freeze script
`docs/PREREG.md` (title "DRAFT v4 (NOT FROZEN)"; `tests/test_r03_prereg.py` ties the text to the code constants):
1. **Margins final** and stated as researcher-chosen, not data-derived: OR 1.25 per tripling (+-0.223 log-odds) for H1/H2, +-0.10 risk difference for H3/H4 (code constants unchanged; the decision string no longer says "placeholder").
2. **D4 rewritten**: E\* by validation probes (val-loss tiebreak), analysed checkpoint = E\*, runs continue to 2E\* for a secondary analysis; reason (I-D039) stated.
3. **Section 9** is the full budget rule (grid, schedule, scaled warmup, rule, sizing check, final runs, 2E\* secondary analysis outside the Holm family, the cosine-span limitation).
4. **Section 7** gains "Interpretation of nulls": nulls are read through CIs; equivalence only when the whole CI lies inside the margins; otherwise inconclusive; the 2E\* analysis cannot rescue or overturn the primary result.
5. **Section 4** gains the chance-baseline bullet: every stored rate is reported with `null_stored_rate` and the `init` checkpoint, and the new "checkpoint" bullet.
6. Header: "Training budget" row; "Supersedes draft v3"; the **freeze-hash and analysis-commit placeholders are unchanged** (`<commit hash>`, `<analysis commit hash>`).

**Freeze script** (`scripts/freeze_prereg.py`, `slm.integration.freeze`): records the PREREG hash, git commit/branch/dirty flag, analysis-code hash, and now `config_sha256`, the config file, **E\***, total epochs, model size, lr, dropout, batch size and the val-loss-optimal epoch (`--config`, `--final-config`; the orchestrator passes them). It refuses when the ledger has any **test-split** entry (an unreadable line counts), a test-split probe row exists, or QA test predictions exist; non-test ledger lines do not block. Refusal tests (`tests/test_r03_budget.py`): test-split ledger entry -> `FreezeRefused` ("1 test-split entry"), file untouched; unreadable ledger line -> refused; val-only ledger line -> no evidence; E\* and config hash appear in the block and in `verify`; CLI exit 0 on a clean run directory and exit 1 after a test ledger line. CLI on the finished mock run with a fresh copy of the v4 PREREG: `FREEZE REFUSED ... ledger ... has 3 test-split entries; probe table ... holds 2160 / 3240 test-split rows; ... QA test predictions exist`, exit 1; on an empty run directory with `--config configs/real.yaml --final-config runs/real_mock/final_config.json`: exit 0, record written (a copy in `/tmp`; the real `docs/PREREG.md` was not touched).

## 5. Decisions (I-D039 to I-D046), deviations, unsure
- I-D039 reasoning; I-D040 rule; I-D041 final runs; I-D042 sizing by the same rule; I-D043 step-scaled schedule; I-D044 PREREG v4; I-D045 freeze record; I-D046 housekeeping. `DESIGN_CHANGES_v1.3.md` rows 47-51 (rows 39/40 superseded; row 31 updated).
- **Deviation:** the sweep schedule is 60-epoch cosine, the final run's cosine spans 2E\*; E\* is a proxy for the budget (written into PREREG section 9). I did not train a separate E\*-long run per seed.
- **Unsure (important):**
  1. **Validation probes and test probes share the canonical prompt** (E-D014): the val canonical probe is the same prompt and value as a test canonical probe, and the sweep's seed 0 is also a final seed, so E\* is partly selected on an outcome that a test probe will repeat. It selects an epoch count, not a fact or a wording, but it is not independent of the test canonical probes.
  2. **Noise:** 240 val probes give a standard error of about 0.02 at a rate of 0.1, larger than the 0.01 tolerance (one probe is 0.004); the winner is a maximum over 12 configs x 13 checkpoints, so its rate is biased upward and E\* ("earliest within 0.01") is sensitive to noise. The mock run shows the failure mode (everything at chance, E\* = 1). A guard against an E\* at chance is only a warning in the table, not a refusal.
  3. One seed in the sweep; the final seeds may not follow the same curve.
  4. The sizing check trains the large model with the small model's chosen lr (not re-tuned).
  5. Real-run cost: 12 configs x 60 epochs plus the 27.6M run is roughly 13 runs of 60 epochs on the full corpus (about 9-10 minutes each for the 12M model by the R02 throughput guess); not measured on the full corpus.
  6. No real-corpus run of the new stages yet (main's P02c3 pending); `data/corpus/manifest.json` still absent.

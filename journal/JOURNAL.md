# Project Journal

Use one entry per prompt:

## [YYYY-MM-DD HH:MM] Pxx — <title>
**Goal:**
**Done:**
**Decisions:** (links D-###)
**Results:** (numbers + file paths)
**Problems & fixes:**
**Next:**

## [2026-10-31 00:00] P00 — Scaffold and tracking
**Goal:** Establish the project scaffold, typed utilities, tests, and tracking protocol.
**Done:** Created the src-layout package, utility modules, tests, tracking files, and empty project directories.
**Decisions:** D-001, D-002, D-003, D-004, D-005, D-006, D-007, D-008, D-009, D-010.
**Results:** See `tests/test_utils.py`, `track.txt`, and P00 commit. Installation, pytest, and ruff could not run because no Python toolchain is available in the environment.
**Problems & fixes:** The supplied design document was at `DESIGN.md`; copied unchanged to `docs/DESIGN.md`. The environment has only a Microsoft Store Python alias, with no usable Python interpreter, pip, pytest, or ruff.
**Next:** P01 KB and preregistration draft.

## [2026-10-31 00:00] P00b — Verification and workflow fix
**Goal:** Verify P00 and make the human/Codex workflow permanent.
**Done:** Saved this prompt, read the design and workflow, updated the workflow, added F-001, corrected P00 tracking semantics, and recorded the environment blocker.
**Decisions:** D-001 through D-010 confirmed in `journal/DECISIONS.md`.
**Results:** `.venv/bin/python` is absent, so pytest and ruff could not run; P00 remains incomplete pending evidence.
**Problems & fixes:** The expected POSIX virtual-environment executable is missing in this Windows workspace; no pip install was attempted.
**Next:** Human provides `.venv\Scripts\python.exe`; rerun the required checks and then complete P00 if green.

## [2026-10-31 00:00] P00b — Verification and workflow fix (GPU platform)
**Goal:** Verify P00 on Windows/CUDA and make the evidence-gated workflow permanent.
**Done:** Read the design and workflow, saved this prompt, added CUDA diagnostics and a CUDA matmul test, added D-011/D-012, and updated tracking/workflow records.
**Decisions:** D-011, D-012.
**Results:** `nvidia-smi` reports Windows-compatible RTX 5080 hardware and CUDA 13.1. `.venv\Scripts\python.exe` is absent, so pytest, ruff, Torch version, and `get_device()` output remain unavailable.
**Problems & fixes:** Verification is blocked by the missing human-created virtual environment; no pip install was attempted.
**Next:** Human restores `.venv\Scripts\python.exe`, then rerun the required commands and record output before completing P00.

## [2026-10-31 00:00] P00c - Verified environment and P00 exit criteria
**Goal:** Re-run P00 verification on the confirmed Windows 11 and RTX 5080 environment.
**Done:** Verified the v1.2 design header, ran the full utility test suite and Ruff, exercised `get_device()`, and completed a CUDA matmul.
**Decisions:** D-011, D-012, D-013.
**Results:** `7 passed in 5.00s`; `All checks passed!`; Torch `2.11.0+cu128`; CUDA `12.8`; NVIDIA GeForce RTX 5080 Laptop GPU; compute capability `(12, 0)`; bf16 `True`; CUDA matmul passed. Evidence is in the command output and `track.txt`.
**Problems & fixes:** P00 remained unverified until the human-provided Windows virtual environment was available.
**Next:** Run P01 (KB + validator + cells + sizing + PREREG draft).

## [2026-10-31 00:00] P01 - Knowledge base, cells, sizing, and preregistration draft
**Goal:** Author the CATD KB and deterministic experiment machinery without generating corpus text or calling an LLM API.
**Done:** Built 120 measured facts and 25 core facts; added validator tests, Latin-square assignment, sizing calculator, cell-balance report, sizing report, and draft preregistration.
**Decisions:** D-014, D-015, D-016.
**Results:** `validate_kb.py` passed all checks; seed 16 chosen with imbalance 0.0214 and KW p=1.0000; 20 facts per cell; SFT splits 8/2/10; 2600 planned mentions; pytest 17 passed; Ruff clean.
**Problems & fixes:** Initial hand-authored numeric collisions were corrected before validation; no LLM API was used.
**Next:** Run P02 (corpus pipeline and data card).

## [2026-11-03 09:00] P02b5 - Cue groups, chat labels, code-inserted templated facts, length calibration, prompt v4, pilot v4
**Goal:** Fix E8-E13 from the prompt-v3 pilot and rerun on the same 30 documents plus 20 fresh ones.
**Done (stage 1, commit P02b5a):** validator v3 (cue groups with value masking, V17 chat format) with v2 frozen; insertion module and V1p for templated facts; length calibration script and yaml; prompt v4; mock updated for placeholders; 152+ tests green; mock passes validator v3 on all 2407 plan rows.
**Decisions:** D-046 to D-052. **Failures:** F-006. **Experiments:** E-003.
**Results (stage 2, commit P02b5b):** pilot v4 on 50 documents (30 same + 20 fresh), prompt v4, validator v3, reasoning none: empty responses 0; mean actual/target 1.069 (nano) and 1.128 (mini), so the length undershoot is gone (nano 69.7% and mini 54.5% of accepted documents within +/-15%, with the V8 reason count still 21 and 50). Nano first-attempt pass 46.0%, accepted within 3 66.0%, projected $4.12; mini 48.0%, 66.0%, $15.80. Same-30 accepted 76.7% / 70.0%, fresh-20 accepted 50.0% / 60.0%. C1, C2 and C4 fail for both on every cohort. New failure mass: V11 (nano 18), V1p (nano 18, mini 8), V15 (nano 9, mini 13), V12 (9 / 6). Confound audit: fact sentences alone on their line are 17% (nano) and 5% (mini) for code-inserted templated facts against 6% and 3% for paraphrased ones. Spend this prompt $0.2731.
**Next:** the human and reviewer read the v4 reports and decide; no model is chosen here.

## [2026-11-02 23:00] P02b4 - Evidence-based validator v2, prompt v3, offline replay, pilot rerun
**Goal:** Fix the pilot failures E1-E7 (pilot_failures.md, pilot_samples.md) with validator v2, a fidelity check and prompt v3, replay the stored pilot offline, then rerun the same 30 documents.
**Done (stage 0-1, commit P02b4a):** preflight with reasoning "none" for both models; validator v1 frozen as doc_validator_v1.py and v2 written (normalisation, V2 word distance plus V2b, V5, V6, V8, V15, V16); configs/attribute_cues.yaml; E1 handling; version stamps; natural mock updated; replay of all 148 attempts; 127 tests and Ruff green.
**Decisions:** D-034 to D-045. **Failures:** F-005. **Experiments:** E-001.
**Results (stage 1):** replay: mini accepted attempts 15 -> 36 and first-attempt pass on non-empty 20.0% -> 60.0%; nano 10 -> 21 and 17.2% -> 41.4%; six pass->fail flips (V15 x5, V16 x2, V2 x1), all genuine meaning, hedge, casing or binding problems.
**Problems & fixes:** the prompt's V13 casing is named V16 because V13 is verbatim copying; V2b compares only entities in the value's own sentence (document-wide reading rejected natural parallel sentences).
**Results (stage 2, commit P02b4b):** rerun on the same 30 documents with prompt v3, validator v2, reasoning none: empty responses 0 and reasoning tokens 0 for both models; nano first-attempt pass 46.7%, accepted within 3 70.0%, projected full run $2.75, 23.8% within +/-15% of target; mini 50.0%, 80.0%, $7.95, 16.7%. C1 and C2 fail for both, C3 passes for nano only, C4 fails for both (mean actual/target 0.79), C5 passes. Failures now concentrate in V8 (nano 24, mini 27 reason lines), V1 (nano 14), V5 (nano 10) and V15 (mini 6). Spend this prompt $0.1033; cumulative pilot spend $0.3859 of $1.00.
**Next:** the human and reviewer fill the GENERATION_DECISION table from reports/tables/pilot_report_v3.md and pilot_samples_v3.md; no model is chosen here.

## [2026-11-02 21:00] P02b3 - Pilot failure diagnosis
**Goal:** Report where and why the pilot attempts failed, without changing the validator, prompts, plan, KB or budget code.
**Done:** Added scripts/analyze_pilot_failures.py (report only, no API calls) and one fixture test; generated reports/tables/pilot_failures.md (sections 0 and A-J).
**Decisions:** none.
**Results:** 16 of 71 mini attempts and 12 of 77 nano attempts were accepted; 6 mini and 10 nano attempts returned empty text with all 900 output tokens spent on reasoning; every V1 "value missing" case is one of those empty attempts. pilot_report.md bins V10-V14 reason lines into V1 (one-digit rule pattern), which inflated its V1 row. Hypothetical full-run costs are in section H.
**Problems & fixes:** none beyond the above; no code outside the new script was changed.
**Next:** Human and reviewer decide on the next step using the pilot report and this diagnosis.

## [2026-11-02 18:00] P02b2 - Validator hardening, run-mode safety, ledger fix, real pilot
**Goal:** Close the degenerate-PASS hole, make mock and real runs impossible to confuse, log every generation attempt, then run the real pilot.
**Done:** Validator rules V10-V14 with structured reasons; whole-word meta pattern and chat-label handling in V5; natural varied mock writer with a violation mode per rule V1-V14; required --client, banner, Client header and cross-client refusal; generator ledger logs every attempt through the global guard and retries carry feedback; mock data moved to data/raw_mock; model status text in the config; WORKFLOW.md updated.
**Decisions:** D-032, D-033.
**Results:** 95 tests passed, Ruff clean before the pilot. Pilot spend $0.2826 of the $1.00 pilot cap; both models failed C1, C2 and C3 (nano: 40.0% accepted, 16.7% first pass, projected $14.63; mini: 53.3%, 23.3%, $31.53); dominant failures V1, V2, V8, V5. No model chosen. Reports: reports/tables/pilot_report.md and pilot_samples.md.
**Problems & fixes:** F-004 logged; F-001 updated. The old meta pattern flagged "there is" and chat first words were flagged by V5; both fixed.
**Next:** Human and reviewer choose a model with docs/GENERATION_DECISION.md.

## [2026-11-02 12:00] P02b - Paid-pilot tooling
**Goal:** Build the paid-pilot tooling without calling the real API; the human runs the pilot.
**Done:** Added chat threads to the compatibility matrix and re-planned; pre-registered the selection rule; wrote `src/slm/data/pilot.py` and `scripts/run_pilot.py` (model-id check, parameter probe, 30 deterministic rows, validator-feedback retries, global budget guard over every ledger, cache and resume, report and samples); added `GlobalBudgetGuard`, `flagged_capitals`, ledger `client` field; wrote PILOT_RUN.md and API_NOTES.md; added mock-only tests.
**Decisions:** D-030, D-031.
**Results:** 65 tests passed; Ruff clean; plan assertions unchanged after the chat-thread change (train mean 344.2 tokens, max pair 6, bin ratios 0.795-1.133); mock pilot end to end writes pilot_report.md and pilot_samples.md; worst-case pilot cost $0.51; no real API call.
**Problems & fixes:** Past mock runs had written untagged entries to `data/raw/ledger.jsonl`; they were tagged `"client": "mock"` so they do not count as spend. The P02a generator still logs only accepted attempts to its ledger; the pilot logs every attempt (to fix before the main run).
**Next:** Human runs the pilot (docs/PILOT_RUN.md) and pastes back pilot_report.md and pilot_samples.md.

## [2026-11-02 00:00] P02a2 - Fix corpus plan and prompts before paid calls
**Goal:** Fix document length, pair co-occurrence, val/test regimes, prompt template, cost estimate, and core-fact usage before any API call.
**Done:** Per-type base words and bucket multipliers; tokens_per_word; constructive + local-search train assignment with escalating cross-family allowance and bin-independence check; iid/novel val/test regimes; prompt template v2 with per-type guidance and optional names; V5/V8 updates; rewritten plan_stats with cost sensitivity; shuffle-cycle core-fact sampler; new tests.
**Decisions:** D-024 (updated), D-028, D-029.
**Results:** Train mean 257.8 words / 348.0 tokens; max pair 6, 30 pairs above 3, 65 cross-family docs (5.0%); bin ratios 0.795-1.133; core-fact use 289-292 docs each; 58 tests passed; Ruff clean; no API calls. See reports/tables/plan_stats.md.
**Problems & fixes:** F-003 updated (cap 3 was an optimizer failure, not infeasibility). Original bucket-by-k mix gave only 233 words per doc, so buckets were decoupled from k (D-028). The V9 test mutation was scaled to text length because documents are longer.
**Next:** Run P02b pilot model selection (gpt-5.4-mini standard is over budget at the +100% reasoning level; use batch or nano).

## [2026-10-31 00:00] P02a - Corpus pipeline infrastructure
**Goal:** Build offline planning, prompt, validation, budget, cache, resume, and mock-generation infrastructure without real API calls.
**Done:** Added generation configuration, document types, style cards, deterministic 2407-row plan, prompt templates and samples, document validator, budget guard, mock/OpenAI client interfaces, CLI, tests, and plan statistics.
**Decisions:** D-024, D-025, D-026, D-027.
**Results:** KB validator PASS; plan contains 2407 documents, train planned mentions reconcile, validation/test counts are two per fact, 50 mock documents accepted, 51 tests passed, and Ruff clean.
**Problems & fixes:** P3 pair cap was infeasible under the fixed allocation; F-003 and the explicit relaxation reason in `reports/tables/plan_stats.md` record it for P02b.
**Next:** Run P02b pilot model selection before any real API calls.

## [2026-10-31 00:00] P01d - Final KB quality pass
**Goal:** Enforce all-integer values, per-entity plausibility ranges, severity ordering, handler-name quality, and entity-level exposure balance.
**Done:** Re-authored affected literals; added per-entity range validation and final payout severity ordering; changed handler initials; extended Latin-square seed search with family permutations and entity-ratio objective; added tests and report tables.
**Decisions:** D-022, D-023.
**Results:** Validator PASS; seed 177; character imbalance 0.0088; entity ratio 3.0000; objective 0.5088; KW p=1.0000; 38 tests passed; Ruff clean; 2600 planned mentions.
**Problems & fixes:** P01c follow-up is recorded in F-002; per-entity ranges now gate the KB.
**Next:** Run P02 (corpus pipeline and data card).

## [2026-10-31 00:00] P01c - KB quality defect corrections
**Goal:** Correct remaining numeric precision, plausibility ordering, canonical-style, and filler-pool defects.
**Done:** Added R11 and configured orderings; re-authored affected values; rewrote all 120 canonical sentences across 20 patterns; expanded filler pools to 60/60/80; added validator and regression tests; reran assignment and sizing.
**Decisions:** D-020, D-021.
**Results:** Validator PASS; seed 3, imbalance 0.0089, KW p=1.0000; 32 tests passed; Ruff clean; 2600 planned mentions and all sizing reconciliations passed.
**Problems & fixes:** P01b follow-up defects are recorded in F-002 and fixed with precision, ordering, style, and pool gates.
**Next:** Run P02 (corpus pipeline and data card).

## [2026-10-31 00:00] P01b - Realistic KB and sizing gate
**Goal:** Replace unrealistic arithmetic-progression values, clean core facts, add filler pools, and correct train-only sizing.
**Done:** Re-authored all 120 literals within configured ranges; added R10, range, cross-attribute, core, and filler validation; renamed the weight attribute; added the numeral policy; corrected sizing over the k by background grid; expanded tests.
**Decisions:** D-017, D-018, D-019.
**Results:** Validator PASS; seed 3, imbalance 0.0145, KW p=1.0000; 20 facts per cell; 2600 planned mentions; sizing reconciliation PASS for all 12 rows; 23 tests passed; Ruff clean.
**Problems & fixes:** P01 arithmetic and sizing defects are recorded in F-002 and corrected by range-driven literals and explicit formulas.
**Next:** Run P02 (corpus pipeline and data card).

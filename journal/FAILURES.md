# Failures

| F-### | date | Plan A (what we tried) | what happened (evidence path) | root cause | Plan B (pivot) | lesson |
|---|---|---|---|---|---|---|
| F-001 | 2026-10-31 | Codex sets up the environment and commits | No Python in the sandbox, `.git` read-only, nothing verified; P00 was marked complete without meeting its exit criteria (`track.txt`) | Codex sandbox restrictions plus no exit-criteria gate | Human owns environment and commits; phase completion requires passing exit criteria | Never mark a phase complete without evidence. |

Resolution - human installed Python 3.12.10 and built .venv; verified at P00c.

Update (P02b2, D-033) - the executor is now Claude Code with a full local shell; the agent runs tests and makes local commits (never pushes), the human reviews and pushes.

| F-002 | 2026-10-31 | Author values to satisfy digit-run uniqueness | Absurd values, meta core facts, and wrong sizing math (P01 report) | Constraint-driven authoring without realism or arithmetic checks | Range-driven authoring with R10, range validation, and a digit-run allocation table | Encode every quality bar as a validator check, not only uniqueness. |

P01b follow-up - Decimals, implausible ordering, awkward canonical sentences, and alphabetical pools slipped through because the checks tested rules but not plausibility or style. Fix: add R11, configured orderings, canonical-style checks, and filler-pool checks.

P01c follow-up - Global ranges and ordering checks alone allowed implausible per-species values. Fix: add per-entity ranges and enforce them in the validator.

| F-003 | 2026-10-31 | Enforce a maximum of three train co-occurrences for every fact pair under the fixed k mix | Deterministic planning reached a maximum pair count above three; the exact exposure totals and fixed 1/2/3-fact document mix leave no feasible assignment in the current family-slot allocation (`reports/tables/plan_stats.md`) | Fixed capacity and exposure constraints interact with family/attribute compatibility | Log the relaxation and revisit the allocation in P02b before real generation | Keep pair balancing outcome-independent and make any relaxation explicit. |

P02a2 resolution (F-003) - The cap of three was never proven infeasible; the P02a greedy planner simply stopped improving (max pair 9 or more). Replaced by P3' (cap 6) with a constructive fill plus swap local search. Within families alone the search ended at max pair 9: the high x high cell needs about 590 pair incidences but only 792 fit under the cap in 132 admissible pairs (75% full, no slack). With 5% cross-family docs (65) the search reaches max pair 6 and bin-independence ratios 0.795-1.133 (reports/tables/plan_stats.md). The cap of 3 was not reached under the bin-independence constraint (30 pairs remain above 3). Lesson: test feasibility with an optimizer and a capacity count before logging a relaxation.

| F-004 | 2026-11-02 | Rely on validator rules V1-V9 plus a repetitive mock client to prove the pipeline | The mock pilot samples (reports/tables/mock/pilot_samples.md, e.g. train-1077) passed the validator although they were one valid sentence followed by the same 14-word filler sentence repeated 20+ times and cut off mid-sentence | V1-V9 only check values, binding, digits, names, markup, length and ASCII; nothing checked repetition, completeness, casing, copying or sentence count, and the mock only had to satisfy those same rules | V10-V14 added to the validator, a natural multi-paragraph mock replaced the repeated-filler one, and the degenerate text is a regression fixture (tests/test_validator_hardening.py) | Test the validator against adversarial junk, not only against its own mock. |

# Failures

| F-### | date | Plan A (what we tried) | what happened (evidence path) | root cause | Plan B (pivot) | lesson |
|---|---|---|---|---|---|---|
| F-001 | 2026-10-31 | Codex sets up the environment and commits | No Python in the sandbox, `.git` read-only, nothing verified; P00 was marked complete without meeting its exit criteria (`track.txt`) | Codex sandbox restrictions plus no exit-criteria gate | Human owns environment and commits; phase completion requires passing exit criteria | Never mark a phase complete without evidence. |

Resolution - human installed Python 3.12.10 and built .venv; verified at P00c.

| F-002 | 2026-10-31 | Author values to satisfy digit-run uniqueness | Absurd values, meta core facts, and wrong sizing math (P01 report) | Constraint-driven authoring without realism or arithmetic checks | Range-driven authoring with R10, range validation, and a digit-run allocation table | Encode every quality bar as a validator check, not only uniqueness. |

P01b follow-up - Decimals, implausible ordering, awkward canonical sentences, and alphabetical pools slipped through because the checks tested rules but not plausibility or style. Fix: add R11, configured orderings, canonical-style checks, and filler-pool checks.

P01c follow-up - Global ranges and ordering checks alone allowed implausible per-species values. Fix: add per-entity ranges and enforce them in the validator.

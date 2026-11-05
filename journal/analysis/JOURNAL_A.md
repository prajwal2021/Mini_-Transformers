# Analysis stream journal

## A01 - analysis pipeline, simulator, PREREG draft
**Goal:** one-command analysis on a long-format probe table, validated on simulated data; PREREG draft.
**Done:** input contract (docs/ANALYSIS_INPUT.md); simulator with planted H1-H4 effects, fact/seed/fact-seed/fact-regime/variant random effects and an acquisition curve; GEE pipeline, Holm, fact-bootstrap risk differences, descriptive and acquisition tables, two figures (PNG+PDF, byte-deterministic); validation report; PREREG draft v1 (unfrozen).
**Result:** the model recovers planted effects and holds the null false-positive rate; H3 (interaction) is badly underpowered at 20 facts/cell (0.32).
**Not done / open:** extraction family (H5, H6) analysis code; the canonical-vs-novel frame column; confirm SESOI (OR 1.25) and the family composition before P05 freeze.

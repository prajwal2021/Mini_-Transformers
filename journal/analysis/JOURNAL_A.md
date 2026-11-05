# Analysis stream journal

## A01 - analysis pipeline, simulator, PREREG draft
**Goal:** one-command analysis on a long-format probe table, validated on simulated data; PREREG draft.
**Done:** input contract (docs/ANALYSIS_INPUT.md); simulator with planted H1-H4 effects, fact/seed/fact-seed/fact-regime/variant random effects and an acquisition curve; GEE pipeline, Holm, fact-bootstrap risk differences, descriptive and acquisition tables, two figures (PNG+PDF, byte-deterministic); validation report; PREREG draft v1 (unfrozen).
**Result:** the model recovers planted effects and holds the null false-positive rate; H3 (interaction) is badly underpowered at 20 facts/cell (0.32).
**Not done / open:** extraction family (H5, H6) analysis code; the canonical-vs-novel frame column; confirm SESOI (OR 1.25) and the family composition before P05 freeze.

## A02 - hypotheses aligned with DESIGN, extraction tests, probe_frame
**Goal:** fix A01's wrong hypothesis labels (A-F001); implement DESIGN's H1-H4 with the eval stream's probe-table columns; add the extraction tests and QA-table contract; re-validate.
**Done:** docs/ANALYSIS_HYPOTHESES.md (verbatim DESIGN wording, ambiguities); contracts for probe and QA tables (docs/ANALYSIS_INPUT.md, schema.py); probe_frame model with H2 as div x frame; extraction.py (McNemar, Fisher, permutation, bootstrap); family.py (Holm over H1-H4); QA simulator with the 40/10/50 split and planted extraction effects; validation report; PREREG draft v2 (unfrozen); A01's `regime` removed.
**Result:** H1, H2, H3 adequately powered at 120 facts; H4 underpowered (0.36). H3/H4 tests are valid but conservative.
**Open:** see PREREG section 12 (Holm family, margins, aggregation rules, comparator, H4 power, train_mentions, canonical probe count).
## A03 - PREREG v3, realized diversity, sensitivity, report generator
**Goal:** apply the architect's decisions, add the realized-diversity covariate and the sensitivity suite, and build a report generator that cannot print an unsourced number or an unmarked simulated result.
**Done:** PREREG v3 (H4 secondary, Holm m = 3, rules, comparator, one checkpoint; deviations D1-D5 for DESIGN v1.3); aggregation rules; per-seed final checkpoint; realized-diversity schema, simulator and models; separation detection and fallback ladder; `run_sensitivity.py`; banner on figures and in the report; `build_report.py` with macros, lint, number provenance, Chrome and Matplotlib backends, and the 5-7 page gate; loss-curve, E0/E1/E2 and sample-table outputs; simulated report committed under docs/report/simulated/.
**Result:** H1-H3 adequately powered at 120 facts, H4 secondary (0.33). A weak manipulation shrinks nominal H2 and its power sharply; the realized-diversity model recovers it.
**Open:** spec PDF and SPEC_COMPLIANCE.md absent (outline from the prompt); realized-diversity column meanings and the report-input files are my definitions; no pandoc/LaTeX/weasyprint path; margins still placeholders.
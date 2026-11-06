# DESIGN changes v1.2 -> v1.3 (proposed; DESIGN.md is not edited)

Every deviation from `docs/DESIGN.md` v1.2 that the stream journals record, with the reason, the
journal id and the evidence. "Status": **in force** (code does it), **proposed** (documented but not
yet frozen), **open** (a DESIGN requirement nobody has done yet). Prefixes: D- data stream
(`journal/DECISIONS.md`), E- eval, M- model, A- analysis, I- integration.

## 1. Data generation (DESIGN section 2)

| # | DESIGN v1.2 | Now | Reason and evidence | Journal | Status |
|---|---|---|---|---|---|
| 1 | 2.1/2.2: the LLM writes documents including fact sentences (templated verbatim, paraphrased in new wording) | **Sentence-bank architecture.** The document model never writes a fact sentence: every mention is a marker `<<FACT Fxxx>>` that code replaces, with the canonical sentence (templated) or a distinct pre-built bank sentence (paraphrased). Background documents carry no markers | Paraphrase frame collapsed: 16 of 17 paraphrases opened "For <entity>" in pilot v5 (E25), so paraphrase diversity could not be controlled inside documents | D-065, D-066, D-067, D-070 | in force |
| 2 | 2.3: reject and regenerate up to 3 tries; validator checks numbers, names, assigned values | Validator v5: fact-sentence checks (V15, V2/V2b, V1 branches) moved to bank level; document validator keeps value-exactly-once, V3-V14, V16-V18; max 5 attempts; a document that fails twice with the same rule set is stuck | Bank sentences are validated once at bank level; retries did not improve first-pass rate (E6) | D-067, D-069, D-091 | in force |
| 3 | 2.3 / section 12: validate then regenerate | **Amendment A1** to the pre-registered model-selection rule (docs/GENERATION_DECISION.md): eligibility = accepted within 5 attempts >= 97% on a fresh cohort, first-attempt pass >= 60%, projected cost <= $7.00, opening 5-gram duplicates <= 10% | The original C1-C6 (accepted within 3 >= 95%) could not be met by any model under validator v3/v4; written before the v5 result | D-030, D-053 | in force |
| 4 | (none) | **Amendments A2, A2b, A2c** (bank gates). A2: per-fact bank gates (a)-(g). A2b (post hoc): the judge NO rate is reported instead of gated; G1 = A2 (a)-(g) on six pilot facts + judge label precision. A2c (post hoc): (d) = ceil(0.8 x min(need, 25)); (a) allows controlled reuse of a sentence inside train mentions only (each at most twice, distinct >= 0.6 x need) | A2b: judge NO measures generation efficiency, not fidelity (run 3). A2c: the first full bank had 14 of 120 facts failing (F040 287 of 340 duplicates), 106 passed; after A2c all 120 pass, 7 facts reuse 39 mentions | D-070, D-074, D-085, D-088, D-089, D-090 | in force; A2b/A2c are post hoc |
| 5 | (none) | Stage-1 gate waived by the architect (replay first-attempt 58.0% / 54.0% vs 60%) | The replay re-scores old prompt text and cannot measure prompt v5 | D-064 | in force |
| 6 | 1.1: 5 skyports | Six entities per family (Latin-square cell assignment) | Balance of the 3 x 2 grid on entity | D-015 | in force |
| 7 | 2.1: stratified by attribute type and entity | Entity-level balance objective `char_len_imbalance + 0.25 x (entity_ratio - 1)`; co-occurrence cap 6 (pair count in train) | Entity frequency and value length confound bins (DESIGN review items 6, 7) | D-023, D-029 | in force |
| 8 | 2.2: doc length capped at ~450 tokens, whole docs in one 512 window | Length band 0.6-1.4 of target, up to 380 words (about 486 tokens); documents over 512 tokens are cut into independent 512-token chunks by the packer; share is reported | Length is a throughput control; per-model length calibration | D-038, D-060, D-061, D-068; M-D015 | in force |
| 9 | 2.4: 90/5/5 split | 2407 documents: train 2167, val 120, test 120 (90.0/5.0/5.0), val/test two regimes (iid, novel style cards; fact twice each, paraphrase-only) | Held-out style axes (roles quality auditor, route editor; tone apologetic) | D-024, D-026 | in force |
| 10 | 2.1: measured exposure by string match, may differ from target | Planned exposure equals measured exposure by construction (each fact once per assigned document, no unassigned values); the corpus run must confirm it | D-025 | D-025 | in force, unconfirmed on the real corpus |
| 11 | 2.2: any numerals | Corpus numeral policy: KB digit runs and single-digit numerals only | Exact exposure counting | D-017 | in force |
| 12 | 2.3: generator LLM unspecified | gpt-5.4-mini, reasoning off; gpt-5.4-nano ineligible under A1 (92.5% within 5 < 97%) | Pilot v6, 40 docs | D-091, D-090 | in force |

## 2. Model, training, tokenizer (sections 3-5)

| # | DESIGN v1.2 | Now | Reason and evidence | Journal | Status |
|---|---|---|---|---|---|
| 13 | 5: weight decay 0.1 on all 2-D matrices incl. the tied embedding | M02 first excluded embeddings (decay on `nn.Linear` weights only), then **reversed**: decay on every 2-D matrix incl. the tied token table and the learned position table; no decay on LayerNorm or biases. Net effect: DESIGN's rule, applied literally to the position table too | The M02 task asked for the exclusion; DESIGN is explicit; both are configurable (`decay_embeddings`) | M-D024, M-D035 | in force (matches DESIGN) |
| 14 | 5: "log-spaced checkpoints (~15)", released checkpoint by the val-probe rule | Checkpoints at epochs 1, 2, 3, 5, 8, 12, 16, 20 (8 files); **the analysed checkpoint is the final one of each seed** after a fixed epoch count chosen on validation loss; the release seed is the lowest final val loss among seeds with an SFT run | No selection on probes; one checkpoint removes a multiplicity source. The val-probe rule needs the probe stream, which was not integrated when M-D047 was written | A-D025, PREREG D4, M-D027, M-D047 | proposed |
| 15 | 5/section 4: confirm size by a 12M vs ~25M sizing check | The sweep is lr {3e-4, 6e-4, 1e-3} x dropout {0, 0.1, 0.2}, 1 seed, 20 epochs; **no model-size comparison has been run**; the default model is 12.4M (6/6/384) | Not done yet | M-D034 | open |
| 16 | 5: 200-step warmup, cosine to 6e-5 | Same (cosine to 0.1 x peak); `label_eos` true: `<|eos|>` is a target, the label at the eos position is masked | Document ends must be learnable | M-D025, M-D030 | in force |
| 17 | 3: tokenizer from scratch, train-only | Same; plus train-only enforced by a hash-verified **split manifest** (not by file names); `min_frequency` 2 for real corpora | Name guard could be fooled by a path | M-D021, M-D022, M-D007 | in force |

## 3. Evaluation and probes (section 6)

| # | DESIGN v1.2 | Now | Reason and evidence | Journal | Status |
|---|---|---|---|---|---|
| 18 | 6: 2 val + 3 test templates; canonical-frame and novel-frame | **Probe frames**: `probe_frame` canonical/novel replaces the briefly used probe `regime`. Per attribute 1 canonical + 3 novel wordings; val = canonical + 1 novel (2 probes), test = canonical + 2 novel (3 probes). **The canonical prefix is shared by val and test**; only the novel wordings are disjoint | Four wordings exist per attribute; the document-level iid/novel regime is a different thing (D-024) | E-D010, E-D014; A-D012 | in force |
| 19 | 6: ranking and binding on summed and length-normalised log-probs | Token-normalised rank and stored are secondary columns (`rank_tokennorm`, `stored_tokennorm`, `norm_unit`); `stored` uses summed scores | The Scorer first could not expose token counts | E-D006, E-D015 | in force |
| 20 | (none) | **Permutation null** (`null_stored_rate`): the same procedure with another entity's value as pseudo-truth; chance is about 0.13, not 0 | A "stored" rate has a non-zero chance level; `init` model reports it | E-D012, E-D013 | in force (addition) |
| 21 | 7.1/7.4: "exact value match" | Primary `exact_value_match` = value present with no rival value of the attribute; `contains_gold` and `sentence_exact` kept apart | DESIGN names no normalisation; sentence equality was too strict | M-D040, M-D043 | in force |
| 22 | 7.2: 2-shot exemplars from SFT-train facts | Exemplars from **SFT-val** facts (F049 airship_onboard_handler_name, F064 species_max_combined_weight), so that they sit in none of E0/E1/E2; seeded (seed 0), two families, plain question. Re-picked from the real `data/sft/sft_val.jsonl` and `data/eval/qa_test.jsonl` in R01 (same ids: the mock files were the real split) and checked disjoint from SFT-train, SFT-val-evaluation and E0/E1/E2 by `tests/test_r01_exemplars.py` | DESIGN says SFT-train facts, but SFT-train facts are the facts of E0 and E1, so an exemplar would put an evaluation answer in the prompt | M-D044, I-D026 | in force |
| 23 | 7.2: test access | Every read of the test split goes through a ledger (`reports/test_access_log.jsonl`) | Auditable once-only test use | M-D041 | in force (addition) |
| 24 | 7.3: LR 1e-4, short warmup, <= 6 epochs, early stop | Batch 16, warmup 20, patience 2, loss on answer + `<|eos|>`; replay (Plan B) not implemented | Free parameters filled in | M-D036-M-D038 | in force |

## 4. Research design and analysis (section 8)

| # | DESIGN v1.2 | Now | Reason and evidence | Journal | Status |
|---|---|---|---|---|---|
| 25 | 8: mixed-effects logistic regression `(1|fact) + (1|template) + (1|seed)` | **Logistic GEE** (fact clusters, bias-reduced covariance, t critical values); seed fixed; templates as within-frame fixed dummies; a variational-Bayes mixed logit stays as a sensitivity row | 3 seeds cannot estimate a variance; VB posteriors are too narrow for a p-value family. Null rejection 0.033-0.062 per test over 1000 replicates | A-D001, A-D002, A-D003; PREREG D3 | proposed (PREREG unfrozen) |
| 26 | 8: H1-H4 equal | **H4 secondary** (effect and CI only, no significance claim); **Holm over H1, H2, H3 (m = 3)**; H1 primary | Power at 120 facts: H1 1.00, H2 0.87, H3 0.97, H4 0.33 (60 E2 facts) | A-D020, A-D022; PREREG D1, D2 | proposed |
| 27 | 6: stored per probe; H3 needs a fact-level notion | **Fact-level rules** (PREREG section 4): stored = stored on more than half of the seed's test probes (2 of 3), then in more than half the seeds; QA-correct = right on more than half of the 3 E2 phrasings, then majority of seeds; `any`/`all` as sensitivity; comparator `base_2shot` (0-shot secondary) | Facts, not items, are independent; the `all` rule nearly erases H3 and H4 (sensitivity table) | A-D014, A-D023, A-D024; E-D018 | proposed |
| 28 | 8: H4 via McNemar/Fisher | H4 between-condition: stratified permutation test on per-fact gains (descriptive, secondary) | DESIGN names none | A-D015 | proposed |
| 29 | 2.1: covariates entity mentions, value length | **Exposure coding** `freq_c` = log3(measured train mentions), centred (bin code when no counts); **realized-diversity covariate** `rdiv_z` = z(1 - mean pairwise skeleton Jaccard) as a sensitivity analysis (replace or add to `div_bin`) | A weak manipulation attenuates the nominal H2 (simulated: 0.80 -> 0.49 -> 0.25 at strengths 1.0 / 0.6 / 0.3); the bank measures realized diversity | A-D019, A-D026; D-085 | proposed |
| 30 | 8: sensitivity not listed | Pre-registered sensitivity suite: aggregation rules, bins vs log3, with/without template terms, GEE vs mixed, token-normalised outcome, comparator, realized diversity, separation report | `run_sensitivity.py` | A-D028 | in force |
| 31 | 8: PREREG committed before full pretraining | PREREG v4 is an **unfrozen draft**; margins (OR 1.25 per tripling; +-0.10 risk difference) are final researcher-chosen values, not data-derived (R03) | Freeze after the team confirms | A-D009, A-D018, A-D022 | open |

## 5. Deliverables (section 9)

| # | DESIGN v1.2 | Now | Reason and evidence | Journal | Status |
|---|---|---|---|---|---|
| 32 | 9: report as IEEE double-column LaTeX in `reports/paper/` | Report built from a `{{macro}}` Markdown template to HTML and PDF by headless Chrome/Edge (Matplotlib fallback); a lint rejects numbers typed in the template; 5-7 page gate. No LaTeX path | No LaTeX, pandoc, weasyprint or reportlab installed; an untested path is not trusted | A-D029 | proposed; **check against docs/Term_Project.pdf, which is missing** |
| 33 | 9: `docs/Term_Project.pdf`, `docs/SPEC_COMPLIANCE.md` implied by the rubric table | Neither file exists in the repo or any sibling worktree; outlines and the 5-7 page limit come from task text | Noted by A-D030, M-D001, M-D050 | A-D030, M-D050 | open |
| 34 | 9: generation and chat entry points `slm.generate`, `slm.chat` | `scripts/generate.py --bundle ... [--interactive]`; bundle layout `bundle/{pretrained,sft}/` with manifest hashes instead of `release/` | Bundle is hash-checked; fresh-clone test passes | M-D046, M-D048, M-D049 | in force |

## 6. Integration (new, I01)

| # | Change | Journal |
|---|---|---|
| 35 | One `tests/conftest.py` (markers `slow`, `gpu`, GPU skip); no `sys.path` edits in tests | I-D002 |
| 36 | Mock pipeline carries a MOCK banner distinct from SIMULATED; `--real` is refused for it | I-D006 |
| 37 | The probe table's `checkpoint` is the optimiser step (int); `init` = 0 | I-D003 |

## 7. Real-run preparation (R00)

| # | Change | Journal |
|---|---|---|
| 38 | Probe wording: two novel prompts reworded (`species_min_age_weeks` n3, `skyport_relief_gate` n3); indefinite articles come from a helper (`a`/`an`), not typed | I-D016, I-D017 |
| 39 | Final epochs are the best epoch of the winning sweep/sizing run (PREREG D4); HPARAM_PROTOCOL 3.4 said "full 20 epochs"; the two documents disagree | I-D020 |
| 40 | The 12M-vs-25M sizing check of DESIGN section 5 is a pipeline stage (row 14 is now implemented, not yet run); selection by validation loss only, val-probe accuracy not used | I-D021 |
| 41 | PREREG freeze is a script with a hash + commit record and a refusal rule (any test probe, QA test file or ledger entry); test probes are logged in the ledger | I-D022, I-D023 |
| 42 | SFT/QA files are built from the KB's own `sft_split` with 14 assertions and a hash manifest (`data/sft`, `data/eval`) | I-D018 |

## 8. Evaluation metrics, samples, README (R01)

| # | Change | Journal |
|---|---|---|
| 43 | Error taxonomy of 7.4 made executable: one class per prediction by fixed rules per value class (`docs/ERROR_TAXONOMY.md`); a value of the wrong class only counts as a format failure | I-D027 |
| 44 | Ranking accuracy of 7.4 taken from the section 6 definition on the QA prompt; the sentence variant (`rank_sentence`) is reported in addition because SFT answers are sentences | I-D029 |
| 45 | Checkpoint sample generator with taxonomy flags and an automatic 6 + 6 selection (DESIGN 6 gallery: "successes + failures, categorized"); the repetition/format-drift categories of DESIGN 6 are the `gibberish` flag | I-D031 |
| 46 | 2-shot exemplars re-picked on the real files (row 22); no change of ids | I-D030 |

## 9. Training budget by validation probes (R03; supersedes rows 12-14 and 39-40 where they disagree)

| # | Change | Journal |
|---|---|---|
| 47 | Checkpoint selection returns to DESIGN section 5's validation probes: the sweep (lr x dropout x batch size, up to 60 epochs) scores the **validation** probes at every checkpoint; the config is chosen by validation-probe stored rate (near-ties within 0.01 by lower validation loss) and **E\*** = the earliest checkpoint within 0.01 of that config's best. Rows 39/40 (final epochs from validation loss) are superseded. Reason: on a corpus of about 0.75M tokens validation loss bottoms out early while fact storage keeps improving | I-D039, I-D040 |
| 48 | Final runs train to 2E\* (cap 60); the primary analysis, the SFT start and `stored_pretrain` use E\*; a secondary H1/H2 analysis uses 2E\* (outside the Holm family). Limitation: the sweep's cosine spans 60 epochs, the final run's spans 2E\* | I-D041 |
| 49 | The 12M-vs-25M sizing check uses the same rule (validation-probe stored rate, val-loss tiebreak) instead of validation loss alone; DESIGN's "val-probe accuracy" is now used | I-D042 |
| 50 | Warmup 5% of the optimiser steps (min 10, at most half), cosine to 10%, evaluation 40 and logging 200 times per run, all from the real step count (`TrainConfig.resolve`) | I-D043 |
| 51 | PREREG v4: final researcher-chosen margins (not data-derived), the E\* rule, the 2E\* secondary analysis, null interpretation through CIs, the chance baseline (`null_stored_rate` and `init`) in every stored rate; the freeze records the config hash and E\* | I-D044 |

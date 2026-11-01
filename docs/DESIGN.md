# CS 5370 Group Project — Design Document
**Building and Investigating a Small Transformer Language Model**
Version: **v1.2** (hardware confirmed) | Status: P00 verification pending; P01 pending team inputs (deadline, domain OK, names, budget)

**Hardware (D-011):** Windows 11 x64 laptop, Intel Core Ultra 9 290HX Plus, 32 GB RAM, **NVIDIA RTX 5080 Laptop GPU** (Blackwell, sm_120 → needs a PyTorch CUDA 12.8+ build, torch ≥ 2.7). Primary device: CUDA with bf16 autocast. No `torch.compile` (Triton is not supported on native Windows). DataLoader `num_workers=0` (data is held in memory as tensors). All helper scripts are Python, not shell, so they run on Windows, Linux, and macOS. Released checkpoints must still run on **CPU** for the grader.

> Master design. Every Codex prompt reads it. Changes are recorded in `journal/DECISIONS.md`
> as new decisions that supersede old ones — never silently edited. §14 lists the v1.0 → v1.1 changes.

---

## 0. Rubric → design mapping

| Spec requirement | Our artifact | Verification |
|---|---|---|
| Fictional org, **one narrow department** | `data/kb/kb.json` (~120 measured + ~25 core facts) | KB validator |
| Consistent KB, no fact creep | Generation validator (numeric + name whitelists) | Reported residual inconsistency rate |
| Diverse doc types/styles, same facts reworded | 11 doc types × style cards; paraphrase as default | Corpus-level diversity stats; templated share of tokens reported |
| Corpus size **in tokens** | `reports/tables/corpus_stats.md` | Auto-generated after tokenization |
| Train/val/test separated | Document-level split, tokenizer fit on **train only**, leakage audit | `leakage_report.json` |
| Tokenizer: vocab, IDs, encode/decode | Byte-level BPE from scratch | Round-trip tests; vocab-size study |
| Vocab size → embedding & LM-head dims | Report §3 + param table | Param formula asserted in tests |
| Decoder-only Transformer (W_Q/W_K/W_V/W_O, causal mask, blocks, residual, norm, LM head) | `src/slm/model/` from scratch | 5 model tests incl. **causality** |
| Pretrain from random init, CE, optimizer, train/val monitoring, checkpoints | `slm.train.pretrain` | init loss ≈ ln V; curves; log-spaced checkpoints |
| Autoregressive generation; held-out eval; plausible text; familiar statements; relationships; success/failure examples | `slm.generate`, `slm.eval.*` | Perplexity, cloze, relationship probes, **KB-consistency of free generations**, gallery |
| SFT on QA; held-out Qs incl. unseen phrasings; **same eval set before & after** | `slm.train.sft`, frozen `qa_test.jsonl` | Eval-set SHA-256 recorded in both result files |
| One research question with evidence | Pre-registered frequency × diversity study (§8) | Mixed-effects regression, bootstrap CIs, 3 seeds |
| Two checkpoints + tokenizer + config, runnable without retraining | `release/{pretrained,sft}/` | **Fresh-clone CPU test** |
| Video, README, AI use, contributions, Q&A | `README.md`, `AI_USE.md`, `CONTRIBUTIONS.md`, `docs/QA_PREP.md`, `docs/DEMO_SCRIPT.md` | Final checklist |

---

## 1. Fictional domain

**Organization:** Aurelia Skyways, a fictional passenger airship line.
**Single department:** the **Companion Animal Travel Desk (CATD)** (pets traveling with passengers).
The pipeline is KB-driven; the domain can be swapped before P02 at no cost.

### 1.1 Entity types
| Entity type | Count | Attributes (one fact each) |
|---|---|---|
| Skyports (invented: Caldreth, Vellmar, Port Isolde, Thornwick, Merrowgate) | 5 | pet-lounge opening time, closing time, lounge manager, daily pet cap, relief-area gate |
| Airships (*Halcyon*, *Brightwater*, …) | 6 | pet-cabin capacity, cabin temperature, pet deck name |
| Species classes (cat, small dog, large dog, rabbit, bird, reptile) | 6 | fee, max weight, crate size |
| Policies | ~15 | booking deadline, health-certificate validity, max pets/passenger, min age, heat-embargo threshold, … |
| Staff roles | ~10 | name of director, compliance officer, … |
| Forms | ~8 | form code per process |
| Incidents & compensation | ~8 | amounts, claim deadline, reporting window |

### 1.2 KB rules (enforced by `validate_kb.py`)
- Facts are `(entity, attribute, value)` triples with **globally unique value strings** → exact exposure counting and contradiction detection.
- Each attribute type has ≥ 6 values (same-type distractors for ranking).
- Values within a type are kept to similar **token length** (checked after tokenizer exists; long outliers re-authored).
- Core facts (org, department, skyport list) appear freely and are excluded from the experiment.
- Each measured fact stores: `freq_bin`, `div_bin`, `sft_split`, `entity_id`, `attr_type`, `canonical_sentence`.

---

## 2. Dataset generation

```
kb.json → doc planner → LLM generator → validator → rebalancer → dedup → split → stats
```

### 2.1 Controlled exposure (experimental backbone)
Measured facts are randomly assigned, **stratified by attribute type and by entity** (each entity's facts are spread across cells to reduce entity-frequency confounding), to a 3 × 2 grid:

| | **Templated** (canonical sentence verbatim) | **Paraphrased** (new wording each time) |
|---|---|---|
| **Low** (~5 train docs) | 20 | 20 |
| **Mid** (~15 train docs) | 20 | 20 |
| **High** (~45 train docs) | 20 | 20 |

- Templated: only the *fact sentence* is fixed; the surrounding document is still diverse. We report the share of corpus tokens that are templated sentences (expected < 5%) to show the corpus as a whole follows the spec's diversity guidance. The templated condition is a deliberate, small contrast group.
- Paraphrased: the generator is forbidden from using the canonical sentence.
- **Manipulation check:** measured mention counts (string match) and phrasing diversity (distinct ±8-token context windows; mean pairwise Jaccard). Analysis uses **measured** exposure.
- Covariates recorded per fact: entity mention count, value token length, attribute type.
- Sizing calculator (P01) sets docs-per-cell so train ≈ 0.8–1.5M tokens.

### 2.2 Document types and style cards
Policy manual sections · employee emails · internal chat threads · incident reports · monthly ops reports · customer notices · help-center articles · training handbook pages · meeting minutes · complaint letters + replies · newsletter blurbs. Each doc gets a sampled style card (formality, author role, length, tone).
- **No "Question:/Answer:" formatted text** in pretraining (QA ability attributable to SFT).
- Doc length capped at ~450 tokens so a doc fits in one context window (§5).

### 2.3 Validation (reject → regenerate, ≤ 3 tries)
- Numbers must be in the KB numeric whitelist (+ small allowed set).
- Capitalized names must be in the entity whitelist (heuristic; flags logged).
- Each assigned fact's value present; templated facts' canonical sentence present verbatim.
- **Unplanned mentions** (a value appearing in a doc it wasn't assigned to) are counted, not rejected; they update measured exposure.
- LLM-judge contradiction audit on a 10% sample → reported residual error rate.

### 2.4 Splits and leakage control
- Document-level split **90 / 5 / 5**; val/test generated with held-out style cards.
- Val/test docs **paraphrase every fact** (no canonical sentences), so val/test loss isn't deflated by verbatim templates.
- Val/test mentions don't count toward exposure.
- **Tokenizer trained on the train split only.**
- Leakage audit: no val/test doc shares a 13-gram with train, apart from listed core-fact boilerplate.
- Generated corpus and all raw API responses are cached and committed (LLM output is non-deterministic, so the committed corpus *is* the dataset). Every API call is logged (prompt hash, tokens, cost); hard `budget_usd` cap.

---

## 3. Tokenizer
- **Byte-level BPE from scratch** (GPT-2-style regex pre-tokenization; merges learned on word-frequency counts; no UNK).
- Justification in report: char-level wastes context, word-level has OOV/huge vocab; BPE balances both.
- Specials: `<|pad|>`, `<|bos|>`, `<|eos|>`.
- Vocab-size study V ∈ {1024, 2048, 4096, 8192}: tokens/word, corpus tokens, embedding parameter share. Default **V = 4096**.
- Report: embedding matrix **V × d_model**; LM head **d_model → V** logits; tied weights share one V × d_model matrix (4096 × 384 = 1.57M params).
- Tests: corpus round-trip, determinism, special tokens. HF `tokenizers` cross-check is sanity only.

---

## 4. Model (from scratch)

| Hyperparameter | Default |
|---|---|
| n_layer / n_head / d_model / d_ff | 6 / 6 / 384 / 1536 (GELU) |
| context length | **512** (whole docs fit; see §5) |
| positions | learned absolute embeddings |
| norm | Pre-LayerNorm + final LN |
| dropout | 0.1 |
| weight tying | embedding ↔ LM head |
| params | ≈ 12.4M (asserted) |

- Explicit attention: separate `W_Q, W_K, W_V, W_O`; scores QKᵀ/√d_head; causal mask from a registered lower-triangular buffer; softmax; dropout; concat heads; W_O. `return_attn=True` for analysis. **No** `nn.MultiheadAttention`, **no** `F.scaled_dot_product_attention`, no pretrained weights.
- Init N(0, 0.02); residual projections scaled by 1/√(2·n_layer).
- **Tests:** shapes · **causality** (perturbing positions > t leaves logits ≤ t unchanged) · param formula = actual · init loss ≈ ln V · single-batch overfit.
- Final size confirmed by a short sizing check: 12M (6/6/384) vs ~25M (8/8/512), same token budget; pick by val loss and val-probe accuracy; logged as a decision. The RTX 5080 makes either size train in minutes per epoch, so model size is chosen for the experiment, not forced by hardware.

---

## 5. Pretraining
- **Document-aware packing:** whole documents (each ending in `<|eos|>`) are packed into 512-token sequences; **no document is split across sequences** (remainder padded, padding masked out of the loss). Each epoch is a shuffled pass over all sequences, so **every fact mention is seen exactly once per epoch** → exposure = mentions × epochs, exactly.
- AdamW (β 0.9/0.95; weight decay 0.1 on 2-D matrices only, tied embedding included, decision logged), peak LR 6e-4, 200-step warmup, cosine to 6e-5, grad-clip 1.0, ~16k tokens/step.
- Device auto-detect CUDA → MPS → CPU. On CUDA: bf16 autocast, TF32 matmuls enabled. `model.eval()` (dropout off) for all evaluation. Evaluation numbers reported from fp32 (bf16 only for training).
- Logs: train loss, val loss (fixed val set), LR, grad norm, tokens seen, epoch, throughput.
- **Log-spaced checkpoints** (~15). Optimizer state kept only for the latest (resume).
- **3 seeds** (model-init + data-order seeds; same corpus). The model is small, so 3 runs are cheap and give RQ1 variance. Seed 0 is the released model.
- Released pretrained checkpoint chosen by a **pre-registered rule** using *val* probes only (§6): the earliest checkpoint within 1 point of max val-probe ranking accuracy. Test probes are never used for selection.
- We expect val loss to rise while fact recall keeps improving; this is reported as a finding.

---

## 6. Generation and base evaluation
- Sampling: greedy, temperature, top-k, top-p; seeded.
- **LM metrics:** val loss / perplexity throughout; **test** loss/perplexity computed once, at the end, on the released checkpoints.
- **Cloze probes**, per measured fact:
  - 2 **val** templates (checkpoint selection only) + 3 **test** templates (all reported results).
  - Probe types: *canonical-frame* (prefix of the canonical sentence) and *novel-frame* (new wording; verified to share no 8-gram with train). For paraphrased facts both frames are novel to the model; this asymmetry is what RQ2 tests.
  - **Generative recall:** greedy continuation contains the normalized value.
  - **Ranking accuracy / MRR:** log p(value | prompt) vs all same-type values; summed and length-normalized log-probs both reported.
  - **Binding score (anti-frequency-prior control):** log p(v | correct entity) − mean log p(v | other entities of the same type). A fact counts as *stored* only if it ranks first **and** its binding score > 0. Without this, a high-exposure value can be "recalled" simply because the model outputs it for every entity.
- **Relationship probes** in both directions (e.g. skyport → manager and manager → skyport); a direction asymmetry is reported as an observation (cf. "reversal curse", Berglund et al. 2023).
- **Free-generation quality:** 200 samples from domain prompts → validator reports KB-consistency (% of numbers/names that are valid and correctly bound), repetition rate, distinct-n.
- Gallery `reports/samples/`: successes + failures, categorized (wrong fact, entity confusion, repetition loop, format drift).

---

## 7. Supervised fine-tuning (QA)

### 7.1 Data
- Format (identical for base and SFT evaluation): `Question: <q>\nAnswer: <one sentence containing the value><|eos|>`
- Per attribute type ~12 question templates (LLM-paraphrased, human-checked) → **7 train / 2 val / 3 test**.
- Facts split, stratified across all 6 cells: **SFT-train 40% / SFT-val 10% / held-out 50%** (E2 gets ~10 facts per cell).
- Loss on **answer tokens only**.

### 7.2 Frozen evaluation set `data/eval/qa_test.jsonl` (SHA-256 logged)
| Subset | Facts | Phrasings | Measures |
|---|---|---|---|
| **E1** | SFT-train facts | unseen test templates | generalization to new question wording |
| **E2** | held-out facts (never in SFT) | unseen test templates | extraction of pretraining knowledge |
| E0 (sanity) | SFT-train facts | train templates | SFT fit |

Base model: zero-shot and fixed 2-shot (examples from SFT-train facts) on the same file. Greedy decoding, stop at `<|eos|>` or newline, max 48 tokens.

### 7.3 Training
LR 1e-4, short warmup, ≤ 6 epochs, early stopping on SFT-val, checkpoint per epoch.
Forgetting check: LM val loss + cloze recall after SFT. Plan B if forgetting is severe: 10–20% pretraining replay (logged comparison).

### 7.4 Metrics
Exact value match, contains-match, ranking accuracy, error taxonomy: correct · right-type wrong-value · out-of-KB hallucination · format failure.

---

## 8. Research investigation (pre-registered)

**RQ:** *How do exposure frequency and paraphrase diversity during pretraining determine whether a small Transformer stores a fact, and does supervised fine-tuning make stored facts retrievable as answers to questions about facts it never saw in fine-tuning?*

| Part | Hypothesis | Evidence | Analysis |
|---|---|---|---|
| **A — storage** | H1: storage rate rises with log exposure. H2: at matched exposure, paraphrased facts generalize better to *novel-frame* probes; templated facts do better only on *canonical-frame* probes. | Cloze + binding across checkpoints × 3 seeds | Mixed-effects logistic regression: `stored ~ log(exposure) * diversity * frame + value_len + entity_freq + attr_type + (1 \| fact) + (1 \| template) + (1 \| seed)`; recall curves with bootstrap 95% CIs (resampling facts); per-fact acquisition step |
| **B — extraction** | H3: E2 QA accuracy after SFT ≫ base, but bounded by pre-SFT storage (P(correct \| stored) ≫ P(correct \| not stored)). H4: the extraction gain is larger for paraphrased facts (cf. Allen-Zhu & Li, *Physics of LMs 3.1*). | E1/E2 before vs after SFT | 2×2 tables (stored × QA-correct) per diversity condition; Fisher exact tests; McNemar for base vs SFT on the same items |

- `docs/PREREG.md` (hypotheses, metrics, selection rule, analysis code paths) is committed **before** the full pretraining run; its commit hash goes in the report.
- Null results are reported as results.
- **Supporting observation, not part of the RQ:** temperature sweep on the SFT model (accuracy vs distinct-n). One small figure; it supports the demo.
- **Stretch only:** attention inspection on recall prompts; 2-hop probes.
- **Accepted limitations:** single generator LLM; synthetic data; string-match exposure; small scale; templated vs paraphrased also differ in sentence-context variety (stated, not hidden).

---

## 9. Deliverables

| Deliverable | Location | Phase |
|---|---|---|
| Report 5–7 pp (IEEE double-column LaTeX) | `reports/paper/` | P10 |
| Dataset, KB, generation method, data card | `data/`, `docs/DATA_CARD.md` | P02 |
| Source code | `src/slm/`, `scripts/` | all |
| Pretrained + SFT checkpoints, tokenizer, config | `release/{pretrained,sft}/` (`model.pt` state-dict, `config.json`, `tokenizer.json`) | P09 |
| Curves, logs, samples, findings | `reports/figures/`, `runs/`, `reports/samples/` | P05–P09 |
| Demo video script (live run; ≥ 1 novel prompt, **verified novel by `scripts/check_novelty.py` on screen**) | `docs/DEMO_SCRIPT.md` | P10 |
| README: install, **pinned** `requirements.txt`, hardware, inference commands, examples | `README.md` | P09 |
| Slides + Q&A prep | `reports/slides/`, `docs/QA_PREP.md` | P10 |
| AI Use Statement | `AI_USE.md` (continuous) | all |
| Contributions | `CONTRIBUTIONS.md` | P10 |
| Reproducibility | `scripts/fresh_clone_test.py` (new venv, **CPU-only torch**, `torch.load(..., map_location="cpu", weights_only=True)`); README gives both CPU and CUDA install commands | P09 |

Inference without retraining:
`python -m slm.generate --model release/pretrained --prompt "..."` · `python -m slm.chat --model release/sft` (interactive QA).

---

## 10. Phase plan

| Phase | Content | Exit criteria |
|---|---|---|
| **P00** | Scaffold, env, tracking/journal, utilities | Tests pass; journal files exist |
| **P01** | KB + validator + bin assignment + sizing calculator + **PREREG draft** | KB valid; bins balanced on attr type and entity |
| **P02** | Corpus pipeline (plan → generate → validate → rebalance → dedup → split) + data card | Measured exposure within ±20% of target; leakage clean; templated-token share reported |
| **P03** | BPE from scratch (train split only) + vocab study + token stats + value-length check | Round-trip 100%; token counts reported |
| **P04** | Transformer + tests | 5 tests pass |
| **P05** | Doc-aware packing, pretraining loop, smoke run, sizing check, **PREREG frozen**, full 3-seed run | Curves; init loss ≈ ln V; checkpoints |
| **P06** | Probes (val/test, canonical/novel) + base eval across checkpoints + free-gen consistency + gallery | Per-checkpoint tables |
| **P07** | SFT data + frozen eval set | Hash recorded; splits verified disjoint |
| **P08** | SFT + pre/post QA eval + forgetting check | E0/E1/E2 for both models |
| **P09** | RQ analysis + figures; release bundle; README; fresh-clone test | Pre-registered analyses run; CPU inference from clean clone |
| **P10** | Report, slides, demo script, QA prep, AI use, contributions | Final checklist green |

---

## 11. Tracking and journal system
```
track.txt                 status, checklist, prompt log, key numbers, open issues, next step
journal/JOURNAL.md        one entry per prompt (goal, done, decisions, results, problems, next)
journal/DECISIONS.md      D-### (context, options, choice, rationale, evidence, status)
journal/EXPERIMENTS.md    E-### (run_id, config hash, commit, data hash, metrics, verdict)
journal/FAILURES.md       F-### (Plan A, what failed + evidence path, root cause, Plan B, lesson)
journal/prompts/Pxx.md    verbatim prompt + outcome
runs/<run_id>/            manifest.json, config.yaml, metrics.jsonl, stdout.log, checkpoints/, samples/
docs/PREREG.md            hypotheses + analysis plan, frozen before full training
AI_USE.md                 running AI-assistance log
```
**End of every prompt:** tests + lint → update `track.txt` → `JOURNAL.md` entry → D/E/F records → `AI_USE.md` → save prompt → `git commit -m "Pxx: …"` → print `REPORT BACK`.

---

## 12. Risks and fallbacks
| Risk | Plan B |
|---|---|
| LLM contradictions / new facts | Validator + regenerate; report residual rate |
| High-exposure facts not stored | More epochs → larger d_model → lower LR (each an F-record) |
| Everything stored (ceiling effect, no contrast) | Use early checkpoints for RQ1 (the acquisition curve still differentiates); lower bins for a regenerated low tier |
| Nothing in low bin stored (floor) | Acceptable as a result; acquisition curves for mid/high carry H1 |
| Overfitting | Dropout/weight decay ↑; pre-registered checkpoint rule |
| BPE too slow | Incremental pair counts; last resort HF tokenizers (logged) |
| PyTorch build lacks sm_120 (RTX 5080) | Install cu128 wheel; verify with a CUDA matmul at setup; fallback CPU/Colab, same code |
| bf16 numerical issues | fp32 training (12–25M params is still fast) |
| Windows path/encoding bugs | `pathlib` everywhere; UTF-8 explicit on all file I/O; tests run on Windows |
| Base can't follow QA format | 2-shot alongside zero-shot |
| SFT forgetting | Replay mixing |
| Budget overrun | Hard cap; stop and log |

---

## 13. Team roles
Data lead (KB, generation, data card) · Model lead (tokenizer, Transformer, tests) · Training/eval lead (pretraining, probes, curves) · SFT/research lead (SFT, RQ analysis, figures).
Everyone drills `docs/QA_PREP.md`: attention math, masking, √d_k scaling, parameter counting, perplexity, BPE, answer-only loss masking, binding score, why document-level splits.

---

## 14. Changelog v1.0 → v1.1 (adversarial review)
| # | Raised by | Flaw in v1.0 | Fix |
|---|---|---|---|
| 1 | Training engineer | Random 256-token windows split facts across boundaries and make exposure stochastic | Doc-aware packing at 512 ctx; exact once-per-epoch exposure |
| 2 | Training engineer | Same probes used for checkpoint selection and reporting (selection leakage) | Val vs test probe templates; pre-registered selection rule |
| 3 | Training engineer | Single seed too weak for acquisition claims; runs are cheap | 3 seeds required |
| 4 | Training engineer | Tokenizer fit on full corpus leaks val/test | Fit on train only |
| 5 | Researcher | **Frequency-prior confound**: a frequent value can be "recalled" for any entity | Binding score; *stored* = rank-1 AND binding > 0 |
| 6 | Researcher | Entity frequency and value token length confound bins | Stratified assignment by entity; covariates in regression |
| 7 | Researcher | 20 facts/cell + binary outcomes → weak inference with simple CIs | Mixed-effects logistic regression over facts × templates × seeds |
| 8 | Researcher | H2 untestable without canonical vs novel probe frames | Two probe frames |
| 9 | Researcher | E2 had only ~8 facts/cell | Fact split 40/10/50 |
| 10 | Researcher | Analysis could be fitted to results post hoc | `PREREG.md` frozen before full training |
| 11 | Professor | Templated condition seems to contradict "emphasize linguistic diversity" | Only fact sentences templated; report templated-token share (< 5%); justified as a control |
| 12 | Professor | Five sub-questions read as unfocused for 5–7 pages | One RQ, two parts; temperature demoted to supporting figure |
| 13 | Professor | "Plausible domain text" had no quantitative measure | KB-consistency of free generations via the validator |
| 14 | Professor | Val docs with verbatim templates deflate val loss | Val/test paraphrase all facts; test loss computed once at end |
| 15 | Professor | Demo "novel prompt" claim unverifiable; grader environment drift | `check_novelty.py` shown in video; pinned requirements; `weights_only` CPU loading |

## 15. Changelog v1.1 → v1.2 (hardware confirmed)
| # | Change | Reason |
|---|---|---|
| 1 | Target platform = Windows 11 + RTX 5080 Laptop (D-011) | Actual team hardware |
| 2 | CUDA cu128 build, bf16 autocast, TF32, no `torch.compile`, `num_workers=0` | Blackwell needs CUDA 12.8+; Triton unavailable on native Windows |
| 3 | Sizing check now 12M vs ~25M | GPU budget allows the larger option |
| 4 | Shell scripts → Python scripts; explicit UTF-8 I/O; `pathlib` | Cross-platform; grader may use any OS |
| 5 | Human runs env setup + git + long jobs; Codex writes code + runs tests via `.venv\Scripts\python.exe` (F-001) | Codex sandbox could not run Python or write `.git` in P00 |
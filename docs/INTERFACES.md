# Interfaces between the streams (I01)

Final contract at the integration commit. Owners: model (M), evaluation (E), analysis (A), data (D).
Everything here is enforced by code or by a test in `tests/integration/`; "decided" marks a rule that
is only documented.

## 1. Scorer (M -> E)

`slm.eval.interface.Scorer` is `score(prompt, continuation) -> float`, the **summed** natural-log
probability of the continuation. `DetailedScorer` adds `score_detailed(prompt, continuation) ->
(logprob, n_tokens)`. `slm.eval_adapter.ModelScorer` implements both, plus the batched
`score_details(pairs) -> list[(logprob, n_tokens)]` and `score_many(pairs)`.

- Boundary: prompt and continuation are tokenised separately; one trailing prompt space moves onto
  the continuation (M-D032). The harness always passes prompts without trailing whitespace and
  continuations as `" " + value` (E-D004), so the move rarely triggers.
- `norm_unit` of a probe row is `token` for a ModelScorer (it has `score_detailed`), `char` for a bare
  `Scorer`.
- Speed-up (I-D004): `slm.eval.probes.prefetch` calls `score_details` once per 6 x 6 group when the
  scorer offers it. Same values as one-by-one scoring (test), one batched call per group instead of 36 single calls.
- `init` = untrained model of a seed: `slm.integration.probing.untrained_model(cfg, seed)` draws the
  same initial weights as `train_run`.
- Test: `tests/integration/test_scorer_contract.py` runs the whole harness (120 facts x 5 probes)
  with a ModelScorer on a 1-layer model.

## 2. Probe table (E -> A)

Columns: `slm.eval.probes.TABLE_COLUMNS` (docs/EVAL_COLUMNS.md). One row per fact x prompt variant x
checkpoint x seed. Key `(fact_id, seed, checkpoint, split, prompt_variant)` is unique.

- `checkpoint`: **optimiser step** (int) of an `epoch_<EEE>.pt` file, read from the file's own
  metadata, or `init` (read as step 0, never primary). The primary checkpoint is the largest step of
  each seed (PREREG D4).
- `probe_frame`: `canonical` (KB canonical prefix) or `novel` (hand-written wording), constant within
  a `prompt_variant`. This is the "frame" of H2. The document-level `regime` is not in this table.
- **Probes per fact (real counts, measured from the table by `probe_counts`):**

  | split | canonical | novel | total | purpose |
  |---|---|---|---|---|
  | val | 1 (`val-canon`) | 1 (`val-n<k>`) | 2 | checkpoint monitoring only, never analysed |
  | test | 1 (`test-canon`) | 2 (`test-n<j>`, `test-n<k>`) | 3 | all reported results |

  The canonical prompt text is the same string in val and test; the 3 novel wordings are split 1 to
  val and 2 to test by a seeded shuffle (E-D014). So val and test share the canonical prefix.
- **Fact-level rule (decided, PREREG v3 section 4):** a fact is *stored* in a seed when it is stored
  on more than half of that seed's test probes at the seed's final checkpoint, and stored overall when
  that holds in more than half of the seeds. With the real count of 3 test probes this is "at least 2
  of 3" (and "at least half" equals "more than half" for every odd count). For an even count the rule
  is strict (2 of 4 is not stored); no real table has an even count. The count is **never a
  constant**: `analysis.aggregation.apply_rule` works on the share `mean(stored)` over whatever probes
  the table holds, and `integration.tables.stored_pretrain` passes the table's rows through it.
  `tests/integration/test_tables.py::test_fact_level_stored_uses_the_probe_count_in_the_table` checks
  n = 3, 4 and 5.
- Exposure covariates (optional, used when present): `train_mentions` (log3 enters `freq_c`),
  `entity_freq`, `value_len`. `build_analysis_tables` adds them from the exposure source (section 3).

## 3. Exposure, plan, KB, realized diversity (D -> A)

- KB `data/kb/kb.json`: `measured_facts[]` with `fact_id, entity_id, entity, attribute_id, value,
  canonical_sentence, canonical_prefix, freq_bin, div_bin, planned_mentions, sft_split
  (sft_train|sft_val|heldout), char_len`.
- Plan `data/plan/plan.jsonl`: one doc per line, `split`, `doc_type`, `fact_ids`, `modes`. Planned
  train mentions per fact equal the KB `planned_mentions` (test).
- **Exposure** (`train_mentions, entity_freq, value_len`), first available: `--exposure` CSV >
  string-match counts over the train files of `--manifest` (word-bounded value count; entity-name
  count; value tokens with `--tokenizer`) > planned counts from the plan (`exposure_source: planned`,
  used by the mock run). D-025 says measured equals planned; the corpus run will show it.
- **Realized diversity** `data/bank/realized_diversity.csv` as the bank stream writes it:
  `fact_id, mentions, n_distinct, n_reused, core_unique_share, mean_pair_skeleton_jaccard,
  mean_pair_core_jaccard, prefixes`. The analysis names differ; `normalize_realized_diversity` maps
  `core_unique_share -> core_uniqueness` and `mean_pair_skeleton_jaccard -> mean_pairwise_jaccard`
  (the analysis stream assumed skeleton-3-gram Jaccard; the bank's skeleton Jaccard is that quantity,
  to be confirmed by the bank owner, I-D007). `rdiv_z = z(1 - mean_pairwise_jaccard)`.

## 4. QA tables (M -> A) and the SFT-outcome contract

Evaluator output (`slm.sft_eval.TABLE_COLUMNS`), one row per question x variant x seed:
`fact_id, seed, eval_set (E0|E1|E2), question_id, prediction, gold, exact_value_match, contains_gold,
sentence_exact, truncated_prompt, gold_value, n_other_values, attribute_id, freq_bin, div_bin,
template_id, checkpoint (pretrained|sft), prompt_mode (zero_shot|2shot)`.

Analysis input `qa.csv` (`integration.tables.qa_table`):
`fact_id, seed, eval_set, question_id, model, exact_value_match, contains_gold, sentence_exact,
stored_pretrain, freq_bin, div_bin, sft_split, attribute_id, template_id`.

- `model`: (pretrained, zero_shot) -> `base_0shot`; (pretrained, 2shot) -> `base_2shot`; (sft,
  zero_shot) -> `sft`. Any other pair is refused.
- `exact_value_match` is the primary outcome (value present, no rival value of the same attribute);
  the analysis reads it through the alias `exact_value_match -> exact_match` (I-D005).
  `contains_gold` and `sentence_exact` are carried, unused by the confirmatory tests.
- `stored_pretrain`: the fact-level rule of section 2 for the **same seed**, from the test probes at
  that seed's final checkpoint (the checkpoint SFT starts from, `final_pretrain_checkpoint`).
- `sft_split`: `sft_train -> train`, `heldout -> heldout`; `sft_val` facts are not evaluated and are
  refused if they appear. Source: `--fact-split` JSON, else the KB's `sft_split`. The mock QA file was
  built from `data/sft_mock/fact_split.json`, which differs from the KB's split, hence the argument.
- Validated by `analysis.schema.validate_qa_table`: E0/E1 are train facts, E2 held-out facts, no fact
  in both, bins constant within a fact.
- Script: `scripts/build_analysis_tables.py` -> `probe.csv, qa.csv, realized_diversity.csv,
  tables_summary.json` (probe counts per fact, exposure source, checkpoints).

## 5. Report inputs (M, E, D -> A)

`slm.integration.report_inputs`, validated with the report builder's own `load_inputs`:

- `run_facts.json`: the 23 keys of `REQUIRED_RUN_FACTS`. From the KB (facts, cells), the model and
  train configs (layers, width, heads, context, vocab, lr, epochs), `count_parameters` of a real
  checkpoint, the token cache stats, the plan (document types), the corpus (document counts, templated
  share of train tokens) and git (`prereg_commit` = last commit touching docs/PREREG.md,
  `analysis_commit` = HEAD). `n_sweep_configs` is 0 when no sweep ran.
- `loss_curves.csv`: `seed, step, split, loss` from each seed's `loss.csv`.
- `samples.csv`: `category, prompt, completion, note`. `category` is `success: recalled fact` or one of
  `failure: wrong fact | entity confusion | repetition loop | format drift`, from `classify` (value
  present and no rival -> success; repeating trigram -> loop; a rival value -> confusion; empty ->
  drift; else wrong fact). Rows come from SFT answers on E2 and from greedy continuations of canonical
  prefixes at every saved pretraining checkpoint (note carries seed, step, epoch).

## 6. Split manifest (D -> M, E)

`docs/SPLIT_MANIFEST.md` (version 1). `data/corpus/manifest.json` arrives with the P02c corpus run
(branch main). Every consumer takes the path as an argument: `scripts/run_all_mock.py
--corpus-manifest`, `scripts/build_analysis_tables.py --manifest`. Test files are only read through
`slm.guard.open_split` (ledger line per read). Corpus rows on main are `{"doc_id", "split", "text",
"fact_ids", ...}` jsonl, which `parse_documents` reads.

## 7. Banner (A <- everyone)

`slm.analysis.banner` holds the label of the visible data-status mark: `SIMULATED` (simulator) or
`MOCK` (the mock pipeline). `--banner-label` on `run_analysis.py` and `build_report.py`. The banner is
off only with `--real`, which `run_all_mock.py` refuses.

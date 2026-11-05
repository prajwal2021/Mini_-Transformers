# Hypothesis-to-column map

Quotes are from `docs/DESIGN.md` section 8 (table "Research investigation") and section 6.
Probe-table columns are defined in `docs/EVAL_COLUMNS.md`. "QA table" = the (not yet built) per-item
E0/E1/E2 result table with `fact_id, model (base|sft), subset, correct`.

Statistical model quoted from DESIGN section 8:
`stored ~ log(exposure) * diversity * frame + value_len + entity_freq + attr_type + (1 | fact) + (1 | template) + (1 | seed)`

| | H1 | H2 | H3 | H4 |
|---|---|---|---|---|
| **DESIGN wording** | "H1: storage rate rises with log exposure." | "H2: at matched exposure, paraphrased facts generalize better to *novel-frame* probes; templated facts do better only on *canonical-frame* probes." | "H3: E2 QA accuracy after SFT ≫ base, but bounded by pre-SFT storage (P(correct \| stored) ≫ P(correct \| not stored))." | "H4: the extraction gain is larger for paraphrased facts (cf. Allen-Zhu & Li, *Physics of LMs 3.1*)." |
| **Outcome** | `stored` | `stored` | QA `correct` (E2), by `stored_fact` | QA `correct_sft - correct_base` (E2) |
| **Predictors** | log exposure (+ value_len, entity_freq, attr_type) | log exposure x `div_bin` x `probe_frame` | `model` (base/sft); `stored_fact` | `div_bin` x `model` |
| **Table columns** | `stored`, `fact_id`, `seed`, `checkpoint`, `attribute_id`, `prompt_variant`; MISSING: exposure, value_len, entity_freq | `stored`, `div_bin`, `probe_frame`, `fact_id`, `seed`, `prompt_variant`; MISSING: exposure | probe: `stored` at the selected base checkpoint; QA table: `correct`, `model`, `subset`; MISSING: `stored_fact` | `div_bin` (probe table or KB); QA table `correct`, `model` |
| **Filter** | `split == "test"`, all non-`init` checkpoints (acquisition curves); `init` rows give the chance level | `split == "test"`, `freq_bin`-matched or exposure-matched | probe rows: `split == "test"`, selected checkpoint (val-probe rule); QA rows: `subset == "E2"` (held-out facts, `fact_split.json` = `heldout`) | QA rows `subset == "E2"`, facts split by `div_bin` |
| **Gap** | Yes: "exposure" is not in the table | Yes: same, plus "matched exposure" | Yes: fact-level `stored` is undefined | Partly: needs the QA table |

## Gaps and proposed columns

1. **Exposure (H1, H2, and the model's covariates).** DESIGN defines exposure as measured train string-match count x epochs seen. The probe table only carries the design cell `freq_bin`. Proposed columns, joined by `fact_id` / `checkpoint`:
   - `train_mentions` (fact level; string-match count of the value in train documents),
   - `epochs_seen` (checkpoint level, float, since checkpoints are log-spaced) and `exposure = train_mentions * epochs_seen`,
   - `value_len_tokens` (tokenizer), `entity_mentions` (train count of the entity string).
   `attr_type` is `attribute_id` (or its family); `(1 | template)` is `prompt_variant`; `(1 | fact)` and `(1 | seed)` are `fact_id` and `seed`.
2. **Fact-level "stored" (H3).** DESIGN defines `stored` per probe, but H3 conditions on a fact being stored. The aggregation rule is not specified. Proposal to pre-register: `stored_fact` = stored on at least 2 of the 3 test probes (canonical, novel 2, novel 3) at the released pretrained checkpoint. `fact_level()` gives the share of probes stored, so any rule can be applied.
3. **QA table (H3, H4).** Not part of the probe table. It needs `fact_id`, `model`, `subset`, `correct` for the same items before and after SFT (McNemar). Join `stored_fact` and `div_bin` by `fact_id`; restrict to the held-out facts in `data/sft_mock/fact_split.json` (same split as `kb.json`).
4. **"Frame" for paraphrased facts (H2).** DESIGN notes that for paraphrased facts both frames are novel to the model. `probe_frame` is therefore a property of the prompt, and the H2 test is the `div_bin x probe_frame` interaction.
5. **Chance level.** `stored` has a nonzero chance rate (about P(rank 1) x P(binding > 0 | rank 1), roughly 0.1 for random scores). Report `null_stored_rate` and the `init` checkpoint alongside H1/H2 curves.
6. **Val vs test.** Val probes (`split == "val"`) are only for the checkpoint-selection rule; every hypothesis test filters to `split == "test"`.
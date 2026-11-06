# REPORT BACK R01 (taxonomy, ranking accuracy, exemplars, samples, README)

Branch `integration` (worktree `../slm-integration`), local only: nothing pushed, main untouched, no OpenAI call, `.env` never read. **Step 0 skipped on instruction: `docs/Term_Project.pdf` and `docs/SPEC_COMPLIANCE.md` were not in the repo, are not committed, and were never read by me.** The spec points relayed by the architect (6/R19, 7/risk 3, 9(f)/risk 5, 9(g), 9(d), 9(j)) are used as given; the journal says so (I-D026).

## 1. Checks
- pytest (whole repo, one invocation, no PYTHONPATH, from a background shell because it exceeds the 10 minute foreground limit; no code changed while it ran): `630 passed, 1 skipped, 7 warnings in 895.12s (0:14:55)` (R00: 515). The skip is main's `tests/test_p02c.py` (no `data/corpus` here). New: `test_r01_taxonomy.py` 97, `test_r01_samples.py` 7, `test_r01_readme.py` 5, `test_r01_exemplars.py` 4, `tests/integration/test_r01_tables.py` 2.
- ruff: `All checks passed!`
- git log --oneline -3 and git status --short: 

```
f15510f R01: taxonomy, ranking accuracy, exemplars, samples, README
2e4f058 R00: real-run prep
75ad334 I01: merge streams, interfaces, end-to-end mock
```
`git status --short`: empty after the commit. (The top hash is the commit before this block was added; the commit was amended once, local only, so the final hash differs.)

## 2. Taxonomy rules and ranking accuracy (`docs/ERROR_TAXONOMY.md`, `slm.sft_eval.taxonomy`, `slm.sft_eval.ranking`)
One class per prediction, decided in this order (first match wins):

| class | rule |
|---|---|
| `correct` | `exact_value_match`: gold value present, no other value of the attribute |
| `format_failure` | empty; or at least 4 words with one 1-3 word n-gram covering more than 50% of them; or (after the right-type check) no value-like string of the attribute's type |
| `right_type_wrong_value` | another value of the same attribute occurs (gold listed with a rival too), or a value-like string equals a KB value of the same value class (also of another attribute) |
| `out_of_kb_hallucination` | value-like strings of the right type exist and none is a KB value |

Value-like string per attribute type (value class; attributes):

| value class | attributes | value-like string |
|---|---|---|
| `person_name` | lounge manager, onboard handler | 2-3 capitalised words; sentence openers, entity names and other-class KB names dropped |
| `place_name` | pet deck name | same capitalised-name rule |
| `role_title` | procedure owner role | same capitalised-name rule |
| `code` | relief gate, form code, escalation extension | `[A-Z]{2,3}-\d{2,4}` |
| `time_of_day` | lounge opening time | `\d{1,2}:\d{2}` |
| `money` | pet fee, payout amount | `$` + digits |
| `count` | daily pet cap, quarantine capacity, cabin capacity | number, optional unit `pets` / `kennels` |
| `weight`, `dimension` | max combined weight, crate size | number, optional `kg` / `cm` |
| `duration` | min age (weeks), certificate validity (days), deadline (hours), claim window (days) | number, optional `weeks` / `days` / `hours` |
| `temperature` | cabin temperature | number, optional `degrees Celsius` |

A value of the wrong class only (a name for a fee) is a `format_failure` (extension of "no value-like token at all", I-D027). 97 tests (`tests/test_r01_taxonomy.py`): every class for each of the 20 attributes. `error_class` is a column of the QA table; `error_taxonomy.csv` (checkpoint x prompt_mode x eval_set x error_class, counts and shares) and `ranking_accuracy.csv` are written with the analysis tables.

**Ranking accuracy.** DESIGN section 6, verbatim: "Ranking accuracy / MRR: log p(value | prompt) vs all same-type values; summed and length-normalized log-probs both reported." Section 7.4 only says "ranking accuracy", so it is that definition under the QA prompt (with the 2-shot prefix for the 2-shot variant), over the 6 values of the question's attribute, scored with `ModelScorer` for the pretrained and the SFT checkpoint: `rank_value` (summed log-prob of `" " + value`, the DESIGN quantity), `rank_value_norm` (per token). **Added:** `rank_sentence` / `rank_sentence_norm` (the gold answer sentence with the value swapped), because SFT answers are sentences (I-D029). Rank = 1 + others scoring at least as high; accuracy = share of rank 1, MRR = mean 1/rank.

## 3. 2-shot exemplars (real KB) and disjointness
Re-picked from the real `data/sft/sft_val.jsonl` and `data/eval/qa_test.jsonl` (`scripts/choose_base_exemplars.py --sft-dir data/sft --eval-dir data/eval`, seed 0, two families, plain question): **F049** (`airship_onboard_handler_name`, Halcyon, "Maro Kest") and **F064** (`species_max_combined_weight`, rabbit, "18 kg"). The regenerated `configs/base_prompts.yaml` is byte-identical to the old one: the earlier "mock" SFT files were the real split (correction of I-D008 / the "mock-split ids" comment, I-D030). `tests/test_r01_exemplars.py` (4 tests, on the real files): both are `sft_val` in the KB, appear in the `sft_val` file with that question and answer, the file hash in the config matches, they are in no row of E0/E1/E2 (`check_exemplars_disjoint`), not in `sft_train`, no evaluation answer sentence occurs in the 2-shot prefix, and the clash check fires on a leaked fact. Deviation from DESIGN 7.2 logged (`DESIGN_CHANGES_v1.3.md` row 22 rewritten): SFT-train facts are the facts of E0 and E1, so an exemplar from them would put an evaluation answer in the prompt. Risk 3 (same questions, same template and decoding for base and SFT; unseen formulations) is covered by `assert_same_questions` in `compare_variants` and by the R00 assertions "E1/E2 templates unseen in SFT".

## 4. Sample generator on the mock run (`scripts/sample_checkpoints.py`, stage `samples`)
`runs/real_mock/samples/` (MOCK banner, toy corpus, seed 0, checkpoints init, 13, 26, 39, 65; 128.6 s). Files: `samples.csv` (all rows: columns `data_status, section, checkpoint, epoch, seed, prompt_id, prompt_kind, fact_id, freq_bin, div_bin, setting, sample_idx, prompt, completion, flag`), `samples_selected.csv`, `samples.md`; copies in `reports/integration/mock_samples_R01.md` and `mock_samples_selected_R01.csv`. Prompts: 10 fixed (5 canonical prefixes from 5 different freq x div cells, 3 novel wordings, 2 off-domain); greedy + 3 samples at t=0.8 per checkpoint; temperature sweep on the final checkpoint with 20 prompts.

**Selection (6 successes + 6 failures): the mock run has no success, so 0 + 6 were selected and the file says "Only 0 of 6 successes ... the selection is not padded".** A model trained for seconds on 200 documents never produces a correct value; the selection logic is tested on synthetic flags (6 + 6, one per checkpoint per round). The 6 failures:

| # | checkpoint | setting | prompt | completion | flag |
|---|---|---|---|---|---|
| 1 | init | t0.8 | The pet lounge at Port Isolde opens at | caeane Wenkailynkai... Skopelduncrezul ... | gibberish |
| 2 | 13 | t0.8 | The escalation extension for the check-in process is | Brimir at theve. | gibberish |
| 3 | 26 | t0.8 | Passengers with animals on the Moonwake board by way of the deck named | with great care, and then writes a short note, the water bowls on the night shift Skopho. | gibberish |
| 4 | 39 | t0.8 | The name of the person who runs the pet lounge at Caldreth: | . | gibberish |
| 5 | 65 | t0.8 | The maximum combined weight for a cat is | at Kojo. | gibberish |
| 6 | init | t0.8 | The onboard handler for the Starling is | Brimir Kojo Lemtorort Monjothafinfin ... | hallucinated |

Flag shares per checkpoint (value_correct / wrong_value / hallucinated / gibberish / off_domain_ok): init 0 / 0 / .30 / .53 / .17; 13: 0 / 0 / .07 / .72 / .20; 26: 0 / 0 / .03 / .78 / .20; 39 and 65: 0 / 0 / 0 / .80 / .20.

Temperature-sweep table format (final checkpoint; `n` = prompts x samples; shares of each flag; `distinct_2` = distinct bigrams / bigrams):

| setting | n | value_correct | wrong_value | hallucinated | gibberish | off_domain_ok | distinct_2 |
|---|---|---|---|---|---|---|---|
| greedy | 20 | 0.00 | 0.00 | 0.00 | 0.80 | 0.20 | 0.27 |
| t0.4 | 60 | 0.00 | 0.00 | 0.02 | 0.78 | 0.20 | 0.41 |
| t0.8 | 60 | 0.00 | 0.00 | 0.00 | 0.80 | 0.20 | 0.45 |
| t1.2 | 60 | 0.00 | 0.00 | 0.07 | 0.73 | 0.20 | 0.36 |
| t0.8+top-k40 | 60 | 0.00 | 0.00 | 0.02 | 0.78 | 0.20 | 0.30 |

(MOCK: meaningless numbers.) The report's `samples.csv` input now takes the selected samples (success and failure categories) next to the classified SFT answers; the mock report builds with 6 pages, MOCK banner. The dry-run ledger gained the `samples` use (4 lines in total: probes, QA test, samples, and the earlier QA run).

Mock QA error taxonomy and ranking (counts per 90 predictions = 30 questions x 3 seeds; MOCK): `reports/integration/mock_error_taxonomy_R01.csv`, `mock_ranking_accuracy_R01.csv`. All 810 predictions are `format_failure` or `out_of_kb_hallucination` (no `correct`, no `right_type_wrong_value`); ranking accuracy of the value rank is 0.11-0.33 against 1/6 = 0.17 chance, noise on toy models.

## 5. README (`docs/README.md`) commands
Installation: `python -m venv .venv`, `pip install -r bundle/requirements.txt` (CPU wheel); CUDA alternative `pip install torch --index-url https://download.pytorch.org/whl/cu128`; `pip install -e ".[dev]"` for training and tests. Hardware: inference on any CPU with about 1 GB RAM, GPU optional; training needs a CUDA GPU with about 5 GB. Commands (all run by `tests/test_r01_readme.py` on a mock bundle, CPU):

    python scripts/generate.py --bundle bundle/sft --prompt "Who manages the pet lounge at Caldreth?"
    python scripts/generate.py --bundle bundle/pretrained --prompt "The pet lounge at Caldreth opens at"
    python scripts/generate.py --bundle bundle/sft --prompt "What is the pet travel fee for a cat?" --temperature 0.7 --top-k 20 --seed 3
    python scripts/generate.py --bundle bundle/sft --interactive

Reproduction: `build_sft_data.py`, `run_real.py --list | --until sizing | --from freeze`, `run_real.py --config configs/real_mock.yaml` (dry run), `make_bundle.py --help`, `fresh_clone_test.py --bundle bundle`, `python -m pytest`. Required files: `bundle/{pretrained,sft}/{model.pt, tokenizer.json, model_config.json, bundle_manifest.json}` plus `requirements.txt` (two checkpoints, tokenizer and configuration, 9(d)/9(j)); no retraining or download at run time. The example inputs include two prompts that are not training examples (a reworded question and an off-KB question), for the demo (9(f)/risk 5). The test also checks every `scripts/`, `configs/`, `docs/`, `src/slm/` path named in backticks and that the stage list equals `run_real.STAGES`. Numbers that need the real run are `<...>` placeholders.

## 6. Decisions (I-D026 to I-D033), deviations, unsure
- I-D026 spec files absent; I-D027 taxonomy rules; I-D028 optional evaluator columns carried to `qa.csv`; I-D029 ranking definition; I-D030 exemplars; I-D031 sample generator; I-D032 `generate.py` fix; I-D033 README and its test. `DESIGN_CHANGES_v1.3.md` rows 43-46 added, row 22 rewritten.
- **Bug found by the README test (I-D032):** `scripts/generate.py` crashed with `UnicodeEncodeError` on a Windows cp1252 console when a model emitted bytes that decode to U+FFFD. stdout/stderr are now UTF-8 with `errors="replace"`. A real demo on Windows could have hit this.
- **Unsure:** (a) the capitalised-name rule can read a capitalised noun phrase ("Lounge Manager") as a hallucinated name; (b) a wrong-class value counts as a format failure, which differs from a literal reading of DESIGN; (c) the thresholds (4 words, 50%) are the task's, untuned on real output; (d) the ranking definition adds the sentence variant, which is my reading of "ranking accuracy" for an SFT model; (e) the sample prompts use canonical prefixes (shared by val and test probes) of KB facts, logged in the ledger, no selection depends on them; (f) the taxonomy, ranking and samples have run only on toy-model output, not on real model output; (g) the spec files were not read, so compliance with R19/risk 3/risk 5/9(g) rests on the architect's summary; (h) `README.md` at the root stays short and points to `docs/README.md`; (i) README numbers are placeholders until the real run.

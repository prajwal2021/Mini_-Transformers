# REPORT BACK M04

## 1. Checks
- pytest: model-stream without GPU `119 passed, 4 deselected in 61.04s`; GPU `4 passed, 119 deselected in 12.11s`; whole repo `325 passed in 255.20s (0:04:15)`. Slowest: existing P02 tests (27-44 s). Mine: `test_generate_error_messages` 11 s, `test_fresh_clone_script_runs_both_bundles` 11 s (marked `slow`, runs with `--no-install`), the rest under 8 s. Nothing of mine exceeds 30 s.
- ruff: `All checks passed!` (six new files carry a file-level `# ruff: noqa: E501`; pyproject.toml is untouched).
- git log --oneline -3 and git status --short: in the message.

## 2. QA metric
DESIGN 7.4: "Metrics: Exact value match, contains-match, ranking accuracy, error taxonomy: correct · right-type wrong-value · out-of-KB hallucination · format failure."
Implemented (M-D043): primary `exact_value_match` = the prediction contains the gold value and none of the other five values of that attribute (from data/kb/kb.json). Secondary: `contains_gold` (no exclusivity) and `sentence_exact` (the old strict sentence equality). A value occurs only when not glued to a word character, so "$85" is not found in "$850" (this also tightens `contains_gold`, which M03 computed as a plain substring). Extra column `n_other_values`.

## 3. Exemplars
`configs/base_prompts.yaml` (seed 0, `scripts/choose_base_exemplars.py`): F049 (airship_onboard_handler_name) "I need the onboard handler for the Halcyon." and F064 (species_max_combined_weight) "I need the maximum combined weight for a rabbit.", both sft_val facts, so in none of E0/E1/E2 (E0/E1 = sft_train facts, E2 = heldout facts). Tests: `test_exemplar_facts_are_sft_val_only` (fixture copy of fact_split.json), `test_disjointness_check_raises_on_overlap`, `test_disjoint_from_the_real_evaluation_file` (reads ../slm-eval qa_test.jsonl when present), and the dry run calls `check_exemplars_disjoint` on all 660 real rows. DESIGN 7.2 says the 2-shot examples come from SFT-train facts; I followed the M04 task instead (M-D044). These ids are mock-split ids.

## 4. generate.py
One-shot:

    python scripts/generate.py --bundle bundle/sft --prompt "Who manages the pet lounge at Vellmar?"
    python scripts/generate.py --bundle bundle/pretrained --prompt "The pet lounge at Vellmar opens at"

Interactive: `python scripts/generate.py --bundle bundle/sft --interactive` (`:set temperature 0.7`, `:set top_k 20`, `:set seed 3`, `:set max_new_tokens 64`, `:set format raw`, `:quit`). Other options: `--max-new-tokens --temperature --top-k --seed --device cpu|cuda --format raw|qa`.
Verbatim from the mock bundle (CPU, CUDA hidden):

    $ C:\Users\prajsrin\Documents\NNP\.venv\Scripts\python.exe scripts/generate.py --bundle C:\Users\prajsrin\Documents\slm-model\runs\m04_dry_run\bundle\sft --prompt Who manages the pet lounge at Vellmar? --device cpu
    loaded: sft (seed 1, 12,417,024 params) from C:\Users\prajsrin\Documents\slm-model\runs\m04_dry_run\bundle\sft on cpu
    settings: max_new_tokens=48 temperature=0.0 top_k=None seed=0 format=qa
    prompt: Who manages the pet lounge at Vellmar?
    completion: The pets is.
    
    $ C:\Users\prajsrin\Documents\NNP\.venv\Scripts\python.exe scripts/generate.py --bundle C:\Users\prajsrin\Documents\slm-model\runs\m04_dry_run\bundle\pretrained --prompt The pet lounge at Vellmar opens at --device cpu
    loaded: pretrained (seed 1, 12,417,024 params) from C:\Users\prajsrin\Documents\slm-model\runs\m04_dry_run\bundle\pretrained on cpu
    settings: max_new_tokens=48 temperature=0.0 top_k=None seed=0 format=raw
    prompt: The pet lounge at Vellmar opens at
    completion:  map before the doors open for map before the doors open for Hol at at Mir. The manager explains the doors open for nobody has to wait for Hol has to wait for Hol at at at Tor It takes 57 minutes.
    
    The desk
    

Mock-model answers are nonsense; the point is that both load and run.

## 5. Bundle and fresh clone
Build command: `C:\Users\prajsrin\Documents\NNP\.venv\Scripts\python.exe scripts/make_bundle.py --pretrain-run C:\Users\prajsrin\Documents\slm-model\runs\m04_dry_run\pretrain --sft-run C:\Users\prajsrin\Documents\slm-model\runs\m04_dry_run\sft --tokenizer C:\Users\prajsrin\Documents\slm-model\runs\m04_dry_run\tokenizer.json --out C:\Users\prajsrin\Documents\slm-model\runs\m04_dry_run\bundle` -> total bundle size: 94.9 MiB.

| file | bytes |
|---|---|
| pretrained\bundle_manifest.json | 1,168 |
| pretrained\model.pt | 49,695,523 |
| pretrained\model_config.json | 185 |
| pretrained\tokenizer.json | 47,738 |
| README_BUNDLE.md | 1,056 |
| requirements.txt | 233 |
| sft\bundle_manifest.json | 1,156 |
| sft\model.pt | 49,695,523 |
| sft\model_config.json | 185 |
| sft\tokenizer.json | 47,738 |

Seed rule (M-D047): lowest pretraining validation loss at the final checkpoint among seeds that also have an SFT run (seed 1 here); never test results.
Fresh-clone test (worktree copy of the source, new venv, `pip install -r bundle/requirements.txt` over the network, CUDA hidden): ok = True; venv + install 174.81 s; whole test 187.3 s; both models loaded, outputs non-empty and identical on repeat; prompts not in the mock corpus. Installing from the network worked, so no fallback was needed.

Before/after on the mock (60 questions per set, 2 seeds, same questions and decoding; all zero, as expected for a model trained on 200 mock documents):

| checkpoint | prompt_mode | eval_set | n | exact_value_match | contains_gold | sentence_exact |
|---|---|---|---|---|---|---|
| pretrained | 2shot | E0 | 120 | 0.0 | 0.0 | 0.0 |
| pretrained | 2shot | E1 | 120 | 0.0 | 0.0 | 0.0 |
| pretrained | 2shot | E2 | 120 | 0.0 | 0.0 | 0.0 |
| pretrained | zero_shot | E0 | 120 | 0.0 | 0.0 | 0.0 |
| pretrained | zero_shot | E1 | 120 | 0.0 | 0.0 | 0.0 |
| pretrained | zero_shot | E2 | 120 | 0.0 | 0.0 | 0.0 |
| sft | zero_shot | E0 | 120 | 0.0 | 0.0 | 0.0 |
| sft | zero_shot | E1 | 120 | 0.0 | 0.0 | 0.0 |
| sft | zero_shot | E2 | 120 | 0.0 | 0.0 | 0.0 |

Dry-run phase seconds: tokenizer_train 0.2; pretrain_2_seeds 11.62; sft_2_seeds 7.8; eval_seed0_3_variants 66.22; eval_seed1_3_variants 70.23; make_bundle 2.83; fresh_clone_test 205.86.

## 6. Decisions, deviations, doubts
M-D043 to M-D050 (journal/model/DECISIONS_M.md).
- Exemplars deviate from DESIGN 7.2 on purpose (M-D044).
- The release seed is chosen by validation loss, not by the val-probe rule of DESIGN section 5, which needs the probe stream (M-D047).
- `scripts/m03_dry_run.py` was removed (its API changed); `reports/model/m03_dry_run.json` stays as history, and its `exact_match` is the old sentence equality.
- `docs/Term_Project.pdf` and `docs/SPEC_COMPLIANCE.md` do not exist in this worktree; README section list comes from the task text.
- There is still no SFT training command-line script; SFT runs through `slm.sft_train.run_sft_seeds`.
- Bundle models are fp32 (47.4 MiB each); half precision was not tried.
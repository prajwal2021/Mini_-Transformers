# Aurelia Skyways Companion Animal Travel Desk: a small Transformer language model

A decoder-only Transformer written from scratch (attention, causal and document masks, byte-level
BPE tokenizer, training loop), pretrained on a synthetic corpus about a fictional airship line's pet
travel desk, then fine-tuned for question answering. Design and rationale: `docs/DESIGN.md`.
This file explains how to **run the trained model without retraining it**, and how to reproduce the
training. Numbers that only exist after the real run are marked `<...>`.

## 1. Installation
Python 3.10 or newer. Running the model needs only `torch`, `regex` and `PyYAML` (pinned in
`bundle/requirements.txt`).

    python -m venv .venv
    .venv\Scripts\activate            # Linux/macOS: source .venv/bin/activate
    pip install -r bundle/requirements.txt          # CPU-only torch wheel

For a CUDA GPU instead (RTX 5080 / Blackwell needs the cu128 build), install torch first:

    pip install torch --index-url https://download.pytorch.org/whl/cu128
    pip install regex PyYAML

Training, the analysis and the tests additionally need the package and its development extras:

    pip install -e ".[dev]"

## 2. Hardware
- **Running the model (inference):** a CPU is enough; no GPU needed. Any x86-64 or ARM machine with
  about 1 GB of free RAM (12.4M parameters, about 50 MB per model); about 2 s per answer on a laptop CPU.
  A GPU is optional (`--device cuda`).
- **Training:** an NVIDIA CUDA GPU with about 5 GB of memory (bf16 autocast, batch of 32 x 512 tokens,
  12M parameters; the optional 25M sizing run needs more). We used Windows 11, Intel Core Ultra 9
  290HX Plus, 32 GB RAM, NVIDIA RTX 5080 Laptop GPU, CUDA 12.8 build of PyTorch. Pretraining
  `<N>` tokens x `<E>` epochs takes `<minutes>` per seed; SFT `<minutes>`.

## 3. Required files
Two checkpoints (after pretraining and after SFT) with the tokenizer and the model configuration
needed to load both are in the release bundle, built by `scripts/make_bundle.py`:

    bundle/
      pretrained/  model.pt  tokenizer.json  model_config.json  bundle_manifest.json
      sft/         model.pt  tokenizer.json  model_config.json  bundle_manifest.json
      requirements.txt  README_BUNDLE.md

`model.pt` holds weights only (`torch.load(..., weights_only=True)`). `bundle_manifest.json` has the
sha256 of every file; `scripts/generate.py` refuses a bundle whose files do not match it. Nothing
else (no run directory, corpus or training config) is needed to run the model, and nothing is
retrained or downloaded at run time.

## 4. Inference
One answer from the fine-tuned model (the prompt is wrapped as `Question: <prompt>\nAnswer:`):

    python scripts/generate.py --bundle bundle/sft --prompt "Who manages the pet lounge at Caldreth?"

Continue free text with the pretrained model:

    python scripts/generate.py --bundle bundle/pretrained --prompt "The pet lounge at Caldreth opens at"

Sampling instead of greedy decoding (seeded, so a run repeats exactly):

    python scripts/generate.py --bundle bundle/sft --prompt "What is the pet travel fee for a cat?" --temperature 0.7 --top-k 20 --seed 3

Interactive session (the model stays loaded; `:set temperature 0.7`, `:set top_k 20`, `:set seed 3`,
`:set max_new_tokens 64`, `:set format raw`, `:quit`):

    python scripts/generate.py --bundle bundle/sft --interactive

Options: `--max-new-tokens N` (48) `--temperature T` (0 = greedy) `--top-k K` `--seed S`
`--device cpu|cuda` (cpu) `--format raw|qa`. The first output line says which model was loaded
(`loaded: sft ...` or `loaded: pretrained ...`), then the settings, the prompt and the completion.

## 5. Example inputs
SFT model (questions like the evaluation questions):
- `Who manages the pet lounge at Caldreth?`
- `What is the pet travel fee for a cat?`
- `How long does the health certificate for a rabbit remain valid?`

Pretrained model (statement openings):
- `The pet lounge at Caldreth opens at`
- `The booking process requires form`

Prompts that are **not** among the training examples (for a demonstration of generalisation, not
recall): reword a question (`Could you tell me the person in charge of the pet lounge at Vellmar?`)
or ask about something that is not in the knowledge base (`Who looks after the cargo pets on the
Zephyrine?`). The second gets a fluent but invented answer, because the model has no source for it.
Failures are expected and are documented next to the successes in the report
(`docs/ERROR_TAXONOMY.md`, `reports/tables/samples.md`).

## 6. Reproducing the training (stages of `scripts/run_real.py`)
The whole pipeline is one resumable orchestrator driven by `configs/real.yaml`; each stage writes
`runs/real/stages/<name>.json` and is skipped on a rerun when it is already ok.

    python scripts/build_sft_data.py                      # data/sft + data/eval from the KB split (once)
    python scripts/run_real.py --list                     # stage status
    python scripts/run_real.py --until sizing             # tokenizer, token cache, sweep, 12M vs 25M check
    python scripts/run_real.py --from freeze              # freeze (PREREG hash + git commit), final 3 seeds, probes, SFT, QA eval, samples, analysis, report
    python scripts/make_bundle.py --help                  # pick the seed by validation loss, write bundle/

Stages in order: `tokenizer`, `token_cache`, `sweep`, `sizing`, `freeze`, `pretrain`, `probes`,
`sft`, `qa_eval`, `samples`, `tables`, `analysis`, `report`. A dry run on a toy corpus (all stages,
MOCK banner, nothing is a result):

    python scripts/run_real.py --config configs/real_mock.yaml

Checks:

    python scripts/fresh_clone_test.py --bundle bundle    # clean copy + new venv + both models on CPU
    python -m pytest                                      # tests (GPU tests skip without CUDA)

`scripts/freeze_prereg.py` is the same freeze as a stand-alone command (it refuses once any test
probe, QA test file or ledger entry exists). Test data are read only through `slm.guard.open_split` (or `record_test_use`), and every read is
logged in `reports/test_access_log.jsonl` (`docs/HPARAM_PROTOCOL.md` section 6).
Results: `<corpus tokens>`, `<val loss>`, `<probe stored rate>`, `<E0/E1/E2 value match, base vs SFT>`.

## 7. What is in this repo
| path | content |
|---|---|
| `src/slm/model/`, `train/`, `tokenizer/`, `data_loading/` | the Transformer, training loop, BPE tokenizer, packing and token cache |
| `src/slm/sft/`, `sft_train/`, `sft_eval/` | SFT data and templates, SFT training, QA evaluation, error taxonomy, ranking accuracy |
| `src/slm/eval/`, `eval_adapter/` | cloze probes (stored / binding / permutation null) and the model scorer |
| `src/slm/analysis/`, `report/` | pre-registered analysis (GEE, Holm) and the report builder |
| `src/slm/integration/` | table builders, report inputs, checkpoint samples, PREREG freeze |
| `src/slm/bundle/`, `generation/` | release bundle (hash-checked) and decoding |
| `src/slm/data/` and the generator scripts in `scripts/` | corpus generation from the knowledge base (data stream) |
| `scripts/` | command-line entry points (`generate.py`, `run_real.py`, `make_bundle.py`, ...) |
| `configs/` | model, training, SFT, orchestrator and base-prompt settings |
| `data/kb/`, `data/sft/`, `data/eval/` | the knowledge base, SFT files and the frozen QA evaluation file (with sha256 manifest) |
| `docs/` | `DESIGN.md`, `PREREG.md`, `INTERFACES.md`, `ERROR_TAXONOMY.md`, `DESIGN_CHANGES_v1.3.md`, ... |
| `journal/`, `AI_USE.md`, `track.txt` | decisions, failures, AI-use disclosure and progress |
| `reports/` | tables, figures, samples and report-back files |
| `tests/` | the test suite |

## 8. Limitations
`<fill in from the report>`: synthetic corpus, one generator LLM, small scale, string-match exposure.

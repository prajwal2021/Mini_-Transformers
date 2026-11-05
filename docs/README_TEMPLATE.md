# Aurelia Skyways Companion Animal Travel Desk: a small Transformer language model

> Template for the final README. Commands are real and tested on the mock bundle; `<...>` marks
> numbers that only exist after the real corpus and the real runs. The course spec PDF
> (`docs/Term_Project.pdf`) is not in the repository, so the section list follows the request for
> section 9(g) as relayed: installation, hardware, commands for inference, required files, example
> inputs.

A decoder-only Transformer written from scratch (attention, causal and document masks, byte-level
BPE tokenizer, training loop), pretrained on a synthetic corpus about a fictional airship line's pet
travel desk, then fine-tuned on question answering. Details: `docs/DESIGN.md`.

## 1. Installation
Python 3.10 or newer. The demo needs only `torch`, `regex` and `PyYAML` (pinned in
`bundle/requirements.txt`). CPU is enough.

    python -m venv .venv
    .venv\Scripts\activate            # Linux/macOS: source .venv/bin/activate
    pip install -r bundle/requirements.txt          # CPU-only torch wheel

For a CUDA GPU instead (RTX 5080 / Blackwell needs the cu128 build), install torch first:

    pip install torch --index-url https://download.pytorch.org/whl/cu128
    pip install regex PyYAML
    # training and analysis additionally need: pip install -e .[dev]

## 2. Hardware
- Demo / inference: any x86-64 or ARM CPU, about 1 GB of free RAM (12.4M parameters, 50 MB per
  model); about 2 s per answer on a laptop CPU.
- Training (what we used): Windows 11, Intel Core Ultra 9 290HX Plus, 32 GB RAM, NVIDIA RTX 5080
  Laptop GPU, CUDA 12.8 build of PyTorch, bf16 autocast, no `torch.compile`.
- Pretraining `<N>` tokens x `<E>` epochs: `<minutes>` per seed. SFT: `<minutes>`.

## 3. Required files
A release bundle, built by `scripts/make_bundle.py`:

    bundle/
      pretrained/  model.pt  tokenizer.json  model_config.json  bundle_manifest.json
      sft/         model.pt  tokenizer.json  model_config.json  bundle_manifest.json
      requirements.txt  README_BUNDLE.md

`model.pt` holds weights only (`torch.load(..., weights_only=True)`). `bundle_manifest.json` has the
sha256 of every file; `generate.py` refuses a bundle whose files do not match it. Nothing else
(no run directory, corpus or config) is needed to run the demo.

## 4. Inference
One answer from the fine-tuned model (the prompt is wrapped as `Question: <prompt>\nAnswer:`):

    python scripts/generate.py --bundle bundle/sft --prompt "Who manages the pet lounge at Caldreth?"

Continue free text with the pretrained model:

    python scripts/generate.py --bundle bundle/pretrained --prompt "The pet lounge at Caldreth opens at"

Interactive session (model stays loaded; `:set temperature 0.7`, `:set top_k 20`, `:set seed 3`,
`:set max_new_tokens 64`, `:set format raw`, `:quit`):

    python scripts/generate.py --bundle bundle/sft --interactive

Options: `--max-new-tokens N` (48) `--temperature T` (0 = greedy) `--top-k K` `--seed S`
`--device cpu|cuda` (cpu) `--format raw|qa`. The first output line says which model was loaded
(`loaded: sft ...` or `loaded: pretrained ...`).

## 5. Example inputs
SFT model (questions of the kinds in the QA set):
- `Who manages the pet lounge at Caldreth?`
- `What is the pet travel fee for a cat?`
- `How long does the health certificate for a rabbit remain valid?`

Pretrained model (statement openings):
- `The pet lounge at Caldreth opens at`
- `The booking process requires form`

A prompt about something that is not in the knowledge base (e.g. `Who looks after the cargo pets on
the Zephyrine?`) gets a fluent but invented answer: the model has no source for it.

## 6. Reproducing the results
    python scripts/fresh_clone_test.py --bundle bundle          # clean copy + new venv + both models
    python -m pytest                                            # tests (GPU tests skip without CUDA)
    python scripts/sweep.py --help                              # hyper-parameter sweep (val loss only)
    python scripts/pretrain.py --help                           # pretraining, 3 seeds
    python scripts/make_bundle.py --help                        # choose seed by validation loss, write bundle

Results: `<corpus tokens>`, `<val loss>`, `<probe stored rate>`, `<E0/E1/E2 value match, base vs SFT>`.
Test data is read only through `slm.guard.open_split` and every read is logged in
`reports/test_access_log.jsonl` (`docs/HPARAM_PROTOCOL.md` section 6).

## 7. Limitations
`<fill in from the report>`: synthetic corpus, one generator LLM, small scale, string-match exposure.
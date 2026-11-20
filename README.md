# A small Transformer language model for a fictional airship pet-travel desk

A 12.4-million-parameter decoder-only Transformer, written from scratch (attention, masks, byte-level BPE tokenizer, training loop), pretrained on a
synthetic corpus about the Companion Animal Travel Desk of a fictional airship line, then fine-tuned to answer questions. The project is a
pre-registered study: *does a small model store a fact more reliably when the fact appeared more often, or in more varied wording?* Design:
`docs/DESIGN.md`; pre-registration: `docs/PREREG.md`; the final report is `reports/integration/r11/report.pdf` (7 pages; R11 text corrections
of the R08 report that is in `bundle/report/`; the numbers are the same).

**What the study found (details and caveats in the report).** Storage rises with exposure (H1, supported) and with paraphrase diversity on novel
probes (H2, supported). Fine-tuning does not make *held-out* facts extractable (H3, not supported). Two things to know before trusting any number:
H1/H2 first came out with the wrong sign because of a coding bug, found and fixed after the results were seen (original and corrected numbers are
both in the report appendix); and the design confounds exposure with value length (see the limitations).

## 1. Run the trained models (no training, no GPU, no internet at run time)

You need Python 3.10 or newer and the **release bundle** (`bundle.zip`, about 150 MB, shipped with the submission). The checkpoints are not in git
because of their size.

    python -m venv .venv
    .venv\Scripts\activate            # Linux/macOS: source .venv/bin/activate
    unzip bundle.zip                  # Windows: Expand-Archive bundle.zip .   (creates ./bundle)
    pip install -r bundle/requirements.txt          # CPU-only torch, regex, PyYAML

Check the files, then ask a question:

    python scripts/make_bundle.py --verify bundle
    python scripts/generate.py --bundle bundle/sft_fixed3 --qa "Who manages the pet lounge at Vellmar?"
    python scripts/generate.py --bundle bundle/sft_early_stopped --qa "Who manages the pet lounge at Vellmar?"
    python scripts/generate.py --bundle bundle/pretrained --prompt "Passengers who arrive with a nervous cat should first" --max-new-tokens 40
    python scripts/generate.py --bundle-root bundle --compare --qa "What would it cost to bring my cat on the airship?"
    python scripts/generate.py --bundle bundle/sft_fixed3 --interactive

Example output of the first command (greedy, deterministic):

    loaded: sft [fixed3_posthoc] (seed 0, 12,417,024 params) from bundle\sft_fixed3 on cpu
    settings: max_new_tokens=48 temperature=0.0 top_k=None seed=0 format=qa
    question: Who manages the pet lounge at Vellmar?
    completion: The lounge manager at Vellmar is Miren Quill.

**Novel prompts** (written for this README; no 5-word sequence of either occurs in the training split), with their real greedy outputs:

    python scripts/generate.py --bundle bundle/pretrained --prompt "A traveller arriving late at Thornwick with an anxious rabbit should" --max-new-tokens 30
    completion:  be calm and orderly. The Companion Animal Travel Desk of Aurelia Skyways closed with steady service, and a reassuring pace for every traveler and every pet.

    python scripts/generate.py --bundle bundle/sft_early_stopped --qa "Can I bring two hamsters in one carrier on a night crossing to Merrowgate?"
    completion: The relief-area gate at Ashenfell is RG-615.

The pretrained model continues in the corpus style; the SFT model answers in the trained answer format but with an unrelated fact (a typical failure).

**Submission package.** In the submission, the same checkpoints are in `d_models/` (`d_models/pretrained`, `d_models/sft_early_stopped`,
`d_models/sft_fixed3`); pass those directories to `--bundle`, or `--bundle-root d_models --compare`.

Flags of `scripts/generate.py`: `--bundle DIR` (one model) or `--bundle-root DIR --compare` (all models on one question); `--prompt TEXT` (continue
raw text) or `--qa QUESTION` (wraps it as `Question: <q>` + newline + `Answer:` and stops at the end-of-answer token or newline; works with any
model) or `--interactive` (REPL: `:set temperature 0.7`, `:set seed 3`, `:set max_new_tokens 64`, `:quit`); `--max-new-tokens N` (48);
`--temperature T` (0 = greedy, deterministic); `--top-k K`; `--seed S` (sampling is repeatable); `--device cpu|cuda` (default cpu); `--format raw|qa`.

**Which model is which** (`bundle/CHECKPOINTS.md`). All are seed 0.
- `pretrained`: pretrained from scratch, epoch 30 (the checkpoint the primary analysis uses).
- `sft_early_stopped`: the **pre-specified primary** SFT. Early stopping on a 12-fact validation set picked epoch 1, so it is lightly trained.
- `sft_fixed3`: a **post-hoc secondary** SFT (3 epochs, no early stopping), added after the results were seen. It answers the fine-tuning facts much better.

Neither SFT model answers questions about facts it never saw in fine-tuning (see `docs/demo_transcript.md` for real outputs, successes and failures).

### Hardware and speed
- **Inference:** any CPU with about 1 GB of free RAM; a GPU is optional (`--device cuda`). Measured on the machine that did the work (Intel Core Ultra 9
  290HX Plus, Windows 11, CPU only, 24 threads; 4 to 8 threads were as fast, 2 threads about twice as slow): loading a model takes 0.2 s; a typical 12-token answer takes 0.05 to 0.07 s
  and 48 tokens of free text about 0.2 s (140 to 240 tokens per second, depending on the thread count). A whole command takes 2 to 4 s, almost all of it
  Python importing PyTorch. A slower laptop CPU will be several times slower than these numbers; they are not guaranteed for other machines.
- **Training:** an NVIDIA GPU with about 5 GB of memory. Done on an RTX 5080 Laptop GPU (CUDA 12.8 build of PyTorch): a 60-epoch pretraining run of one
  seed took 6 to 7.5 minutes; the 7-run budget sweep took 42 minutes; the QA evaluation of three seeds took 11 minutes.

### Required files
`bundle/pretrained`, `bundle/sft_early_stopped`, `bundle/sft_fixed3` (each: `model.pt` weights only, `tokenizer.json`, `model_config.json`,
`bundle_manifest.json` with sha256), `bundle/MANIFEST.json` (sha256 of every file), `bundle/requirements.txt`. Nothing else is needed to run a model
(no corpus, no config, no API key); `generate.py` refuses a model whose hash does not match.

## 2. Reproduce the tables from the saved artifacts (no retraining)

    pip install -e .                          # the full package: pandas, statsmodels, scipy, matplotlib
    python scripts/reproduce_tables.py --bundle bundle

This re-runs the pre-registered analysis (GEE, Holm) on `bundle/reproduce/probe.csv` and `qa.csv` and checks every estimate, interval and p-value
against `bundle/results/analysis_family_corrected.csv` (about 10 seconds). `bundle/results/` also holds the original (sign-bugged) table, the sensitivity
tables, the value-length check, the fixed-3-epoch results and the stored rate by epoch. `bundle/report/report.pdf` is the R08 report; the final R11 text is `reports/integration/r11/report.pdf`.

## 3. Reproduce the training (needs a CUDA GPU; the data are in the repository)

    pip install -e ".[dev]"
    python scripts/run_real.py --list                 # stages and their status
    python scripts/run_real.py --config configs/real.yaml --until sizing   # tokenizer, token cache, budget sweep, size check
    python scripts/run_real.py --config configs/real.yaml --from freeze    # freeze, 3 seeds, probes, SFT, QA evaluation, tables, report
    python scripts/make_bundle.py --release --out bundle                   # rebuild the bundle from runs/real

`configs/real.yaml` drives the stages; each stage writes `runs/real/stages/<name>.json` and is skipped on a rerun when it is ok. The corpus
(`data/corpus/`), knowledge base (`data/kb/`) and SFT/QA files (`data/sft/`, `data/eval/`) are in the repository, so no OpenAI call is needed. Test
data are read only through the ledgered path (`reports/test_access_log.jsonl`, 5 entries: probes, QA evaluation, checkpoint samples, the post-hoc fixed-3 SFT evaluation, and a read-only demo-prompt overlap check). The post-hoc SFT is `python scripts/posthoc_sft_fixed3.py
train` then `eval`. Tests: `python -m pytest` and `ruff check .` (GPU tests skip without CUDA).

## 4. Repository map
| path | content |
|---|---|
| `src/slm/model/`, `train/`, `tokenizer/`, `data_loading/` | Transformer, training loop, byte-level BPE, packing and token cache |
| `src/slm/sft/`, `sft_train/`, `sft_eval/` | SFT data, SFT training, QA evaluation, error taxonomy, ranking accuracy |
| `src/slm/eval/`, `eval_adapter/` | cloze probes (stored, binding, permutation null) |
| `src/slm/analysis/`, `report/` | the pre-registered analysis and the report builder |
| `src/slm/integration/`, `bundle/`, `generation/` | table builders, PREREG freeze, release bundle, decoding |
| `src/slm/data/`, `scripts/run_corpus.py` | corpus generation from the knowledge base (OpenAI models; not needed to run anything) |
| `scripts/` | command-line entry points (`generate.py`, `run_real.py`, `make_bundle.py`, `reproduce_tables.py`, ...) |
| `configs/` | model, training, SFT, orchestrator and base-prompt settings |
| `data/kb/`, `data/corpus/`, `data/sft/`, `data/eval/` | knowledge base, corpus splits with manifest, SFT files, QA evaluation file |
| `docs/` | `DESIGN.md`, `PREREG.md`, `DESIGN_CHANGES_v1.3.md`, `DATA_CARD.md`, `ERROR_TAXONOMY.md`, `demo_transcript.md`, statements |
| `journal/`, `track.txt`, `AI_USE.md` | decisions, failures, AI-use log and progress |
| `reports/` | report-back files, result tables and the test-access ledger |
| `tests/` | the test suite |

## 5. Statements
`docs/AI_USE_STATEMENT.md` (how AI was used), `docs/CONTRIBUTIONS.md`, `docs/PROFESSOR_NOTES.md` (deviations from the simplest reading of the
spec), `docs/DEMO_SHOTLIST.md` (the demo video script).

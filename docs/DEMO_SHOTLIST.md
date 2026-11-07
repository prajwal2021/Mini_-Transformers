# Demo shot list (about 4 minutes)

Record the terminal at the repository root with the bundle in `bundle/` (unzip `bundle.zip` there). Every command below runs on the CPU. The outputs
shown in `docs/demo_transcript.md` are real outputs of exactly these commands; yours will match them (greedy decoding is deterministic, the sampled
runs use `--seed 0`). Say the words in quotes in your own voice; the bullets are the facts to hit.

| time | what you show | command | what to say |
|---|---|---|---|
| 0:00 | the question and the model | `python scripts/make_bundle.py --verify bundle` | "A 12-million-parameter Transformer I built from scratch, trained on a synthetic corpus about a fictional airship pet-travel desk. This checks the release files against their hashes." (prints `MANIFEST OK`) |
| 0:20 | what is in the bundle | `type bundle\CHECKPOINTS.md` (Linux/macOS: `cat bundle/CHECKPOINTS.md`) | "Three models, all seed 0: the pretrained model, the SFT model that was pre-specified as the primary one, and a post-hoc SFT I added after seeing results. I will say which is which each time." |
| 0:45 | pretrained model, free text | `python scripts/generate.py --bundle bundle/pretrained --prompt "Passengers who arrive with a nervous cat should first" --max-new-tokens 40` | "The pretrained model continues text in the house style of the corpus: fluent, on topic, but it does not answer questions." |
| 1:15 | same prompt, sampled | `python scripts/generate.py --bundle bundle/pretrained --prompt "Passengers who arrive with a nervous cat should first" --max-new-tokens 40 --temperature 0.8 --seed 0` | "Temperature 0.8 gives more varied text; the seed makes it repeatable." |
| 1:40 | SUCCESS: a fact it was fine-tuned on | `python scripts/generate.py --bundle bundle/sft_fixed3 --qa "Who manages the pet lounge at Vellmar?"` | "This exact question was in the SFT training data. The fixed-3-epoch SFT answers it: Miren Quill. That is recall of a trained fact." |
| 2:05 | the pre-specified SFT on the same question | `python scripts/generate.py --bundle bundle/sft_early_stopped --qa "Who manages the pet lounge at Vellmar?"` | "The pre-specified primary SFT used early stopping on a 12-fact validation set, which picked epoch 1, so this model is under-trained and answers about the wrong attribute. I report both, and label the second SFT as post-hoc." |
| 2:35 | FAILURE: a novel question, all three models | `python scripts/generate.py --bundle-root bundle --compare --qa "What would it cost to bring my cat on the airship?"` | "A question that is not in any training, validation or test file. The pretrained model rambles; both SFT models give a fluent sentence about the wrong attribute. This is the main finding: the SFT models learn the answer format and the trained facts, not retrieval of new ones. H3, held-out extraction, is not supported." |
| 3:10 | FAILURE: an invented answer | `python scripts/generate.py --bundle bundle/sft_fixed3 --qa "Who looks after the cargo pets on the Zephyrine?"` | "The Zephyrine is not in the knowledge base. The model still answers with a confident, invented fact: it was never trained to say it does not know." |
| 3:35 | the results, one line | open `bundle/report/report.pdf` at the findings table | "Pre-registered analysis: stored rate rises with exposure (H1) and with paraphrase diversity on novel probes (H2), both supported; H3 not. I found and fixed a sign bug after seeing results; the original numbers are in the appendix." |
| 3:55 | close | | "Everything runs from the bundle with no retraining; the README has the commands, and the report has the limitations: a memorization regime, one model size, three seeds, and a value-length confound in the design." |

Notes for the recording
- If a command is slow on the first run, that is Python importing PyTorch (about 2 to 3 seconds); the model itself answers in well under a second on a CPU.
- Keep the greedy commands as the main takes; show a sampled command at most once.
- The 4 minutes leave about 15 seconds of slack per step; drop the 1:15 step first if you run long.
- Do not claim more than the transcript shows. The only success in the demo is a trained-fact answer; the novel questions fail.

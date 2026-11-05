# What a small language model stores: exposure frequency and paraphrase diversity

Course project report. Companion Animal Travel Desk knowledge base, decoder-only Transformer, pre-registered study.

> **SIMULATED DATA - NOT RESULTS.** Every number, table and figure in this document was generated from simulated inputs to test the report pipeline. None of it is a result of the study.

## Dataset

We built a fictional organisation with one narrow department, the pet-travel desk of an airship line, and a knowledge base of 120 measured facts about it. Each fact is an (entity, attribute, value) triple whose value string is globally unique, so exposure can be counted by string match and contradictions can be detected. The facts are assigned to 6 design cells, three exposure bins crossed with two diversity conditions, with 20 facts per cell. In the templated condition the canonical fact sentence is used verbatim; in the paraphrased condition each mention is worded differently.

A generator model wrote 2,407 training documents of 11 document types (1,000,000 tokens in total), and validation and test sets of 120 and 120 documents. Templated fact sentences are 3.2% of corpus tokens, so the corpus as a whole is diverse and the templated condition is a small, deliberate contrast group. Exposure is measured as the string-match count of each value in the training documents.

## Research question

How do exposure frequency and paraphrase diversity during pretraining determine whether a small Transformer stores a fact, and does supervised fine-tuning make stored facts retrievable as answers to questions about facts it never saw in fine-tuning? A fact counts as stored only if its value ranks first among the same-attribute values and its binding score, the log-probability of the value given the right entity minus its mean given the other entities, is above zero. The binding score removes the frequency prior: a common value cannot count as recalled just because the model emits it for every entity.

We pre-registered four hypotheses. **H1:** storage rises with log exposure. **H2:** at matched exposure, paraphrased facts generalise better to novel-frame probes and templated facts do better only on canonical-frame probes, tested as the diversity by frame interaction. **H3:** held-out question accuracy after fine-tuning (E2) exceeds the base model but is bounded by pre-fine-tuning storage. **H4:** the extraction gain is larger for paraphrased facts. H1 to H3 are confirmatory with a Holm correction; H4 is secondary and reported as an effect with its interval only, because its power at this sample size is low.

## Architecture

The model is a decoder-only Transformer with 6 layers, model width 384, 6 attention heads, a context of 512 tokens and a byte-pair vocabulary of 8,192 tokens, giving 12,000,000 parameters. It is trained from random initialisation with next-token cross-entropy and runs on a CPU for the released checkpoints.

## Training procedure

Pretraining uses 3 seeds on the same corpus. The number of epochs, 4, was chosen on validation loss in a sweep of 6 configurations, with a learning rate of 0.0006. The final checkpoint of each seed is the single checkpoint that is analysed; it is also the starting point of fine-tuning and the source of each fact's pre-fine-tuning storage status. Fine-tuning on question-answer pairs runs for 3 epochs at a learning rate of 0.0001 with the loss on answer tokens only. At the final step the training loss is 1.11 and the validation loss 1.67, a validation perplexity of 5.3.

![Figure 1. Training and validation loss for each seed.](figures/loss_curves.png)

## Evaluation

Storage is probed with cloze prompts in two frames, the canonical sentence prefix and a novel wording, using test templates only; validation templates are used for model selection and never for results. Extraction is measured on three question sets: E0 (fine-tuning facts, training phrasings), E1 (fine-tuning facts, unseen phrasings) and E2 (held-out facts never seen in fine-tuning), for the base model with zero and two examples and for the fine-tuned model.

H1 and H2 use a logistic model for stored with fact clusters (a GEE, because three seeds cannot support a random-effect variance), with exposure, diversity, frame, their interactions, covariates and template terms. H3 and H4 use fact-level outcomes on E2: a fact is stored, or correct, when that holds for at least two of its three probes or phrasings and in a majority of seeds. H3 combines an exact McNemar test (base against fine-tuned) with a Fisher exact test (stored against correct); H4 is a permutation test on the per-fact gain. Sensitivity analyses vary the aggregation rule, the exposure coding, the template terms, the estimator, the outcome definition and the diversity measure.

![Figure 2. E0/E1/E2 accuracy for the base models and the SFT model.](figures/eval_before_after.png)

## Findings

The analysed checkpoint is step 20,000, with 120 facts and 3 seeds. Overall the stored rate across design cells is 0.47.

- H1: estimate 0.69 log-odds per tripling of exposure, 95% CI 0.41 to 0.96; Holm-adjusted p 8.11e-06; outcome: supported.
- H2: estimate 0.19 log-odds for the diversity x frame interaction (paraphrased advantage, novel minus canonical), 95% CI -0.33 to 0.71; Holm-adjusted p 0.474; outcome: not supported; inconclusive.
- H3: estimate 0.30 risk difference for the SFT gain on E2 (SFT minus 2-shot base), 95% CI 0.18 to 0.42; Holm-adjusted p 1.53e-05; outcome: supported.
- H4: estimate 0.13 risk difference for the gain difference (paraphrased minus templated), 95% CI -0.07 to 0.33; secondary hypothesis, effect and CI only (no significance claim).

**Table 1.** Hypotheses H1-H4. H1-H3 are confirmatory (Holm adjusted); H4 is secondary (effect and CI only). Estimates are log-odds (H1, H2) or risk differences (H3, H4).

| hypothesis | label | estimate | ci_low | ci_high | p_holm | status |
|---|---|---|---|---|---|---|
| H1 | storage rises with log exposure (per tripling) | 0.688 | 0.413 | 0.963 | 8.11e-06 | supported |
| H2 | diversity x frame (paraphrased advantage, novel - canonical) | 0.189 | -0.332 | 0.71 | 0.474 | not supported; inconclusive |
| H3 | E2 gain after SFT, bounded by pre-SFT storage (IUT) | 0.3 | 0.183 | 0.417 | 1.53e-05 | supported |
| H4 | extraction gain larger for paraphrased (secondary) | 0.133 | -0.0667 | 0.333 | n/a | secondary: effect and CI only |

For H2 the effect of diversity within each frame, paraphrased minus templated at mid exposure, is 0.78 log-odds on canonical probes (95% CI 0.26 to 1.30) and 0.97 on novel probes (95% CI 0.48 to 1.47). On the risk-difference scale, high against low exposure changes the stored rate by 0.29 (95% CI 0.17 to 0.40).

![Figure 3. Stored rate by exposure bin, diversity condition and probe frame at the final checkpoint (95% fact-bootstrap CI).](figures/stored_rate_by_cell.png)

![Figure 4. Stored rate across checkpoints by exposure, diversity and probe frame.](figures/learning_curves.png)

On E2 the fine-tuned model reaches 0.36 exact-match accuracy against 0.08 for the two-shot base model and 0.04 for the zero-shot base; on the fine-tuning facts it reaches 0.80 (E0) and 0.64 (E1). Among the 60 held-out facts, the difference in correctness between stored and not-stored facts is 0.62 (95% CI 0.43 to 0.81).

**Table 2.** E2 held-out facts by diversity condition: base (2-shot) and SFT fact-level accuracy, gain and the exact McNemar test.

| div_bin | n_facts | acc_base | acc_sft | gain | mcnemar_p |
|---|---|---|---|---|---|
| templated | 30 | 0 | 0.233 | 0.233 | 0.0156 |
| paraphrased | 30 | 0 | 0.367 | 0.367 | 0.000977 |

Replacing the nominal diversity label by the realized diversity of the generated mentions changes the H2 estimate from 0.19 to 0.49 log-odds per nominal contrast. A manipulation that only partly separates the conditions biases the nominal estimate toward zero, so the nominal H2 is a lower bound on the effect of realized diversity. The full set of sensitivity analyses follows; none of them is part of the confirmatory family.

**Table 3.** Pre-registered sensitivity analyses (none is part of the Holm family).

| analysis | hypothesis | estimate | ci_low | ci_high |
|---|---|---|---|---|
| primary (GEE, log3 mentions if present, with tem | H1 | 0.688 | 0.413 | 0.963 |
| primary (GEE, log3 mentions if present, with tem | H2 | 0.189 | -0.332 | 0.71 |
| exposure coding: bins | H1 | 0.707 | 0.422 | 0.993 |
| exposure coding: bins | H2 | 0.173 | -0.347 | 0.694 |
| exposure coding: measured | H1 | 0.688 | 0.413 | 0.963 |
| exposure coding: measured | H2 | 0.189 | -0.332 | 0.71 |
| without prompt_variant terms | H1 | 0.687 | 0.412 | 0.962 |
| without prompt_variant terms | H2 | 0.188 | -0.333 | 0.71 |
| Bayesian mixed logit (fact, fact x seed; point e | H1 | 0.848 | n/a | n/a |
| Bayesian mixed logit (fact, fact x seed; point e | H2 | 0.22 | n/a | n/a |
| outcome: stored_tokennorm | H1 | 0.477 | 0.232 | 0.723 |
| outcome: stored_tokennorm | H2 | 0.0948 | -0.421 | 0.61 |
| realized diversity replaces div_bin | H2 (scaled to nominal contrast) | 0.489 | 0.0848 | 0.893 |
| realized diversity replaces div_bin | H1 | 0.707 | 0.433 | 0.981 |
| div_bin and realized diversity together | H2 (nominal term given realized) | -0.933 | -1.82 | -0.0458 |
| div_bin and realized diversity together | H2 (realized term, per SD) | 0.682 | 0.261 | 1.1 |
| fact-level rule: any | H3 (gain) | 0.267 | 0.133 | 0.4 |
| fact-level rule: any | H4 | 0.267 | 0 | 0.567 |
| fact-level rule: majority (primary) | H3 (gain) | 0.3 | 0.2 | 0.409 |
| fact-level rule: majority (primary) | H4 | 0.133 | -0.0667 | 0.333 |
| fact-level rule: all | H3 (gain) | 0.0167 | 0 | 0.05 |
| fact-level rule: all | H4 | 0.0333 | 0 | 0.1 |
| comparator: base_0shot (secondary) | H3 (gain) | 0.3 | 0.2 | 0.409 |
| comparator: base_0shot (secondary) | H4 | 0.133 | -0.0667 | 0.333 |

## Generated samples

The gallery contains 4 successes and 4 failures, grouped by the failure categories wrong fact, entity confusion, repetition loop and format drift.

**Table 4.** Generated-text samples: successes and failures.

| category | prompt | completion | note |
|---|---|---|---|
| success: recalled fact | The pet lounge at Skyport A opens at | [SIM] 06:30 and closes at 21:00. | value matches the KB |
| success: recalled fact | Question: Who is the compliance officer? Answer: | [SIM] The compliance officer is Person B. | exact match after SFT |
| success: consistent generation | Booking a pet on an airship requires | [SIM] a health certificate issued within the validity window. | numbers and names valid |
| success: novel phrasing | How many pets may one passenger bring? | [SIM] Each passenger may bring at most two pets. | novel-frame probe, rank 1 |
| failure: wrong fact | The pet lounge at Skyport C opens at | [SIM] 07:00 and closes at 21:00. | right type, wrong value |
| failure: entity confusion | The lounge manager at Skyport B is | [SIM] Person D, who also manages Skyport A. | value of another entity |
| failure: repetition loop | Cabin temperature on Airship E is | [SIM] 20 degrees. 20 degrees. 20 degrees. 20 degrees. | loops until max length |
| failure: format drift | Question: What is the pet fee for a rabbit? Answer: | [SIM] Fee schedule, section two, see also section two. | no value produced |

## Limitations

The corpus comes from a single generator model and is synthetic, the study is small, and exposure is a string-match count, so a value stated in an unusual way is missed. Templated and paraphrased facts differ in sentence-context variety as well as in wording; we state this rather than hide it. Fact-level outcomes discard item-level information to keep facts independent, and the McNemar and Fisher tests are conservative at this size. E2 has 60 facts, so H4 is secondary and every H3 and H4 interval is wide. The analysis was fixed in a pre-registration before any result was seen; the pre-registration commit is TBD (simulated) and the analysis code commit is TBD (simulated).

# What a small language model stores: exposure frequency and paraphrase diversity

Course project report. Companion Animal Travel Desk knowledge base, decoder-only Transformer, pre-registered study.

{{banner_notice}}

## Dataset

We built a fictional organisation with one narrow department, the pet-travel desk of an airship line, and a knowledge base of {{run.n_measured_facts}} measured facts about it. Each fact is an (entity, attribute, value) triple whose value string is globally unique, so exposure can be counted by string match and contradictions can be detected. The facts are assigned to {{run.n_cells}} design cells, three exposure bins crossed with two diversity conditions, with {{run.facts_per_cell}} facts per cell. In the templated condition the canonical fact sentence is used verbatim; in the paraphrased condition each mention is worded differently.

A generator model wrote {{run.n_train_docs}} training documents of {{run.n_doc_types}} document types ({{run.train_tokens}} tokens in total), and validation and test sets of {{run.n_val_docs}} and {{run.n_test_docs}} documents. Templated fact sentences are {{run.templated_token_share_pct:.1f}}% of corpus tokens, so the corpus as a whole is diverse and the templated condition is a small, deliberate contrast group. Exposure is measured as the string-match count of each value in the training documents.

## Research question

How do exposure frequency and paraphrase diversity during pretraining determine whether a small Transformer stores a fact, and does supervised fine-tuning make stored facts retrievable as answers to questions about facts it never saw in fine-tuning? A fact counts as stored only if its value ranks first among the same-attribute values and its binding score, the log-probability of the value given the right entity minus its mean given the other entities, is above zero. The binding score removes the frequency prior: a common value cannot count as recalled just because the model emits it for every entity.

We pre-registered four hypotheses. **H1:** storage rises with log exposure. **H2:** at matched exposure, paraphrased facts generalise better to novel-frame probes and templated facts do better only on canonical-frame probes, tested as the diversity by frame interaction. **H3:** held-out question accuracy after fine-tuning (E2) exceeds the base model but is bounded by pre-fine-tuning storage. **H4:** the extraction gain is larger for paraphrased facts. H1 to H3 are confirmatory with a Holm correction; H4 is secondary and reported as an effect with its interval only, because its power at this sample size is low.

## Architecture

The model is a decoder-only Transformer with {{run.n_layers}} layers, model width {{run.d_model}}, {{run.n_heads}} attention heads, a context of {{run.context_len}} tokens and a byte-pair vocabulary of {{run.vocab_size}} tokens, giving {{run.n_params}} parameters. It is trained from random initialisation with next-token cross-entropy and runs on a CPU for the released checkpoints.

## Training procedure

Pretraining uses {{run.n_seeds}} seeds on the same corpus. The number of epochs, {{run.epochs_chosen}}, was chosen on validation loss in a sweep of {{run.n_sweep_configs}} configurations, with a learning rate of {{run.lr}}. The final checkpoint of each seed is the single checkpoint that is analysed; it is also the starting point of fine-tuning and the source of each fact's pre-fine-tuning storage status. Fine-tuning on question-answer pairs runs for {{run.sft_epochs}} epochs at a learning rate of {{run.sft_lr}} with the loss on answer tokens only. At the final step the training loss is {{loss.train_final:.2f}} and the validation loss {{loss.val_final:.2f}}, a validation perplexity of {{loss.val_perplexity:.1f}}.

{{figure:loss_curves}}

## Evaluation

Storage is probed with cloze prompts in two frames, the canonical sentence prefix and a novel wording, using test templates only; validation templates are used for model selection and never for results. Extraction is measured on three question sets: E0 (fine-tuning facts, training phrasings), E1 (fine-tuning facts, unseen phrasings) and E2 (held-out facts never seen in fine-tuning), for the base model with zero and two examples and for the fine-tuned model.

H1 and H2 use a logistic model for stored with fact clusters (a GEE, because three seeds cannot support a random-effect variance), with exposure, diversity, frame, their interactions, covariates and template terms. H3 and H4 use fact-level outcomes on E2: a fact is stored, or correct, when that holds for at least two of its three probes or phrasings and in a majority of seeds. H3 combines an exact McNemar test (base against fine-tuned) with a Fisher exact test (stored against correct); H4 is a permutation test on the per-fact gain. Sensitivity analyses vary the aggregation rule, the exposure coding, the template terms, the estimator, the outcome definition and the diversity measure.

{{figure:eval_before_after}}

## Findings

The analysed checkpoint is step {{meta.checkpoint}}, with {{meta.n_facts}} facts and {{meta.n_seeds}} seeds. Overall the stored rate across design cells is {{stored_rate_overall:.2f}}.

- {{sentence.H1}}
- {{sentence.H2}}
- {{sentence.H3}}
- {{sentence.H4}}

{{table:family}}

For H2 the effect of diversity within each frame, paraphrased minus templated at mid exposure, is {{simple.canonical.div_effect_log_odds:.2f}} log-odds on canonical probes ({{ci_level}}% CI {{simple.canonical.ci_low:.2f}} to {{simple.canonical.ci_high:.2f}}) and {{simple.novel.div_effect_log_odds:.2f}} on novel probes ({{ci_level}}% CI {{simple.novel.ci_low:.2f}} to {{simple.novel.ci_high:.2f}}). On the risk-difference scale, high against low exposure changes the stored rate by {{rd.H1.risk_difference:.2f}} ({{ci_level}}% CI {{rd.H1.ci_low:.2f}} to {{rd.H1.ci_high:.2f}}).

{{figure:stored_rate_by_cell}}

{{figure:learning_curves}}

On E2 the fine-tuned model reaches {{acc.E2.sft.accuracy:.2f}} exact-match accuracy against {{acc.E2.base_2shot.accuracy:.2f}} for the two-shot base model and {{acc.E2.base_0shot.accuracy:.2f}} for the zero-shot base; on the fine-tuning facts it reaches {{acc.E0.sft.accuracy:.2f}} (E0) and {{acc.E1.sft.accuracy:.2f}} (E1). Among the {{n_e2_facts}} held-out facts, the difference in correctness between stored and not-stored facts is {{H3b.estimate:.2f}} ({{ci_level}}% CI {{H3b.ci_low:.2f}} to {{H3b.ci_high:.2f}}).

{{table:per_condition}}

Replacing the nominal diversity label by the realized diversity of the generated mentions changes the H2 estimate from {{sens.primary_H2.estimate:.2f}} to {{sens.realized_H2.estimate:.2f}} log-odds per nominal contrast. A manipulation that only partly separates the conditions biases the nominal estimate toward zero, so the nominal H2 is a lower bound on the effect of realized diversity. The full set of sensitivity analyses follows; none of them is part of the confirmatory family.

{{table:sensitivity}}

## Generated samples

The gallery contains {{n_success}} successes and {{n_failure}} failures, grouped by the failure categories wrong fact, entity confusion, repetition loop and format drift.

{{table:samples}}

## Limitations

The corpus comes from a single generator model and is synthetic, the study is small, and exposure is a string-match count, so a value stated in an unusual way is missed. Templated and paraphrased facts differ in sentence-context variety as well as in wording; we state this rather than hide it. Fact-level outcomes discard item-level information to keep facts independent, and the McNemar and Fisher tests are conservative at this size. E2 has {{n_e2_facts}} facts, so H4 is secondary and every H3 and H4 interval is wide. The analysis was fixed in a pre-registration before any result was seen; the pre-registration commit is {{run.prereg_commit}} and the analysis code commit is {{run.analysis_commit}}.

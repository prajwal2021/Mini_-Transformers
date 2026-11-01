# Preregistration draft v0 (not frozen)

Frozen at: `<commit hash>, <date>` = TBD

This draft will be frozen at P05, before the full three-seed training run.

## Research question

How do exposure frequency and paraphrase diversity during pretraining determine whether a small Transformer stores a fact, and does supervised fine-tuning make stored facts retrievable as answers to questions about facts it never saw in fine-tuning?

## Hypotheses

- **H1:** Storage rate rises with log exposure.
- **H2:** At matched exposure, paraphrased facts generalize better to novel-frame probes; templated facts do better only on canonical-frame probes.
- **H3:** E2 QA accuracy after SFT is much greater than base, but bounded by pre-SFT storage: P(correct | stored) is much greater than P(correct | not stored).
- **H4:** The extraction gain is larger for paraphrased facts.

## Operational definitions

- **Measured exposure:** string-match count in train documents multiplied by the number of epochs seen.
- **Stored:** rank-1 among the six same-attribute values and binding score greater than zero.
- **Canonical frame:** a probe using the beginning of the canonical sentence.
- **Novel frame:** a held-out wording verified not to share an eight-gram with training text.
- **Validation probes:** two templates per fact used for checkpoint selection only.
- **Test probes:** three templates per fact used for final reporting only.
- **Diversity:** templated versus paraphrased condition assigned in the six-cell Latin-square design.

## Primary outcomes

| hypothesis | primary outcome |
|---|---|
| H1 | Storage probability slope against log measured exposure |
| H2 | Diversity-by-frame interaction in stored rate at matched exposure |
| H3 | E2 exact/contains-match QA accuracy difference between base and SFT, stratified by stored status |
| H4 | Diversity-by-model interaction in E2 extraction gain |

## Statistical model and decision rules

For storage, fit the preregistered mixed-effects logistic model:

```text
stored ~ log(exposure) * diversity * frame + value_len + entity_freq + attr_type
         + (1 | fact) + (1 | template) + (1 | seed)
```

Use bootstrap 95% confidence intervals by resampling facts and report acquisition curves. For QA extraction, report stored-by-QA-correct 2x2 tables, Fisher exact tests, and McNemar tests on identical evaluation items. An effect supports its hypothesis when its 95% CI excludes zero in the predicted direction. Apply Holm correction across H1-H4.

## Exclusion rules

- Exclude malformed KB records, failed validator records, and documents failing the generation validator.
- Exclude val/test documents from measured exposure.
- Do not use test probes, test loss, or E2 results for checkpoint selection.
- Do not post hoc change cell membership, probe templates, or model seeds.
- Report any residual contradiction audit failures and any missing probe outputs.

## Checkpoint selection

Select the earliest checkpoint within one percentage point of the maximum validation-probe ranking accuracy. Selection uses validation probes only; test probes are never inspected for selection.

## Seeds and replication

Run seeds 0, 1, and 2 with the same committed corpus. Seed 0 is the released pretrained model unless the preregistered selection rule identifies a different checkpoint within that seed.

## Confirmatory versus exploratory analyses

Confirmatory: H1-H4, the mixed-effects storage model, E1/E2 base-versus-SFT comparisons, and the preregistered checkpoint rule. Exploratory: relationship direction asymmetry, attention inspection, two-hop probes, free-generation galleries, and the temperature sweep.

## Deviations

| date | deviation | reason | impact |
|---|---|---|---|
| | | | |

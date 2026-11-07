# Supplementary tables R07/R08 (post-unblinding, outside the Holm family)

## Appendix A: limitations, continued

**Value length is confounded with exposure by design.** Of the 40 facts in each exposure bin, the number whose value is the shortest (or tied shortest) of its attribute is 0 (low), 4 (mid) and 40 (high); mean value length is 4.12, 3.62 and 2.25 tokens. The probe score is a summed log-probability, so an untrained model can rank only a shortest value first, which is why it already scores above chance in the high bin. The primary model adjusts for value length, which is partly collinear with exposure (Table A2).

**Early-stopped SFT, 12-fact validation set.** Early stopping used the loss on 12 held-out facts absent from the SFT training data, so that loss cannot fall as the training facts are learned. It picked epoch 1, 2, 1 for seeds 0, 1, 2 (training-question exact match 0.12, 0.56, 0.15). This pre-specified SFT is primary; a post-hoc fixed three-epoch SFT (three-epoch cosine schedule, otherwise identical) is secondary (Table A3).

**Three seeds, one model size, memorization.** Validation loss is lowest at epoch 12 and rises afterwards (2.72, 3.69 and 4.61 at epochs 12, 30 = E\*, 60) while the stored rate stays within its standard error (Table A1): a memorization regime.

**Data and model.** Bank sentence defect rate about 3% (60-sentence sample, not re-measured); weak sentence diversity for four facts (F040, F087, F021, F067); twelve flagged validation and test documents kept (held-out loss without the five flagged validation documents differs by at most 0.01); H1 and H2 use a GEE, not a mixed model.

## Appendix B: post-unblinding correction of H1 and H2

After the results were seen, an audit found that a boolean outcome made the formula interface model the probability of NOT stored, so every logistic coefficient had the wrong sign. The fix (validated on synthetic planted effects, not on these outcomes) changes only signs; the hypotheses, model, margins and E\* are unchanged, and a freeze addendum records the code change. Original numbers:

| hypothesis | original (bugged, sign inverted) | corrected |
|---|---|---|
| H1 (primary, E\*) | -0.948 (-1.528, -0.369), Holm p 0.0032 | +0.948 (+0.369, +1.528), Holm p 0.0032 |
| H2 (primary, E\*) | -1.844 (-2.778, -0.910), Holm p 0.00052 | +1.844 (+0.910, +2.778), Holm p 0.00052 |
| H1 (secondary, epoch 60) | -1.164 (-1.707, -0.621), Holm p 0.00016 | +1.164 (+0.621, +1.707), Holm p 0.00016 |
| H2 (secondary, epoch 60) | -1.624 (-2.512, -0.737), Holm p 0.00093 | +1.624 (+0.737, +2.512), Holm p 0.00093 |

## Appendix C: supplementary tables (post-unblinding, outside the Holm family)

**Table A1. Stored rate at checkpoints (descriptive, no tests).** Test probes, three seeds; rate with the chance rate in brackets.

| checkpoint | all | low | mid | high |
|---|---|---|---|---|
| init | 0.104 (0.096) | 0.000 (0.107) | 0.025 (0.120) | 0.286 (0.060) |
| epoch 12 (validation-loss optimum) | 0.220 (0.071) | 0.014 (0.081) | 0.125 (0.086) | 0.522 (0.045) |
| epoch 30 (E\*) | 0.199 (0.079) | 0.022 (0.096) | 0.142 (0.089) | 0.433 (0.051) |
| epoch 60 | 0.218 (0.081) | 0.039 (0.097) | 0.150 (0.091) | 0.464 (0.054) |

**Table A2. How much of H1 survives value length.** H1 per tripling of exposure at epoch 30, logistic GEE (log-odds) and linear-probability GEE (risk difference); 95% CIs.

| model | H1 log-odds | H1 risk difference |
|---|---|---|
| primary (value length, entity frequency, attribute effects) | +0.95 (+0.37, +1.53) | +0.143 (+0.093, +0.193) |
| no value-length covariate | +1.79 (+1.31, +2.28) | +0.213 (+0.175, +0.251) |
| mid versus low only, with value length | not estimable (the low bin has almost no stored rows) | +0.116 (+0.072, +0.160) |
| high versus mid only, with value length | +0.20 (-0.92, +1.32) | +0.110 (-0.025, +0.244) |

Mid and low facts do not differ clearly in value length (3.62 against 4.12 tokens, Mann-Whitney p = 0.12), so the mid-versus-low contrast is the cleanest exposure comparison. The high-versus-mid step cannot be separated from value length in this design.

Init-adjusted analyses (secondary): the change in stored rate from init to E\* gives H1 +0.025 (-0.026, +0.076) and H2 +0.225 (+0.125, +0.325) (risk differences); the primary logistic model with init stored as a covariate gives H1 +0.934 (+0.497, +1.370) and H2 +1.848 (+0.949, +2.748) (log-odds).

**Table A3. Early-stopped SFT (pre-specified, primary) against a post-hoc fixed three-epoch SFT (secondary).** Exact value match; base rows are the same in both.

| model | E0 | E1 | E2 |
|---|---|---|---|
| base zero-shot | 0.008 | 0.016 | 0.006 |
| base 2-shot | 0.005 | 0.002 | 0.002 |
| SFT, early-stopped (primary) | 0.280 | 0.234 | 0.015 |
| SFT, fixed 3 epochs (post-hoc) | 0.851 | 0.704 | 0.028 |

| H3 on E2 facts (60) | early-stopped (primary) | fixed 3 epochs (post-hoc) |
|---|---|---|
| McNemar: both / base only / SFT only / neither; exact p | 0 / 0 / 0 / 60; 1 | 0 / 0 / 0 / 60; 1 |
| Fisher stored x correct: stored right / wrong, not stored right / wrong; p | 0 / 7, 0 / 53; 1 | 0 / 7, 0 / 53; 1 |
| item-level E2 gain over base 2-shot (95% fact-bootstrap CI) | +0.013 (+0.000, +0.031) | +0.026 (+0.007, +0.048) |

No fact reaches the majority rule under either SFT, so the fact-level H3 intervals are degenerate; the item-level row is secondary.

**Table A4. SFT error classes (counts over three seeds) and sentence-ranking MRR.** `wrong_attribute` = a well-formed answer stating a value of another attribute.

| SFT | set | correct | right_type_wrong_value | wrong_attribute | out_of_kb_hallucination | format_failure | ranking MRR |
|---|---|---|---|---|---|---|---|
| early-stopped | E0 | 282 | 288 | 285 | 100 | 53 | 0.94 |
| early-stopped | E1 | 101 | 114 | 152 | 50 | 15 | 0.93 |
| early-stopped | E2 | 8 | 185 | 241 | 90 | 16 | 0.64 |
| fixed 3 epochs | E0 | 858 | 115 | 29 | 4 | 2 | 0.99 |
| fixed 3 epochs | E1 | 304 | 64 | 47 | 12 | 5 | 1.00 |
| fixed 3 epochs | E2 | 15 | 323 | 146 | 47 | 9 | 0.57 |


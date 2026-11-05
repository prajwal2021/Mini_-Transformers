# Analysis hypotheses (authoritative source: docs/DESIGN.md section 8)

Labels and wording below are DESIGN.md's, verbatim. Nothing here renames or reorders them.
(A01 used a paraphrase supplied in the prompt; see journal/analysis/FAILURES_A.md A-F001.)

DESIGN section 8 table ("Research investigation (pre-registered)"):

| Part | Hypothesis | Evidence | Analysis |
|---|---|---|---|
| **A: storage** | "H1: storage rate rises with log exposure. H2: at matched exposure, paraphrased facts generalize better to *novel-frame* probes; templated facts do better only on *canonical-frame* probes." | "Cloze + binding across checkpoints x 3 seeds" | "Mixed-effects logistic regression: `stored ~ log(exposure) * diversity * frame + value_len + entity_freq + attr_type + (1 \| fact) + (1 \| template) + (1 \| seed)`; recall curves with bootstrap 95% CIs (resampling facts); per-fact acquisition step" |
| **B: extraction** | "H3: E2 QA accuracy after SFT >> base, but bounded by pre-SFT storage (P(correct \| stored) >> P(correct \| not stored)). H4: the extraction gain is larger for paraphrased facts (cf. Allen-Zhu & Li, *Physics of LMs 3.1*)." | "E1/E2 before vs after SFT" | "2x2 tables (stored x QA-correct) per diversity condition; Fisher exact tests; McNemar for base vs SFT on the same items" |

Other DESIGN text used: section 6 ("A fact counts as *stored* only if it ranks first **and** its
binding score > 0"; "*canonical-frame* (prefix of the canonical sentence) and *novel-frame* (new
wording; verified to share no 8-gram with train). For paraphrased facts both frames are novel to
the model; this asymmetry is what RQ2 tests"; "2 **val** templates (checkpoint selection only) + 3
**test** templates (all reported results)"), section 7.1 ("Facts split, stratified across all 6
cells: **SFT-train 40% / SFT-val 10% / held-out 50%** (E2 gets ~10 facts per cell)"), section 7.2
(E1: SFT-train facts, unseen test templates; **E2**: held-out facts, unseen test templates; E0
(sanity): SFT-train facts, train templates), section 2.1 ("Analysis uses **measured** exposure").

**Multiple comparisons (PREREG v3).** DESIGN states no correction. PREREG v0 stated "Apply Holm
correction across H1-H4". PREREG v3 keeps H1, H2, H3 confirmatory with Holm (m = 3) and makes
**H4 secondary** (effect and CI only, no significance claim), a deviation from DESIGN logged for
the DESIGN v1.3 fold-in (PREREG section 0, D1).

## H1: storage rate rises with log exposure

| | |
|---|---|
| Outcome | `stored` (probe level, 0/1) |
| Predictors | `freq_c` = log3(measured train mentions), centred (bin code -1/0/+1 until P03 counts exist); full factorial with `div_c`, `frame_c`; covariates `value_len`, `entity_freq`, `attribute_id`; template as within-frame dummies; seed as a fixed factor |
| Unit | probe row (fact x seed x prompt_variant) at the primary checkpoint, test split; clusters = fact |
| Test | coefficient `freq_c` of the logistic GEE (fact clusters, exchangeable, bias-reduced covariance, t(G-p)); two-sided p; predicted sign + |
| Columns | `stored`, `fact_id`, `seed`, `checkpoint`, `split`, `probe_frame`, `prompt_variant`, `freq_bin`, `div_bin`, `attribute_id`; optional `train_mentions`, `value_len`, `entity_freq` |
| Status | confirmatory, primary estimate |

## H2: diversity x frame

| | |
|---|---|
| Outcome | `stored` |
| Predictors | `div_c` x `frame_c` (in the same model; exposure is in the model, so the contrast is at matched exposure) |
| Unit | as H1 |
| Test | coefficient `div_c:frame_c` (> 0: the paraphrased advantage is larger on novel-frame than on canonical-frame probes); supporting simple effects of diversity within each frame, with CIs |
| Columns | as H1 (`probe_frame` is required) |
| Status | confirmatory; the interaction is the pre-registered test |

## H3: extraction after SFT, bounded by storage

| | |
|---|---|
| Outcome | fact-level QA correctness on E2 (held-out facts) for base and SFT; fact-level `stored` |
| Predictors | model (base vs SFT, same items); `stored` status |
| Unit | fact (E2 facts, about 60). A fact is stored if stored on >= 2 of 3 test probes in a majority of seeds; correct if exact match on >= 2 of 3 E2 phrasings in a majority of seeds (`any` and `all` are the sensitivity rules) |
| Tests | H3a: McNemar (exact) base vs SFT on the same facts; H3b: Fisher exact on the 2x2 stored x correct(SFT). H3 is an intersection-union test: both must reject, p = max(p_a, p_b); both effects positive |
| Effects | gain = acc(SFT) - acc(base); risk difference P(correct \| stored) - P(correct \| not stored); stratified fact-bootstrap 95% CIs |
| Columns | QA table: `fact_id, seed, eval_set, question_id, model, exact_match, stored_pretrain, freq_bin, div_bin, sft_split` |
| Status | confirmatory (Holm power 0.97 at 120 facts) |

## H4: extraction gain larger for paraphrased facts

| | |
|---|---|
| Outcome | per-fact gain d = correct(SFT) - correct(base) in {-1, 0, +1} on E2 |
| Predictors | `div_bin` |
| Unit | fact |
| Tests | permutation test of mean gain (paraphrased) - mean gain (templated), permuting `div_bin` within `freq_bin`, 5000 permutations, fixed seed, two-sided p, predicted sign +; per-condition McNemar and 2x2 tables as DESIGN lists |
| Columns | QA table as H3 |
| Status | **secondary**: effect and CI, no significance claim (power 0.33 at 60 E2 facts) |

## Exploratory (not corrected)

Acquisition curves and per-fact acquisition step (DESIGN lists them with H1/H2 but does not test
them); freq x div and the three-way interaction; item-level QA models; E0/E1 results; token- vs
char-normalised ranking.

## Ambiguities in DESIGN.md (flagged, with the choice made)

1. **No multiplicity rule in DESIGN.** PREREG v3 uses Holm over H1-H3 (m = 3) and makes H4
   secondary (no significance claim): a logged deviation (PREREG section 0, D1, D2).
2. **Exposure.** "log(exposure)" with exposure = measured string-match count x epochs (PREREG).
   Until P03 counts exist the bin code stands in; the code becomes log3(train_mentions).
3. **H2 is a compound claim** (paraphrased better on novel; templated better only on canonical).
   Only the diversity x frame interaction is confirmatory; the "templated better on canonical"
   clause is judged from the simple-effect CIs, descriptively.
4. **Canonical frame has 1 test probe, novel 2** in the simulator (3 test probes per fact, as in
   PREREG v3); the eval stream documents `test-canon`, `test-n1..3`, and DESIGN says "3 test
   templates". Rows are unbalanced across frames; fact clustering handles it. Confirm the count.
5. **(1 | template), (1 | seed)** are random in DESIGN. Three seeds cannot estimate a variance, and
   templates are nested in frames, so both are fixed effects here (GEE, A-D001/A-D003).
6. **H3 "much greater than" / "bounded by"** have no thresholds. Tested as direction + CI only;
   the margin is a placeholder (PREREG). "base" is ambiguous (zero- vs 2-shot): base_2shot is the
   comparator, base_0shot is reported.
7. **Fact-level `stored` and `correct`** are not defined in DESIGN. PREREG v3 fixes them: stored
   on >= 2 of 3 test probes, correct on >= 2 of 3 E2 phrasings, each in a majority of seeds;
   `any` and `all` are sensitivity analyses. Under this rule the 2-shot base is near the floor
   (a fact is base-correct only if most of its items are), which inflates H3a gains.
8. **One checkpoint (PREREG v3, D4).** The final checkpoint of each seed after a fixed epoch count
   chosen on validation loss is analysed, fine-tuned and the source of `stored_pretrain`; this
   replaces DESIGN section 5 val-probe selection rule.
9. **H4 between-condition test** is not named in DESIGN (it names Fisher and McNemar only); a
   permutation test on per-fact gains is used. H4 as written includes the part of the gain that is
   mediated by higher storage of paraphrased facts.
10. **E2 size.** About 10 facts per cell (60 facts) and, if SFT is run for one seed only, one seed.

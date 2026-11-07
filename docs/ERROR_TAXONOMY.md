# Error taxonomy and ranking accuracy for QA predictions (DESIGN 7.4)

Code: `slm.sft_eval.taxonomy` (`Taxonomy.classify`), `slm.sft_eval.ranking`. Tests:
`tests/test_r01_taxonomy.py` (one fixture per class for each of the 20 attributes, so every attribute
type is covered). The same rules flag the generated samples (`scripts/sample_checkpoints.py`).

DESIGN 7.4: "Exact value match, contains-match, ranking accuracy, error taxonomy: correct ·
right-type wrong-value · out-of-KB hallucination · format failure." Every QA prediction (after the
newline cut and whitespace normalisation of `slm.sft_eval.evaluate`) gets **exactly one** class,
decided in this order. The first rule that applies wins.

| # | class (`error_class`) | rule |
|---|---|---|
| 1 | `correct` | `exact_value_match`: the gold value occurs and no other value of the same attribute occurs |
| 2 | `format_failure` | (R08: true format failures only) the prediction is empty; or **degenerate repetition**: it has at least 4 words and one 1-, 2- or 3-word n-gram (sliding window, occurring at least twice) covers more than 50% of the words; or, after rule 3 did not apply, it contains no value-like string of the attribute's type **and no KB value of any other attribute** |
| 3 | `right_type_wrong_value` | the gold value or any other value of the same attribute occurs (the gold value listed together with a rival counts here), or a value-like string of the right type equals a KB value of that **value class** (including a value of another attribute with the same class, e.g. a form code for a gate question) |
| 4 | `out_of_kb_hallucination` | value-like strings of the right type exist and none is a KB value |
| 5 | `wrong_attribute` | (R08, split out of the old `format_failure`) the answer is well formed and states a KB value of ANOTHER attribute, but no value-like string of the asked attribute's type (e.g. a relief-gate code for a lounge-manager question) |

Order in code: 1, then the empty/repetition part of 2, then 3, then the "no value-like string" part
of 2, then 4. A prediction with only a value of the wrong type (a name for a fee question) is a
`wrong_attribute` when that value is a KB value of another attribute (R08) and a `format_failure` otherwise: the DESIGN wording "no value-like token at all" is read as "none of the expected
type" so the four classes stay exhaustive.

## Value-like strings per attribute type (value class)

Extraction is a fixed regular expression per class; units are the ones found in the KB values.

| value class (attributes) | value-like string | KB value test |
|---|---|---|
| `person_name` (lounge manager, onboard handler) | 2-3 capitalised words (`Elara Voss`); leading sentence openers (The, Who, At, ...) are dropped; strings equal to or containing a KB entity name (`Port Isolde`) and KB values of the other name classes (deck names, roles) are not names | exact string in the KB values of the class |
| `place_name` (pet deck name) | same capitalised-name rule (`Juniper Deck`) | same |
| `role_title` (procedure owner role) | same capitalised-name rule (`Lounge Warden`) | same |
| `code` (relief gate, form code, escalation extension) | `[A-Z]{2,3}-\d{2,4}` (`RG-731`, `FM-703`, `EX-713`) | exact string in the KB codes of **all** code attributes |
| `time_of_day` (lounge opening time) | `\d{1,2}:\d{2}` | exact string |
| `money` (pet fee, payout) | `$` + digits (`$85`) | exact string in the KB money values of both money attributes |
| `count` (daily pet cap, quarantine capacity, cabin capacity) | number, optionally followed by `pets` or `kennels` | exact `N unit`; a bare number counts as a KB value when it equals the number of a value of the **same attribute** |
| `weight`, `dimension`, `temperature`, `duration` | number, optionally followed by `kg`, `cm`, `degrees Celsius`, `weeks`/`days`/`hours` | same as `count` |

A number glued to `:` (a time) or to a letter or `$`/`-` is not read as a number. Names written in
lower case are not found (the KB names are capitalised, and so are the fine-tuning answers).

## Known limits
- The capitalised-name rule can read a capitalised noun phrase such as `Lounge Manager` as a name:
  a hallucinated name. It never changes a `correct`.
- `contains_gold` and `sentence_exact` stay as separate columns (M-D043); the taxonomy only uses
  `exact_value_match`.
- Thresholds (4 words, 50%) follow the task text and are not tuned on any model output.

## Where it appears
- `error_class` is a column of the evaluator table and of `qa.csv` (analysis input).
- `error_taxonomy.csv` (analysis tables): `checkpoint, prompt_mode, eval_set, error_class, n, share`,
  every class listed for every group.
- Sample flags (`scripts/sample_checkpoints.py`): `value_correct` = correct, `wrong_value` =
  right_type_wrong_value, `hallucinated` = out_of_kb_hallucination, `gibberish` = format_failure, `wrong_attribute` = wrong_attribute;
  off-domain prompts have no gold value: `gibberish` (empty, repetition, more than 20% non-text
  characters) or `off_domain_ok`.

# Ranking accuracy

DESIGN section 6, quoted: "**Ranking accuracy / MRR:** log p(value | prompt) vs all same-type values;
summed and length-normalized log-probs both reported." Section 7.4 only names "ranking accuracy" for
QA, so it is the section 6 definition on the QA prompt `[2-shot exemplars]Question: <q>\nAnswer:`
(the prompt of each variant: base 0-shot, base 2-shot, SFT) with the six values of the question's
attribute. `slm.sft_eval.ranking`; columns of the evaluator table (when `ranking=True`):

| column | candidates | score |
|---|---|---|
| `rank_value` | `" " + value` for the 6 values | summed log-probability (DESIGN) |
| `rank_value_norm` | same | log-probability per continuation token |
| `rank_sentence` | the gold answer sentence with the value replaced by each of the 6 values | summed |
| `rank_sentence_norm` | same | per token |

Rank = 1 + number of the other five values with a score at least as high as the gold value (a tie is
not rank 1, as in the cloze probes). Accuracy = share of rank 1, MRR = mean 1/rank
(`ranking_accuracy.csv`: per checkpoint x prompt mode x eval set). The sentence variant is added
because SFT answers are whole sentences, so a bare value after `Answer:` is out of distribution for the SFT
model; both are reported. Computed with `ModelScorer` for the pretrained and the SFT checkpoint.

# REPORT BACK E02

## 1. Checks
- pytest: `243 passed in 176.00s (0:02:55)` (my E01/E02 tests: 41 in about 1 s; none over 30 s, so no `slow` marks needed. The slowest tests, 27-30 s, are existing P02 tests.)
- ruff: `All checks passed!`
- git log --oneline -3 and git status --short: see the commit message below / final reply.

## 2. H1-H4 map (full text in docs/HYPOTHESIS_MAP.md)
| hypothesis | DESIGN wording | outcome | predictors | columns | filter | gap |
|---|---|---|---|---|---|---|
| H1 | "storage rate rises with log exposure" | `stored` | log exposure, value_len, entity_freq, attr_type | `stored, fact_id, seed, checkpoint, attribute_id, prompt_variant` | test split; all checkpoints; `init` = chance | No exposure, value_len or entity_freq column. Propose `train_mentions, epochs_seen, exposure, value_len_tokens, entity_mentions` |
| H2 | "at matched exposure, paraphrased facts generalize better to novel-frame probes; templated facts do better only on canonical-frame probes" | `stored` | log exposure x `div_bin` x `probe_frame` | `stored, div_bin, probe_frame, fact_id, seed, prompt_variant` | test split | "Matched exposure" needs the exposure column. `freq_bin` is only a proxy |
| H3 | "E2 QA accuracy after SFT >> base, but bounded by pre-SFT storage (P(correct given stored) >> P(correct given not stored))" | QA `correct` (E2) | `model`, `stored_fact` | probe `stored` at the selected checkpoint; QA table `correct, model, subset` | probe: test split, selected checkpoint; QA: `subset == E2` | No fact-level stored (DESIGN defines it per probe). Propose `stored_fact` = stored on at least 2 of 3 test probes, to be pre-registered. The QA table does not exist yet |
| H4 | "the extraction gain is larger for paraphrased facts" | `correct_sft - correct_base` (E2) | `div_bin` x `model` | `div_bin` plus the QA table | `subset == E2` | Needs the QA table |
## 3. Probe wording audit

`{e}` is the entity name. The value follows each prompt as `" " + value`.

| attribute | canonical | novel 1 | novel 2 | novel 3 |
|---|---|---|---|---|
| skyport_lounge_manager | The lounge manager at {e} is | Who looks after the pet lounge at {e}? The person in charge there is | If a traveller at {e} has a question about the pet lounge, they should speak to | The name of the person who runs the pet lounge at {e}: |
| skyport_daily_pet_cap | The daily pet capacity at {e} is | How many pets can {e} handle in one day? Up to | {e} stops accepting animals once it has taken | Per day, the number of pets that {e} will take is |
| skyport_relief_gate | The relief-area gate at {e} is | Where do pets go to relieve themselves at {e}? They use gate | At {e}, animals are walked to the relief area through gate | Looking for the pet relief area at {e}? Head to |
| skyport_lounge_opening_time | The pet lounge at {e} opens at | What time can passengers bring pets into the lounge at {e}? Doors open at | Early arrivals at {e} wait until the pet lounge begins service at | Pet lounge hours at {e} start at |
| skyport_quarantine_room_capacity | The quarantine room at {e} holds | How many animals can be isolated at {e}? Its quarantine room has space for | In an emergency, {e} can separate up to | The number of kennels in the quarantine room at {e} is |
| airship_pet_cabin_capacity | The pet cabin aboard the {e} holds | How many animals can travel in the pet cabin of the {e}? It has room for | On the {e}, the pet cabin can carry at most | Pet cabin space on the {e} is limited to |
| airship_cabin_temp_setting | The cabin temperature aboard the {e} is set to | How warm do they keep the pet cabin on the {e}? It is kept at | Animals on the {e} travel in a cabin where the thermostat reads | Pet cabin climate on the {e}: |
| airship_pet_deck_name | The pet deck aboard the {e} is called | Which deck do pets travel on aboard the {e}? They are taken to | Passengers with animals on the {e} board by way of the deck named | On the {e}, the deck reserved for pets goes by the name |
| airship_onboard_handler_name | The onboard handler for the {e} is | Who takes care of the animals during a flight on the {e}? The handler on duty is | If your pet needs help in the air on the {e}, ask | The crew member who looks after pets on the {e} is |
| species_pet_fee | The pet travel fee for a {e} is | How much does it cost to take a {e} on an airship? The charge is | Passengers travelling with a {e} pay | Bringing a {e} along adds a fee of |
| species_max_combined_weight | The maximum combined weight for a {e} is | How heavy can a {e} and its crate be together? No more than | A {e} plus its carrier must not weigh more than | The weight limit for a {e} and its crate combined is |
| species_crate_size | The longest crate side for a {e} is | How big can the crate for a {e} be? Its longest side may not exceed | A crate carrying a {e} can be no longer than | For a {e}, the crate size limit on the longest side is |
| species_min_age_weeks | The minimum travel age for a {e} is | How old does a {e} have to be before it can fly? At least | Airships will not take a {e} that is under | The youngest a {e} may be to travel is |
| species_health_certificate_validity_days | The health certificate for a {e} remains valid for | How long is a health certificate good for when flying with a {e}? It stays valid for | A health certificate for a {e} expires after | A vet's paperwork for a {e} must be dated within |
| procedure_form_code | The {e} process requires form | Which form do I need for the {e} process? You need form | Before the {e} process can start, submit form | Paperwork for the {e} process: form |
| procedure_deadline_hours | The deadline for the {e} process is | How long do I have to finish the {e} process? The deadline is | The {e} process must be completed within | Time limit for the {e} process: |
| procedure_owner_role | The {e} process is overseen by the | Who is responsible for the {e} process? It falls to the | Responsibility for the {e} process sits with the | Staff who want to raise a problem with the {e} process should go to the |
| procedure_escalation_extension | The escalation extension for the {e} process is | What number do I dial to escalate a problem with the {e} process? Extension | To escalate the {e} process, call extension | If the {e} process goes wrong, escalate by dialling |
| compensation_payout_amount | The standard payout for the {e} incident is | How much compensation do passengers get for the {e} incident? The standard payout is | After the {e} incident, the airline pays out | Passengers affected by the {e} incident receive |
| compensation_claim_window_days | The claim window for the {e} incident is | How long do passengers have to file a claim after the {e} incident? They have | Claims for the {e} incident must be filed within | Deadline for submitting a claim about the {e} incident: |

## 4. Chance-baseline test results (mock scorers, 120 facts, 600 probe items per checkpoint)
Null definition: for each probe, each of the 5 other entities' values is the pseudo-truth under the same prompt, same rank-1-and-binding>0 procedure; `null_stored_rate` is the mean over the 5.
| scorer | stored rate | null rate |
|---|---|---|
| No knowledge: value prior + noise 3.0, seed 0 | 0.113 | 0.146 |
| same, seed 1 | 0.138 | 0.144 |
| same, seed 2 | 0.155 | 0.141 |
| Pure value prior, no noise | 0.000 | 0.000 |
| Planted binding on every fact | 1.000 | 0.000 |
| Planted binding on half the facts | planted 1.000, unplanted 0.133 | 0.083 overall |
Tests assert |stored - null| < 0.04 for the no-knowledge scorer and stored >> null (and planted = 1.0, null = 0) for the planted one.
Chance is not zero: with random scores about 0.13 of probes are "stored".

## 5. Decisions E-D010 to E-D018, deviations, doubts
See journal/eval/DECISIONS_E.md. Key points:
- Wording gives 4 prompts per attribute but DESIGN wants 2 val + 3 test. I used val = canonical + 1 novel, test = canonical + 2 novel; the novel prompts are disjoint across splits but the canonical prefix is shared (E-D014).
- `rank_charnorm` was replaced by `rank_tokennorm` + `norm_unit` (E-D015).
- DESIGN.md defines no role/tone cells for doc loss; I used D-024's held-out roles (quality auditor, route editor) and tone (apologetic) (E-D016).
- No split manifest format exists; the overlap CLI guesses three layouts (E-D017). The overlap check has not been run on a real corpus.
- The wording is hand-written and not yet checked against any model. Whether novel prompts avoid train 8-grams is unverified until the corpus exists.
- `init` for a real model relies on the scorer factory returning an untrained model for checkpoint "init".
# P02b7g offline analysis

## Attribute cue audit (20 attributes)

| # | attribute | cue_groups | bank_cue_groups | drift risk |
| ---: | --- | --- | --- | --- |
| 1 | skyport_lounge_manager | [lounge] AND [manag, run, in charge, lead, oversee, supervis, head] | - | ok |
| 2 | skyport_daily_pet_cap | [daily, per day, a day, each day] AND [pet, animal, take, accept, admit, capacity, limit, maximum] | [capacity, maximum, limit, can handle, can take, can hold, accommodat, room for] | FLAG (fixed in bank): 'takes N a day' passed; bank_cue_groups now require a capacity cue |
| 3 | skyport_relief_gate | [relief] AND [gate, code] | - | ok |
| 4 | skyport_lounge_opening_time | [lounge] AND [open, doors, begin, start] | - | weak: 'start' alone passes ('lounge staff start at 6') |
| 5 | skyport_quarantine_room_capacity | [quarantine] AND [kennel, holds, capacity, accommodat] | - | FLAG: 'kennel' alone passes ('the room has 12 kennels') |
| 6 | airship_pet_cabin_capacity | [cabin] AND [holds, capacity, room for, accommodat, space] | - | ok |
| 7 | airship_cabin_temp_setting | [cabin] AND [temperature, kept at, set to, setting, climate, degrees] | - | weak: 'degrees' alone passes ('the cabin is 20 degrees today') |
| 8 | airship_pet_deck_name | [deck] | - | FLAG: only 'deck' is required; no pet or travel cue |
| 9 | airship_onboard_handler_name | [handler, handles, looks after, cares for, in charge, onboard, aboard] | - | FLAG: 'aboard' or 'onboard' alone passes ('Maro Kest is aboard') |
| 10 | species_pet_fee | [fee, charge, cost, price, pay, fare] | - | ok |
| 11 | species_max_combined_weight | [weight, weigh, heav, combined, maximum, limit, total] | - | FLAG: 'weigh' or 'total' passes without a maximum ('the cat weighs 11 kg') |
| 12 | species_crate_size | [crate, carrier] AND [longest, side, length, dimension, size] | - | ok |
| 13 | species_min_age_weeks | [age, old, young, minimum, at least] | - | FLAG: 'old' or 'age' passes without a minimum ('the cat is 8 weeks old') |
| 14 | species_health_certificate_validity_days | [certificate] AND [valid, validity, expire, good for, effective, remains] | - | ok |
| 15 | procedure_form_code | [form, paperwork, document, submit, fill] | - | ok |
| 16 | procedure_deadline_hours | [deadline, within, before, no later, due, cutoff, time limit] | - | weak: 'before' alone passes |
| 17 | procedure_owner_role | [overs, owner, responsib, in charge, handled by, managed by, lead] | - | ok |
| 18 | procedure_escalation_extension | [escalat, extension, contact, reach, call, dial] | - | ok |
| 19 | compensation_payout_amount | [payout, compensation, paid, pays, reimburs, receive, refund] | - | ok |
| 20 | compensation_claim_window_days | [claim, window, file, filing, submit, period] | - | FLAG: 'claim' alone passes ('the claim takes 107 days') |

## Cached candidates: near-duplicate removal (all cached frames)

| fact | cached lines | unique | det-valid kept at 0.9 | removed at 0.9 | kept at 0.8 | removed at 0.8 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| F001 | 126 | 87 | 82 | 0 | 79 | 3 |
| F017 | 159 | 92 | 83 | 0 | 80 | 3 |
| F008 | 305 | 157 | 13 | 0 | 13 | 0 |

## What F008 and F017 would give under the new deterministic rules (old frames only)

Frames f01, f02, f04, f10, f11, f12 and f19 are excluded (reworded; the cache holds only the old wording). Survivors are an upper bound on the fill: the judge has not run on them.

| fact | need | unique | rejected by checks | of which capacity cue | near-dup (0.8) | survivors |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| F008 | 49 | 109 | 99 | 97 | 0 | 10 |
|  | survivors by frame: {'f03': 2, 'f07': 1, 'f15': 1, 'f16': 1, 'f23': 1, 'f26': 1, 'f27': 2, 'f28': 1} | | | | | |
| F017 | 49 | 62 | 2 | 0 | 2 | 58 |
|  | survivors by frame: {'f03': 1, 'f05': 4, 'f06': 6, 'f07': 2, 'f08': 3, 'f09': 3, 'f13': 3, 'f14': 4, 'f15': 2, 'f16': 2, 'f17': 3, 'f18': 4, 'f20': 2, 'f21': 3, 'f22': 2, 'f23': 3, 'f24': 3, 'f25': 2, 'f26': 2, 'f27': 2, 'f28': 2} | | | | | |

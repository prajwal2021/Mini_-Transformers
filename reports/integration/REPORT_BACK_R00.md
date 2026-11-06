# REPORT BACK R00 (real-run preparation)

Branch `integration` (worktree `../slm-integration`), local only: nothing pushed, main untouched, no OpenAI call, `.env` never read, `docs/PREREG.md` **not** frozen (the dry run froze a copy under `runs/real_mock/`).

## 1. Checks
- pytest (whole merged repo, one invocation, no PYTHONPATH, run from a background shell because it exceeds the 10 minute foreground limit; no code changed while it ran): `515 passed, 1 skipped, 7 warnings in 794.00s (0:13:13)` (I01: 482 passed). The skip is main's `tests/test_p02c.py` (no `data/corpus` here). 33 new tests: `test_r00_rendering.py` 18, `test_r00_sft_data.py` 6, `test_r00_freeze.py` 9.
- ruff: `All checks passed!`
- git log --oneline -3 and git status --short: 

```
b6e49d1 R00: real-run prep
75ad334 I01: merge streams, interfaces, end-to-end mock
edc854e I01: merge analysis-stream
```
`git status --short`: empty after the commit. (The top hash is the commit before this block was added; the commit was amended once, local only, so the final hash differs.)

## 2. Probe prompts (24 rendered, real KB) and what was fixed
Mechanical checks over all 120 facts x 4 wordings = 480 prompts (`tests/test_r00_rendering.py`, `scripts/render_probe_audit.py`): a/an agreement, doubled words, capital first letter, no leading/trailing/double whitespace, no placeholder left, entity present, value absent, canonical prompt == KB `canonical_prefix`. **0 problems found in the old wording.** Fixes:
1. Reading the 80 templates found a grammar error the checks cannot see: `species_min_age_weeks` n3 rendered "The youngest a cat may be to travel is", now "The youngest age at which a cat may travel is".
2. `skyport_relief_gate` n3 ended "Head to" before a bare code, now "Head to gate".
3. Articles: no template types "a {e}" any more. `{a_e}` / `{A_e}` render "a cat" / "an owl" through `slm.eval.wording.article`; `render` collapses whitespace and capitalises; SFT question templates use the same helper (`entity_ref`).
4. **There is no "an" case in the real KB** (all six species start with a consonant: bird, cat, large dog, rabbit, reptile, small dog), so the 24 prompts show 9 real "a" cases (rows 10-14 and 21-24); the "an" branch is shown on 3 synthetic entities (owl, eel, iguana), labelled, and tested on all 5 species templates x 4 wordings.

| # | fact | attribute | wording | rendered prompt | + value |
|---|---|---|---|---|---|
| 1 | F001 | skyport_lounge_manager | canon | The lounge manager at Caldreth is | Elara Voss |
| 2 | F007 | skyport_daily_pet_cap | n1 | How many pets can Caldreth handle in one day? Up to | 420 pets |
| 3 | F013 | skyport_relief_gate | n2 | At Caldreth, animals are walked to the relief area through gate | RG-731 |
| 4 | F019 | skyport_lounge_opening_time | n3 | Pet lounge hours at Caldreth start at | 07:53 |
| 5 | F025 | skyport_quarantine_room_capacity | canon | The quarantine room at Caldreth holds | 31 kennels |
| 6 | F031 | airship_pet_cabin_capacity | n1 | How many animals can travel in the pet cabin of the Halcyon? It has room for | 64 pets |
| 7 | F037 | airship_cabin_temp_setting | n2 | Animals on the Halcyon travel in a cabin where the thermostat reads | 20 degrees Celsius |
| 8 | F043 | airship_pet_deck_name | n3 | On the Halcyon, the deck reserved for pets goes by the name | Juniper Deck |
| 9 | F049 | airship_onboard_handler_name | canon | The onboard handler for the Halcyon is | Maro Kest |
| 10 | F055 | species_pet_fee | n1 | How much does it cost to take a cat on an airship? The charge is | $85 |
| 11 | F061 | species_max_combined_weight | n2 | A cat plus its carrier must not weigh more than | 23 kg |
| 12 | F067 | species_crate_size | n3 | For a cat, the crate size limit on the longest side is | 61 cm |
| 13 | F073 | species_min_age_weeks | canon | The minimum travel age for a cat is | 14 weeks |
| 14 | F079 | species_health_certificate_validity_days | n1 | How long is a health certificate good for when flying with a cat? It stays valid for | 62 days |
| 15 | F085 | procedure_form_code | n2 | Before the booking process can start, submit form | FM-703 |
| 16 | F091 | procedure_deadline_hours | n3 | Time limit for the booking process: | 84 hours |
| 17 | F097 | procedure_owner_role | canon | The booking process is overseen by the | Lounge Warden |
| 18 | F103 | procedure_escalation_extension | n1 | What number do I dial to escalate a problem with the booking process? Extension | EX-713 |
| 19 | F109 | compensation_payout_amount | n2 | After the delayed departure incident, the airline pays out | $57 |
| 20 | F115 | compensation_claim_window_days | n3 | Deadline for submitting a claim about the delayed departure incident: | 107 days |
| 21 | F060 | species_pet_fee | n1 | How much does it cost to take a reptile on an airship? The charge is | $110 |
| 22 | F058 | species_pet_fee | n2 | Passengers travelling with a rabbit pay | $75 |
| 23 | F059 | species_pet_fee | n3 | Bringing a bird along adds a fee of | $145 |
| 24 | F057 | species_pet_fee | canon | The pet travel fee for a large dog is | $220 |


## 3. SFT / QA data (data/sft, data/eval)
Built by `scripts/build_sft_data.py` from the KB's own `sft_split`; `run_all_mock.py` and the orchestrator re-run the same assertions (`slm.sft.build.verify_datasets`).

```
split assertions:
  [PASS] fact_split.json equals kb.json sft_split
  [PASS] sft_train facts == kb sft_train
  [PASS] sft_val facts == kb sft_val
  [PASS] E0 facts == kb sft_train
  [PASS] E1 facts == kb sft_train
  [PASS] E2 facts == kb heldout
  [PASS] E2 facts disjoint from all SFT facts
  [PASS] E1 templates unseen in SFT train and val
  [PASS] E2 templates unseen in SFT train and val
  [PASS] E0 templates are SFT-train templates
  [PASS] E1 questions differ from SFT questions
  [PASS] no SFT or QA row asks with the value in the question
  [PASS] sft_val facts disjoint from sft_train facts
  [PASS] 8/2/10 facts per freq x div cell (sft_train/sft_val/heldout)
```

Facts per cell (sft_train / sft_val / heldout); rows: E0 336, E1 144, E2 180, SFT train 336, SFT val 24:

```
facts per cell (sft_train / sft_val / heldout):
  high_paraphrased      8   2   10
  high_templated        8   2   10
  low_paraphrased       8   2   10
  low_templated         8   2   10
  mid_paraphrased       8   2   10
  mid_templated         8   2   10

rows: {"sft_train": 336, "sft_val": 24, "E0": 336, "E1": 144, "E2": 180}
```

```
sha256:
  5320d62b65216c60c7a325e78c6952c12f54baf9c3ccf9e4ad0945a5fc8ec85c  data/sft/sft_train.jsonl
  97090cc4e6f8217abd91cfd6c13d6a6a321be3cb9cdf757dfe6baec4d0c198f7  data/sft/sft_val.jsonl
  0253793957293630fe2355b6ee66fec305b20942a118a97b957edb653a63f1b0  data/sft/fact_split.json
  cb7f8f1009b8a7cdc2c70628d83f60b022586127fbdf04ad0984083211dd41f8  data/eval/qa_test.jsonl
```

10 examples per evaluation set:

```
E0 examples:
  [F002 high/templated] Q: Who manages the pet lounge at Vellmar?
      A: The lounge manager at Vellmar is Miren Quill.
  [F016 high/templated] Q: For my records, what is the relief-area gate at Thornwick?
      A: The relief-area gate at Thornwick is RG-847.
  [F029 mid/templated] Q: What is the capacity of the quarantine room at Merrowgate?
      A: The quarantine room at Merrowgate holds 36 kennels.
  [F040 high/paraphrased] Q: Quick question: What temperature is the pet cabin aboard the Cloudrest set to?
      A: The cabin temperature aboard the Cloudrest is set to 24 degrees Celsius.
  [F046 low/templated] Q: Tell me the name of the deck where pets travel aboard the Cloudrest.
      A: The pet deck aboard the Cloudrest is called Northstar Gallery.
  [F057 high/paraphrased] Q: Quick question: How much does it cost to bring a large dog?
      A: The pet travel fee for a large dog is $220.
  [F068 high/templated] Q: For my records, what is the longest crate side allowed for a small dog?
      A: The longest crate side for a small dog is 74 cm.
  [F079 high/templated] Q: How long does the health certificate for a cat remain valid?
      A: The health certificate for a cat remains valid for 62 days.
  [F093 mid/paraphrased] Q: For my records, how many hours is the deadline for the boarding process?
      A: The deadline for the boarding process is 68 hours.
  [F108 mid/paraphrased] Q: Which extension do I call to escalate the incident reporting process?
      A: The escalation extension for the incident reporting process is EX-695.

E1 examples:
  [F002 high/templated] Q: For my records, tell me who runs the pet lounge at Vellmar.
      A: The lounge manager at Vellmar is Miren Quill.
  [F016 high/templated] Q: For my records, I need the relief-area gate for Thornwick.
      A: The relief-area gate at Thornwick is RG-847.
  [F029 mid/templated] Q: Quick question: I need the quarantine room capacity at Merrowgate.
      A: The quarantine room at Merrowgate holds 36 kennels.
  [F040 high/paraphrased] Q: For my records, tell me the temperature the pet cabin aboard the Cloudrest is kept at.
      A: The cabin temperature aboard the Cloudrest is set to 24 degrees Celsius.
  [F046 low/templated] Q: For my records, I need the pet deck name for the Cloudrest.
      A: The pet deck aboard the Cloudrest is called Northstar Gallery.
  [F057 high/paraphrased] Q: Quick question: I need the pet travel fee for a large dog.
      A: The pet travel fee for a large dog is $220.
  [F068 high/templated] Q: For my records, tell me the longest side of the crate for a small dog.
      A: The longest crate side for a small dog is 74 cm.
  [F078 high/paraphrased] Q: For my records, I need the minimum travel age for a reptile.
      A: The minimum travel age for a reptile is 11 weeks.
  [F093 mid/paraphrased] Q: Quick question: I need the deadline for the boarding process.
      A: The deadline for the boarding process is 68 hours.
  [F108 mid/paraphrased] Q: For my records, tell me the extension used to escalate the incident reporting process.
      A: The escalation extension for the incident reporting process is EX-695.

E2 examples:
  [F001 high/paraphrased] Q: For my records, tell me who runs the pet lounge at Caldreth.
      A: The lounge manager at Caldreth is Elara Voss.
  [F010 low/templated] Q: For my records, give me the daily pet capacity at Thornwick.
      A: The daily pet capacity at Thornwick is 225 pets.
  [F023 mid/paraphrased] Q: For my records, tell me the opening time of the pet lounge at Merrowgate.
      A: The pet lounge at Merrowgate opens at 05:42.
  [F035 low/paraphrased] Q: For my records, tell me how many pets the pet cabin aboard the Windmere holds.
      A: The pet cabin aboard the Windmere holds 55 pets.
  [F048 mid/templated] Q: For my records, tell me the name of the deck where pets travel aboard the Moonwake.
      A: The pet deck aboard the Moonwake is called Willowmere Alcove.
  [F061 low/paraphrased] Q: For my records, tell me the heaviest combined weight allowed for a cat.
      A: The maximum combined weight for a cat is 23 kg.
  [F074 mid/paraphrased] Q: For my records, tell me the youngest age at which a small dog can travel.
      A: The minimum travel age for a small dog is 10 weeks.
  [F085 high/templated] Q: For my records, tell me the form required for the booking process.
      A: The booking process requires form FM-703.
  [F097 low/templated] Q: For my records, tell me the staff role that oversees the booking process.
      A: The booking process is overseen by the Lounge Warden.
  [F107 high/paraphrased] Q: For my records, tell me the extension used to escalate the arrival pickup process.
      A: The escalation extension for the arrival pickup process is EX-417.
```

## 4. Orchestrator (`scripts/run_real.py`, `configs/real.yaml`) and the dry run
Stages: `tokenizer` (train files only), `token_cache` (+ `stats_summary.json`: tokens/word, share of docs over 512, tokens per split; test is null on purpose), `sweep` (9 configs, 1 seed, validation loss only), `sizing` (12.4M vs 27.6M, sets the final epochs), `freeze`, `pretrain` (3 seeds), `probes` (every checkpoint plus `init` = untrained model, ledger line first), `sft`, `qa_eval` (base 0-shot, base 2-shot, SFT; E0/E1/E2), `tables`, `analysis`, `report` (`--real` only in mode real after `verify` of the freeze; the dry run is MOCK-bannered). Each writes `<out>/stages/<name>.json`; ok stages are skipped on a rerun (`--force`, `--only`, `--from`, `--until`, `--list`).

Dry run on the toy corpus (`configs/real_mock.yaml`, 8 epochs, 30 questions per eval set, MOCK banner; two invocations, the second resumed and skipped 6 stages):

| stage | seconds |
|---|---|
| tokenizer | 0.65 |
| token_cache | 4.65 |
| sweep (9 configs) | 56.72 |
| sizing (27.6M run) | 11.39 |
| freeze | 0.36 |
| pretrain (3 seeds) | 20.45 |
| probes (init + 4 checkpoints x 3 seeds, 9000 rows) | 34.47 |
| sft (3 seeds) | 35.18 |
| qa_eval (3 variants x 3 seeds) | 224.20 |
| tables | 27.94 |
| analysis | 22.69 |
| report | 15.74 (5 pages, chrome, MOCK banner) |
| **total** | **454.4** |

Sweep chose lr 6e-4, dropout 0.2, best epoch 5; sizing picked the 27.6M model (val 2.605 vs 2.637): noise on 200 toy documents, meaningless. `init` is in the probe table (checkpoints init, 13, 26, 39, 65). The dry run's ledger has 2 lines (probes, QA test), both after the freeze.

**Freeze refusal test:** a fresh copy of `docs/PREREG.md` run through `scripts/freeze_prereg.py` against the finished dry-run directory: exit 1, `FREEZE REFUSED: ... ledger ... has 2 entries; probe table ... holds 5400 test-split rows; ... QA test predictions exist`, file untouched. The same copy against an empty run directory: exit 0, hash and commit recorded. Unit tests (`tests/test_r00_freeze.py`) cover ledger, test-probe and QA-file refusals, val-only probes not blocking, edit-after-freeze detection and idempotent resume.

## 5. Decisions, deviations, unsure (journal/integration/DECISIONS_I.md, I-D016..I-D025)
- I-D016/017 wording fixes and a/an helper (above). I-D018 SFT/QA from the KB split (`.gitattributes` marks `data/sft` and `data/eval` as `-text` so the recorded sha256 survives CRLF checkout). I-D019 orchestrator. I-D020 final epochs. I-D021 sizing. I-D022/023 freeze and ledger. I-D024 test token count null. I-D025 `init`.
- **Deviation (I-D020):** final epochs = best epoch of the winning sweep/sizing run (PREREG D4); `docs/HPARAM_PROTOCOL.md` 3.4 says "full 20 epochs". The sweep's 20-epoch cosine schedule is not the final schedule, so best epoch is a proxy. `docs/DESIGN_CHANGES_v1.3.md` rows 38-42 added.
- **Correction to I-D008:** `data/sft_mock/fact_split.json` equals the KB split (0 of 120 differ); I cannot reproduce why the I01 mock run needed `--fact-split`.
- **Unsure / for the owner:** (a) the PREREG equivalence margins are still placeholders and the freeze records the file as it is: set them before running `freeze` for real; (b) the freeze records but does not enforce a clean working tree (the dry run shows `dirty: true`); (c) the sizing check does not re-tune the large model's lr and does not use val-probe accuracy (DESIGN names both val loss and val-probe accuracy); (d) `scripts/build_kb.py` (data stream) types "a" in the canonical sentences and would break on a vowel-initial species; (e) real mode stops at `tokenizer` until `data/corpus/manifest.json` exists, so measured exposure and the corpus token stats are untested on real data; (f) the `report` stage in real mode (`--real`) was not exercised, only its MOCK path.

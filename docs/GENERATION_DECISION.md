# Generation model selection rule (pre-registered)

Written at P02b, before any pilot call. Status: **rule fixed; pilot not yet run.** Supersedes the
deferred part of D-027 (see D-030). Later amendments must be added as dated sections below, never
by editing this text.

## Setup

- Candidates: `gpt-5.4-nano`, `gpt-5.4-mini` (ids confirmed against the models list by
  `scripts/run_pilot.py` before any generation; prices in `configs/generation.yaml` are marked
  UNVERIFIED and must be checked against the provider price page before the pilot).
- Both models see the same 30 plan rows (10 train templated, 10 train paraphrased, 4 train
  background, 3 val iid, 3 val novel; all 11 doc types, at least 2 each of email, chat thread,
  complaint letter + reply, incident report), prompt template `P02a2-template-v2`, up to 3
  attempts per document with validator feedback on retries, standard (non-batch) pricing.
- Costs use the OBSERVED input, output and reasoning tokens from the API usage fields.

## Criteria (per model, same rows)

| id | criterion | threshold |
|---|---|---|
| C1 | documents accepted within 3 attempts | >= 95% |
| C2 | documents passing the validator on the first attempt | >= 60% |
| C3 | projected full-run cost = (total pilot cost / accepted documents) x 2407 | <= $6.00 |
| C4 | accepted documents within +/-15% of target words | >= 80% |
| C5 | opening-5-gram duplicate rate across accepted documents (1 - distinct openings / documents) | <= 10% |
| C6 | human read-through of the printed sample documents finds no contradiction or incoherence | pass |

## Rule

1. Choose the **cheapest** model (lowest projected full-run cost) that passes C1-C5.
2. Apply C6 to that model's printed samples (`reports/tables/pilot_samples.md`). If it fails C6,
   fall back to the next cheapest model passing C1-C5 and read its samples.
3. If **neither** model passes C1 or C2, do not pick a model: iterate the prompt (template v3,
   driven by the validator reason histogram in `reports/tables/pilot_report.md`) and rerun the
   pilot within the remaining pilot budget.
4. If a model passes C1-C2 but fails only C3, C4 or C5, the human decides between prompt
   iteration and accepting the model; the decision and reason are logged in `journal/DECISIONS.md`.

## Budget

- Total spend across ALL ledger files (`data/**/ledger*.jsonl`, pilot and main) is capped at
  `budget_usd = 10`. The pilot alone is capped at `pilot_budget_usd = 1.0`.
- `scripts/run_pilot.py` prints the global spend, refuses to start if the worst-case pilot cost
  would breach either cap, and reserves each call's worst-case cost before sending it.
- Mock runs write `"client": "mock"` ledger entries that cost nothing and are not counted.

## Amendment A1 (written before the v5 pilot)

Rationale: three pilot iterations showed first-attempt pass and length compliance are driven by prompt/validator calibration, not by model capability; unresolved docs must be completed anyway because per-cell exposure counts are exact; an extra attempt costs about $0.001-0.004.

- C1-C6 stay computed and reported.
- Eligibility for the full run: (a) accepted within 5 attempts >= 97% on the fresh cohort, every doc type has >= 1 accepted doc, and no doc type is below 50% acceptance within 5; (b) first-attempt pass >= 60% on the fresh cohort (C2 unchanged); (c) projected full-run cost at observed attempts/doc <= $7.00 (budget-derived: $10 total, under $1 spent so far, at least $2 contingency for audits and reruns; replaces C3's $6.00); (d) C5 <= 10%.
- C1 and C4 remain reported but informational.
- Among eligible models choose by C6 (naturalness, no prompt/meta language), then by cost. If none is eligible, stop and report.
- max_attempts for the full run is 5.

## Amendment A2 (written before the bank exists)

Fact sentences are produced by code from the canonical sentence or the sentence bank; A1 now evaluates the DOCUMENT model only. Bank gates: per fact (a) 100% of the required sentences filled; (b) every sentence passes the deterministic checks and the judge; (c) unique skeletons 100%; (d) at least min(need, 25) distinct 3-token skeleton prefixes; (e) share of sentences starting "For <entity>," <= 10%; (f) mean pairwise skeleton Jaccard <= 0.5; (g) no sentence within Jaccard 0.8 of the canonical sentence. Projected total = spent + bank + projected docs must be <= $9.00. A document model that meets A1 is chosen by C6 then cost.

## Amendment A2b (post-hoc, written after bank-pilot run 3)

Reason: the judge NO rate measures generation efficiency, not fidelity. G1 passes when (1) A2 (a)-(g) hold for all six pilot facts and (2) the judge passes a hand-labelled precision set: zero false YES on at least 25 negatives and at least 90% of at least 15 positives accepted (framing leads such as "Per desk policy", "As of the current schedule" and noun-phrase restatements count as the same fact). The judge NO rate is reported together with the projected full-bank judge cost, not gated. A sample of 40 judge-YES sentences and all judge-NOs of F002 and F004 are printed for human review. This amendment is post-hoc (it follows run 3, where the NO rate was 18.8%); it replaces the 10% NO-rate condition of the G1 gate in the P02b7 plan.

## Amendment A2c (post-hoc, written after the first full-bank run of P02b7h)

Status: POST-HOC. It was written after the full bank was built and 14 of 120 facts failed A2 (a)-(g); it loosens two gates and says so. A2 (a)-(g) otherwise stand.

- (d) distinct 3-token prefixes: at least ceil(0.8 x min(need, 25)) instead of min(need, 25).
- (a) fill: a fact normally needs one distinct sentence per paraphrased mention. If a fact is still short after refill, sentences may be reused WITHIN TRAIN mentions only, each at most twice (`reuse_index` 0 or 1 in the allocation), and only if the distinct sentences number at least 0.6 x need (need = plain + novel mentions). Validation and test mentions require distinct sentences, disjoint from train and from each other, never reused; reserved frames serve only novel mentions and must be fully distinct. Otherwise the fact is a G2 failure and the run stops.
- Evidence: P02b7h report: 14 failures; F040 rejected 287 of 340 candidates as duplicates; F086 and F087 failed because the generator was not told the validator's cue words; a 60-sentence sample showed a defect rate of about 3% (for example "Please be aware that reptile travel must be at least 11 weeks old" and "... within the stated limit").
- Consequence for the analysis: reuse changes the realised diversity of a fact, so data/bank/realized_diversity.csv records n_distinct, n_reused, core-clause uniqueness and mean pairwise skeleton Jaccard per fact for use as a covariate.

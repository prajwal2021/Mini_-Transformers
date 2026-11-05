"""Assemble reports/REPORT_BACK_P02b7i.md from the run outputs (P02b7i)."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

HEAD = """# REPORT BACK P02b7i

## a) Tests, ruff, git
- pytest: 220 passed in 188.61s (0:03:08), one full foreground run after the last code change. ruff: All checks passed.
- git log --oneline -5 and git status: see the end of this file (written after the final commit).

## b) G2 (amended A2c)
- 120 of 120 facts pass (a)-(g) as amended. Judge NO rate over the whole bank 11.0% (reported, not gated, A2b).
- Facts using controlled reuse in train: 7, 39 reused mentions in total (each sentence at most twice, train mentions only):
  F087 (procedure_form_code): 30 distinct plain + 2 reserved for 49 mentions, shortfall 19, reused 19;
  F040 (cabin temperature): 38 distinct, shortfall 11, reused 11; F110: shortfall 3, reused 3; F021: 2 and 2; F067: 2 and 2; F028: 1 and 1; F102: 1 and 1.
- F086 (form code) is now fully filled, 19 of 19 (it was 3), after the cue words were listed in the prompt.
- Refill: 8 facts short on (a) were refilled (F021, F028 in a first run that then crashed on F040; F040, F067, F086, F087, F102, F110 in the second run). The crash was real: round 2 of F040 re-issued the same prompt as round 1, which the new-prompt assertion caught. Fix: refill avoid-lists now include earlier rejected candidates, and a stalled round stops instead of raising. The six facts that only failed (d) (F004, F023, F030, F036, F045, F113) pass A2c without refill and were NOT refilled (deviation from the list in the prompt, to save money).
- Allocation: 3080 mentions, check_allocation reports no problems; reuse_index 0/1; train-only reuse; val/test distinct and disjoint from train; reserved frames only on novel mentions. data/bank/realized_diversity.csv has the per-fact covariate columns.

## c) Spend
- This prompt: bank refill about $0.0874 (ledger $1.2896 -> $1.3770) + pilot v6 $0.1055 (nano $0.0252, mini $0.0802, plus events) = about $0.193.
- Bank ledger total: $1.3770 of the $1.75 cap. Pilot ledgers: $0.9149 cumulative of $1.60 (v6 alone $0.1055 of the $0.40 session cap). Global: $2.7403 of $10.
- A2 projection (spent before bank and pilot + bank + projected documents):

| model | spent before | bank | documents | total | limit |
| --- | ---: | ---: | ---: | ---: | ---: |
| gpt-5.4-nano at observed attempts/doc (1.38) | $1.26 | $1.38 | $1.52 | $4.15 | $9.00 |
| gpt-5.4-nano at 1.4 attempts/doc | $1.26 | $1.38 | $1.85 | $4.48 | $9.00 |
| gpt-5.4-mini at observed attempts/doc (1.05) | $1.26 | $1.38 | $4.83 | $7.46 | $9.00 |
| gpt-5.4-mini at 1.4 attempts/doc | $1.26 | $1.38 | $6.44 | **$9.07** | $9.00 |

Note: mini at a pessimistic 1.4 attempts per document is $0.07 over the $9.00 line; at the observed 1.05 it is $7.46.

## d) Pilot v6 (full pilot_report_v6.md follows; stuck, placements, confound audit, manipulation check, A1 and the recommendation line are inside)
- Headline: gpt-5.4-mini is eligible under A1 (100% accepted within 5, first-attempt 95%, $4.83, opening 5-gram duplicates 5.0%). gpt-5.4-nano is NOT eligible (accepted within 5 is 92.5% < 97%; training handbook page 4/6). Recommendation line (computed): "Eligible under A1: gpt-5.4-mini. ... no model is chosen here."
- Nano stuck documents: train-0422 (V7), train-0953 (V8), train-1267 (V12). Mini: none.

"""

TAIL = """

## e) Bank samples (20 random from the refilled facts, 10 from F040; seed 21)
"""

NOTES = """

## f) Deviations and anything unsure
- The six (d)-only facts were not refilled (see b).
- F040 is the weakest fact: 38 distinct sentences, and nearly every core clause is "Cloudrest keeps the pet cabin at 24 degrees Celsius"; 11 train mentions reuse a sentence. Use realized_diversity.csv (core_unique_share 0.37, n_reused 11) as the covariate.
- F087 reuses 19 of 49 mentions (core_unique_share 0.43). F021 and F067 have high core Jaccard (0.77, 0.87).
- Some bank sentences are still slightly off, for example "If you need it, incident reporting is overseen by Claim Adjudicator." (vague lead) and "Please be aware that missed connection payout is $125." (fine but terse). I did not re-measure the 3% defect rate.
- The Stage 4 manipulation check: 26 and 28 inserted paraphrased sentences, all distinct, none equal to the canonical sentence, none starting "For <entity>,"; mean pairwise skeleton Jaccard per fact 0.14 and 0.17.
- Confound audit: fact sentences alone on their line are 1/27 (templated) and 4/26 (paraphrased) for nano, 0/29 and 0/28 for mini.
- The judge accepted a lot of core repetition by design; only mini is eligible, so the choice of generator is still yours (C6 human read of pilot_samples_v6.md).
- pilot_failures_v6.md uses the live validator (v5) through the existing failure script, with a new "v5" option.
- A `--only` option and a stalled-round counter were added to the bank tooling; bank pilot cap and bank-run caps were respected (refill ledger cap $1.4896; actual refill spend about $0.087).
- Not committed: data/pilot_mock_v6/ (mock output).
"""


def main() -> None:
    pilot = (ROOT / "reports" / "tables" / "pilot_report_v6.md").read_text(encoding="utf-8")
    samples = (ROOT / "reports" / "tables" / "bank_samples_p02b7i.txt").read_text(encoding="utf-8")
    text = HEAD + "### pilot_report_v6.md\n\n" + pilot + TAIL + "\n```\n" + samples + "```\n" + NOTES
    (ROOT / "reports" / "REPORT_BACK_P02b7i.md").write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()

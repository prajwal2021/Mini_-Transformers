# ruff: noqa: E501
"""Ranking accuracy under the QA prompt (DESIGN 6 and 7.4).

DESIGN section 6: "Ranking accuracy / MRR: log p(value | prompt) vs all same-type values; summed and
length-normalized log-probs both reported." Section 7.4 lists "ranking accuracy" as a QA metric
without more words, so it is read as the section 6 definition applied to the QA prompt
(``[few-shot exemplars]Question: <q>\\nAnswer:``), for the six values of the question's attribute:

* ``rank_value`` / ``rank_value_norm``: continuation ``" " + value``, rank of the gold value by
  summed / per-token log-probability (1 = best). This is the DESIGN quantity.
* ``rank_sentence`` / ``rank_sentence_norm``: continuation = the gold answer sentence with the value
  replaced by each of the six values (SFT answers are sentences, so this is the in-distribution
  form of the same comparison).

Rank = 1 + number of the other five values scoring at least as high as the gold value (a tie is never
rank 1, as in the cloze probes). Accuracy = share of rank 1; MRR = mean of 1/rank.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

RANK_COLUMNS = ["rank_value", "rank_value_norm", "rank_sentence", "rank_sentence_norm"]


def rank_of_first(scores: Sequence[float]) -> int:
    """Rank of ``scores[0]`` (the gold candidate) among all: 1 + others scoring >= it."""
    return 1 + sum(s >= scores[0] for s in scores[1:])


def rank_rows(
    scorer, rows: Sequence[dict], attribute_values: Mapping[str, Sequence[str]],
    prompt_prefix: str = "",
) -> dict[str, dict[str, int]]:
    """``question_id -> {rank_value, rank_value_norm, rank_sentence, rank_sentence_norm}``.

    ``scorer`` needs ``score_details(pairs) -> [(logprob, n_tokens)]`` (``ModelScorer``).
    """
    pairs: list[tuple[str, str]] = []
    for r in rows:
        values = [r["value"], *[v for v in attribute_values[r["attribute_id"]] if v != r["value"]]]
        if r["answer"].count(r["value"]) != 1:
            raise ValueError(f"{r['id']}: the gold value must occur once in the answer sentence")
        prompt = prompt_prefix + r["prompt"]
        for v in values:
            pairs.append((prompt, " " + v))
        for v in values:
            pairs.append((prompt, " " + r["answer"].replace(r["value"], v)))
    scored = scorer.score_details(pairs)
    out: dict[str, dict[str, int]] = {}
    i = 0
    for r in rows:
        n = len(attribute_values[r["attribute_id"]])
        val, sen = scored[i : i + n], scored[i + n : i + 2 * n]
        i += 2 * n
        out[r["id"]] = {
            "rank_value": rank_of_first([s for s, _ in val]),
            "rank_value_norm": rank_of_first([s / max(t, 1) for s, t in val]),
            "rank_sentence": rank_of_first([s for s, _ in sen]),
            "rank_sentence_norm": rank_of_first([s / max(t, 1) for s, t in sen]),
        }
    return out


def ranking_summary(table, by: Sequence[str] = ("checkpoint", "prompt_mode", "eval_set")):
    """Accuracy (rank 1) and MRR per group for each of the four rank columns."""
    g = table.groupby(list(by), sort=True)
    cols = {"n": ("rank_value", "size")}
    for c in RANK_COLUMNS:
        cols[f"{c}_acc"] = (c, lambda s: float((s == 1).mean()))
        cols[f"{c}_mrr"] = (c, lambda s: float((1.0 / s).mean()))
    return g.agg(**cols).reset_index()

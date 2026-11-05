"""Oracle mock scorers with known ground truth, for harness tests and ``--mock`` runs.

Additive model: ``score(entity e, value v_o) = prior[o] + (bind[(o, prompt)] if e owns v_o)``.
For fact ``e`` and a prompt ``k`` the harness must then find

* ``binding_score == bind[(e, k)]``  (the baseline is ``prior[e]``);
* ``rank == 1 + #{o != e : prior[o] >= prior[e] + bind[(e, k)]}``;
* ``stored == (rank == 1 and bind[(e, k)] > 0)``.
"""

from __future__ import annotations

import random
from collections.abc import Mapping

from slm.eval.interface import MockScorer
from slm.eval.probes import ProbeSet, continuation


def oracle_scorer(
    probes: ProbeSet,
    prior: Mapping[str, float],
    bind: Mapping[tuple[str, str], float],
    *,
    noise: float = 0.0,
    seed: int = 0,
) -> MockScorer:
    fact_of_value: dict[tuple[str, str], str] = {}
    for it in probes.items:
        fact_of_value[it.attribute_id, it.value] = it.fact_id
    table: dict[tuple[str, str], float] = {}
    for it in probes.items:
        own = it.fact_id
        for cand in it.candidates:
            o = fact_of_value[it.attribute_id, cand]
            extra = bind[(own, it.prompt)] if o == own else 0.0
            table[(it.prompt, continuation(cand))] = prior[o] + extra
        cont = continuation(it.value)
        for p in it.baseline_prompts:
            table[(p, cont)] = prior[own]
    return MockScorer(table, noise=noise, seed=seed)


def random_ground_truth(
    probes: ProbeSet, seed: int
) -> tuple[dict[str, float], dict[tuple[str, str], float]]:
    """Integer priors in [-6, -1] and bindings in [-2, 3]: plenty of ties and zero bindings."""
    rng = random.Random(seed)
    prior = {f: float(rng.randint(-6, -1)) for f in sorted({i.fact_id for i in probes.items})}
    # Keyed by prompt text, not variant: the canonical prompt is shared by the val and test splits
    # and a scorer can only give identical text one score.
    bind = {(i.fact_id, i.prompt): float(rng.randint(-2, 3)) for i in probes.items}
    return prior, bind

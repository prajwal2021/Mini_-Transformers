"""Oracle mock scorers with known ground truth, for harness tests and ``--mock`` runs.

Additive model: ``score(entity i's prompt, value j) = prior[j] + (bind[(i, prompt_i)] if i == j)``.
For fact ``i`` and prompt ``k`` the harness must then find

* ``binding_score == bind[(i, k)]``  (the baseline is ``prior[i]``);
* ``rank == 1 + #{o != i : prior[o] >= prior[i] + bind[(i, k)]}``;
* ``stored == (rank == 1 and bind[(i, k)] > 0)``.

With ``bind == 0`` everywhere the scorer has no knowledge of which entity owns which value
(a pure value prior), so ``stored`` is never true and the permutation null is 0 as well.
"""

from __future__ import annotations

import random
from collections.abc import Mapping

from slm.eval.interface import MockDetailedScorer, MockScorer
from slm.eval.probes import ProbeSet, continuation, groups


def oracle_scorer(
    probes: ProbeSet,
    prior: Mapping[str, float],
    bind: Mapping[tuple[str, str], float] | None = None,
    *,
    noise: float = 0.0,
    seed: int = 0,
    detailed: bool = False,
) -> MockScorer:
    bind = bind or {}
    table: dict[tuple[str, str], float] = {}
    for items in groups(probes).values():
        for a in items:
            for b in items:
                extra = bind.get((a.fact_id, a.prompt), 0.0) if a is b else 0.0
                table[(a.prompt, continuation(b.value))] = prior[b.fact_id] + extra
    cls = MockDetailedScorer if detailed else MockScorer
    return cls(table, noise=noise, seed=seed)


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

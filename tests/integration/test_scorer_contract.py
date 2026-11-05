"""I01 2a: ModelScorer (model stream) implements the eval stream's Scorer protocols and drives the
probe harness end to end."""

import numpy as np
import pandas as pd

from slm.eval.interface import DetailedScorer, Scorer
from slm.eval.probes import (
    TABLE_COLUMNS,
    assert_no_leakage,
    build_probes,
    load_facts,
    run_probes,
)
from slm.eval_adapter import ModelScorer

from .conftest import KB_PATH


def test_model_scorer_satisfies_both_protocols(tiny_model, tokenizer):
    s = ModelScorer(tiny_model, tokenizer, device="cpu")
    assert isinstance(s, Scorer)
    assert isinstance(s, DetailedScorer)


def test_score_detailed_agrees_with_score_and_token_count(tiny_model, tokenizer):
    s = ModelScorer(tiny_model, tokenizer, device="cpu")
    prompt, cont = "The lounge manager at Caldreth is", " Elara Voss"
    lp, n = s.score_detailed(prompt, cont)
    assert lp == s.score(prompt, cont)
    assert n == len(tokenizer.encode(cont)) and n >= 2
    assert (lp, n) == s.score_details([(prompt, cont)])[0]


class _Unbatched:
    """Hides ``score_details`` so the harness takes the one-pair-at-a-time path."""

    def __init__(self, inner):
        self.inner = inner

    def score_detailed(self, prompt, continuation):
        return self.inner.score_detailed(prompt, continuation)

    def score(self, prompt, continuation):
        return self.inner.score(prompt, continuation)


def test_probe_harness_runs_with_model_scorer_and_batching_changes_nothing(tiny_model, tokenizer):
    probes = build_probes(load_facts(KB_PATH), seed=0)
    assert_no_leakage(probes)
    s = ModelScorer(tiny_model, tokenizer, device="cpu", batch_size=64)
    batched = run_probes(s, probes, checkpoint="7", seed=3)
    single = run_probes(_Unbatched(s), probes, checkpoint="7", seed=3)

    assert list(batched.columns) == TABLE_COLUMNS
    assert len(batched) == 120 * 5  # 2 val + 3 test probes per fact
    assert set(batched["norm_unit"]) == {"token"}  # score_detailed was used
    assert batched["rank"].between(1, 6).all()
    np.testing.assert_allclose(batched["true_logprob"], single["true_logprob"], atol=1e-3)
    np.testing.assert_allclose(batched["binding_score"], single["binding_score"], atol=1e-3)
    same_rank = (batched["rank"] == single["rank"]).mean()
    assert same_rank > 0.99  # near-ties may differ by float noise, nothing else may
    assert (batched["stored"] == ((batched["rank"] == 1) & (batched["binding_score"] > 0))).all()


def test_probe_counts_per_fact_are_two_val_and_three_test(tiny_model, tokenizer):
    probes = build_probes(load_facts(KB_PATH), seed=0)
    s = ModelScorer(tiny_model, tokenizer, device="cpu", batch_size=64)
    t = run_probes(s, probes, checkpoint="1", seed=0)
    per = t.groupby(["fact_id", "split", "probe_frame"]).size().unstack(["split", "probe_frame"])
    assert (per[("test", "canonical")] == 1).all() and (per[("test", "novel")] == 2).all()
    assert (per[("val", "canonical")] == 1).all() and (per[("val", "novel")] == 1).all()
    assert isinstance(t, pd.DataFrame)

"""ModelScorer tests."""

import pytest
import torch
import torch.nn.functional as F

from slm.eval_adapter import ModelScorer
from slm.model import Transformer
from slm.tokenizer import EOS_ID

from .conftest import small_config

PROMPT = "Meanwhile, the desk checks the morning list"


@pytest.fixture(scope="module")
def scorer(tokenizer):
    torch.manual_seed(0)
    model = Transformer(small_config(vocab_size=4096, context_len=64, d_model=64, dropout=0.0))
    return ModelScorer(model, tokenizer, device="cpu", batch_size=3)


def manual(scorer, ids, n_c):
    x = torch.tensor([ids])
    logits, _ = scorer.model(x)
    lp = F.log_softmax(logits[0].double(), -1)
    return sum(lp[t - 1, ids[t]].item() for t in range(len(ids) - n_c, len(ids)))


def test_matches_manual_computation(scorer):
    for cont in [" before the doors open.", " x", "\nNext line"]:
        ids, n_c = scorer.encode_pair(PROMPT, cont)
        assert n_c >= 1
        assert scorer.score(PROMPT, cont) == pytest.approx(manual(scorer, ids, n_c), abs=1e-4)
        assert scorer.score(PROMPT, cont) < 0


def test_batched_equals_single_for_mixed_lengths(scorer):
    pairs = [(PROMPT, " before the doors open."), ("The desk", " opens."),
             (PROMPT + " and then", " writes a short note"), ("Often, a clerk", " waits"),
             ("The old guide checks", " the front gate during the busy season")]
    batched = scorer.score_many(pairs)
    single = [scorer.score(p, c) for p, c in pairs]
    assert batched == pytest.approx(single, abs=1e-4)
    shuffled = scorer.score_many(pairs[::-1])[::-1]
    assert shuffled == pytest.approx(single, abs=1e-4)  # order independent


def test_leading_space_is_handled(scorer, tokenizer):
    a = scorer.encode_pair("The desk checks the", " morning list")
    b = scorer.encode_pair("The desk checks the ", "morning list")  # space on the prompt side
    assert a == b
    assert a[0] == tokenizer.encode("The desk checks the morning list")  # = joint tokenisation
    assert scorer.score("The desk checks the", " morning list") == pytest.approx(
        scorer.score("The desk checks the ", "morning list"), abs=1e-6)
    # already-spaced continuation after a spaced prompt is left alone (two spaces really there)
    ids, _ = scorer.encode_pair("The desk ", " opens")
    assert ids == tokenizer.encode("The desk") + tokenizer.encode(" ") + tokenizer.encode(" opens")
    # a prompt that is only a space cannot be shifted into an empty prompt
    assert ScorerAdjust(" ", "x") == (" ", "x")


def ScorerAdjust(p, c):  # noqa: N802
    return ModelScorer.adjust_boundary(p, c)


def test_continuation_does_not_leak_into_context(scorer, tokenizer):
    # 1) chain rule: score(p, a+b) == score(p, a) + score(p+a, b)  (only true without leakage)
    a, b = " before the doors", " open."
    whole = scorer.score(PROMPT, a + b)
    chained = scorer.score(PROMPT, a) + scorer.score(PROMPT + a, b)
    assert whole == pytest.approx(chained, abs=1e-4)
    # 2) first continuation token's log-prob comes from prompt-only logits
    p_ids = tokenizer.encode(PROMPT)
    first = tokenizer.encode(a)[0]
    logits, _ = scorer.model(torch.tensor([p_ids]))
    expect = F.log_softmax(logits[0, -1].double(), -1)[first].item()
    one_token = scorer.score(PROMPT, tokenizer.decode([first]))
    assert one_token == pytest.approx(expect, abs=1e-4)
    # 3) the prompt ids never change with the continuation
    ids1, n1 = scorer.encode_pair(PROMPT, " alpha")
    ids2, n2 = scorer.encode_pair(PROMPT, " a much longer continuation")
    assert ids1[: len(p_ids)] == ids2[: len(p_ids)] == p_ids
    # 4) no <|eos|> or other token is appended
    assert EOS_ID not in ids1


def test_edge_cases(scorer):
    assert scorer.score(PROMPT, "") == 0.0
    with pytest.raises(ValueError, match="empty prompt"):
        scorer.score("", " hello")
    long_prompt = " ".join(["desk"] * 200)
    ids, n_c = scorer.encode_pair(long_prompt, " opens")
    assert len(ids) == scorer.context_len and n_c >= 1  # prompt trimmed from the left
    assert ids[-n_c:] == scorer.tokenizer.encode(" opens")
    assert scorer.score(long_prompt, " opens") < 0
    with pytest.raises(ValueError, match="does not fit"):
        scorer.score("a", "word " * 200)


def test_model_in_eval_and_no_grad(scorer):
    assert not scorer.model.training
    scorer.score(PROMPT, " list")
    assert all(p.grad is None for p in scorer.model.parameters())

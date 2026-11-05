"""Greedy decoder."""

import torch
from torch import nn

from slm.generation import generate_ids, generate_text, greedy_generate, newline_token_ids
from slm.model import ModelConfig, Transformer
from slm.tokenizer import EOS_ID


def real_model(ctx=64, vocab=64):
    torch.manual_seed(1)
    cfg = ModelConfig(vocab_size=vocab, context_len=ctx, n_layer=2, n_head=4, d_model=32,
                      d_ff=128, dropout=0.1)
    return Transformer(cfg)


class Scripted(nn.Module):
    """Stand-in model: the next token is script[number of tokens generated so far]."""

    def __init__(self, script, prompt_len, ctx=32, vocab=16):
        super().__init__()
        self.cfg = ModelConfig(vocab_size=vocab, context_len=ctx, n_layer=1, n_head=1,
                               d_model=4, d_ff=8)
        self.w = nn.Parameter(torch.zeros(1))
        self.script, self.prompt_len, self.vocab = script, prompt_len, vocab
        self.seen = []

    def forward(self, x, doc_ids=None):
        self.seen.append((x.clone(), None if doc_ids is None else doc_ids.clone()))
        n_gen = x.size(1) - self.prompt_len
        logits = torch.zeros(1, x.size(1), self.vocab)
        logits[0, -1, self.script[min(n_gen, len(self.script) - 1)]] = 1.0
        return logits, None


def test_deterministic_and_model_mode_restored():
    m = real_model().train()
    a = greedy_generate(m, [5, 6, 7], max_new_tokens=10)
    b = greedy_generate(m, [5, 6, 7], max_new_tokens=10)
    assert a == b and len(a.token_ids) <= 10 and m.training  # dropout 0.1 did not leak in


def test_equals_argmax_of_logits_step_by_step():
    m = real_model().eval()
    prompt = [3, 9, 4, 11]
    gen = greedy_generate(m, prompt, max_new_tokens=12, eos_id=-1)  # eos never fires
    ids = list(prompt)
    for tok in gen.token_ids:
        with torch.no_grad():
            logits, _ = m(torch.tensor([ids]))  # plain causal pass, no doc mask
        assert tok == int(logits[0, -1].argmax())
        ids.append(tok)
    assert len(gen.token_ids) == 12 and gen.stopped == "max"


def test_stops_at_eos_without_emitting_it():
    m = Scripted([5, 6, EOS_ID, 7], prompt_len=3)
    g = greedy_generate(m, [1, 2, 3], max_new_tokens=10)
    assert g.token_ids == [5, 6] and g.stopped == "eos"
    assert len(m.seen) == 3  # three forward passes, then it stopped


def test_stop_ids_end_generation_and_are_kept():
    m = Scripted([5, 9, 6], prompt_len=2)
    g = greedy_generate(m, [1, 2], max_new_tokens=10, stop_ids={9})
    assert g.token_ids == [5, 9] and g.stopped == "stop"


def test_max_new_tokens_limit():
    m = Scripted([5], prompt_len=2)
    g = greedy_generate(m, [1, 2], max_new_tokens=4)
    assert g.token_ids == [5, 5, 5, 5] and g.stopped == "max"


def test_uses_a_single_document_mask():
    m = Scripted([5, EOS_ID], prompt_len=2)
    greedy_generate(m, [1, 2], max_new_tokens=4)
    for x, d in m.seen:
        assert d is not None and d.shape == x.shape and bool((d == 1).all())


def test_long_prompt_is_truncated_from_the_left_and_counted():
    ctx, new = 32, 8
    m = Scripted([EOS_ID], prompt_len=ctx - new, ctx=ctx)
    prompt = list(range(1, 41))  # 40 tokens, room for 24
    g = greedy_generate(m, prompt, max_new_tokens=new)
    assert g.truncated_prompt and g.n_dropped == 16
    assert m.seen[0][0][0].tolist() == prompt[16:]  # the END of the prompt is kept
    short = greedy_generate(Scripted([EOS_ID], prompt_len=5, ctx=ctx), prompt[:5], new)
    assert not short.truncated_prompt and short.n_dropped == 0


def test_full_length_generation_never_exceeds_the_context():
    m = real_model(ctx=24)
    g = greedy_generate(m, list(range(3, 40)), max_new_tokens=8, eos_id=-1)
    assert g.n_dropped == 37 - 16 and len(g.token_ids) == 8  # 16 + 8 == context


def test_errors():
    import pytest

    m = real_model()
    with pytest.raises(ValueError):
        greedy_generate(m, [], 4)
    with pytest.raises(ValueError):
        greedy_generate(m, [1], 0)
    with pytest.raises(ValueError):
        greedy_generate(m, [1], m.cfg.context_len)


def test_generate_text_and_newline_ids(tokenizer):
    nl = newline_token_ids(tokenizer)
    assert nl and all(b"\n" in tokenizer.token_bytes(i) for i in nl)
    assert tokenizer.encode("\n")[0] in nl
    torch.manual_seed(0)
    cfg = ModelConfig(vocab_size=tokenizer.vocab_size, context_len=64, n_layer=1, n_head=2,
                      d_model=16, d_ff=32, dropout=0.0)
    text, gen = generate_text(Transformer(cfg), tokenizer, "Question: hi\nAnswer:", 6, nl)
    assert isinstance(text, str) and len(gen.token_ids) <= 6


def test_sampling_is_seeded_and_temperature_zero_is_greedy():
    m = real_model()
    kw = dict(max_new_tokens=12, eos_id=-1)
    a = generate_ids(m, [3, 9, 4], temperature=1.0, seed=5, **kw)
    assert a == generate_ids(m, [3, 9, 4], temperature=1.0, seed=5, **kw)
    seeds = {tuple(generate_ids(m, [3, 9, 4], temperature=1.5, seed=s, **kw).token_ids)
             for s in range(8)}
    assert len(seeds) > 1  # different seeds give different samples
    greedy = greedy_generate(m, [3, 9, 4], 12, -1)
    assert generate_ids(m, [3, 9, 4], temperature=0.0, **kw) == greedy


def test_top_k_restricts_the_candidates():
    m = real_model()
    prompt = [3, 9, 4]
    with torch.no_grad():
        top3 = set(torch.topk(m.eval()(torch.tensor([prompt]))[0][0, -1], 3).indices.tolist())
    firsts = {generate_ids(m, prompt, 1, eos_id=-1, temperature=5.0, top_k=3, seed=s).token_ids[0]
              for s in range(40)}
    assert firsts <= top3 and len(firsts) > 1
    k1 = generate_ids(m, prompt, 6, eos_id=-1, temperature=5.0, top_k=1, seed=3)
    assert k1.token_ids == greedy_generate(m, prompt, 6, -1).token_ids  # top-1 is greedy


def test_sampling_argument_errors():
    import pytest

    m = real_model()
    with pytest.raises(ValueError):
        generate_ids(m, [1], 3, temperature=-1.0)
    with pytest.raises(ValueError):
        generate_ids(m, [1], 3, temperature=1.0, top_k=0)
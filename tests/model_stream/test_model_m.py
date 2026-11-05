"""Transformer tests (fast, CPU unless marked gpu)."""

import math

import pytest
import torch
import torch.nn.functional as F

from slm.model import (
    ModelConfig,
    Transformer,
    count_parameters,
    expected_parameters,
    load_checkpoint,
    save_checkpoint,
)

from .conftest import small_config

CONFIG_YAML = "configs/model.yaml"


def real_cfg():
    from pathlib import Path

    return ModelConfig.from_yaml(Path(__file__).resolve().parents[2] / CONFIG_YAML)


def test_real_config_param_count():
    cfg = real_cfg()
    assert (cfg.n_layer, cfg.n_head, cfg.d_model, cfg.context_len, cfg.vocab_size) == (
        6, 6, 384, 512, 4096)
    model = Transformer(cfg)
    n = count_parameters(model)
    assert 10_000_000 <= n <= 14_000_000
    assert n == expected_parameters(cfg) == 12_417_024


def test_param_formula_matches_for_untied_and_small():
    for cfg in (small_config(), small_config(tie_embeddings=False, n_layer=3)):
        assert count_parameters(Transformer(cfg)) == expected_parameters(cfg)


def test_tied_embeddings_share_storage():
    m = Transformer(small_config())
    assert m.lm_head.weight is m.tok_emb.weight


def test_output_shapes(small_model):
    x = torch.randint(0, 128, (3, 20))
    logits, loss = small_model(x)
    assert logits.shape == (3, 20, 128) and loss is None
    logits, loss, attn = small_model(x, labels=x, return_attn=True)
    assert loss.ndim == 0 and len(attn) == 2 and attn[0].shape == (3, 4, 20, 20)
    assert torch.allclose(attn[0].sum(-1), torch.ones(3, 4, 20), atol=1e-5)
    assert torch.equal(attn[0].triu(1), torch.zeros_like(attn[0]))  # nothing above the diagonal


def test_context_limit(small_model):
    with pytest.raises(ValueError):
        small_model(torch.zeros(1, 33, dtype=torch.long))


def test_causality_future_change_leaves_past_bit_identical(small_model):
    torch.manual_seed(1)
    x = torch.randint(0, 128, (2, 24))
    base, _ = small_model(x)
    for t in (0, 7, 15, 23):
        y = x.clone()
        y[:, t:] = (y[:, t:] + 1) % 128  # change positions >= t
        out, _ = small_model(y)
        assert torch.equal(out[:, :t], base[:, :t])
        if t < 23:
            assert not torch.equal(out[:, t:], base[:, t:])


def test_manual_attention_matches_sdpa(small_model):
    """Test-only: compare the explicit attention to torch's reference kernel."""
    torch.manual_seed(2)
    attn = small_model.blocks[0].attn
    x = torch.randn(2, 16, 64)
    out, _ = attn(x)
    B, T, _ = x.shape
    sp = lambda t: t.view(B, T, 4, 16).transpose(1, 2)  # noqa: E731
    ref = F.scaled_dot_product_attention(
        sp(attn.W_Q(x)), sp(attn.W_K(x)), sp(attn.W_V(x)), is_causal=True
    )
    ref = attn.W_O(ref.transpose(1, 2).reshape(B, T, -1))
    assert torch.allclose(out, ref, atol=1e-5, rtol=1e-4)


def test_init_loss_is_ln_vocab():
    torch.manual_seed(0)
    cfg = small_config(vocab_size=512)
    m = Transformer(cfg).eval()
    x = torch.randint(0, 512, (8, 32))
    y = torch.randint(0, 512, (8, 32))  # independent targets (tied weights favour y == x)
    _, loss = m(x, labels=y)
    assert abs(loss.item() - math.log(512)) < 0.1


def test_labels_ignore_index():
    torch.manual_seed(0)
    m = Transformer(small_config()).eval()
    x = torch.randint(0, 128, (2, 10))
    lab = x.clone()
    lab[:, 5:] = -100
    logits, loss = m(x, labels=lab)
    ref = F.cross_entropy(logits[:, :5].reshape(-1, 128), x[:, :5].reshape(-1))
    assert torch.allclose(loss, ref, atol=1e-6)


def _overfit(cfg, device, steps=300, lr=2e-3, seq=32, n=16):
    torch.manual_seed(0)
    m = Transformer(cfg).to(device).train()
    opt = torch.optim.AdamW(m.parameters(), lr=lr, weight_decay=0.0)
    x = torch.randint(3, cfg.vocab_size, (n, seq), device=device)
    lab = x.clone()
    lab[:, :-1] = x[:, 1:]
    lab[:, -1] = -100
    first = last = None
    for _ in range(steps):
        _, loss = m(x, labels=lab)
        opt.zero_grad()
        loss.backward()
        opt.step()
        first = first if first is not None else loss.item()
        last = loss.item()
    return first, last


def test_overfit_16_sequences_cpu():
    first, last = _overfit(small_config(vocab_size=256, d_model=64), "cpu")
    assert first > 4.5 and last < 0.1


def test_gradients_finite_and_reach_every_parameter():
    torch.manual_seed(0)
    m = Transformer(small_config(dropout=0.1)).train()
    x = torch.randint(0, 128, (4, 16))
    _, loss = m(x, labels=x)
    loss.backward()
    for name, p in m.named_parameters():
        assert p.grad is not None, name
        assert torch.isfinite(p.grad).all(), name
        assert p.grad.abs().sum() > 0, name


def test_checkpoint_roundtrip_identical_logits(tmp_path, small_model):
    x = torch.randint(0, 128, (2, 16))
    ref, _ = small_model(x)
    save_checkpoint(small_model, tmp_path / "m.pt")
    loaded = load_checkpoint(tmp_path / "m.pt").eval()
    assert loaded.cfg == small_model.cfg
    out, _ = loaded(x)
    assert torch.equal(out, ref)


def test_seeds_give_reproducible_distinct_inits():
    def weights(seed):
        torch.manual_seed(seed)
        return Transformer(small_config()).state_dict()

    a, a2, b, c = weights(0), weights(0), weights(1), weights(2)
    assert all(torch.equal(a[k], a2[k]) for k in a)
    for other in (b, c):
        assert not torch.equal(a["tok_emb.weight"], other["tok_emb.weight"])
        assert not torch.equal(a["blocks.0.attn.W_Q.weight"], other["blocks.0.attn.W_Q.weight"])
    assert not torch.equal(b["tok_emb.weight"], c["tok_emb.weight"])


@pytest.mark.gpu
def test_bf16_forward_gpu():
    torch.manual_seed(0)
    m = Transformer(small_config()).cuda().eval()
    x = torch.randint(0, 128, (2, 16), device="cuda")
    with torch.autocast("cuda", dtype=torch.bfloat16):
        logits, loss = m(x, labels=x)
    assert torch.isfinite(logits.float()).all() and torch.isfinite(loss)
    ref, _ = m(x)
    assert (logits.float() - ref).abs().max() < 0.1


@pytest.mark.gpu
def test_real_config_overfits_on_gpu():
    cfg = ModelConfig(dropout=0.0)
    first, last = _overfit(cfg, "cuda", steps=300, lr=1e-3, seq=64)
    assert first > 7 and last < 0.1

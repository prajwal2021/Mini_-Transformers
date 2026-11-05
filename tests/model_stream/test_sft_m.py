"""SFT data, loss masking, trainer (early stopping, resume), seed pairing."""

import json

import pytest
import torch
import torch.nn.functional as F

from slm.model import ModelConfig, Transformer, load_checkpoint, save_checkpoint
from slm.sft_train import (
    SFTConfig,
    SFTDataset,
    build_prompt,
    collate,
    encode_rows,
    final_pretrain_checkpoint,
    prepare_sft_data,
    run_sft_seeds,
    sft_run,
)
from slm.split_manifest import build_manifest
from slm.tokenizer import EOS_ID, PAD_ID


def make_rows(n, offset=0):
    rows = []
    for i in range(offset, offset + n):
        q = f"What is the code for item {i}?"
        rows.append({"id": f"r{i}", "question": q, "prompt": build_prompt(q),
                     "answer": f"The code for item {i} is AB-{i * 7 % 100}.",
                     "value": f"AB-{i * 7 % 100}", "fact_id": f"F{i}", "subset": "x",
                     "attribute_id": "a", "freq_bin": "low", "div_bin": "templated",
                     "template_id": "t"})
    return rows


def tiny_cfg_model(tok):
    return ModelConfig(vocab_size=tok.vocab_size, context_len=96, n_layer=2, n_head=4,
                       d_model=64, d_ff=256, dropout=0.0)


def pretrained(tmp_path, tok, seed=0, name="pre.pt"):
    torch.manual_seed(seed)
    path = tmp_path / name
    save_checkpoint(Transformer(tiny_cfg_model(tok)), path, {"epoch": 3})
    return path


def sft_cfg(**kw):
    base = dict(epochs=4, batch_size=4, lr=3e-3, warmup_steps=2, log_every=1, bf16=False,
                patience=99, val_batch_size=8)
    base.update(kw)
    return SFTConfig(**base)


def datasets(tok, n_train=8, n_val=4):
    return (SFTDataset(encode_rows(tok, make_rows(n_train), 96)),
            SFTDataset(encode_rows(tok, make_rows(n_val, offset=50), 96)))


# ---- masking -----------------------------------------------------------------------------------
def test_prompt_tokens_carry_no_loss_and_eos_does(tokenizer):
    (ex,) = encode_rows(tokenizer, make_rows(1), 96)
    labels = ex.labels()
    p, a = len(ex.prompt_ids), len(ex.answer_ids)
    ids = ex.input_ids
    assert len(ids) == len(labels) == p + a
    assert all(v == -100 for v in labels[: p - 1])  # no loss on any prompt prediction
    assert labels[p - 1 : p + a - 1] == list(ex.answer_ids)  # answer tokens, then <|eos|>
    assert ex.answer_ids[-1] == EOS_ID and labels[p + a - 2] == EOS_ID  # eos carries loss
    assert labels[-1] == -100  # nothing follows eos
    assert sum(v != -100 for v in labels) == a
    assert tokenizer.decode(ex.prompt_ids) == build_prompt(make_rows(1)[0]["question"])
    assert tokenizer.decode(ex.answer_ids).startswith(" The code for item 0")


def test_loss_equals_cross_entropy_over_answer_positions_only(tokenizer):
    torch.manual_seed(0)
    model = Transformer(tiny_cfg_model(tokenizer)).eval()
    exs = encode_rows(tokenizer, make_rows(3), 96)
    b = collate(exs)
    with torch.no_grad():
        logits, loss = model(b["input_ids"], doc_ids=b["doc_ids"], labels=b["labels"])
        manual = []
        for i, e in enumerate(exs):
            ids = torch.tensor([e.input_ids])
            lg, _ = model(ids)  # no padding, plain causal
            p = len(e.prompt_ids)
            manual.append(F.cross_entropy(lg[0, p - 1 : -1], ids[0, p:], reduction="sum"))
        n = sum(len(e.answer_ids) for e in exs)
    assert float(loss) == pytest.approx(float(sum(manual)) / n, rel=1e-4)
    # changing a prompt token's label slot changes nothing: there is no label there
    assert (b["labels"][:, 0] == -100).all()


def test_collate_pads_and_masks(tokenizer):
    exs = encode_rows(tokenizer, make_rows(3), 96)
    b = collate(exs)
    for i, e in enumerate(exs):
        n = len(e.input_ids)
        assert (b["input_ids"][i, n:] == PAD_ID).all() and (b["labels"][i, n:] == -100).all()
        assert (b["doc_ids"][i, :n] == 1).all() and (b["doc_ids"][i, n:] == 0).all()


def test_template_and_length_guards(tokenizer):
    bad = make_rows(1)
    bad[0]["prompt"] = "Q: something else\nA:"
    with pytest.raises(ValueError, match="template"):
        encode_rows(tokenizer, bad, 96)
    with pytest.raises(ValueError, match="exceed"):
        encode_rows(tokenizer, make_rows(1), 10)


def test_epoch_order_depends_only_on_seed_and_epoch(tokenizer):
    ds, _ = datasets(tokenizer)
    a = [b["input_ids"].tolist() for b in ds.epoch(3, epoch=2, seed=1)]
    assert a == [b["input_ids"].tolist() for b in ds.epoch(3, epoch=2, seed=1)]
    assert a != [b["input_ids"].tolist() for b in ds.epoch(3, epoch=3, seed=1)]
    flat = [e for b in ds.epoch(3, epoch=2, seed=1) for e in b["input_ids"]]
    assert len(flat) == len(ds)  # every example exactly once


# ---- trainer -----------------------------------------------------------------------------------
def test_loss_decreases_on_a_tiny_set(tmp_path, tokenizer):
    tr, va = datasets(tokenizer)
    s = sft_run(pretrained(tmp_path, tokenizer), sft_cfg(epochs=12), tr, va, tmp_path / "run", 0,
                device="cpu")
    rows = [r for r in (tmp_path / "run" / "loss.csv").read_text().splitlines()[1:]
            if r.startswith("train")]
    train = [float(r.split(",")[4]) for r in rows]
    assert train[-1] < 0.5 * train[0]
    vals = list(s["val_by_epoch"].values())
    assert min(vals) < vals[0]


def test_run_directory_and_best_checkpoint(tmp_path, tokenizer):
    tr, va = datasets(tokenizer)
    pre = pretrained(tmp_path, tokenizer)
    s = sft_run(pre, sft_cfg(epochs=3), tr, va, tmp_path / "run", 2, device="cpu")
    run = tmp_path / "run"
    for f in ("config.yaml", "meta.json", "loss.csv", "summary.json"):
        assert (run / f).exists(), f
    meta = json.loads((run / "meta.json").read_text())
    assert meta["seed"] == 2 and len(meta["pretrained_sha256"]) == 64
    assert "commit" in meta["git"] and meta["sft_train_hash"] == tr.data_hash()
    names = sorted(p.name for p in (run / "checkpoints").glob("*.pt"))
    assert names == ["best.pt", "epoch_001.pt", "epoch_002.pt", "epoch_003.pt", "last.pt"]
    best = load_checkpoint(run / "checkpoints" / "best.pt")
    ref = load_checkpoint(run / "checkpoints" / f"epoch_{s['best_epoch']:03d}.pt")
    assert all(torch.equal(a, b) for a, b in zip(best.state_dict().values(),
                                                 ref.state_dict().values(), strict=True))
    blob = torch.load(run / "checkpoints" / "best.pt", weights_only=True)  # CPU-loadable
    assert blob["val_loss"] == s["best_val_loss"]


def test_starts_from_the_pretrained_weights_and_changes_them(tmp_path, tokenizer):
    tr, va = datasets(tokenizer)
    pre = pretrained(tmp_path, tokenizer)
    sft_run(pre, sft_cfg(epochs=1, lr=0.0), tr, va, tmp_path / "frozen", 0, device="cpu")
    a, b = load_checkpoint(pre), load_checkpoint(tmp_path / "frozen/checkpoints/epoch_001.pt")
    assert all(torch.equal(x, y) for x, y in zip(a.state_dict().values(),
                                                 b.state_dict().values(), strict=True))
    sft_run(pre, sft_cfg(epochs=1), tr, va, tmp_path / "moved", 0, device="cpu")
    c = load_checkpoint(tmp_path / "moved/checkpoints/epoch_001.pt")
    assert not torch.equal(a.tok_emb.weight, c.tok_emb.weight)


def test_early_stopping_on_val_loss(tmp_path, tokenizer):
    tr, va = datasets(tokenizer)
    s = sft_run(pretrained(tmp_path, tokenizer), sft_cfg(epochs=6, lr=0.0, patience=2), tr, va,
                tmp_path / "run", 0, device="cpu")
    # lr 0: the val loss never improves after epoch 1 -> stop after epoch 3
    assert s["epochs_done"] == 3 and s["stopped_early"] and s["best_epoch"] == 1
    s2 = sft_run(pretrained(tmp_path, tokenizer), sft_cfg(epochs=3, patience=99), tr, va,
                 tmp_path / "run2", 0, device="cpu")
    assert s2["epochs_done"] == 3 and not s2["stopped_early"]


def test_resume_matches_an_uninterrupted_run(tmp_path, tokenizer):
    tr, va = datasets(tokenizer)
    pre = pretrained(tmp_path, tokenizer)
    cfg = sft_cfg(epochs=4, dropout=0.1)  # dropout on: the RNG state must be restored too
    sft_run(pre, cfg, tr, va, tmp_path / "full", 3, device="cpu")
    sft_run(pre, cfg, tr, va, tmp_path / "part", 3, device="cpu", stop_after_epoch=2)
    assert not (tmp_path / "part/checkpoints/epoch_003.pt").exists()
    s = sft_run(pre, cfg, tr, va, tmp_path / "part", 3, device="cpu")  # resumes at epoch 2
    assert s["epochs_done"] == 4
    a = load_checkpoint(tmp_path / "full/checkpoints/epoch_004.pt")
    b = load_checkpoint(tmp_path / "part/checkpoints/epoch_004.pt")
    assert all(torch.equal(x, y) for x, y in zip(a.state_dict().values(),
                                                 b.state_dict().values(), strict=True))
    steps = [int(r.split(",")[1]) for r in (tmp_path / "part/loss.csv").read_text().splitlines()[1:]
             if r.startswith("train")]
    assert steps == sorted(set(steps))  # no duplicated rows after the resume


def test_dropout_override(tmp_path, tokenizer):
    import yaml

    tr, va = datasets(tokenizer)
    sft_run(pretrained(tmp_path, tokenizer), sft_cfg(epochs=1, dropout=0.2), tr, va,
            tmp_path / "run", 0, device="cpu")
    cfg = yaml.safe_load((tmp_path / "run/config.yaml").read_text())
    assert cfg["model"]["dropout"] == 0.2 and cfg["sft"]["dropout"] == 0.2


def test_sft_yaml_loads_with_the_design_values():
    from pathlib import Path

    cfg = SFTConfig.from_yaml(Path(__file__).resolve().parents[2] / "configs" / "sft.yaml")
    assert cfg.lr == 1e-4 and cfg.epochs == 6 and cfg.seeds == (0, 1, 2)
    assert cfg.max_new_tokens == 48 and cfg.dropout is None and cfg.decay_embeddings is True


# ---- seed pairing --------------------------------------------------------------------------------
def test_each_seed_starts_from_its_own_final_pretraining_checkpoint(tmp_path, tokenizer):
    root = tmp_path / "pre"
    for seed in (0, 1):
        d = root / f"seed{seed}" / "checkpoints"
        d.mkdir(parents=True)
        for ep in (1, 3, 12):
            torch.manual_seed(100 * seed + ep)
            save_checkpoint(Transformer(tiny_cfg_model(tokenizer)), d / f"epoch_{ep:03d}.pt")
        (d / "last.pt").write_bytes(b"not a model")
    assert final_pretrain_checkpoint(root / "seed1").name == "epoch_012.pt"
    sft = tmp_path / "sft"
    sft.mkdir()
    for name, rows in (("sft_train.jsonl", make_rows(8)), ("sft_val.jsonl", make_rows(4, 50))):
        (sft / name).write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    m = build_manifest({sft / "sft_train.jsonl": "train", sft / "sft_val.jsonl": "val"},
                       sft / "splits.json")
    assert [len(d) for d in prepare_sft_data(m, tokenizer, 96)] == [8, 4]
    out = run_sft_seeds("sft", root, m, tokenizer, sft_cfg(epochs=1), context_len=96,
                        runs_root=tmp_path / "runs", seeds=(0, 1), device="cpu")
    assert set(out["seeds"]) == {0, 1}
    for seed in (0, 1):
        meta = json.loads((tmp_path / "runs/sft" / f"seed{seed}" / "meta.json").read_text())
        assert meta["pretrained"].endswith(f"seed{seed}\\checkpoints\\epoch_012.pt") or \
            meta["pretrained"].endswith(f"seed{seed}/checkpoints/epoch_012.pt")
        assert meta["pretrained_sha256"] and meta["seed"] == seed

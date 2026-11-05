"""Training-loop pieces (fast, CPU) and a GPU run."""

import csv
import math
import random

import numpy as np
import pytest
import torch

from slm.data_loading import PackedDataset, tokenize_split, write_stats
from slm.model import Transformer, load_checkpoint
from slm.train import TrainConfig, TrainingAborted, lr_at, param_groups, train_run
from slm.train.sweep import run_sweep, select_best

from .conftest import small_config


def tiny_ds(n=24, seed=0, vocab=128, **kw):
    rng = random.Random(seed)
    docs = [[rng.randrange(3, vocab) for _ in range(rng.randint(5, 14))] for _ in range(n)]
    return PackedDataset(docs, seq_len=32, **kw)


def tiny_cfg(**kw):
    base = dict(epochs=4, batch_size=4, lr=3e-3, warmup_steps=3, log_every=1, val_every=5,
                dropout=0.1, bf16=False, checkpoint_epochs=(1, 2, 4), val_batch_size=8)
    base.update(kw)
    return TrainConfig(**base)


# ---- schedule -----------------------------------------------------------------------------
def test_lr_schedule_shape():
    cfg = TrainConfig(lr=1e-3, min_lr_ratio=0.1, warmup_steps=10)
    total = 110
    lrs = [lr_at(s, total, cfg) for s in range(total)]
    assert lrs[0] == pytest.approx(1e-4) and lrs[9] == pytest.approx(1e-3)  # linear warmup
    assert all(a < b for a, b in zip(lrs[:9], lrs[1:10]))
    assert lrs[10] == pytest.approx(1e-3)  # peak
    assert all(a >= b for a, b in zip(lrs[10:], lrs[11:]))  # monotone cosine decay
    assert lrs[60] == pytest.approx(0.55e-3, rel=1e-6)  # half-way = mean of peak and floor
    assert lrs[-1] == pytest.approx(1e-4, rel=0.02)
    assert min(lrs[10:]) >= 1e-4 - 1e-12


def test_checkpoint_schedule():
    assert TrainConfig().save_epochs() == [1, 2, 3, 5, 8, 12, 16, 20]
    assert TrainConfig(epochs=10).save_epochs() == [1, 2, 3, 5, 8, 10]  # last always saved
    assert TrainConfig(epochs=6, checkpoint_epochs=(2, 4)).save_epochs() == [2, 4, 6]


def test_train_yaml_loads():
    from pathlib import Path

    cfg = TrainConfig.from_yaml(Path(__file__).resolve().parents[2] / "configs" / "train.yaml")
    assert cfg.seeds == (0, 1, 2) and cfg.checkpoint_epochs == (1, 2, 3, 5, 8, 12, 16, 20)
    assert cfg.weight_decay == 0.1 and cfg.betas == (0.9, 0.95) and cfg.grad_clip == 1.0


# ---- weight decay groups ---------------------------------------------------------------------
def test_weight_decay_groups():
    m = Transformer(small_config())
    decay, no_decay = param_groups(m, 0.1)
    assert decay["weight_decay"] == 0.1 and no_decay["weight_decay"] == 0.0
    names = {id(p): n for n, p in m.named_parameters()}
    dec = {names[id(p)] for p in decay["params"]}
    nod = {names[id(p)] for p in no_decay["params"]}
    assert dec | nod == set(names.values()) and not dec & nod  # a partition, tied head once
    # M-D035 (DESIGN section 5): every 2-D matrix decays, the tied embedding included;
    # only LayerNorm parameters and biases are excluded.
    assert all(n.endswith(".weight") and ".ln" not in n for n in dec)
    wq = {"blocks.0.attn.W_Q.weight", "blocks.1.attn.W_Q.weight"}
    assert {n for n in dec if "W_Q" in n} == wq
    for n, p in m.named_parameters():
        assert (n in dec) == (p.ndim >= 2), n
        if "ln" in n or n.endswith(".bias"):
            assert n in nod, n
    assert "tok_emb.weight" in dec and "pos_emb.weight" in dec
    assert not any("lm_head" in n for n in names.values())  # tied head is the same tensor
    assert m.lm_head.weight is m.tok_emb.weight
    assert sum(p.numel() for g in param_groups(m, 0.1) for p in g["params"]) == sum(
        p.numel() for p in m.parameters())


def test_weight_decay_flag_restores_old_behaviour():
    m = Transformer(small_config())
    decay, no_decay = param_groups(m, 0.1, decay_embeddings=False)
    names = {id(p): n for n, p in m.named_parameters()}
    nod = {names[id(p)] for p in no_decay["params"]}
    dec = {names[id(p)] for p in decay["params"]}
    assert {"tok_emb.weight", "pos_emb.weight"} <= nod
    assert all("emb" not in n and ".ln" not in n for n in dec) and "blocks.0.attn.W_Q.weight" in dec
    assert TrainConfig().decay_embeddings is True and TrainConfig(decay_embeddings=False).to_dict()[
        "decay_embeddings"] is False


def test_optimizer_applies_group_decay():
    m = Transformer(small_config())
    opt = torch.optim.AdamW(param_groups(m, 0.1), lr=1e-3)
    assert [g["weight_decay"] for g in opt.param_groups] == [0.1, 0.0]


# ---- labels ----------------------------------------------------------------------------------
def test_label_eos_flag():
    docs = [[5, 6, 7], [8, 9]]
    on = PackedDataset(docs, seq_len=16, label_eos=True)
    off = PackedDataset(docs, seq_len=16, label_eos=False)
    assert 2 in on.labels and 2 not in off.labels
    assert on.labels[0, :3].tolist() == [6, 7, 2] and off.labels[0, :3].tolist() == [6, 7, -100]
    assert torch.equal(on.input_ids, off.input_ids)


# ---- token cache -----------------------------------------------------------------------------
def test_token_cache(tmp_path, mock_manifest, tokenizer, mock_docs):
    a = tokenize_split(mock_manifest, "train", tokenizer, tmp_path)
    b = tokenize_split(mock_manifest, "train", tokenizer, tmp_path)
    assert a.stats["cache_hit"] is False and b.stats["cache_hit"] is True
    assert a.data_hash == b.data_hash and np.array_equal(a.ids, b.ids)
    assert a.ids.dtype == np.uint16 and a.stats["n_docs"] == 200
    docs = a.documents()
    assert len(docs) == 200 and tokenizer.decode(docs[3].tolist()) == mock_docs[3]
    assert a.ids[a.offsets[1] - 1] == tokenizer.eos_id
    assert 1.0 < a.stats["tokens_per_word"] < 1.5 and 0 < a.stats["share_docs_over_context"] < 0.2
    v = tokenize_split(mock_manifest, "val", tokenizer, tmp_path)
    write_stats([a, v], tmp_path / "stats.json")
    assert {"train", "val"} == set(__import__("json").loads((tmp_path / "stats.json").read_text()))
    other = train_tokenizer_small(mock_manifest)
    c = tokenize_split(mock_manifest, "train", other, tmp_path)
    assert c.stats["cache_hit"] is False  # keyed by tokenizer hash


def train_tokenizer_small(manifest):
    from slm.tokenizer import train_tokenizer

    return train_tokenizer(manifest, 600, 1)


# ---- runs ------------------------------------------------------------------------------------
def test_run_directory_contents(tmp_path):
    tr, va = tiny_ds(), tiny_ds(8, seed=1)
    s = train_run(small_config(), tiny_cfg(), tr, va, tmp_path / "seed0", 0,
                  meta={"tokenizer_hash": "abc", "data_hash": {"train": "d"}}, device="cpu")
    run = tmp_path / "seed0"
    for f in ("config.yaml", "meta.json", "loss.csv", "summary.json"):
        assert (run / f).exists(), f
    meta = __import__("json").loads((run / "meta.json").read_text())
    assert meta["tokenizer_hash"] == "abc" and "commit" in meta["git"] and meta["seed"] == 0
    names = sorted(p.name for p in (run / "checkpoints").glob("epoch_*.pt"))
    assert names == ["epoch_001.pt", "epoch_002.pt", "epoch_004.pt"]
    blob = torch.load(run / "checkpoints" / "epoch_002.pt", weights_only=True)
    assert blob["epoch"] == 2 and blob["step"] == 2 * math.ceil(len(tr) / 4)
    assert blob["seed"] == 0 and "val_loss" in blob
    load_checkpoint(run / "checkpoints" / "epoch_002.pt")  # still a plain model checkpoint
    rows = list(csv.DictReader((run / "loss.csv").open(encoding="utf-8")))
    assert {r["split"] for r in rows} == {"train", "val"}
    train_loss = [float(r["loss"]) for r in rows if r["split"] == "train"]
    assert train_loss[-1] < train_loss[0] and set(s["val_by_epoch"]) == {1, 2, 3, 4}
    assert s["steps"] == 4 * math.ceil(len(tr) / 4)


def _rows(path):
    rows = list(csv.DictReader(path.open(encoding="utf-8")))
    return [{k: v for k, v in r.items() if k != "elapsed_s"} for r in rows]


def test_resume_gives_identical_continuation(tmp_path):
    tr, va = tiny_ds(), tiny_ds(8, seed=1)
    cfg, mcfg = tiny_cfg(), small_config()
    train_run(mcfg, cfg, tr, va, tmp_path / "straight", 7, device="cpu")
    train_run(mcfg, cfg, tr, va, tmp_path / "split", 7, device="cpu", stop_after_epoch=2)
    assert not (tmp_path / "split" / "checkpoints" / "epoch_004.pt").exists()
    train_run(mcfg, cfg, tr, va, tmp_path / "split", 7, device="cpu")  # resumes from epoch 2
    a = torch.load(tmp_path / "straight" / "checkpoints" / "epoch_004.pt", weights_only=True)
    b = torch.load(tmp_path / "split" / "checkpoints" / "epoch_004.pt", weights_only=True)
    assert a["step"] == b["step"]
    assert all(torch.equal(a["state_dict"][k], b["state_dict"][k]) for k in a["state_dict"])
    assert _rows(tmp_path / "straight" / "loss.csv") == _rows(tmp_path / "split" / "loss.csv")


def test_resume_discards_rows_from_a_crashed_partial_epoch(tmp_path):
    tr, va = tiny_ds(), tiny_ds(8, seed=1)
    run = tmp_path / "r"
    train_run(small_config(), tiny_cfg(), tr, va, run, 0, device="cpu", stop_after_epoch=1)
    with (run / "loss.csv").open("a", encoding="utf-8") as f:
        f.write("train,9999,2,0,1.0,1e-3,1.0,0.0\n")  # as if killed mid epoch 2
    train_run(small_config(), tiny_cfg(), tr, va, run, 0, device="cpu")
    steps = [int(r["step"]) for r in csv.DictReader((run / "loss.csv").open(encoding="utf-8"))]
    assert 9999 not in steps and steps == sorted(steps)


def test_seeds_change_init_and_data_order(tmp_path):
    tr, va = tiny_ds(), tiny_ds(8, seed=1)
    cfg = tiny_cfg(epochs=1, checkpoint_epochs=(1,))
    for s in (0, 1):
        train_run(small_config(), cfg, tr, va, tmp_path / f"s{s}", s, device="cpu")
    w = [torch.load(tmp_path / f"s{s}" / "checkpoints" / "epoch_001.pt", weights_only=True)
         ["state_dict"]["tok_emb.weight"] for s in (0, 1)]
    assert not torch.equal(w[0], w[1])
    order = lambda s, e: next(tr.epoch(4, epoch=e, seed=s))["input_ids"]  # noqa: E731
    assert not torch.equal(order(0, 1), order(1, 1)) and not torch.equal(order(0, 1), order(0, 2))


def test_nan_guard_aborts_with_clear_message(tmp_path, monkeypatch):
    import slm.train.pretrain as pt

    monkeypatch.setattr(pt, "lr_at", lambda step, total, cfg: float("nan"))
    with pytest.raises(TrainingAborted, match="non-finite"):
        train_run(small_config(), tiny_cfg(), tiny_ds(), tiny_ds(8, seed=1), tmp_path / "r", 0,
                  device="cpu")


def test_val_loss_is_token_weighted_and_dropout_off():
    from slm.train import evaluate

    torch.manual_seed(0)
    m = Transformer(small_config(dropout=0.3)).train()
    va = tiny_ds(8, seed=1)
    a, b = evaluate(m, va, 3, "cpu"), evaluate(m, va, 8, "cpu")
    assert a == pytest.approx(b, rel=1e-5) and m.training  # batch size irrelevant, mode restored


# ---- sweep -----------------------------------------------------------------------------------
def test_select_best_uses_validation_loss_only():
    rows = [
        {"name": "a", "status": "ok", "val_by_epoch": {"1": 3.0, "5": 2.5}, "probe_acc": 0.99,
         "test_loss": 0.1},
        {"name": "b", "status": "ok", "val_by_epoch": {"1": 2.9, "5": 2.2}, "probe_acc": 0.01,
         "test_loss": 9.9},
        {"name": "c", "status": "aborted", "val_by_epoch": {"1": 0.0}},
    ]
    best = select_best(rows)
    assert best["name"] == "b" and best["best_epoch"] == 5 and best["best_val"] == 2.2
    with pytest.raises(ValueError):
        select_best([rows[2]])


def test_run_sweep_records_every_config(tmp_path):
    tr, va = tiny_ds(), tiny_ds(8, seed=1)
    cfg = tiny_cfg(epochs=2, checkpoint_epochs=(1, 2))
    out = run_sweep(small_config(), cfg, tr, va, tmp_path, {"lr": [1e-3, 3e-3], "dropout": [0.0]},
                    device="cpu")
    res = __import__("json").loads((tmp_path / "results.json").read_text())
    assert len(res) == 2 and all(r["status"] == "ok" for r in res)
    assert (tmp_path / "chosen.json").exists() and out["chosen"]["lr"] in (1e-3, 3e-3)


# ---- GPU -------------------------------------------------------------------------------------
@pytest.mark.gpu
def test_real_model_trains_on_gpu_and_scores(tmp_path, mock_manifest, tokenizer):
    from slm.eval_adapter import ModelScorer
    from slm.model import ModelConfig
    from slm.train.runner import prepare_data

    mcfg = ModelConfig()
    cfg = TrainConfig(epochs=3, batch_size=16, warmup_steps=5, log_every=2, val_every=10,
                      checkpoint_epochs=(1, 3))
    tr, va, meta = prepare_data(mock_manifest, tokenizer, mcfg, cfg, tmp_path / "cache")
    s = train_run(mcfg, cfg, tr, va, tmp_path / "seed0", 0, meta=meta)
    assert s["val_by_epoch"][3] < s["val_by_epoch"][1] < 8.4
    tokenizer.save(tmp_path / "tok.json")
    scorer = ModelScorer.from_files(tmp_path / "seed0" / "checkpoints" / "epoch_003.pt",
                                    tmp_path / "tok.json")
    assert scorer.device.type == "cuda"
    assert math.isfinite(scorer.score("Meanwhile, the desk checks the morning list", " today."))

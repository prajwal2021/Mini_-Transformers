"""Pretraining loop (docs/DESIGN.md section 5).

One call to ``train_run`` trains one seed into ``<run_dir>`` (normally runs/<name>/seed<k>/):

    config.yaml        model + train config snapshot, seed
    meta.json          git commit, tokenizer hash, tokenized-data hash, library versions, device
    loss.csv           split,step,epoch,tokens_seen,loss,lr,grad_norm,elapsed_s
    checkpoints/       epoch_<EEE>.pt (model + step/epoch metadata) and last.pt (resume state)

Sources of non-determinism that remain are listed in docs/HPARAM_PROTOCOL.md section 5.
"""

from __future__ import annotations

import csv
import json
import math
import os
import platform
import subprocess
import time
from dataclasses import replace
from pathlib import Path

import torch
import yaml
from torch import nn

from slm.data_loading import PackedDataset
from slm.model import ModelConfig, Transformer, count_parameters, save_checkpoint

from .config import TrainConfig, lr_at

CSV_FIELDS = ["split", "step", "epoch", "tokens_seen", "loss", "lr", "grad_norm", "elapsed_s"]


class TrainingAborted(RuntimeError):
    """Training stopped on purpose (non-finite loss or gradient)."""


def param_groups(
    model: Transformer, weight_decay: float, decay_embeddings: bool = True
) -> list[dict]:
    """AdamW groups (DESIGN section 5, M-D035): decay every 2-D matrix, tied embedding included.

    Decayed: nn.Linear weight matrices and both embedding tables (the tied LM head is the token
    embedding, listed once). Not decayed: LayerNorm weights/biases and all linear biases (1-D).
    ``decay_embeddings=False`` restores the M-D024 behaviour (embedding tables not decayed).
    """
    embed_ids = {id(model.tok_emb.weight), id(model.pos_emb.weight)}
    decay, no_decay = [], []
    for _, p in model.named_parameters():  # a tied parameter is yielded once
        is_matrix = p.ndim >= 2
        if is_matrix and (decay_embeddings or id(p) not in embed_ids):
            decay.append(p)
        else:
            no_decay.append(p)
    assert len(decay) + len(no_decay) == len(list(model.parameters()))
    return [
        {"params": decay, "weight_decay": weight_decay},
        {"params": no_decay, "weight_decay": 0.0},
    ]


@torch.no_grad()
def evaluate(model: Transformer, ds: PackedDataset, batch_size: int, device) -> float:
    """Token-weighted mean cross-entropy over ``ds`` in fp32 with dropout off."""
    was_training = model.training
    model.eval()
    total, count = 0.0, 0
    for b in ds.epoch(batch_size, epoch=0, seed=0):
        b = {k: v.to(device) for k, v in b.items()}
        _, loss = model(b["input_ids"], doc_ids=b["doc_ids"], labels=b["labels"])
        n = int((b["labels"] != -100).sum())
        total += float(loss) * n
        count += n
    model.train(was_training)
    return total / max(count, 1)


def git_info() -> dict:
    root = Path(__file__).resolve().parents[3]

    def run(*args):
        return subprocess.run(
            ["git", *args], cwd=root, capture_output=True, text=True, timeout=20
        ).stdout.strip()

    try:
        commit = run("rev-parse", "HEAD") or "unknown"
        return {"commit": commit, "dirty": bool(run("status", "--short"))}
    except (OSError, subprocess.SubprocessError):
        return {"commit": "unknown", "dirty": None}


def _write_meta(run_dir: Path, seed: int, meta: dict, device, n_params: int) -> None:
    info = {
        "seed": seed,
        "git": git_info(),
        "torch": torch.__version__,
        "cuda": torch.version.cuda,
        "device": torch.cuda.get_device_name(0) if device.type == "cuda" else str(device),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "n_params": n_params,
        **meta,
    }
    (run_dir / "meta.json").write_text(json.dumps(info, indent=2), encoding="utf-8")


def _trim_csv(path: Path, max_step: int) -> None:
    """Drop rows written after the checkpoint we resume from (a crashed partial epoch)."""
    if not path.exists():
        return
    with path.open(newline="", encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f) if int(r["step"]) <= max_step]
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, CSV_FIELDS)
        w.writeheader()
        w.writerows(rows)


def train_run(
    model_cfg: ModelConfig,
    cfg: TrainConfig,
    train_ds: PackedDataset,
    val_ds: PackedDataset,
    run_dir: str | Path,
    seed: int,
    meta: dict | None = None,
    device: str | torch.device | None = None,
    resume: bool = True,
    stop_after_epoch: int | None = None,
) -> dict:
    """Train one seed; returns a summary. Resumes from ``last.pt`` (an epoch boundary) if present.

    ``stop_after_epoch`` ends the run early (used by the resume test).
    """
    run_dir = Path(run_dir)
    (run_dir / "checkpoints").mkdir(parents=True, exist_ok=True)
    device = torch.device(device or ("cuda" if torch.cuda.is_available() else "cpu"))
    cuda = device.type == "cuda"
    model_cfg = replace(model_cfg, dropout=cfg.dropout)
    if cfg.deterministic:
        os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")
        torch.use_deterministic_algorithms(True, warn_only=True)
        torch.backends.cudnn.benchmark = False
    if cuda:
        torch.backends.cuda.matmul.allow_tf32 = True
        torch.backends.cudnn.allow_tf32 = True

    torch.manual_seed(seed)
    if cuda:
        torch.cuda.manual_seed_all(seed)
    model = Transformer(model_cfg).to(device).train()
    opt = torch.optim.AdamW(
        param_groups(model, cfg.weight_decay, cfg.decay_embeddings),
        lr=cfg.lr, betas=cfg.betas, fused=cuda,
    )
    spe = math.ceil(len(train_ds) / cfg.batch_size)
    total_steps = spe * cfg.epochs
    save_epochs = set(cfg.save_epochs())

    step, start_epoch, tokens_seen, elapsed_prior = 0, 0, 0, 0.0
    last = run_dir / "checkpoints" / "last.pt"
    csv_path = run_dir / "loss.csv"
    if resume and last.exists():
        blob = torch.load(last, map_location=device, weights_only=True)
        model.load_state_dict(blob["state_dict"])
        opt.load_state_dict(blob["optimizer"])
        step, start_epoch = blob["step"], blob["epoch"]
        tokens_seen, elapsed_prior = blob["tokens_seen"], blob["elapsed_s"]
        torch.set_rng_state(blob["rng_cpu"].cpu())
        if cuda and blob.get("rng_cuda") is not None:
            torch.cuda.set_rng_state(blob["rng_cuda"].cpu())
        _trim_csv(csv_path, step)
    else:
        csv_path.unlink(missing_ok=True)
        (run_dir / "config.yaml").write_text(
            yaml.safe_dump({"seed": seed, "model": model_cfg.to_dict(), "train": cfg.to_dict()}),
            encoding="utf-8",
        )
        _write_meta(run_dir, seed, meta or {}, device, count_parameters(model))
    if not csv_path.exists():
        with csv_path.open("w", newline="", encoding="utf-8") as f:
            csv.DictWriter(f, CSV_FIELDS).writeheader()
    csv_f = csv_path.open("a", newline="", encoding="utf-8")
    writer = csv.DictWriter(csv_f, CSV_FIELDS)

    t0 = time.perf_counter()
    elapsed = lambda: elapsed_prior + time.perf_counter() - t0  # noqa: E731
    val_history: dict[int, float] = {}
    last_good, window, grad_norm = float("nan"), [], float("nan")
    lr = cfg.lr
    epoch = start_epoch

    def log(split, epoch, loss, lr_, gn):
        writer.writerow(dict(split=split, step=step, epoch=epoch, tokens_seen=tokens_seen,
                             loss=f"{loss:.6f}", lr=f"{lr_:.3e}", grad_norm=gn,
                             elapsed_s=f"{elapsed():.2f}"))
        csv_f.flush()

    try:
        for epoch in range(start_epoch + 1, cfg.epochs + 1):
            for b in train_ds.epoch(cfg.batch_size, epoch=epoch, seed=seed):
                lr = lr_at(step, total_steps, cfg)
                for g in opt.param_groups:
                    g["lr"] = lr
                b = {k: v.to(device, non_blocking=True) for k, v in b.items()}
                with torch.autocast(device.type, dtype=torch.bfloat16, enabled=cuda and cfg.bf16):
                    _, loss = model(b["input_ids"], doc_ids=b["doc_ids"], labels=b["labels"])
                loss_v = float(loss.detach())
                if not math.isfinite(loss_v):
                    raise TrainingAborted(
                        f"non-finite loss ({loss_v}) at step {step}, epoch {epoch}, seed {seed}, "
                        f"lr {lr:.3e}; last finite loss {last_good:.4f}. Lower the learning rate, "
                        f"lengthen warmup, or set bf16: false and retry."
                    )
                opt.zero_grad(set_to_none=True)
                loss.backward()
                grad_norm = float(nn.utils.clip_grad_norm_(model.parameters(), cfg.grad_clip))
                if not math.isfinite(grad_norm):
                    raise TrainingAborted(
                        f"non-finite gradient norm ({grad_norm}) at step {step}, epoch {epoch}, "
                        f"seed {seed}, lr {lr:.3e}; loss was {loss_v:.4f}."
                    )
                opt.step()
                step += 1
                tokens_seen += int((b["doc_ids"] > 0).sum())
                last_good = loss_v
                window.append(loss_v)
                if step % cfg.log_every == 0:
                    log("train", epoch, sum(window) / len(window), lr, f"{grad_norm:.4f}")
                    window = []
                if step % cfg.val_every == 0:
                    log("val", epoch, evaluate(model, val_ds, cfg.val_batch_size, device), lr, "")
            if window:
                log("train", epoch, sum(window) / len(window), lr, f"{grad_norm:.4f}")
                window = []
            val_loss = evaluate(model, val_ds, cfg.val_batch_size, device)
            val_history[epoch] = val_loss
            log("val", epoch, val_loss, lr, "")
            state = {"step": step, "epoch": epoch, "tokens_seen": tokens_seen, "seed": seed,
                     "val_loss": val_loss, "train_config": cfg.to_dict()}
            if epoch in save_epochs:
                save_checkpoint(model, run_dir / "checkpoints" / f"epoch_{epoch:03d}.pt", state)
            torch.save(
                {"state_dict": model.state_dict(), "optimizer": opt.state_dict(),
                 "rng_cpu": torch.get_rng_state(),
                 "rng_cuda": torch.cuda.get_rng_state() if cuda else None,
                 "elapsed_s": elapsed(), "step": step, "epoch": epoch,
                 "tokens_seen": tokens_seen},
                last,
            )
            if stop_after_epoch is not None and epoch >= stop_after_epoch:
                break
    finally:
        csv_f.close()
    summary = {"seed": seed, "epochs_done": epoch, "steps": step,
               "tokens_seen": tokens_seen, "val_by_epoch": val_history,
               "final_val_loss": val_history.get(epoch), "train_seconds": elapsed()}
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary

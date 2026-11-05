"""SFT loop (docs/DESIGN.md section 7.3): one call trains one seed into ``<run_dir>``.

    config.yaml    SFT config + model config + seed + the pretraining checkpoint used
    meta.json      git commit/dirty, pretraining checkpoint sha256, tokenizer hash, SFT data hashes
    loss.csv       split,step,epoch,tokens_seen,loss,lr,grad_norm,elapsed_s (train rows: mean of the
                   steps since the last row; val rows: token-weighted fp32 CE on sft_val)
    checkpoints/   epoch_<EEE>.pt every epoch, best.pt (lowest val loss), last.pt (resume state)
    summary.json   best epoch, best val loss, whether early stopping fired

Resume is at epoch boundaries only (as in pretraining, M-D028). Early stopping: stop when the val
loss has not improved by more than ``min_delta`` for ``patience`` consecutive epochs.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import platform
import shutil
import time
from dataclasses import replace
from pathlib import Path

import torch
import yaml
from torch import nn

from slm.model import ModelConfig, Transformer, count_parameters, save_checkpoint
from slm.train.config import lr_at
from slm.train.pretrain import CSV_FIELDS, TrainingAborted, _trim_csv, git_info, param_groups

from .config import SFTConfig
from .data import SFTDataset


def file_sha256(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def final_pretrain_checkpoint(seed_dir: str | Path) -> Path:
    """The highest-numbered ``epoch_<EEE>.pt`` of a pretraining run directory (its last epoch)."""
    ckpts = sorted(Path(seed_dir, "checkpoints").glob("epoch_*.pt"))
    if not ckpts:
        raise FileNotFoundError(f"no epoch checkpoints under {seed_dir}/checkpoints")
    return ckpts[-1]


@torch.no_grad()
def evaluate_sft(model: Transformer, ds: SFTDataset, batch_size: int, device) -> float:
    """Token-weighted mean cross-entropy over the supervised (answer + eos) tokens, fp32."""
    was_training = model.training
    model.eval()
    total, count = 0.0, 0
    for b in ds.ordered_batches(batch_size):
        b = {k: v.to(device) for k, v in b.items()}
        _, loss = model(b["input_ids"], doc_ids=b["doc_ids"], labels=b["labels"])
        n = int((b["labels"] != -100).sum())
        total += float(loss) * n
        count += n
    model.train(was_training)
    return total / max(count, 1)


def sft_run(
    pretrained: str | Path,
    cfg: SFTConfig,
    train_ds: SFTDataset,
    val_ds: SFTDataset,
    run_dir: str | Path,
    seed: int,
    meta: dict | None = None,
    device: str | torch.device | None = None,
    resume: bool = True,
    stop_after_epoch: int | None = None,
) -> dict:
    run_dir = Path(run_dir)
    (run_dir / "checkpoints").mkdir(parents=True, exist_ok=True)
    device = torch.device(device or ("cuda" if torch.cuda.is_available() else "cpu"))
    cuda = device.type == "cuda"
    if cuda:
        torch.backends.cuda.matmul.allow_tf32 = True
        torch.backends.cudnn.allow_tf32 = True

    blob = torch.load(pretrained, map_location="cpu", weights_only=True)
    model_cfg = ModelConfig.from_dict(blob["config"])
    if cfg.dropout is not None:
        model_cfg = replace(model_cfg, dropout=cfg.dropout)
    torch.manual_seed(seed)
    if cuda:
        torch.cuda.manual_seed_all(seed)
    model = Transformer(model_cfg)
    model.load_state_dict(blob["state_dict"])
    model = model.to(device).train()
    opt = torch.optim.AdamW(
        param_groups(model, cfg.weight_decay, cfg.decay_embeddings),
        lr=cfg.lr, betas=cfg.betas, fused=cuda,
    )
    spe = math.ceil(len(train_ds) / cfg.batch_size)
    total_steps = spe * cfg.epochs

    step, start_epoch, tokens_seen, elapsed_prior = 0, 0, 0, 0.0
    best_val, best_epoch, bad = float("inf"), 0, 0
    last = run_dir / "checkpoints" / "last.pt"
    csv_path = run_dir / "loss.csv"
    if resume and last.exists():
        st = torch.load(last, map_location=device, weights_only=True)
        model.load_state_dict(st["state_dict"])
        opt.load_state_dict(st["optimizer"])
        step, start_epoch = st["step"], st["epoch"]
        tokens_seen, elapsed_prior = st["tokens_seen"], st["elapsed_s"]
        best_val, best_epoch, bad = st["best_val"], st["best_epoch"], st["bad_epochs"]
        torch.set_rng_state(st["rng_cpu"].cpu())
        if cuda and st.get("rng_cuda") is not None:
            torch.cuda.set_rng_state(st["rng_cuda"].cpu())
        _trim_csv(csv_path, step)
    else:
        csv_path.unlink(missing_ok=True)
        (run_dir / "config.yaml").write_text(
            yaml.safe_dump({"seed": seed, "sft": cfg.to_dict(), "model": model_cfg.to_dict(),
                            "pretrained": str(pretrained)}),
            encoding="utf-8",
        )
        info = {
            "seed": seed, "git": git_info(), "torch": torch.__version__,
            "device": torch.cuda.get_device_name(0) if cuda else str(device),
            "python": platform.python_version(), "n_params": count_parameters(model),
            "pretrained": str(pretrained), "pretrained_sha256": file_sha256(pretrained),
            "sft_train_hash": train_ds.data_hash(), "sft_val_hash": val_ds.data_hash(),
            "n_train_examples": len(train_ds), "n_val_examples": len(val_ds),
            **(meta or {}),
        }
        (run_dir / "meta.json").write_text(json.dumps(info, indent=2), encoding="utf-8")
    if not csv_path.exists():
        with csv_path.open("w", newline="", encoding="utf-8") as f:
            csv.DictWriter(f, CSV_FIELDS).writeheader()
    csv_f = csv_path.open("a", newline="", encoding="utf-8")
    writer = csv.DictWriter(csv_f, CSV_FIELDS)

    t0 = time.perf_counter()
    elapsed = lambda: elapsed_prior + time.perf_counter() - t0  # noqa: E731
    val_history: dict[int, float] = {}
    window: list[float] = []
    last_good, grad_norm, lr, epoch = float("nan"), float("nan"), cfg.lr, start_epoch
    stopped_early = False

    def log(split, ep, loss, lr_, gn):
        writer.writerow(dict(split=split, step=step, epoch=ep, tokens_seen=tokens_seen,
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
                        f"non-finite SFT loss ({loss_v}) at step {step}, epoch {epoch}, seed "
                        f"{seed}, lr {lr:.3e}; last finite loss {last_good:.4f}."
                    )
                opt.zero_grad(set_to_none=True)
                loss.backward()
                grad_norm = float(nn.utils.clip_grad_norm_(model.parameters(), cfg.grad_clip))
                if not math.isfinite(grad_norm):
                    raise TrainingAborted(
                        f"non-finite gradient norm ({grad_norm}) at step {step}, epoch {epoch}, "
                        f"seed {seed}; loss was {loss_v:.4f}."
                    )
                opt.step()
                step += 1
                tokens_seen += int((b["labels"] != -100).sum())
                last_good = loss_v
                window.append(loss_v)
                if step % cfg.log_every == 0:
                    log("train", epoch, sum(window) / len(window), lr, f"{grad_norm:.4f}")
                    window = []
            if window:
                log("train", epoch, sum(window) / len(window), lr, f"{grad_norm:.4f}")
                window = []
            val_loss = evaluate_sft(model, val_ds, cfg.val_batch_size, device)
            val_history[epoch] = val_loss
            log("val", epoch, val_loss, lr, "")
            state = {"step": step, "epoch": epoch, "tokens_seen": tokens_seen, "seed": seed,
                     "val_loss": val_loss, "sft_config": cfg.to_dict()}
            ckpt = run_dir / "checkpoints" / f"epoch_{epoch:03d}.pt"
            save_checkpoint(model, ckpt, state)
            if val_loss < best_val - cfg.min_delta:
                best_val, best_epoch, bad = val_loss, epoch, 0
                shutil.copyfile(ckpt, run_dir / "checkpoints" / "best.pt")
            else:
                bad += 1
            torch.save(
                {"state_dict": model.state_dict(), "optimizer": opt.state_dict(),
                 "rng_cpu": torch.get_rng_state(),
                 "rng_cuda": torch.cuda.get_rng_state() if cuda else None,
                 "elapsed_s": elapsed(), "step": step, "epoch": epoch,
                 "tokens_seen": tokens_seen, "best_val": best_val, "best_epoch": best_epoch,
                 "bad_epochs": bad},
                last,
            )
            if bad >= cfg.patience:
                stopped_early = epoch < cfg.epochs
                break
            if stop_after_epoch is not None and epoch >= stop_after_epoch:
                break
    finally:
        csv_f.close()
    summary = {"seed": seed, "epochs_done": epoch, "steps": step, "tokens_seen": tokens_seen,
               "val_by_epoch": val_history, "best_epoch": best_epoch, "best_val_loss": best_val,
               "stopped_early": stopped_early, "train_seconds": elapsed()}
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary

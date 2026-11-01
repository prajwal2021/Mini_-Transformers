"""Run manifest creation and finalization."""

import json
import platform
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import torch

from .config import config_hash
from .device import get_device


def _git_info() -> tuple[str, bool]:
    try:
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
        dirty = bool(subprocess.check_output(["git", "status", "--porcelain"], text=True).strip())
        return commit, dirty
    except (OSError, subprocess.CalledProcessError):
        return "unknown", False


def _read(run_dir: Path) -> dict[str, Any]:
    with (run_dir / "manifest.json").open(encoding="utf-8") as handle:
        return json.load(handle)


def _write(run_dir: Path, manifest: Mapping[str, Any]) -> None:
    with (run_dir / "manifest.json").open("w", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=2, sort_keys=True)
        handle.write("\n")


def write_manifest(run_dir: str | Path, config: Mapping[str, Any]) -> dict[str, Any]:
    """Write a manifest containing reproducibility metadata."""
    path = Path(run_dir)
    commit, dirty = _git_info()
    started = datetime.now(timezone.utc)
    manifest = {
        "git_commit": commit, "git_dirty": dirty, "config": dict(config),
        "config_hash": config_hash(config), "seed": config.get("seed"),
        "python_version": platform.python_version(), "torch_version": torch.__version__,
        "platform": platform.platform(), "device": str(get_device()),
        "start_time_utc": started.isoformat(),
    }
    _write(path, manifest)
    return manifest


def finalize_manifest(
    run_dir: str | Path,
    status: str,
    extra_metrics: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Add completion metadata and optional metrics to an existing manifest."""
    path = Path(run_dir)
    manifest = _read(path)
    ended = datetime.now(timezone.utc)
    started = datetime.fromisoformat(manifest["start_time_utc"])
    manifest.update(
        {
            "end_time_utc": ended.isoformat(),
            "duration_seconds": (ended - started).total_seconds(),
            "status": status,
        }
    )
    if extra_metrics:
        manifest["extra_metrics"] = dict(extra_metrics)
    _write(path, manifest)
    return manifest

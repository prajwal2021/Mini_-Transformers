"""Test-access ledger (docs/HPARAM_PROTOCOL.md section 6, M-D039).

``open_split(manifest, split, purpose)`` is the only way to read the files of the ``test`` split:
``SplitManifest.read_verified`` refuses them unless this function is reading. Every call for
``split == "test"`` appends one JSON line to ``reports/test_access_log.jsonl`` *before* the read:

    {"ts", "split", "purpose", "git": {"commit", "dirty"}, "caller", "manifest", "files": [...]}

Reads of ``train`` and ``val`` files are verified (listed, right split, hash) but not logged.
The guard cannot stop code from opening a file path directly with ``open()``; it makes the
sanctioned route logged and every manifest-based route refuse test files.
"""

from __future__ import annotations

import contextlib
import datetime as dt
import inspect
import json
from collections.abc import Iterator
from pathlib import Path

from slm.split_manifest import _TEST_ACCESS_GRANTED, SPLITS, ManifestError, SplitManifest

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_LOG = ROOT / "reports" / "test_access_log.jsonl"


@contextlib.contextmanager
def _granted() -> Iterator[None]:
    token = _TEST_ACCESS_GRANTED.set(True)
    try:
        yield
    finally:
        _TEST_ACCESS_GRANTED.reset(token)


def _caller() -> str:
    frame = inspect.stack()[2]  # [0] _caller, [1] open_split, [2] the code that called it
    module = inspect.getmodule(frame.frame)
    return f"{module.__name__ if module else frame.filename}:{frame.function}"


def open_split(
    manifest: SplitManifest,
    split: str,
    purpose: str,
    *,
    path: str | Path | None = None,
    log_path: str | Path | None = None,
    caller: str | None = None,
) -> dict[Path, bytes]:
    """Bytes of every file listed under ``split`` (or just ``path``), keyed by resolved path.

    ``path`` must be listed in the manifest under ``split``; otherwise ``ManifestError``.
    A non-empty ``purpose`` is required for the test split.
    """
    if split not in SPLITS:
        raise ManifestError(f"unknown split {split!r}")
    if path is not None:
        entries = [manifest.entry(path)]  # raises when unlisted
        if entries[0].split != split:
            raise ManifestError(f"{entries[0].path} is marked {entries[0].split!r}, not {split!r}")
    else:
        entries = manifest.files(split)
    if not entries:
        raise ManifestError(f"the manifest lists no {split!r} files")
    if split == "test":
        if not purpose or not purpose.strip():
            raise ManifestError("reading the test split needs a purpose")
        from slm.train.pretrain import git_info

        line = {
            "ts": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            "split": split,
            "purpose": purpose,
            "git": git_info(),
            "caller": caller or _caller(),
            "manifest": str(manifest.source) if manifest.source else None,
            "files": [{"path": str(e.path), "sha256": e.sha256} for e in entries],
        }
        log = Path(log_path) if log_path else DEFAULT_LOG
        log.parent.mkdir(parents=True, exist_ok=True)
        with log.open("a", encoding="utf-8") as f:
            f.write(json.dumps(line, sort_keys=True) + "\n")
        with _granted():
            return {e.path: manifest.read_verified(e.path, (split,)) for e in entries}
    return {e.path: manifest.read_verified(e.path, (split,)) for e in entries}

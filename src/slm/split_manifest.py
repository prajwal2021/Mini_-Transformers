"""Split manifest: which file belongs to which split, pinned by SHA-256.

Format (docs/SPLIT_MANIFEST.md)::

    {"version": 1,
     "files": {"train/train_000.jsonl": {"split": "train", "sha256": "<hex>"}, ...}}

File paths are relative to the manifest's directory (POSIX separators). Every reader of
training data goes through ``SplitManifest.read_verified`` so a file is only used if the manifest
lists it, with the expected split, and its bytes still match the recorded hash.
"""

from __future__ import annotations

import contextvars
import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

SPLITS = ("train", "val", "test")
MANIFEST_VERSION = 1

# True only while slm.guard.open_split is reading (and logging) a test file.
_TEST_ACCESS_GRANTED: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "test_access_granted", default=False
)


class ManifestError(ValueError):
    """The manifest refuses a file (unlisted, wrong split, or hash mismatch)."""


@dataclass(frozen=True)
class Entry:
    path: Path
    split: str
    sha256: str

    def read_verified(self) -> bytes:
        data = self.path.read_bytes()
        got = hashlib.sha256(data).hexdigest()
        if got != self.sha256:
            raise ManifestError(
                f"hash mismatch for {self.path}: manifest says {self.sha256[:12]}..., "
                f"file is {got[:12]}... (file changed after the manifest was written)"
            )
        return data


class SplitManifest:
    def __init__(self, entries: Iterable[Entry], source: Path | None = None) -> None:
        self.entries = list(entries)
        self.source = source
        for e in self.entries:
            if e.split not in SPLITS:
                raise ManifestError(f"unknown split {e.split!r} for {e.path}")
        self._by_path = {e.path.resolve(): e for e in self.entries}

    @classmethod
    def load(cls, path: str | Path) -> SplitManifest:
        path = Path(path)
        blob = json.loads(path.read_text(encoding="utf-8"))
        if blob.get("version") != MANIFEST_VERSION:
            raise ManifestError(f"unsupported manifest version {blob.get('version')!r}")
        entries = [
            Entry((path.parent / rel).resolve(), meta["split"], meta["sha256"])
            for rel, meta in blob["files"].items()
        ]
        return cls(entries, path)

    def files(self, split: str) -> list[Entry]:
        return sorted((e for e in self.entries if e.split == split), key=lambda e: str(e.path))

    def entry(self, path: str | Path) -> Entry:
        try:
            return self._by_path[Path(path).resolve()]
        except KeyError:
            raise ManifestError(f"{path} is not listed in the split manifest") from None

    def read_verified(self, path: str | Path, allowed: Iterable[str]) -> bytes:
        """Bytes of ``path`` if it is listed, in an allowed split, and its hash matches.

        Files of the ``test`` split are readable only through ``slm.guard.open_split``, which
        records the access (M-D039); asking for them here directly is refused.
        """
        e = self.entry(path)
        if e.split not in tuple(allowed):
            raise ManifestError(
                f"{e.path} is marked {e.split!r} in the manifest; allowed here: {tuple(allowed)}"
            )
        if e.split == "test" and not _TEST_ACCESS_GRANTED.get():
            raise ManifestError(
                f"{e.path} is a test file: open it with slm.guard.open_split "
                "so the access is logged"
            )
        return e.read_verified()


def build_manifest(files: dict[str | Path, str], out_path: str | Path) -> SplitManifest:
    """Write a manifest for ``{file: split}`` (hashes computed now). Used by tests/tools."""
    out_path = Path(out_path)
    root = out_path.parent.resolve()
    table = {}
    for f, split in files.items():
        f = Path(f).resolve()
        table[f.relative_to(root).as_posix()] = {
            "split": split,
            "sha256": hashlib.sha256(f.read_bytes()).hexdigest(),
        }
    out_path.write_text(
        json.dumps({"version": MANIFEST_VERSION, "files": table}, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return SplitManifest.load(out_path)

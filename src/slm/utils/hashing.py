"""Content hashing helpers."""

import hashlib
from pathlib import Path


def file_sha256(path: str | Path) -> str:
    """Return the SHA-256 digest of a file."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def dir_sha256(path: str | Path) -> str:
    """Return a deterministic SHA-256 digest of relative paths and file contents."""
    root = Path(path)
    digest = hashlib.sha256()
    files = (candidate for candidate in root.rglob("*") if candidate.is_file())
    for item in sorted(files, key=lambda p: p.relative_to(root).as_posix()):
        relative = item.relative_to(root).as_posix().encode("utf-8")
        digest.update(relative + b"\0")
        digest.update(bytes.fromhex(file_sha256(item)))
    return digest.hexdigest()

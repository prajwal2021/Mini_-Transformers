"""Split-manifest guard tests."""

import json

import pytest

from slm.data_loading import tokenize_split
from slm.split_manifest import ManifestError, SplitManifest, build_manifest
from slm.tokenizer import BPETokenizer, read_split, train_tokenizer


def make(tmp_path, files: dict[str, tuple[str, str]]):
    """files: {name: (split, text)} -> manifest in tmp_path."""
    entries = {}
    for name, (split, text) in files.items():
        (tmp_path / name).write_text(text, encoding="utf-8")
        entries[tmp_path / name] = split
    return build_manifest(entries, tmp_path / "splits.json")


def test_roundtrip_and_format(tmp_path):
    m = make(tmp_path, {"a.txt": ("train", "hello world"), "b.txt": ("val", "bye")})
    blob = json.loads((tmp_path / "splits.json").read_text(encoding="utf-8"))
    assert blob["version"] == 1 and set(blob["files"]) == {"a.txt", "b.txt"}
    meta = blob["files"]["a.txt"]
    assert meta["split"] == "train" and len(meta["sha256"]) == 64
    assert [e.path.name for e in SplitManifest.load(tmp_path / "splits.json").files("val")] == [
        "b.txt"
    ]
    assert m.files("test") == []


def test_val_file_with_neutral_name_is_refused(tmp_path):
    """The old name-based guard would have accepted 'part2.txt'; the manifest does not."""
    m = make(tmp_path, {"part1.txt": ("train", "alpha beta alpha beta"),
                        "part2.txt": ("val", "gamma delta")})
    with pytest.raises(ManifestError, match="'val'"):
        m.read_verified(tmp_path / "part2.txt", allowed=("train",))
    with pytest.raises(ValueError):
        read_split(m, "val", allowed=("train",))
    # the tokenizer trainer only ever sees the train file
    tok = train_tokenizer(m, 300, 1)
    assert b"gamma" not in b"".join(tok.token_bytes(i) for i in range(259, tok.vocab_size))


def test_tampered_train_file_is_refused(tmp_path):
    m = make(tmp_path, {"part1.txt": ("train", "alpha beta"), "v.txt": ("val", "gamma")})
    (tmp_path / "part1.txt").write_text("alpha beta TAMPERED", encoding="utf-8")
    with pytest.raises(ManifestError, match="hash mismatch"):
        train_tokenizer(m, 300, 1)
    with pytest.raises(ManifestError, match="hash mismatch"):
        read_split(m, "train")
    tok = BPETokenizer([])
    with pytest.raises(ManifestError, match="hash mismatch"):
        tokenize_split(m, "train", tok, tmp_path / "cache")


def test_unlisted_file_is_refused(tmp_path):
    m = make(tmp_path, {"a.txt": ("train", "x y")})
    (tmp_path / "extra.txt").write_text("sneaky", encoding="utf-8")
    with pytest.raises(ManifestError, match="not listed"):
        m.read_verified(tmp_path / "extra.txt", allowed=("train", "val"))


def test_test_split_is_refused_everywhere(tmp_path):
    m = make(tmp_path, {"a.txt": ("train", "x y"), "t.txt": ("test", "secret words")})
    with pytest.raises(ValueError):
        read_split(m, "test")
    with pytest.raises(ValueError):
        tokenize_split(m, "test", BPETokenizer([]), tmp_path / "cache")
    with pytest.raises(ManifestError):
        m.read_verified(tmp_path / "t.txt", allowed=("train", "val"))


def test_unknown_split_and_version_rejected(tmp_path):
    (tmp_path / "a.txt").write_text("x", encoding="utf-8")
    bad = {"version": 1, "files": {"a.txt": {"split": "dev", "sha256": "0" * 64}}}
    (tmp_path / "m.json").write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(ManifestError, match="unknown split"):
        SplitManifest.load(tmp_path / "m.json")
    (tmp_path / "m.json").write_text(json.dumps({"version": 9, "files": {}}), encoding="utf-8")
    with pytest.raises(ManifestError, match="version"):
        SplitManifest.load(tmp_path / "m.json")


def test_empty_train_split_refused(tmp_path):
    m = make(tmp_path, {"v.txt": ("val", "only validation")})
    with pytest.raises(ValueError, match="no train documents"):
        train_tokenizer(m, 300, 1)

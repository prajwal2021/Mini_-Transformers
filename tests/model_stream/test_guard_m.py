"""Test-access ledger: slm.guard.open_split and the manifest's refusal of direct test reads."""

import json
from pathlib import Path

import pytest

from slm.guard import open_split
from slm.split_manifest import ManifestError, build_manifest
from slm.tokenizer import read_split


@pytest.fixture()
def manifest(tmp_path):
    for name, text in (("a.txt", "alpha"), ("b.txt", "beta"), ("c.txt", "gamma"),
                       ("d.txt", "delta")):
        (tmp_path / name).write_bytes(text.encode())
    return build_manifest(
        {tmp_path / "a.txt": "train", tmp_path / "b.txt": "val", tmp_path / "c.txt": "test",
         tmp_path / "d.txt": "test"},
        tmp_path / "splits.json",
    )


def lines(log: Path):
    return [json.loads(x) for x in log.read_text(encoding="utf-8").splitlines()]


def test_test_reads_are_logged(manifest, tmp_path):
    log = tmp_path / "log" / "test_access_log.jsonl"
    got = open_split(manifest, "test", "unit test: final eval", log_path=log)
    assert sorted(got.values()) == [b"delta", b"gamma"]
    (rec,) = lines(log)
    assert rec["split"] == "test" and rec["purpose"] == "unit test: final eval"
    assert rec["caller"].endswith(":test_test_reads_are_logged")
    assert rec["git"]["commit"] and "dirty" in rec["git"]
    assert rec["ts"].endswith("+00:00") and rec["manifest"].endswith("splits.json")
    assert sorted(f["path"][-5:] for f in rec["files"]) == ["c.txt", "d.txt"]
    open_split(manifest, "test", "second read", log_path=log, path=tmp_path / "c.txt")
    assert [r["purpose"] for r in lines(log)] == ["unit test: final eval", "second read"]
    assert len(lines(log)[1]["files"]) == 1


def test_train_and_val_reads_are_not_logged(manifest, tmp_path):
    log = tmp_path / "test_access_log.jsonl"
    assert list(open_split(manifest, "val", "monitoring", log_path=log).values()) == [b"beta"]
    assert list(open_split(manifest, "train", "fit", log_path=log).values()) == [b"alpha"]
    assert not log.exists()


def test_unlisted_and_misfiled_paths_are_refused(manifest, tmp_path):
    (tmp_path / "e.txt").write_bytes(b"epsilon")
    log = tmp_path / "log.jsonl"
    for split in ("train", "val", "test"):
        with pytest.raises(ManifestError, match="not listed"):
            open_split(manifest, split, "x", path=tmp_path / "e.txt", log_path=log)
    with pytest.raises(ManifestError, match="not 'test'"):
        open_split(manifest, "test", "x", path=tmp_path / "a.txt", log_path=log)
    with pytest.raises(ManifestError, match="unknown split"):
        open_split(manifest, "dev", "x", log_path=log)
    assert not log.exists()


def test_test_split_needs_a_purpose(manifest, tmp_path):
    with pytest.raises(ManifestError, match="purpose"):
        open_split(manifest, "test", "  ", log_path=tmp_path / "log.jsonl")


def test_hash_mismatch_is_refused(manifest, tmp_path):
    (tmp_path / "c.txt").write_bytes(b"tampered")
    with pytest.raises(ManifestError, match="hash mismatch"):
        open_split(manifest, "test", "x", log_path=tmp_path / "log.jsonl")


def test_manifest_refuses_direct_test_reads(manifest, tmp_path):
    with pytest.raises(ManifestError, match="slm.guard.open_split"):
        manifest.read_verified(tmp_path / "c.txt", ("test",))
    with pytest.raises(ManifestError):  # the usual readers still refuse it
        manifest.read_verified(tmp_path / "c.txt", ("train", "val"))
    with pytest.raises(ValueError, match="not allowed here"):
        read_split(manifest, "test")
    with pytest.raises(ManifestError, match="slm.guard.open_split"):  # even if allowed is widened
        read_split(manifest, "test", allowed=("test",))
    # and the permission does not leak out of open_split
    open_split(manifest, "test", "x", log_path=tmp_path / "log.jsonl")
    with pytest.raises(ManifestError, match="slm.guard.open_split"):
        manifest.read_verified(tmp_path / "c.txt", ("test",))


def test_only_the_guard_grants_test_access():
    src = Path(__file__).resolve().parents[2] / "src" / "slm"
    users = {
        p.relative_to(src).as_posix()
        for p in src.rglob("*.py") if "_TEST_ACCESS_GRANTED" in p.read_text(encoding="utf-8")
    }
    assert users == {"split_manifest.py", "guard/ledger.py"}

"""Byte-level BPE tests."""

import random

import pytest

from slm.tokenizer import (
    EOS_ID,
    BPETokenizer,
    assert_train_only,
    calibrate,
    read_documents,
    train_tokenizer,
)

from .conftest import MOCK_CORPUS

TRICKY = "“Curly” quotes — dashes – ‘single’ … café \U0001f600 \t\n  x"


def test_vocab_size_and_specials(tokenizer):
    assert tokenizer.vocab_size == 4096
    assert (tokenizer.pad_id, tokenizer.bos_id, tokenizer.eos_id) == (0, 1, 2)


def test_roundtrip_random_unicode(tokenizer):
    rng = random.Random(0)
    pools = [(0x20, 0x7E), (0xA0, 0x24F), (0x2010, 0x2060), (0x4E00, 0x4E80), (0x1F600, 0x1F640)]
    for _ in range(300):
        s = "".join(
            chr(rng.randint(*rng.choice(pools))) if rng.random() < 0.9 else rng.choice(" \n\t")
            for _ in range(rng.randint(0, 80))
        )
        assert tokenizer.decode(tokenizer.encode(s)) == s


def test_roundtrip_arbitrary_bytes(tokenizer):
    rng = random.Random(1)
    for _ in range(300):
        data = bytes(rng.randrange(256) for _ in range(rng.randint(0, 120)))
        assert tokenizer.decode_bytes(tokenizer.encode_bytes(data)) == data


def test_roundtrip_curly_quotes_and_dashes(tokenizer):
    assert tokenizer.decode(tokenizer.encode(TRICKY)) == TRICKY
    assert tokenizer.decode(tokenizer.encode("")) == ""


def test_roundtrip_whole_corpus(tokenizer, mock_docs):
    for d in mock_docs:
        assert tokenizer.decode(tokenizer.encode(d)) == d


def test_special_tokens(tokenizer):
    assert tokenizer.encode("a<|eos|>b") != tokenizer.encode("a<|eos|>b", allow_special=True)
    assert EOS_ID in tokenizer.encode("a<|eos|>b", allow_special=True)
    assert tokenizer.encode_document("hello")[-1] == EOS_ID
    assert tokenizer.decode([EOS_ID]) == ""
    assert tokenizer.decode([EOS_ID], skip_special=False) == "<|eos|>"
    assert all(i >= 3 for i in tokenizer.encode("<|pad|><|bos|>"))  # plain text by default


def test_training_is_deterministic(tmp_path):
    a = train_tokenizer([MOCK_CORPUS], 1000, 1)
    b = train_tokenizer([MOCK_CORPUS], 1000, 1)
    assert a.merges == b.merges
    a.save(tmp_path / "a.json")
    b.save(tmp_path / "b.json")
    assert (tmp_path / "a.json").read_bytes() == (tmp_path / "b.json").read_bytes()


def test_save_load(tmp_path, tokenizer, mock_docs):
    tokenizer.save(tmp_path / "tok.json")
    loaded = BPETokenizer.load(tmp_path / "tok.json")
    assert loaded.vocab_size == tokenizer.vocab_size
    assert loaded.encode(mock_docs[0]) == tokenizer.encode(mock_docs[0])


def test_merges_compress(tokenizer, mock_docs):
    assert len(tokenizer.encode(mock_docs[0])) < len(mock_docs[0].encode("utf-8"))


def test_guard_refuses_val_and_test_paths(tmp_path):
    for name in ["val.txt", "corpus_test.jsonl", "valid_docs.txt", "split-validation.txt",
                 "dev.txt", "Test.txt"]:
        p = tmp_path / name
        p.write_text("hello world", encoding="utf-8")
        with pytest.raises(ValueError, match="held-out"):
            assert_train_only([p])
        with pytest.raises(ValueError, match="held-out"):
            train_tokenizer([p], 300)
        with pytest.raises(ValueError, match="held-out"):
            read_documents([p])
    assert_train_only([tmp_path / "train.txt", tmp_path / "latest.txt"])  # not refused


def test_guard_checks_files_inside_a_directory(tmp_path):
    (tmp_path / "train.txt").write_text("alpha beta", encoding="utf-8")
    (tmp_path / "val.txt").write_text("gamma", encoding="utf-8")
    with pytest.raises(ValueError, match="held-out"):
        read_documents([tmp_path])


def test_jsonl_corpus(tmp_path):
    p = tmp_path / "train.jsonl"
    p.write_text('{"text": "one two"}\n{"text": "three"}\n', encoding="utf-8")
    assert read_documents([p]) == ["one two", "three"]


def test_calibration_on_mock_corpus(tokenizer):
    stats = calibrate(tokenizer, [MOCK_CORPUS], context_len=512)
    assert stats["n_docs"] == 200
    assert 1.0 < stats["tokens_per_word"] < 1.5
    assert 0.0 < stats["share_over_context"] < 0.2
    assert calibrate(tokenizer, [MOCK_CORPUS], context_len=10_000)["share_over_context"] == 0.0

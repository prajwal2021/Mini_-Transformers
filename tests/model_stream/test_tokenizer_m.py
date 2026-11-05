"""Byte-level BPE tests."""

import random

from slm.tokenizer import EOS_ID, BPETokenizer, calibrate, parse_documents, train_tokenizer

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


def test_training_is_deterministic(tmp_path, mock_manifest):
    a = train_tokenizer(mock_manifest, 1000, 1)
    b = train_tokenizer(mock_manifest, 1000, 1)
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


def test_parse_documents():
    raw = b'{"text": "one two"}\n{"text": "three"}\n'
    assert parse_documents(raw, ".jsonl") == ["one two", "three"]
    assert parse_documents(b"a b\x0cc d\x0c", ".txt") == ["a b", "c d"]


def test_hash_identifies_merge_table(tokenizer, mock_manifest):
    assert tokenizer.hash() == train_tokenizer(mock_manifest, 4096, 1).hash()
    assert tokenizer.hash() != train_tokenizer(mock_manifest, 1000, 1).hash()


def test_calibration_on_mock_corpus(tokenizer, mock_docs):
    stats = calibrate(tokenizer, mock_docs, context_len=512)
    assert stats["n_docs"] == 200
    assert 1.0 < stats["tokens_per_word"] < 1.5
    assert 0.0 < stats["share_over_context"] < 0.2
    assert calibrate(tokenizer, mock_docs, context_len=10_000)["share_over_context"] == 0.0

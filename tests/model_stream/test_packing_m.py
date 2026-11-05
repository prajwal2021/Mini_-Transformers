"""Document-aware packing tests."""

import random
from collections import Counter

import torch

from slm.data_loading import PackedDataset
from slm.model import Transformer
from slm.tokenizer import EOS_ID

from .conftest import small_config


def make_docs(n=40, seed=0, vocab=100, max_len=20):
    rng = random.Random(seed)
    return [[rng.randrange(3, vocab) for _ in range(rng.randint(1, max_len))] for _ in range(n)]


def test_every_token_exactly_once_per_epoch():
    docs = make_docs()
    ds = PackedDataset(docs, seq_len=32)
    expected = Counter(t for d in docs for t in d + [EOS_ID])
    seen = Counter()
    n_seq = 0
    for b in ds.epoch(batch_size=7, epoch=0, seed=3):
        real = b["doc_ids"] > 0
        seen.update(b["input_ids"][real].tolist())
        n_seq += b["input_ids"].size(0)
    assert seen == expected
    assert n_seq == len(ds)
    assert ds.n_tokens == sum(len(d) + 1 for d in docs)


def test_documents_are_whole_and_separated_by_eos():
    docs = make_docs()
    ds = PackedDataset(docs, seq_len=32)
    found = []
    for row in range(len(ds)):
        for k in range(1, int(ds.doc_ids[row].max()) + 1):
            toks = ds.input_ids[row][ds.doc_ids[row] == k].tolist()
            assert toks[-1] == EOS_ID and toks.count(EOS_ID) == 1
            found.append(toks[:-1])
    assert sorted(found) == sorted(docs)


def test_padding_and_boundary_labels_masked():
    ds = PackedDataset([[5, 6, 7], [8, 9]], seq_len=16)
    assert len(ds) == 1
    ids, lab = ds.input_ids[0], ds.labels[0]
    assert ids[:7].tolist() == [5, 6, 7, EOS_ID, 8, 9, EOS_ID]
    assert lab[:7].tolist() == [6, 7, EOS_ID, -100, 9, EOS_ID, -100]
    assert (lab[7:] == -100).all() and (ds.doc_ids[0, 7:] == 0).all()


def test_overlong_document_is_chunked():
    ds = PackedDataset([list(range(3, 43))], seq_len=16)
    assert ds.n_split_docs == 1 and ds.n_tokens == 41
    assert (ds.input_ids <= 42).all()


def test_deterministic_with_seed_and_different_across_seeds():
    ds = PackedDataset(make_docs(60), seq_len=32)
    first = lambda s, e=0: next(ds.epoch(4, epoch=e, seed=s))["input_ids"]  # noqa: E731
    assert torch.equal(first(5), first(5))
    assert not torch.equal(first(5), first(6))
    assert not torch.equal(first(5, 0), first(5, 1))
    ds2 = PackedDataset(make_docs(60), seq_len=32)
    assert torch.equal(ds.input_ids, ds2.input_ids)


def test_no_cross_document_attention():
    """Perturbing a token in doc A leaves doc B's logits unchanged (and earlier-doc ones too)."""
    torch.manual_seed(0)
    cfg = small_config(vocab_size=128, context_len=32)
    model = Transformer(cfg).eval()
    ds = PackedDataset([[5, 6, 7, 8, 9], [10, 11, 12, 13]], seq_len=16)
    x, d = ds.input_ids[:1], ds.doc_ids[:1]
    assert d[0, :6].eq(1).all() and d[0, 6:10].eq(2).all()
    base, _ = model(x, doc_ids=d)
    x2 = x.clone()
    x2[0, 2] = 99  # inside document A
    pert, _ = model(x2, doc_ids=d)
    assert torch.equal(base[0, 6:], pert[0, 6:])  # doc B and padding untouched
    assert not torch.equal(base[0, 2:6], pert[0, 2:6])  # doc A does change
    # without the document mask, B would see A's change (the mask is doing the work)
    nomask_a, _ = model(x)
    nomask_b, _ = model(x2)
    assert not torch.equal(nomask_a[0, 6:10], nomask_b[0, 6:10])

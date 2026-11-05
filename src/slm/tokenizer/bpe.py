"""Byte-level BPE tokenizer, implemented from scratch (DESIGN.md section 3).

Id layout: 0 <|pad|>, 1 <|bos|>, 2 <|eos|>, 3..258 the 256 raw bytes, 259.. learned merges
in the order they were learned. There is no <|unk|>: every byte sequence is representable.
"""

from __future__ import annotations

import heapq
import json
from collections import Counter, defaultdict
from collections.abc import Iterable
from pathlib import Path

import regex

SPECIAL_TOKENS = ("<|pad|>", "<|bos|>", "<|eos|>")
PAD_ID, BOS_ID, EOS_ID = 0, 1, 2
N_SPECIAL = len(SPECIAL_TOKENS)
BYTE_OFFSET = N_SPECIAL
FIRST_MERGE_ID = BYTE_OFFSET + 256

# GPT-2 style pre-tokenisation: contractions, letter runs, digit runs, symbol runs, whitespace.
PRETOKEN_PATTERN = (
    r"'(?:[sdmt]|ll|ve|re)| ?\p{L}+| ?\p{N}+| ?[^\s\p{L}\p{N}]+|\s+(?!\S)|\s+"
)
_PRETOKEN_RE = regex.compile(PRETOKEN_PATTERN)
_SPECIAL_RE = regex.compile("(" + "|".join(regex.escape(s) for s in SPECIAL_TOKENS) + ")")
_NO_RANK = 1 << 60


def _pretokens(data: bytes) -> list[bytes]:
    """Split raw bytes into pre-tokens without ever altering the bytes.

    Invalid UTF-8 is carried through as lone surrogates (surrogateescape) so any byte string
    round-trips exactly.
    """
    text = data.decode("utf-8", "surrogateescape")
    return [m.group().encode("utf-8", "surrogateescape") for m in _PRETOKEN_RE.finditer(text)]


def _merge_word(word: list[int], pair: tuple[int, int], new_id: int) -> list[int]:
    a, b = pair
    out: list[int] = []
    i = 0
    n = len(word)
    while i < n:
        if i < n - 1 and word[i] == a and word[i + 1] == b:
            out.append(new_id)
            i += 2
        else:
            out.append(word[i])
            i += 1
    return out


class BPETokenizer:
    """Trainable, saveable byte-level BPE tokenizer."""

    pad_id, bos_id, eos_id = PAD_ID, BOS_ID, EOS_ID

    def __init__(self, merges: list[tuple[int, int]] | None = None) -> None:
        self.merges: list[tuple[int, int]] = [tuple(m) for m in (merges or [])]
        self._ranks = {pair: i for i, pair in enumerate(self.merges)}
        self._vocab: list[bytes] = [b""] * N_SPECIAL + [bytes([i]) for i in range(256)]
        for a, b in self.merges:
            self._vocab.append(self._vocab[a] + self._vocab[b])
        self._cache: dict[bytes, tuple[int, ...]] = {}

    @property
    def vocab_size(self) -> int:
        return len(self._vocab)

    def token_bytes(self, token_id: int) -> bytes:
        return self._vocab[token_id]

    # ---- training ------------------------------------------------------------------------
    @classmethod
    def train(
        cls, texts: Iterable[str | bytes], vocab_size: int = 4096, min_frequency: int = 2
    ) -> BPETokenizer:
        """Learn merges from word-frequency counts. Deterministic: ties go to the smaller pair."""
        if vocab_size < FIRST_MERGE_ID:
            raise ValueError(f"vocab_size must be at least {FIRST_MERGE_ID}")
        counts: Counter[bytes] = Counter()
        for text in texts:
            data = text.encode("utf-8") if isinstance(text, str) else text
            counts.update(_pretokens(data))
        # sorted so that word indices (and hence all later iteration order) are deterministic
        types = sorted(counts)
        words = [[BYTE_OFFSET + b for b in w] for w in types]
        freqs = [counts[w] for w in types]

        pair_counts: dict[tuple[int, int], int] = defaultdict(int)
        where: dict[tuple[int, int], set[int]] = defaultdict(set)
        for i, word in enumerate(words):
            for pair in zip(word, word[1:]):
                pair_counts[pair] += freqs[i]
                where[pair].add(i)
        heap = [(-c, p) for p, c in pair_counts.items()]
        heapq.heapify(heap)

        merges: list[tuple[int, int]] = []
        while len(merges) < vocab_size - FIRST_MERGE_ID and heap:
            neg, pair = heapq.heappop(heap)
            if pair_counts.get(pair, 0) != -neg:
                continue  # stale heap entry
            if -neg < min_frequency:
                break
            new_id = FIRST_MERGE_ID + len(merges)
            merges.append(pair)
            touched: set[tuple[int, int]] = set()
            for i in sorted(where.pop(pair)):
                word = words[i]
                merged = _merge_word(word, pair, new_id)
                if merged == word:
                    continue
                for p in zip(word, word[1:]):
                    pair_counts[p] -= freqs[i]
                    touched.add(p)
                for p in zip(merged, merged[1:]):
                    pair_counts[p] += freqs[i]
                    where[p].add(i)
                    touched.add(p)
                words[i] = merged
            pair_counts.pop(pair, None)
            for p in touched:
                if p not in pair_counts:
                    continue
                if pair_counts[p] <= 0:
                    del pair_counts[p]
                else:
                    heapq.heappush(heap, (-pair_counts[p], p))
        return cls(merges)

    # ---- encode / decode -----------------------------------------------------------------
    def _encode_piece(self, piece: bytes) -> tuple[int, ...]:
        hit = self._cache.get(piece)
        if hit is not None:
            return hit
        ids = [BYTE_OFFSET + b for b in piece]
        while len(ids) > 1:
            best = min((self._ranks.get(p, _NO_RANK) for p in zip(ids, ids[1:])))
            if best == _NO_RANK:
                break
            ids = _merge_word(ids, self.merges[best], FIRST_MERGE_ID + best)
        out = tuple(ids)
        self._cache[piece] = out
        return out

    def encode_bytes(self, data: bytes) -> list[int]:
        out: list[int] = []
        for piece in _pretokens(data):
            out.extend(self._encode_piece(piece))
        return out

    def encode(self, text: str, allow_special: bool = False) -> list[int]:
        """Encode text. Special-token strings are plain text unless ``allow_special``."""
        if not allow_special:
            return self.encode_bytes(text.encode("utf-8"))
        out: list[int] = []
        for i, part in enumerate(_SPECIAL_RE.split(text)):
            if i % 2:
                out.append(SPECIAL_TOKENS.index(part))
            elif part:
                out.extend(self.encode_bytes(part.encode("utf-8")))
        return out

    def encode_document(self, text: str) -> list[int]:
        """Encode one document followed by <|eos|> (the unit that gets packed)."""
        return self.encode(text) + [EOS_ID]

    def decode_bytes(self, ids: Iterable[int], skip_special: bool = True) -> bytes:
        parts = []
        for i in ids:
            if i < N_SPECIAL:
                if not skip_special:
                    parts.append(SPECIAL_TOKENS[i].encode("utf-8"))
            else:
                parts.append(self._vocab[i])
        return b"".join(parts)

    def decode(self, ids: Iterable[int], skip_special: bool = True) -> str:
        return self.decode_bytes(ids, skip_special).decode("utf-8", "replace")

    # ---- persistence ---------------------------------------------------------------------
    def save(self, path: str | Path) -> None:
        payload = {
            "type": "byte-level-bpe",
            "version": 1,
            "specials": list(SPECIAL_TOKENS),
            "pretoken_pattern": PRETOKEN_PATTERN,
            "merges": [list(m) for m in self.merges],
        }
        Path(path).write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> BPETokenizer:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        if payload.get("pretoken_pattern") != PRETOKEN_PATTERN:
            raise ValueError("tokenizer file was built with a different pre-tokenisation pattern")
        return cls([tuple(m) for m in payload["merges"]])

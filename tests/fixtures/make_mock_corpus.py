"""Generate the synthetic mock corpus (200 short plain-English documents).

Run: python tests/fixtures/make_mock_corpus.py
Writes tests/fixtures/mock_corpus_train.txt (form-feed separated documents). Fully seeded, so
the output is reproducible. The corpus is only for tests and the GPU smoke test; it contains no
real project data. Invented names are built from syllables so the word-type count is large
enough for a 4096-entry BPE vocabulary to be reachable on a small text.
"""

from __future__ import annotations

import random
from pathlib import Path

SEED = 1234
N_DOCS = 200

SUBJECTS = [
    "the desk", "our team", "the keeper", "a traveler", "the manager", "the crew",
    "every guest", "the night shift", "the planning group", "a volunteer", "the driver",
    "the old guide", "the harbor office", "the committee", "a young clerk",
]
VERBS = [
    "checks", "records", "prepares", "reviews", "explains", "carries", "opens", "closes",
    "repairs", "counts", "welcomes", "inspects", "schedules", "answers", "organizes",
    "delivers", "cleans", "measures", "reports", "approves",
]
OBJECTS = [
    "the morning list", "a small crate", "every new form", "the blue ledger", "a spare key",
    "the weekly notice", "two heavy boxes", "the front gate", "a long letter",
    "the quiet room", "an extra blanket", "the oldest map", "a pot of tea", "the water bowls",
    "the booking record",
]
ENDINGS = [
    "before the doors open", "after the evening meeting", "without any delay",
    "during the busy season", "as the weather turns cold", "while the others rest",
    "on the first day of the month", "just in case of rain", "with great care",
    "and then writes a short note", "so nobody has to wait", "before anyone arrives",
]
CONNECTORS = ["However,", "Meanwhile,", "Usually,", "In the end,", "Later that week,", "Often,"]
SYLLABLES = [
    "ba", "ko", "ri", "tel", "mon", "va", "ley", "dor", "quin", "sa", "lem", "tor", "fin",
    "gar", "nel", "pho", "ust", "wen", "yar", "zul", "bri", "cae", "dun", "eph", "hol",
    "ane", "mir", "sko", "tha", "ive", "oru", "lyn", "cre", "dax", "jo", "kai", "pel", "rhu",
    "sym",
]


def _name(rng: random.Random) -> str:
    return "".join(rng.choice(SYLLABLES) for _ in range(rng.randint(2, 5))).capitalize()


def _sentence(rng: random.Random, names: list[str]) -> str:
    s = f"{rng.choice(SUBJECTS)} {rng.choice(VERBS)} {rng.choice(OBJECTS)} {rng.choice(ENDINGS)}"
    r = rng.random()
    if r < 0.6:
        s += f" for {rng.choice(names)} at {rng.choice(names)}"
    elif r < 0.85:
        s += f", and {rng.choice(names)} agrees"
    s = s[0].upper() + s[1:]
    if rng.random() < 0.3:
        s = f"{rng.choice(CONNECTORS)} {s[0].lower()}{s[1:]}"
    if rng.random() < 0.2:
        s += f" It takes {rng.randint(2, 95)} minutes."
        return s
    return s + "."


def make_documents(seed: int = SEED, n_docs: int = N_DOCS) -> list[str]:
    rng = random.Random(seed)
    names = [_name(rng) for _ in range(4000)]
    docs = []
    for i in range(n_docs):
        # most documents are short; a handful are long so the >512-token share is non-zero
        n_sent = rng.randint(30, 45) if i % 25 == 0 else rng.randint(4, 22)
        paras, left = [], n_sent
        while left > 0:
            k = min(left, rng.randint(2, 5))
            paras.append(" ".join(_sentence(rng, rng.sample(names, 6)) for _ in range(k)))
            left -= k
        docs.append("\n\n".join(paras))
    return docs


if __name__ == "__main__":
    out = Path(__file__).with_name("mock_corpus_train.txt")
    out.write_text("\f".join(make_documents()), encoding="utf-8", newline="\n")
    print(f"wrote {out}")

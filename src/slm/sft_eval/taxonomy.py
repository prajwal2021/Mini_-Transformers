# ruff: noqa: E501
"""Error taxonomy for QA predictions (DESIGN 7.4; rules written out in docs/ERROR_TAXONOMY.md).

Every prediction gets exactly one class, decided in this order:

1. ``correct``: ``exact_value_match`` (gold value present, no other value of the attribute).
2. ``format_failure``: empty; or degenerate repetition (one 1-3 word n-gram covers more than half
   of the words); or no value-like string of the attribute's type at all.
3. ``right_type_wrong_value``: a value-like string of the right type that is a KB value of that
   type (another value of the same attribute, a value of another attribute with the same value
   class, or the gold value listed together with a rival).
4. ``out_of_kb_hallucination``: value-like strings of the right type exist and none is a KB value.

The same rules flag generated samples (``slm.integration`` / ``scripts/sample_checkpoints.py``).
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

CORRECT = "correct"
RIGHT_TYPE = "right_type_wrong_value"
HALLUCINATION = "out_of_kb_hallucination"
FORMAT = "format_failure"
WRONG_ATTRIBUTE = "wrong_attribute"  # R08: a well-formed answer that states a KB value of ANOTHER attribute
CLASSES = (CORRECT, RIGHT_TYPE, HALLUCINATION, WRONG_ATTRIBUTE, FORMAT)

NUMBER_UNIT_CLASSES = ("count", "weight", "dimension", "duration", "temperature")
NAME_CLASSES = ("person_name", "place_name", "role_title")
REPETITION_SHARE = 0.5
MIN_WORDS_FOR_REPETITION = 4
_STOP_FIRST = {"The", "A", "An", "This", "That", "It", "Its", "Question", "Answer", "Who", "What",
               "Which", "How", "Where", "When", "For", "At", "On", "In", "To", "Per", "If", "I",
               "Passengers", "Staff", "Early", "Claims", "Time", "Before", "After", "Responsibility",
               "Paperwork", "Pet", "Animals", "Looking", "Bringing", "Airships", "Deadline"}
_CAP_SEQ = re.compile(r"(?<![\w'-])[A-Z][a-z]+(?: [A-Z][a-z]+){1,2}(?![\w'-])")
_CODE = re.compile(r"(?<![\w-])[A-Z]{2,3}-\d{2,4}(?![\w-])")
_TIME = re.compile(r"(?<![\w:])\d{1,2}:\d{2}(?![\w:])")
_MONEY = re.compile(r"(?<![\w$])\$\d[\d,]*(?:\.\d+)?(?![\w])")


def _norm(text: str) -> str:
    return " ".join(text.split())


def is_degenerate(text: str) -> bool:
    """One 1-, 2- or 3-word n-gram makes up more than half of the words (at least 4 words)."""
    words = text.split()
    if len(words) < MIN_WORDS_FOR_REPETITION:
        return False
    for n in (1, 2, 3):
        if len(words) < n:
            continue
        counts: dict[tuple[str, ...], int] = {}
        for i in range(len(words) - n + 1):
            g = tuple(words[i : i + n])
            counts[g] = counts.get(g, 0) + 1
        best = max(counts.values())
        if best >= 2 and best * n / len(words) > REPETITION_SHARE:
            return True
    return False


@dataclass(frozen=True)
class Taxonomy:
    """KB-derived lookup tables: value class and units per attribute, KB values per class."""

    class_of: Mapping[str, str]  # attribute_id -> value_class
    values_of: Mapping[str, tuple[str, ...]]  # attribute_id -> its six values
    class_values: Mapping[str, frozenset[str]]  # value_class -> every KB value of that class
    units: Mapping[str, tuple[str, ...]]  # number-unit class -> units seen in the KB
    entity_names: frozenset[str]
    other_class_names: Mapping[str, frozenset[str]]  # name class -> KB name values of OTHER classes

    @classmethod
    def from_kb(cls, kb: Mapping | str | Path) -> Taxonomy:
        if not isinstance(kb, Mapping):
            kb = json.loads(Path(kb).read_text(encoding="utf-8"))
        facts = kb["measured_facts"]
        class_of, values_of, class_values = {}, {}, {}
        for f in facts:
            class_of[f["attribute_id"]] = f["value_class"]
            values_of.setdefault(f["attribute_id"], []).append(f["value"])
            class_values.setdefault(f["value_class"], set()).add(f["value"])
        units: dict[str, set[str]] = {}
        for c in NUMBER_UNIT_CLASSES:
            for v in class_values.get(c, ()):
                m = re.fullmatch(r"\d+(?:\.\d+)?\s+(.+)", v)
                if m:
                    units.setdefault(c, set()).add(m.group(1))
        names_all = {c: class_values.get(c, set()) for c in NAME_CLASSES}
        other = {c: frozenset().union(*(names_all[o] for o in NAME_CLASSES if o != c))
                 for c in NAME_CLASSES}
        return cls(class_of, {k: tuple(v) for k, v in values_of.items()},
                   {k: frozenset(v) for k, v in class_values.items()},
                   {k: tuple(sorted(v, key=len, reverse=True)) for k, v in units.items()},
                   frozenset(f["entity"] for f in facts), other)

    # ---- value-like strings ------------------------------------------------------------
    def extract(self, text: str, value_class: str) -> list[str]:
        """Value-like strings of ``value_class`` in ``text`` (rules per class: ERROR_TAXONOMY.md)."""
        text = _norm(text)
        if value_class == "code":
            return _CODE.findall(text)
        if value_class == "time_of_day":
            return _TIME.findall(text)
        if value_class == "money":
            return _MONEY.findall(text)
        if value_class in NUMBER_UNIT_CLASSES:
            units = "|".join(re.escape(u) for u in self.units.get(value_class, ()))
            unit_part = rf"(?:\s+({units})(?![\w]))?" if units else ""
            pat = re.compile(rf"(?<![\w$.:-])(\d+(?:\.\d+)?){unit_part}(?![\w:])"
                             if units else r"(?<![\w$.:-])(\d+(?:\.\d+)?)(?![\w:])")
            out = []
            for m in pat.finditer(text):
                if text[m.end() : m.end() + 1] == ":" or text[m.start() - 1 : m.start()] == "-":
                    continue
                out.append(m.group(1) + (f" {m.group(2)}" if units and m.group(2) else ""))
            return out
        if value_class in NAME_CLASSES:
            out = []
            for m in _CAP_SEQ.finditer(text):
                words = m.group(0).split()
                while words and words[0] in _STOP_FIRST:
                    words = words[1:]
                s = " ".join(words)
                if len(words) < 2 or s in self.entity_names or s in self.other_class_names[value_class]:
                    continue
                if any(e in s for e in self.entity_names):
                    continue
                out.append(s)
            return out
        raise ValueError(f"no extraction rule for value class {value_class!r}")

    def is_kb_value(self, s: str, attribute_id: str) -> bool:
        vc = self.class_of[attribute_id]
        if s in self.class_values[vc]:
            return True
        if re.fullmatch(r"\d+(?:\.\d+)?", s) and vc in NUMBER_UNIT_CLASSES:  # bare number, no unit
            return any(v.split()[0] == s for v in self.values_of[attribute_id])
        return False

    def _states_another_value(self, pred: str) -> bool:
        return any(_occurs(pred, v) for vs in self.values_of.values() for v in vs)

    # ---- the decision ------------------------------------------------------------------
    def classify(self, prediction: str, attribute_id: str, gold_value: str,
                 exact_value_match: bool | None = None) -> str:
        pred = _norm(prediction)
        if exact_value_match is None:
            exact_value_match = _occurs(pred, gold_value) and not any(
                _occurs(pred, v) for v in self.values_of[attribute_id] if v != gold_value)
        if exact_value_match:
            return CORRECT
        if not pred or is_degenerate(pred):
            return FORMAT
        vc = self.class_of[attribute_id]
        found = self.extract(pred, vc)
        if _occurs(pred, gold_value) or any(_occurs(pred, v) for v in self.values_of[attribute_id]):
            return RIGHT_TYPE  # gold listed with a rival value, or a rival value of the attribute
        if not found:
            return WRONG_ATTRIBUTE if self._states_another_value(pred) else FORMAT
        if any(self.is_kb_value(s, attribute_id) for s in found):
            return RIGHT_TYPE
        return HALLUCINATION


def _occurs(text: str, value: str) -> bool:
    v = _norm(value)
    return bool(v) and re.search(r"(?<!\w)" + re.escape(v) + r"(?!\w)", text) is not None


def error_summary(table, by: Iterable[str] = ("checkpoint", "prompt_mode", "eval_set")):
    """Counts and shares per (by..., error_class); every class appears for every group."""
    import pandas as pd

    by = list(by)
    counts = table.groupby(by + ["error_class"]).size().rename("n").reset_index()
    groups = table[by].drop_duplicates()
    grid = groups.merge(pd.DataFrame({"error_class": list(CLASSES)}), how="cross")
    out = grid.merge(counts, on=by + ["error_class"], how="left").fillna({"n": 0})
    out["n"] = out["n"].astype(int)
    out["share"] = out["n"] / out.groupby(by)["n"].transform("sum")
    return out.sort_values(by + ["error_class"]).reset_index(drop=True)

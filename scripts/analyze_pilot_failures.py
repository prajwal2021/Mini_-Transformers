"""Report-only diagnosis of the pilot failures (no API calls, no validator changes).

Reads data/pilot/<model>/attempts.jsonl, pilot_rows.jsonl and the KB, and writes
reports/tables/pilot_failures.md. The validator is only imported, never modified.
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import yaml

from slm.data import doc_validator, doc_validator_v1, doc_validator_v2, doc_validator_v3
from slm.data.doc_validator_v1 import ALLOWED_CAPITALS, SPEAKER_LABEL, WORD_RE

ROOT = Path(__file__).resolve().parents[1]
FULL_RUN_DOCS = 2407
VALIDATOR = {"name": "v1"}


def flagged_capitals(text: str, row: dict[str, Any], kb: dict[str, Any]) -> list[str]:
    """V5 flags under the validator selected with --validator."""
    module = {"v1": doc_validator_v1, "v2": doc_validator_v2, "v3": doc_validator_v3, "v4": doc_validator, "v5": doc_validator}[VALIDATOR["name"]]
    return module.flagged_capitals(text, row, kb)

RULE_RE = re.compile(r"(V\d+[bp]?(?:/V\d+)?|API error|E1)")
QA_RE = re.compile(r"(?:^|\n)\s*(?:Q:|A:|- |\* )|\b(?:Question|Answer)\b", re.IGNORECASE)
PRONOUNS = {"it", "its", "they", "them", "their", "this", "that", "these", "those", "which"}
ONES = (
    "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen "
    "fifteen sixteen seventeen eighteen nineteen"
).split()
TENS = "_ _ twenty thirty forty fifty sixty seventy eighty ninety".split()


def spelled(n: int) -> str | None:
    if n < 20:
        return ONES[n]
    if n < 100:
        return TENS[n // 10] + ("" if n % 10 == 0 else "-" + ONES[n % 10])
    return None


def contains(text: str, value: str) -> int:
    return len(re.findall(rf"(?<!\w){re.escape(value)}(?!\w)", text))


def sentences(text: str) -> list[str]:
    return [p.strip() for p in re.split(r"(?<=[.!?])\s+", text.strip()) if p.strip()]


def rule_ids(reasons: list[str]) -> list[str]:
    seen: list[str] = []
    for reason in reasons:
        match = RULE_RE.match(reason)
        key = match.group(1) if match else "other"
        if key not in seen:
            seen.append(key)
    return seen


def md_table(header: list[str], body: list[list[Any]]) -> list[str]:
    lines = ["| " + " | ".join(header) + " |", "| " + " | ".join("---" for _ in header) + " |"]
    for row in body:
        cells = [str(c).replace("|", "\\|").replace("\n", " ") for c in row]
        lines.append("| " + " | ".join(cells) + " |")
    return lines


def clip(text: str, n: int = 220) -> str:
    text = " ".join(text.split())
    return text if len(text) <= n else text[: n - 3] + "..."


class Data:
    def __init__(self, pilot_dir: Path, kb_path: Path, config_path: Path) -> None:
        self.kb = json.loads(kb_path.read_text(encoding="utf-8"))
        self.facts = {f["fact_id"]: f for f in self.kb["measured_facts"]}
        self.config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        self.rows = {
            r["doc_id"]: r
            for r in (
                json.loads(x)
                for x in (pilot_dir / "pilot_rows.jsonl").read_text(encoding="utf-8").splitlines()
                if x.strip()
            )
        }
        self.models: dict[str, list[dict[str, Any]]] = {}
        self.events: dict[str, list[dict[str, Any]]] = {}
        for sub in sorted(p for p in pilot_dir.iterdir() if (p / "attempts.jsonl").exists()):
            attempts = [
                json.loads(x)
                for x in (sub / "attempts.jsonl").read_text(encoding="utf-8").splitlines()
                if x.strip()
            ]
            for a in attempts:
                a["rules"] = rule_ids(a["reasons"])
                a["row"] = self.rows[a["doc_id"]]
                a["words"] = len(WORD_RE.findall(a["text"]))
            self.models[sub.name] = sorted(attempts, key=lambda a: (a["doc_id"], a["attempt"]))
            events_path = sub / "api_events.jsonl"
            self.events[sub.name] = [
                json.loads(x)
                for x in (events_path.read_text(encoding="utf-8").splitlines() if events_path.exists() else [])
                if x.strip()
            ]

    def by_doc(self, model: str) -> dict[str, list[dict[str, Any]]]:
        out: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for a in self.models[model]:
            out[a["doc_id"]].append(a)
        return out

    def assigned(self, row: dict[str, Any]) -> list[tuple[dict[str, Any], str]]:
        return [(self.facts[f], m) for f, m in zip(row["fact_ids"], row["modes"])]


def modes_label(row: dict[str, Any]) -> str:
    return ",".join(sorted(set(row["modes"]))) or "none"


def section_notes(d: Data) -> list[str]:
    models = list(d.models)
    lines = ["## 0. Data notes", ""]
    stats = []
    for m in models:
        attempts = d.models[m]
        empty = [a for a in attempts if not a["text"].strip()]
        stats.append(
            [m, len(attempts), len({a["doc_id"] for a in attempts}), sum(a["ok"] for a in attempts),
             len(empty), sum(a["output_tokens"] == a["reasoning_tokens"] for a in empty),
             max(a["output_tokens"] for a in attempts), len(d.events.get(m, [])),
             sum(1 for a in attempts if a.get("api_failure"))]
        )
    lines += md_table(
        ["model", "attempts", "docs", "accepted attempts", "attempts with empty text",
         "of those: all output tokens were reasoning tokens", "max output tokens in any call",
         "E1 API events (empty or length)", "docs lost to E1"],
        stats,
    )
    lines += ["", "Validator reason lines by exact rule id (all attempts). pilot_report.md bins "
              "reasons with a one-digit pattern, so its V1 row also holds V10-V14 reason lines "
              "(for example V11 and V14).", ""]
    counts = {m: Counter(rule_ids([r])[0] for a in d.models[m] for r in a["reasons"]) for m in models}
    rules = sorted({r for c in counts.values() for r in c}, key=lambda x: (len(x), x))
    lines += md_table(["rule id"] + models, [[r] + [counts[m][r] for m in models] for r in rules])
    lines += [""]
    return lines


# ---- A ----------------------------------------------------------------------------------


def section_a(d: Data) -> list[str]:
    lines = ["## A. Attempt table", ""]
    for model, attempts in d.models.items():
        lines += [f"### {model}", ""]
        body = [
            [
                a["doc_id"],
                modes_label(a["row"]),
                a["row"]["doc_type"],
                a["attempt"],
                "yes" if a["ok"] else "no",
                ", ".join(a["rules"]) or "-",
            ]
            for a in attempts
        ]
        lines += md_table(["doc_id", "mode(s)", "doc_type", "attempt", "accepted?", "rules failed"], body)
        lines.append("")
    return lines


# ---- B ----------------------------------------------------------------------------------


def nearest(text: str, target: str) -> tuple[str, float]:
    pieces = sentences(text) + [x.strip() for x in text.split("\n") if x.strip()]
    best, score = "", 0.0
    for piece in pieces:
        ratio = difflib.SequenceMatcher(None, target, piece).ratio()
        if ratio > score:
            best, score = piece, ratio
    return best, score


def alt_form(text: str, value: str) -> str:
    """Classify how an absent value appears in another form, if at all."""
    low = text.lower()
    norm = lambda s: " ".join(re.sub(r"[^a-z0-9]", " ", s.lower()).split())  # noqa: E731
    if f" {norm(value)} " in f" {norm(text)} ":
        return "case, spacing or hyphenation variant"
    time = re.fullmatch(r"0?(\d{1,2}):(\d{2})", value)
    if time and re.search(rf"\b0?{time.group(1)}[:.]{time.group(2)}\b", text):
        return "different spacing, unit or format"
    number = re.search(r"\d+(?:\.\d+)?", value)
    if number and not time:
        raw = number.group(0)
        remainder = (value[: number.start()] + value[number.end() :]).strip().lower()
        stem = re.sub(r"[^a-z]", "", remainder)[:3]
        word = spelled(int(raw)) if raw.isdigit() else None
        if word and re.search(rf"\b{re.escape(word)}\b[\s-]*\S{{0,3}}\s*{re.escape(stem)}", low):
            return "spelled-out number"
        if stem and re.search(rf"(?<!\d){re.escape(raw)}-{re.escape(stem)}", low):
            return "hyphenated compound (e.g. 11-week)"
        if re.search(rf"\$?{re.escape(raw)}\.0+(?!\d)", text):
            return "decimal or currency format (e.g. $85.00)"
        if re.search(rf"(?<![\d.]){re.escape(raw)}(?!\d)", text):
            return "number present with a different unit or format"
    tokens = [t for t in re.findall(r"[A-Za-z]{3,}", value)]
    if len(tokens) >= 2 and any(contains(text, t) for t in tokens):
        return "partial value (some tokens only)"
    return "not found in any form"


def v1_findings(d: Data, attempt: dict[str, Any]) -> list[dict[str, Any]]:
    text, out = attempt["text"], []
    for fact, mode in d.assigned(attempt["row"]):
        value, canonical = fact["value"], fact["canonical_sentence"]
        count = contains(text, value)
        if count == 0:
            near, score = nearest(text, canonical)
            out.append({"cause": "value missing", "fact": fact, "mode": mode, "actual": near,
                        "score": score, "alt": alt_form(text, value)})
        elif count > 1:
            hits = [s for s in sentences(text) if contains(s, value)]
            out.append({"cause": "value present more than once", "fact": fact, "mode": mode,
                        "actual": " || ".join(hits), "score": 1.0})
        if mode == "templated" and text.count(canonical) != 1:
            near, score = nearest(text, canonical)
            out.append({"cause": "templated sentence missing or altered", "fact": fact,
                        "mode": mode, "actual": near, "score": score})
        if mode == "paraphrased":
            if canonical in text:
                out.append({"cause": "canonical sentence leaked in a paraphrased doc",
                            "fact": fact, "mode": mode, "actual": canonical, "score": 1.0})
            if fact["canonical_prefix"] in text:
                hit = next((s for s in sentences(text) if fact["canonical_prefix"] in s), "")
                out.append({"cause": "canonical prefix leaked in a paraphrased doc",
                            "fact": fact, "mode": mode, "actual": hit, "score": 1.0})
    return out


CAUSES = [
    "value missing",
    "value present more than once",
    "templated sentence missing or altered",
    "canonical sentence leaked in a paraphrased doc",
    "canonical prefix leaked in a paraphrased doc",
]


def section_b(d: Data) -> list[str]:
    lines = [
        "## B. V1 sub-causes",
        "",
        "Counts are (attempt, assigned fact) pairs, recomputed from the stored texts with the same "
        "tests V1 uses. One failed attempt can contribute to several causes.",
        "",
    ]
    found: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for model, attempts in d.models.items():
        found[model] = defaultdict(list)
        for a in attempts:
            if "V1" not in a["rules"]:
                continue
            for item in v1_findings(d, a):
                item["doc_id"], item["attempt"] = a["doc_id"], a["attempt"]
                found[model][item["cause"]].append(item)
    models = list(d.models)
    lines += md_table(
        ["sub-cause"] + models,
        [[c] + [len(found[m][c]) for m in models] for c in CAUSES]
        + [["attempts with a V1 reason"] + [sum("V1" in a["rules"] for a in d.models[m]) for m in models]]
        + [["of those, attempts whose text is empty"]
           + [sum("V1" in a["rules"] and not a["text"].strip() for a in d.models[m]) for m in models]]
        + [["value missing, excluding empty-text attempts"]
           + [sum(1 for i in found[m]["value missing"] if i["actual"] != "") for m in models]],
    )
    lines += ["", "### Absent values that appear in another form", ""]
    alts = ["case, spacing or hyphenation variant", "spelled-out number",
            "hyphenated compound (e.g. 11-week)", "decimal or currency format (e.g. $85.00)",
            "number present with a different unit or format", "different spacing, unit or format",
            "partial value (some tokens only)", "not found in any form"]
    counts = {m: Counter(i["alt"] for i in found[m]["value missing"]) for m in models}
    lines += md_table(["form of the absent value"] + models,
                      [[a] + [counts[m][a] for m in models] for a in alts])
    for model in models:
        for cause in CAUSES:
            items = found[model][cause]
            lines += ["", f"### {model}: {cause} ({len(items)})", ""]
            if not items:
                lines.append("(none)")
                continue
            for item in items[:3]:
                fact = item["fact"]
                lines += [
                    f"- {item['doc_id']} attempt {item['attempt']} ({item['mode']}): assigned value "
                    f"`{fact['value']}` (entity `{fact['entity']}`)",
                    f"  - expected: `{fact['canonical_sentence']}`",
                    f"  - actual ({'nearest sentence, similarity %.2f' % item['score']}): "
                    f"`{clip(item['actual'])}`"
                    + (f" [alt form: {item['alt']}]" if "alt" in item else ""),
                ]
    lines.append("")
    return lines


# ---- C ----------------------------------------------------------------------------------


def word_distance(text: str, entity: str, value: str) -> int | None:
    e = [m.start() for m in re.finditer(re.escape(entity), text)]
    v = [m.start() for m in re.finditer(re.escape(value), text)]
    if not e or not v:
        return None
    index = [m.start() for m in WORD_RE.finditer(text)]

    def widx(pos: int) -> int:
        return sum(1 for p in index if p < pos)

    return min(abs(widx(a) - widx(b)) for a in e for b in v)


def entity_form(sentence: str, entity: str) -> str:
    low = sentence.lower()
    if re.search(rf"\b{re.escape(entity)}(?:s|es)\b", sentence):
        return "plural"
    if entity not in sentence and entity.lower() in low:
        return "case variant"
    if entity in sentence:
        return "exact entity present"
    tokens = [t for t in WORD_RE.findall(entity) if len(t) > 2]
    if len(tokens) > 1 and any(t.lower() in low for t in tokens):
        return "alias (partial entity)"
    if PRONOUNS & set(WORD_RE.findall(low)):
        return "pronoun or reference word"
    return "entity absent"


def section_c(d: Data) -> list[str]:
    lines = ["## C. V2 entity/value binding", ""]
    for model, attempts in d.models.items():
        rows, forms, dist, kinds = [], Counter(), Counter(), Counter()
        for a in attempts:
            if "V2" not in a["rules"]:
                continue
            text, sents = a["text"], sentences(a["text"])
            for fact, _mode in d.assigned(a["row"]):
                entity, value = fact["entity"], fact["value"]
                bound = [s for s in sents if entity in s and value in s]
                if bound:
                    if len(WORD_RE.findall(bound[0])) <= 25:
                        continue
                    kinds["window too wide (> 25 words)"] += 1
                    sentence = bound[0]
                else:
                    kinds["entity and value never share a sentence"] += 1
                    sentence = next((s for s in sents if value in s), "")
                form = entity_form(sentence, entity) if sentence else "value absent"
                forms[form] += 1
                gap = word_distance(text, entity, value)
                if gap is None:
                    label = "entity absent" if entity not in text else "value absent"
                elif gap <= 10:
                    label = "<= 10 words"
                elif gap <= 25:
                    label = "11-25 words"
                elif gap <= 50:
                    label = "26-50 words"
                else:
                    label = "> 50 words"
                dist[label] += 1
                rows.append([a["doc_id"], a["attempt"], entity, value, clip(sentence, 160),
                             len(WORD_RE.findall(sentence)), form])
        lines += [f"### {model}", "", f"Failing (attempt, fact) pairs: {sum(kinds.values())}", ""]
        lines += md_table(["kind", "count"], sorted(kinds.items()))
        lines += ["", "Entity form in the sentence that holds the value:", ""]
        lines += md_table(["form", "count"], sorted(forms.items()))
        lines += ["", "Word distance between entity and value (closest pair anywhere in the document):", ""]
        order = ["<= 10 words", "11-25 words", "26-50 words", "> 50 words", "entity absent", "value absent"]
        lines += md_table(["distance", "count"], [[k, dist[k]] for k in order])
        lines += ["", "Failing pairs:", ""]
        lines += md_table(["doc_id", "attempt", "entity", "value", "sentence with value",
                           "words", "entity form"], rows)
        lines.append("")
    return lines


# ---- D ----------------------------------------------------------------------------------


def line_kind(lines: list[str], index: int, token: str) -> str:
    line = lines[index].strip()
    nonempty = [i for i, ln in enumerate(lines) if ln.strip()]
    if line.startswith(token + ":"):
        return "chat label"
    tail = nonempty[-3:]
    if index in tail and ("Desk" in line or not re.search(r"[.!?][\"')]*$", line)):
        return "sign-off"
    short = len(WORD_RE.findall(line)) <= 14 and not re.search(r"[.!?][\"')]*$", line)
    if index == nonempty[0] or short:
        return "heading/title line"
    return "body sentence"


def flagged_locations(text: str, row: dict[str, Any], kb: dict[str, Any]) -> list[tuple[str, str]]:
    flagged = flagged_capitals(text, row, kb)
    wanted = set(flagged)
    stripped = text.strip()
    lines = stripped.split("\n")
    starts = [0]
    for line in lines[:-1]:
        starts.append(starts[-1] + len(line) + 1)
    out: list[tuple[str, str]] = []
    position = 0
    for part in re.split(r"(?<=[.!?])\s+", stripped):
        chunk = part.strip()
        if not chunk:
            continue
        offset = stripped.find(chunk, position)
        position = offset + len(chunk)
        label = SPEAKER_LABEL.match(chunk)
        after = chunk[label.end():] if label else ""
        for m in re.finditer(r"\b[A-Z][A-Za-z'-]*\b", chunk):
            token = m.group(0)
            if token not in wanted or token in ALLOWED_CAPITALS:
                continue
            if chunk.startswith(token) or (after and after.startswith(token)):
                continue
            line_index = max(i for i, s in enumerate(starts) if s <= offset + m.start())
            out.append((token, line_kind(lines, line_index, token)))
    return out


def title_style(text: str) -> str | None:
    first = next((x.strip() for x in text.strip().split("\n") if x.strip()), "")
    if not first or first.startswith("Subject:"):
        return None
    if re.search(r"[.!?][\"')]*$", first) or len(WORD_RE.findall(first)) > 14:
        return None
    words = [w for w in WORD_RE.findall(first) if len(w) > 3]
    if first[:1].islower():
        return "lowercase-initial title line"
    caps = sum(w[:1].isupper() for w in words)
    if words and caps / len(words) >= 0.7:
        return "Title Case heading"
    if any(w[:1].islower() for w in words):
        return "sentence-case title line"
    return "other title line"


def section_d(d: Data) -> list[str]:
    lines = [
        "## D. V5 flagged capitalized tokens",
        "",
        "Counts are flagged occurrences over all attempts of the model (not only attempts that "
        "failed V5), using the validator's own `flagged_capitals`.",
        "",
    ]
    for model, attempts in d.models.items():
        tally: Counter[str] = Counter()
        where: dict[str, Counter[str]] = defaultdict(Counter)
        styles: Counter[str] = Counter()
        mismatch = 0
        for a in attempts:
            located = flagged_locations(a["text"], a["row"], d.kb)
            if len(located) != len(flagged_capitals(a["text"], a["row"], d.kb)):
                mismatch += 1
            for token, kind in located:
                tally[token] += 1
                where[token][kind] += 1
            style = title_style(a["text"])
            if style:
                styles[style] += 1
        lines += [f"### {model}", ""]
        kinds = ["heading/title line", "sign-off", "body sentence", "chat label"]
        lines += md_table(
            ["token", "count"] + kinds,
            [[t, n] + [where[t][k] for k in kinds] for t, n in tally.most_common(25)],
        )
        total = Counter()
        for t in tally:
            total.update(where[t])
        lines += ["", "Occurrences by location: " + ", ".join(f"{k} {total[k]}" for k in kinds)]
        if mismatch:
            lines.append(f"(location tagging could not align {mismatch} attempts exactly)")
        lines += ["", "Title lines (first non-empty line without terminal punctuation, 14 words or fewer, "
                  "not a Subject line); unit is attempts:", ""]
        lines += md_table(["title style", "attempts"], sorted(styles.items()))
        lines.append("")
    return lines


# ---- E ----------------------------------------------------------------------------------


def section_e(d: Data) -> list[str]:
    lines = ["## E. V6 triggers (gpt-5.4-mini)", ""]
    model = next((m for m in d.models if "mini" in m), None)
    if model is None:
        return lines + ["(no mini data)", ""]
    shown: set[str] = set()
    for a in d.models[model]:
        if "V6" not in a["rules"] or a["doc_id"] in shown or len(shown) >= 3:
            continue
        shown.add(a["doc_id"])
        questions = [s for s in sentences(a["text"]) if s.endswith("?")]
        markers = [clip(a["text"][max(0, m.start() - 40): m.end() + 40], 120) for m in QA_RE.finditer(a["text"])]
        lines += [
            f"- {a['doc_id']} attempt {a['attempt']} ({a['row']['doc_type']}): reasons "
            f"{[r for r in a['reasons'] if r.startswith('V6')]}",
            f"  - question sentences: {len(questions)} (rule: more than 2 fails)",
        ]
        lines += [f"    - `{clip(q, 160)}`" for q in questions[:4]]
        lines.append(f"  - Q/A marker matches: {len(markers)}")
        lines += [f"    - `{m}`" for m in markers[:4]]
    if not shown:
        lines.append("(no V6 failures)")
    lines.append("")
    return lines


# ---- F ----------------------------------------------------------------------------------

BINS = [("< 0.6", 0, 0.6), ("0.6-0.8", 0.6, 0.8), ("0.8-1.2", 0.8, 1.2), ("1.2-1.4", 1.2, 1.4), ("> 1.4", 1.4, 99)]


def bin_of(ratio: float) -> str:
    return next(name for name, lo, hi in BINS if lo <= ratio < hi)


def section_f(d: Data) -> list[str]:
    lines = ["## F. V8 length ratio (actual words / target words), all attempts", ""]
    models = list(d.models)
    ratios = {m: [(a["row"]["doc_type"], a["words"] / a["row"]["target_words"]) for a in d.models[m]] for m in models}
    lines += md_table(
        ["ratio bin"] + models,
        [[name] + [sum(bin_of(r) == name for _t, r in ratios[m]) for m in models] for name, _lo, _hi in BINS]
        + [["mean ratio"] + [f"{sum(r for _t, r in ratios[m]) / len(ratios[m]):.3f}" for m in models]],
    )
    for model in models:
        lines += ["", f"### {model} by doc type", ""]
        types = sorted({t for t, _r in ratios[model]})
        body = []
        for t in types:
            sel = [r for tt, r in ratios[model] if tt == t]
            body.append([t, len(sel)] + [sum(bin_of(r) == n for r in sel) for n, _l, _h in BINS]
                        + [f"{sum(sel) / len(sel):.3f}"])
        lines += md_table(["doc type", "attempts"] + [n for n, _l, _h in BINS] + ["mean ratio"], body)
    lines.append("")
    return lines


# ---- G ----------------------------------------------------------------------------------


def section_g(d: Data) -> list[str]:
    lines = ["## G. Retry dynamics", ""]
    for model in d.models:
        docs = d.by_doc(model)
        lines += [f"### {model}", ""]
        body = []
        for n in (1, 2, 3):
            at = [x for atts in docs.values() for x in atts if x["attempt"] == n]
            ok = sum(x["ok"] for x in at)
            body.append([n, len(at), ok, f"{ok / len(at):.1%}" if at else "-"])
        lines += md_table(["attempt", "attempts made", "passed", "pass rate"], body)
        for n in (2, 3):
            counts: dict[str, Counter[str]] = defaultdict(Counter)
            for atts in docs.values():
                prev = next((x for x in atts if x["attempt"] == n - 1), None)
                cur = next((x for x in atts if x["attempt"] == n), None)
                if not prev or not cur or prev["ok"]:
                    continue
                for rule in prev["rules"]:
                    if rule in cur["rules"]:
                        status = "persisted"
                    elif set(cur["rules"]) - set(prev["rules"]):
                        status = "replaced by a new rule"
                    else:
                        status = "fixed"
                    counts[rule][status] += 1
            lines += ["", f"Attempt {n - 1} -> {n}: fate of each rule that failed at attempt {n - 1}:", ""]
            body = []
            for rule in sorted(counts):
                total = sum(counts[rule].values())
                body.append([rule, total] + [
                    f"{counts[rule][s]} ({counts[rule][s] / total:.0%})"
                    for s in ("fixed", "persisted", "replaced by a new rule")
                ])
            lines += md_table(["prior rule", "docs", "fixed", "persisted", "replaced by a new rule"], body) if body else ["(no retries)"]
        lines.append("")
    return lines


# ---- H ----------------------------------------------------------------------------------


def section_h(d: Data) -> list[str]:
    lines = [
        "## H. Tokens and cost",
        "",
        "Per-call means are over every non-cached call. Rows marked HYPOTHETICAL are arithmetic on "
        "the observed means, not measurements: cost = 2407 docs x attempts per doc x (mean input "
        "tokens x input price + output tokens x output price). Visible output = output tokens - "
        "reasoning tokens.",
        "",
    ]
    rows = []
    cost_rows: list[list[Any]] = []
    for model, attempts in d.models.items():
        calls = [a for a in attempts if not a["cached"]]
        mean = lambda k: sum(a[k] for a in calls) / len(calls)  # noqa: E731
        docs = d.by_doc(model)
        per_doc = sum(
            next((x["attempt"] for x in atts if x["ok"]), 3) for atts in docs.values()
        ) / len(docs)
        price = d.config["models"][model]
        n_in, n_out, n_reason = mean("input_tokens"), mean("output_tokens"), mean("reasoning_tokens")
        visible = n_out - n_reason

        def cost(attempts_per_doc: float, output: float, price=price, n_in=n_in) -> float:
            per_call = (n_in * price["input_usd_per_million"] + output * price["output_usd_per_million"]) / 1e6
            return FULL_RUN_DOCS * attempts_per_doc * per_call

        rows.append([model, f"{n_in:.0f}", f"{n_out:.0f}", f"{n_reason:.0f}", f"{visible:.0f}",
                     f"{n_reason / n_out:.1%}", f"{per_doc:.2f}"])
        scenarios = [
            ("observed tokens, observed attempts per doc", per_doc, n_out, "observed means"),
            ("HYPOTHETICAL: zero reasoning tokens, observed attempts per doc", per_doc, visible, "hypothetical"),
            ("HYPOTHETICAL: observed tokens, 70% first-attempt pass (1.43 attempts per doc)", 1.43, n_out, "hypothetical"),
            ("HYPOTHETICAL: zero reasoning tokens, 70% first-attempt pass (1.43 attempts per doc)", 1.43, visible, "hypothetical"),
        ]
        cost_rows.extend(
            [[model, name, f"{a:.2f}", f"{n_in:.0f}", f"{o:.0f}", f"${cost(a, o):.2f}"]
             for name, a, o, _k in scenarios]
        )
    lines += md_table(
        ["model", "mean input / call", "mean output / call", "mean reasoning / call",
         "mean visible output / call", "reasoning share of output", "observed attempts / doc"],
        rows,
    )
    lines += [""]
    lines += md_table(
        ["model", "scenario", "attempts / doc", "input tokens / call", "output tokens / call",
         "full-run cost (2407 docs)"],
        cost_rows,
    )
    lines.append("")
    return lines


# ---- I ----------------------------------------------------------------------------------


def section_i(d: Data) -> list[str]:
    reason_counts: Counter[str] = Counter()
    attempt_counts: Counter[str] = Counter()
    for attempts in d.models.values():
        for a in attempts:
            if not a["ok"]:
                attempt_counts.update(a["rules"])
                reason_counts.update(rule_ids([r]) [0] for r in a["reasons"])
    top = [r for r, _n in reason_counts.most_common(3)]
    lines = [
        "## I. Rejected attempts in full",
        "",
        "Failure types ranked by number of validator reason lines over both models (the same "
        "basis as the reason histogram in pilot_report.md): "
        + ", ".join(f"{r} ({reason_counts[r]} reasons in {attempt_counts[r]} attempts)" for r in top)
        + ". One attempt per model per type, first match by doc_id.",
        "",
    ]
    used: dict[str, set[str]] = defaultdict(set)
    for model, attempts in d.models.items():
        for rule in top:
            pick = next((a for a in attempts if not a["ok"] and rule in a["rules"] and a["doc_id"] not in used[model]), None)
            pick = pick or next((a for a in attempts if not a["ok"] and rule in a["rules"]), None)
            lines += [f"### {model} - {rule}", ""]
            if pick is None:
                lines += ["(no attempt)", ""]
                continue
            used[model].add(pick["doc_id"])
            assigned = [
                f"{f['entity']} = {f['value']} ({m})" for f, m in d.assigned(pick["row"])
            ] or ["none (background)"]
            lines += [
                f"- doc_id: {pick['doc_id']}, attempt {pick['attempt']}, doc type {pick['row']['doc_type']}, "
                f"target {pick['row']['target_words']} words, actual {pick['words']} words",
                f"- assigned facts + modes: {'; '.join(assigned)}",
                "- canonical sentences: " + " | ".join(f["canonical_sentence"] for f, _m in d.assigned(pick["row"])),
                f"- rules failed: {', '.join(pick['rules'])}",
                "- reasons:",
            ]
            lines += [f"  - {r}" for r in pick["reasons"]]
            lines += ["", "```text", pick["text"], "```", ""]
    return lines


# ---- J ----------------------------------------------------------------------------------


def history(atts: list[dict[str, Any]]) -> str:
    return " | ".join(
        f"a{a['attempt']}: " + ("PASS" if a["ok"] else ",".join(a["rules"])) for a in atts
    )


def section_j(d: Data) -> list[str]:
    lines = ["## J. Coverage gap (zero accepted documents)", ""]
    for model in d.models:
        docs = d.by_doc(model)
        lines += [f"### {model}", ""]
        for label, key in (
            ("doc types", lambda r: r["doc_type"]),
            ("modes / categories", lambda r: f"{r.get('pilot_category', '?')} [{modes_label(r)}]"),
        ):
            groups: dict[str, list[str]] = defaultdict(list)
            for doc_id, atts in docs.items():
                groups[key(atts[0]["row"])].append(doc_id)
            empty = [g for g, ids in sorted(groups.items()) if not any(docs[i][-1]["ok"] for i in ids)]
            lines.append(f"{label} with zero accepted docs: {', '.join(empty) or 'none'}")
            for g in empty:
                for doc_id in groups[g]:
                    lines.append(f"- {g} / {doc_id}: {history(docs[doc_id])}")
            lines.append("")
    return lines


def build(d: Data) -> str:
    lines = [
        "# Pilot failure diagnosis",
        "",
        "Report only: no interpretation or recommendation. Source: data/pilot/ (attempt records "
        "with stored texts, reasons and token usage), pilot_rows.jsonl, the KB and the config. "
        "Rule ids come from the validator reasons stored at run time; sub-cause counts are "
        "recomputed from the texts.",
        "",
    ]
    for section in (section_notes, section_a, section_b, section_c, section_d, section_e, section_f,
                    section_g, section_h, section_i, section_j):
        lines += section(d)
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pilot-dir", type=Path, default=ROOT / "data" / "pilot")
    parser.add_argument("--out", type=Path, default=ROOT / "reports" / "tables" / "pilot_failures.md")
    parser.add_argument("--kb", type=Path, default=ROOT / "data" / "kb" / "kb.json")
    parser.add_argument("--config", type=Path, default=ROOT / "configs" / "generation.yaml")
    parser.add_argument("--validator", choices=["v1", "v2", "v3", "v4", "v5"], default="v1",
                        help="validator whose V5 flags are tabulated in section D")
    args = parser.parse_args(argv)
    VALIDATOR["name"] = args.validator
    data = Data(args.pilot_dir, args.kb, args.config)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(build(data), encoding="utf-8")
    print(f"Wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

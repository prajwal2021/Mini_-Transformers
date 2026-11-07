# ruff: noqa: E501
"""R09 demo prompts: novelty check (numbers only) and the real transcript.

    python scripts/demo_prompts.py check   # overlap of each candidate prompt with every corpus split and the SFT/QA files (prints numbers only)
    python scripts/demo_prompts.py run     # runs the prompts through scripts/generate.py on the bundles and writes docs/demo_transcript.md

The check reads, text only (no tokenizer): data/corpus/{train,val,test}.jsonl, data/sft/{sft_train,sft_val}.jsonl and data/eval/qa_test.jsonl.
For the two TEST files it computes only "exact match?" and "longest shared word run" and prints those numbers: no test text is printed, shown or saved,
and nothing is evaluated (no model, no ledger line; the user asked for the ledger to stay at 4 lines). Novel = no exact match and a shared run
shorter than 8 words with every source; a 13-word shingle search is reported too (prompts shorter than 13 words cannot contain one).
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "bundle"

FREE_TEXT = [  # novel continuations for the PRETRAINED model
    "Passengers who arrive with a nervous cat should first",
    "Before boarding the airship, every traveller with a pet must",
    "The quietest place for an animal to rest during a long flight is",
]
QUESTIONS = [  # novel questions for the SFT models
    "I am flying with a kitten soon, how many weeks old does it need to be?",
    "Which person is in charge of the pet lounge at Vellmar?",
    "What would it cost to bring my cat on the airship?",
]
FAILURE = "Who looks after the cargo pets on the Zephyrine?"  # an entity that is not in the knowledge base: expect an invented answer
STORED_FACT_ID = None  # chosen from the probe table by `pick_stored`; the canonical prefix is KB text (not test data)


def norm(s: str) -> str:
    return " ".join(re.findall(r"[a-z0-9$:.'-]+", s.lower()))


def sources() -> dict[str, str]:
    out = {}
    for name, files in {"corpus_train": ["data/corpus/train.jsonl"], "corpus_val": ["data/corpus/val.jsonl"], "corpus_test": ["data/corpus/test.jsonl"],
                        "sft_train_val": ["data/sft/sft_train.jsonl", "data/sft/sft_val.jsonl"], "qa_test": ["data/eval/qa_test.jsonl"]}.items():
        texts = []
        for f in files:
            for line in (ROOT / f).read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                d = json.loads(line)
                texts += [str(d[k]) for k in ("text", "question", "answer", "prompt") if k in d]
        out[name] = " \x00 ".join(norm(t) for t in texts)  # NUL keeps runs from crossing documents
    return out


def longest_run(prompt: str, hay: str) -> int:
    w = norm(prompt).split()
    best = 0
    for i in range(len(w)):
        for j in range(len(w), i + best, -1):  # only try runs longer than the best so far
            if " ".join(w[i:j]) in hay:
                best = j - i
                break
    return best


def check(prompts: list[str]) -> list[dict]:
    src = sources()
    rows = []
    for p in prompts:
        w = norm(p).split()
        row = {"prompt": p, "words": len(w)}
        for name, hay in src.items():
            row[name] = {"exact": norm(p) in hay, "longest_shared_run_words": longest_run(p, hay),
                         "has_13gram": len(w) >= 13 and any(" ".join(w[i:i + 13]) in hay for i in range(len(w) - 12))}
        row["novel"] = all(not v["exact"] and v["longest_shared_run_words"] < 8 and not v["has_13gram"] for k, v in row.items() if isinstance(v, dict))
        rows.append(row)
    return rows


def pick_stored() -> dict:
    """A high-exposure fact stored (rank 1, binding > 0) at E* on the canonical probe in all three seeds, from the written probe table; its KB canonical prefix."""
    import pandas as pd

    p = pd.read_csv(ROOT / "runs/real/probes/probes_raw.csv")
    p = p[(p["split"] == "test") & (p["checkpoint"].astype(str) == "2970") & (p["probe_frame"] == "canonical")]
    ok = p.groupby("fact_id").stored.all()
    kb = json.loads((ROOT / "data/kb/kb.json").read_text(encoding="utf-8"))["measured_facts"]
    cand = [f for f in kb if f["fact_id"] in set(ok[ok].index) and f["freq_bin"] == "high" and f["div_bin"] == "templated"]
    cand += [f for f in kb if f["fact_id"] in set(ok[ok].index) and f["freq_bin"] == "high" and f["div_bin"] == "paraphrased"]
    return {"candidates": [f["fact_id"] for f in cand], "facts": cand}


def gen(args: list[str]) -> str:
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "generate.py"), *args], capture_output=True, text=True, cwd=ROOT, encoding="utf-8", errors="replace")
    if r.returncode:
        raise SystemExit(r.stderr)
    return r.stdout


def completion(out: str) -> str:
    return next(line[len("completion: "):] for line in out.splitlines() if line.startswith("completion: "))


def pick_trained_question() -> dict:
    """First SFT TRAINING question (file order) that the fixed-3 SFT answers exactly with greedy decoding (train file only, no test data)."""
    sys.path.insert(0, str(ROOT / "src"))
    from slm.bundle import load_bundle
    from slm.generation import generate_text, newline_token_ids
    from slm.sft_eval import load_attribute_values
    from slm.sft_eval.evaluate import clean_prediction, occurs

    b = load_bundle(BUNDLE / "sft_fixed3", "cpu")
    av = load_attribute_values(ROOT / "data" / "kb" / "kb.json")
    stop = newline_token_ids(b.tokenizer)
    for line in (ROOT / "data" / "sft" / "sft_train.jsonl").read_text(encoding="utf-8").splitlines():
        r = json.loads(line)
        text, _ = generate_text(b.model, b.tokenizer, r["prompt"], 48, stop, "cpu")
        pred = clean_prediction(text)
        if occurs(pred, r["value"]) and not any(occurs(pred, v) for v in av[r["attribute_id"]] if v != r["value"]):
            return r
    raise SystemExit("no SFT training question answered correctly by sft_fixed3")


def cli(args: list[str]) -> tuple[str, str]:
    """(shown command, completion line) for one scripts/generate.py call."""
    out = gen(args)
    shown = "python scripts/generate.py " + " ".join(f'"{a}"' if " " in a else a for a in args)
    return shown, completion(out)


def write_transcript() -> int:
    st = pick_stored()
    chosen = st["facts"][0]  # a fact stored by all three seeds on the probe criterion; the demo shows what free completion does with it
    trained = pick_trained_question()
    md =["# Demo transcript (real outputs)", "",
          "Every output below was produced by `scripts/generate.py` on the release bundle (CPU, bundle in `bundle/`). Nothing is edited. "
          "Greedy = `--temperature 0`; sampled = `--temperature 0.8 --seed 0`. Models: `pretrained` (seed 0, E*=30), `sft_early_stopped` (the pre-specified primary SFT), "
          "`sft_fixed3` (the post-hoc secondary SFT). The prompts in sections 1, 2 and 4 do not occur in the corpus (train/val/test) or the SFT/QA files "
          "(no exact match, no shared run of 8 or more words; checked by `scripts/demo_prompts.py check`). Section 3 is a training fact on purpose.", ""]
    sampled = ["--temperature", "0.8", "--seed", "0"]

    def block(title: str, note: str, items: list[tuple[str, list[str]]]) -> None:
        md.extend([f"## {title}", "", note, ""])
        for name, base in items:
            for label, extra in (("greedy", []), ("sampled T=0.8", sampled)):
                shown, comp = cli([*base, *extra])
                md.extend([f"**{name}, {label}**", "", "```", shown, f"completion: {comp}", "```", ""])

    block("1. Free-text prompts, pretrained model", "Novel openings; a pretrained model continues text, it does not answer questions.",
          [("pretrained", ["--bundle", "bundle/pretrained", "--prompt", p, "--max-new-tokens", "40"]) for p in FREE_TEXT])
    qitems = []
    for q in QUESTIONS:
        for b in ("pretrained", "sft_early_stopped", "sft_fixed3"):
            qitems.append((b, ["--bundle", f"bundle/{b}", "--qa", q]))
    md.extend(["## 2. Novel questions", "", "The same three questions through all three models (`--qa` wraps the question as `Question: <q>` + newline + `Answer:`).", ""])
    for q in QUESTIONS:
        md.extend([f"### {q}", ""])
        for b in ("pretrained", "sft_early_stopped", "sft_fixed3"):
            for label, extra in (("greedy", []), ("sampled T=0.8", sampled)):
                shown, comp = cli(["--bundle", f"bundle/{b}", "--qa", q, *extra])
                md.extend([f"**{b}, {label}**", "", "```", shown, f"completion: {comp}", "```", ""])
    md.extend(["## 3a. A fact the model was fine-tuned on, answered (success)", "",
               f"This question is one of the SFT training questions (`data/sft/sft_train.jsonl`, fact {trained['fact_id']}), so it shows learned recall, not generalisation. Gold answer: **{trained['answer']}** "
               "Chosen as the first training question (in file order) that the fixed-3 SFT answers correctly with greedy decoding; the other models' outputs are shown as they came out.", ""])
    for b in ("pretrained", "sft_early_stopped", "sft_fixed3"):
        for label, extra in (("greedy", []), ("sampled T=0.8", sampled)):
            shown, comp = cli(["--bundle", f"bundle/{b}", "--qa", trained["question"], *extra])
            md.extend([f"**{b}, {label}**", "", "```", shown, f"completion: {comp}", "```", ""])
    block("3b. A fact the probe calls stored, completed freely (pretrained model)", f"Fact {chosen['fact_id']} ({chosen['attribute_id']}) is ranked first among its six candidate values (stored) by all three pretraining seeds at E* on the canonical probe. KB value: **{chosen['value']}**. The probe ranks six candidates; free greedy decoding does not have to produce the value, and here it does not.",
          [("pretrained", ["--bundle", "bundle/pretrained", "--prompt", chosen["canonical_prefix"], "--max-new-tokens", "12"])])
    md.extend(["## 4. A plausible failure: an entity that is not in the knowledge base", "", "The Zephyrine does not exist in the knowledge base. A fluent answer is therefore an invention; the models were trained to produce an answer sentence, not to say they do not know.", ""])
    for b in ("pretrained", "sft_early_stopped", "sft_fixed3"):
        for label, extra in (("greedy", []), ("sampled T=0.8", sampled)):
            shown, comp = cli(["--bundle", f"bundle/{b}", "--qa", FAILURE, *extra])
            md.extend([f"**{b}, {label}**", "", "```", shown, f"completion: {comp}", "```", ""])
    md.extend(["## 5. Comparing all models on one question", "", "```", "python scripts/generate.py --bundle-root bundle --compare --qa \"" + QUESTIONS[2] + "\"", gen(["--bundle-root", "bundle", "--compare", "--qa", QUESTIONS[2]]).strip(), "```", ""])
    (ROOT / "docs" / "demo_transcript.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print("wrote docs/demo_transcript.md; stored fact:", chosen["fact_id"])
    return 0


def main() -> int:
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "check":
        st = pick_stored()
        print("stored-everywhere high-exposure facts (canonical probe, 3 seeds, E*):", st["candidates"][:12])
        for f in st["facts"][:12]:
            print(f"  {f['fact_id']} {f['attribute_id']} prefix={f['canonical_prefix']!r} value={f['value']!r}")
        rows = check(FREE_TEXT + QUESTIONS + [FAILURE])
        for r in rows:
            print(json.dumps({k: v for k, v in r.items()}, default=str)[:600])
        return 0
    if cmd == "run":
        return write_transcript()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

# ruff: noqa: E501
"""Checkpoint sample generator (R01 4; DESIGN 6 gallery, course spec 6: document successes AND failures).

Fixed prompt lists, greedy + temperature 0.8 samples at every saved checkpoint (and ``init``) of
one seed, a temperature sweep on the final checkpoint, flags by the taxonomy rules
(``slm.sft_eval.taxonomy``) and an automatic, checkpoint-spread selection of successes and failures.
"""

from __future__ import annotations

import random
import re
from collections.abc import Mapping
from pathlib import Path

import pandas as pd
import torch

from slm.eval.wording import NOVEL_IDS, prefix
from slm.generation import generate_text
from slm.integration.probing import list_checkpoints, untrained_model
from slm.model import ModelConfig, load_checkpoint
from slm.sft_eval.taxonomy import (
    CORRECT,
    FORMAT,
    HALLUCINATION,
    RIGHT_TYPE,
    WRONG_ATTRIBUTE,
    Taxonomy,
    is_degenerate,
)

OFF_DOMAIN = ("The capital of France is", "Once upon a time", "To make a good cup of tea, first", "The quick brown fox")
FLAGS = ("value_correct", "wrong_value", "hallucinated", "wrong_attribute", "gibberish", "off_domain_ok")
FLAG_OF = {CORRECT: "value_correct", RIGHT_TYPE: "wrong_value", HALLUCINATION: "hallucinated",
           WRONG_ATTRIBUTE: "wrong_attribute", FORMAT: "gibberish"}
SETTINGS_SERIES = (("greedy", 0.0, None, 1), ("t0.8", 0.8, None, 3))
SETTINGS_SWEEP = (("greedy", 0.0, None, 1), ("t0.4", 0.4, None, 3), ("t0.8", 0.8, None, 3),
                  ("t1.2", 1.2, None, 3), ("t0.8+top-k40", 0.8, 40, 3))
COLUMNS = ["data_status", "section", "checkpoint", "epoch", "seed", "prompt_id", "prompt_kind", "fact_id",
           "freq_bin", "div_bin", "setting", "sample_idx", "prompt", "completion", "flag"]


def build_prompts(kb: Mapping, n: int = 20, seed: int = 0) -> list[dict]:
    """``n`` (10 or 20) fixed prompts; the first 10 are 5 canonical + 3 novel + 2 off-domain.

    Canonical prefixes come round-robin from the six freq x div cells (seeded within a cell); novel
    prompts are the hand-written wordings n1..n3 of other facts. The list depends only on the KB and
    ``seed``, so every checkpoint sees the same prompts.
    """
    if n not in (10, 20):
        raise ValueError("n is 10 or 20")
    facts = sorted(kb["measured_facts"], key=lambda f: f["fact_id"])
    cells: dict[str, list[dict]] = {}
    for f in facts:
        cells.setdefault(f"{f['freq_bin']}_{f['div_bin']}", []).append(f)
    rng = random.Random(f"samples:{seed}")
    for k in sorted(cells):
        rng.shuffle(cells[k])
    order = [cells[k][i] for i in range(len(next(iter(cells.values())))) for k in sorted(cells)]
    canon, novel = order[:10], order[10:16]

    def item(kind: str, f: dict | None, text: str, pid: str) -> dict:
        return {"prompt_id": pid, "prompt_kind": kind, "fact_id": f["fact_id"] if f else "", "freq_bin": f["freq_bin"] if f else "",
                "div_bin": f["div_bin"] if f else "", "prompt": text}

    c = [item("canonical", f, f["canonical_prefix"].rstrip(), f"c{i}") for i, f in enumerate(canon)]
    nv = [item("novel", f, prefix(f["attribute_id"], NOVEL_IDS[i % 3], f["entity"]), f"n{i}") for i, f in enumerate(novel)]
    off = [item("off_domain", None, t, f"o{i}") for i, t in enumerate(OFF_DOMAIN)]
    first = c[:5] + nv[:3] + off[:2]
    rest = c[5:] + nv[3:] + off[2:]
    return first if n == 10 else first + rest


def completion_of(text: str) -> str:
    """The first sentence (up to . ! ? or a newline) of a generated continuation."""
    return " ".join(re.split(r"(?<=[.!?])(?:\s|$)|\n", text.strip(), maxsplit=1)[0].split())


def flag_of(taxonomy: Taxonomy, kb_facts: Mapping[str, dict], prompt: dict, text: str) -> str:
    comp = completion_of(text)
    if prompt["prompt_kind"] == "off_domain":
        junk = sum(not (ch.isprintable() and ord(ch) < 0x2500) for ch in comp) > 0.2 * max(len(comp), 1)
        return "gibberish" if (not comp or is_degenerate(comp) or junk) else "off_domain_ok"
    f = kb_facts[prompt["fact_id"]]
    return FLAG_OF[taxonomy.classify(comp, f["attribute_id"], f["value"])]


def _generate(model, tok, device, prompt: str, temperature: float, top_k: int | None, sample_seed: int, max_new: int) -> str:
    text, _ = generate_text(model, tok, prompt, max_new, (), device, temperature, top_k, sample_seed)
    return text


def run_samples(
    pretrain_root: str | Path, tokenizer, kb: Mapping, *, seed: int = 0, data_status: str = "MOCK",
    max_new_tokens: int = 32, device: str | None = None,
) -> pd.DataFrame:
    """The checkpoint series (10 prompts) and the temperature sweep (20 prompts, final checkpoint)."""
    dev = torch.device(device or ("cuda" if torch.cuda.is_available() else "cpu"))
    tax, facts = Taxonomy.from_kb(kb), {f["fact_id"]: f for f in kb["measured_facts"]}
    ckpts = list_checkpoints(Path(pretrain_root) / f"seed{seed}")
    if not ckpts:
        raise FileNotFoundError(f"no epoch checkpoints under {pretrain_root}/seed{seed}")
    cfg = ModelConfig.from_dict(torch.load(ckpts[-1][2], map_location="cpu", weights_only=True)["config"])
    rows: list[dict] = []

    def add(section, ck, epoch, prompt, setting, idx, text):
        rows.append({"data_status": data_status, "section": section, "checkpoint": ck, "epoch": epoch, "seed": seed,
                     **{k: prompt[k] for k in ("prompt_id", "prompt_kind", "fact_id", "freq_bin", "div_bin")},
                     "setting": setting, "sample_idx": idx, "prompt": prompt["prompt"],
                     "completion": completion_of(text) if text.strip() else "",
                     "flag": flag_of(tax, facts, prompt, text)})

    p10, p20 = build_prompts(kb, 10, seed), build_prompts(kb, 20, seed)
    series = [("init", 0, untrained_model(cfg, seed).to(dev).eval())] + [
        (str(step), epoch, None) for step, epoch, _ in ckpts]
    for (ck, epoch, model), path in zip(series, [None] + [p for _, _, p in ckpts], strict=True):
        model = model or load_checkpoint(path, map_location=dev).to(dev).eval()
        for p in p10:
            for name, temp, top_k, n in SETTINGS_SERIES:
                for i in range(n):
                    add("checkpoint_series", ck, epoch, p, name, i, _generate(model, tokenizer, dev, p["prompt"], temp, top_k, seed * 100 + i, max_new_tokens))
    final = load_checkpoint(ckpts[-1][2], map_location=dev).to(dev).eval()
    for p in p20:
        for name, temp, top_k, n in SETTINGS_SWEEP:
            for i in range(n):
                add("temperature_sweep", str(ckpts[-1][0]), ckpts[-1][1], p, name, i, _generate(final, tokenizer, dev, p["prompt"], temp, top_k, seed * 100 + i, max_new_tokens))
    return pd.DataFrame(rows, columns=COLUMNS)


def select_samples(df: pd.DataFrame, n_each: int = 6, seed: int = 0) -> pd.DataFrame:
    """``n_each`` successes and ``n_each`` failures from the checkpoint series, spread over checkpoints.

    Success = flag value_correct. Failure = wrong_value / hallucinated, or gibberish on any prompt.
    Round-robin over checkpoints (in training order), one sample per checkpoint per round, a different
    prompt each time where possible; fewer than ``n_each`` are returned when fewer exist (the caller
    reports that, it is not padded).
    """
    s = df[df["section"] == "checkpoint_series"].copy()
    order = {ck: i for i, ck in enumerate(dict.fromkeys(s["checkpoint"]))}
    rng = random.Random(f"select:{seed}")
    picks = []
    for label, flags in (("success", {"value_correct"}), ("failure", {"wrong_value", "hallucinated", "gibberish"})):
        cand = s[s["flag"].isin(flags)]
        by_ck = {ck: g.sample(frac=1.0, random_state=rng.randrange(10**6)).to_dict("records") for ck, g in cand.groupby("checkpoint")}
        used_prompts: set[str] = set()
        chosen: list[dict] = []
        while len(chosen) < n_each and any(by_ck.values()):
            for ck in sorted(by_ck, key=order.get):
                items = by_ck[ck]
                if not items or len(chosen) >= n_each:
                    continue
                j = next((k for k, it in enumerate(items) if it["prompt_id"] not in used_prompts), 0)
                it = items.pop(j)
                used_prompts.add(it["prompt_id"])
                chosen.append({**it, "selected_as": label})
        picks.extend(chosen)
    return pd.DataFrame(picks, columns=[*COLUMNS, "selected_as"])


def sweep_table(df: pd.DataFrame) -> pd.DataFrame:
    """Per setting of the temperature sweep: n and the share of each flag, plus distinct-2."""
    t = df[df["section"] == "temperature_sweep"]
    out = []
    for name, g in t.groupby("setting", sort=False):
        words = [w for c in g["completion"] for w in [c.split()]]
        bigrams = [tuple(w[i : i + 2]) for w in words for i in range(len(w) - 1)]
        row = {"setting": name, "n": len(g), **{f: float((g["flag"] == f).mean()) for f in FLAGS},
               "distinct_2": len(set(bigrams)) / len(bigrams) if bigrams else 0.0}
        out.append(row)
    return pd.DataFrame(out)


def flag_table(df: pd.DataFrame) -> pd.DataFrame:
    """Checkpoint series: share of each flag per checkpoint (targeted prompts only for value flags)."""
    s = df[df["section"] == "checkpoint_series"]
    rows = []
    for ck, g in s.groupby("checkpoint", sort=False):
        rows.append({"checkpoint": ck, "n": len(g), **{f: float((g["flag"] == f).mean()) for f in FLAGS}})
    return pd.DataFrame(rows)


def to_markdown(df: pd.DataFrame, selected: pd.DataFrame, n_each: int, data_status: str) -> str:
    def md(t: pd.DataFrame) -> str:
        cols = list(t.columns)
        lines = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
        for r in t.itertuples(index=False):
            lines.append("| " + " | ".join((f"{v:.2f}" if isinstance(v, float) else str(v)).replace("|", "\\|").replace("\n", " ") for v in r) + " |")
        return "\n".join(lines)

    banner = ("**MOCK RUN: toy corpus and a tiny training budget. NOTHING HERE IS A RESULT.**\n\n" if data_status == "MOCK" else "")
    n_s, n_f = (selected["selected_as"] == "success").sum(), (selected["selected_as"] == "failure").sum()
    note = "" if (n_s == n_each and n_f == n_each) else f"\n> Only {n_s} of {n_each} successes and {n_f} of {n_each} failures exist in this run; the selection is not padded.\n"
    sel = selected[["selected_as", "checkpoint", "epoch", "setting", "prompt_kind", "prompt", "completion", "flag"]]
    return (f"# Checkpoint samples (seed {int(df['seed'].iloc[0])})\n\n{banner}"
            f"## Selected samples ({n_each} successes, {n_each} failures, spread over checkpoints)\n{note}\n{md(sel)}\n\n"
            f"## Flag shares per checkpoint (10 prompts x greedy + 3 samples at t=0.8)\n\n{md(flag_table(df))}\n\n"
            f"## Temperature sweep, final checkpoint (20 prompts)\n\n{md(sweep_table(df))}\n")


def categories(selected: pd.DataFrame) -> list[dict]:
    """Rows for the report's samples.csv (category/prompt/completion/note) from the selection."""
    cat = {"value_correct": "success: recalled fact", "wrong_value": "failure: entity confusion",
           "hallucinated": "failure: wrong fact", "wrong_attribute": "failure: wrong attribute",
           "gibberish": "failure: format drift"}
    out = []
    for r in selected.itertuples():
        c = "failure: repetition loop" if r.flag == "gibberish" and is_degenerate(r.completion) else cat[r.flag]
        out.append({"category": c, "prompt": r.prompt, "completion": r.completion,
                    "note": f"pretrained seed {r.seed}, checkpoint {r.checkpoint} (epoch {r.epoch}), {r.setting}: {r.flag}"})
    return out

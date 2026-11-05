"""Report-side inputs and their simulated stand-ins (docs/ANALYSIS_INPUT.md section 4).

run_facts.json   flat facts about the dataset, model and training run (other streams write it)
loss_curves.csv  seed, step, split (train|val), loss
samples.csv      category, prompt, completion, note (successes and failures)

`simulate_report_inputs` writes all three plus the probe/QA/realized-diversity tables, entirely
from a seed. Everything it makes is fake and the report builder banners it.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from slm.analysis.simulate import (
    SimParams,
    simulate_probe_table,
    simulate_qa_table,
    simulate_realized_diversity,
)

REQUIRED_RUN_FACTS = (
    "n_measured_facts", "n_cells", "facts_per_cell", "n_doc_types", "n_train_docs",
    "n_val_docs", "n_test_docs", "train_tokens", "templated_token_share_pct", "vocab_size",
    "n_layers", "d_model", "n_heads", "context_len", "n_params", "n_seeds", "epochs_chosen",
    "n_sweep_configs", "lr", "sft_epochs", "sft_lr", "prereg_commit", "analysis_commit",
)
LOSS_COLUMNS = ("seed", "step", "split", "loss")
SAMPLE_COLUMNS = ("category", "prompt", "completion", "note")


class InputError(ValueError):
    """A report input is missing or malformed."""


def load_inputs(inputs_dir: Path) -> tuple[dict, pd.DataFrame, pd.DataFrame]:
    """Read run_facts.json, loss_curves.csv and samples.csv, failing with a clear message."""
    missing = [n for n in ("run_facts.json", "loss_curves.csv", "samples.csv")
               if not (inputs_dir / n).exists()]
    if missing:
        raise InputError(f"missing report inputs in {inputs_dir}: {missing}")
    facts = json.loads((inputs_dir / "run_facts.json").read_text(encoding="utf-8"))
    absent = [k for k in REQUIRED_RUN_FACTS if k not in facts]
    if absent:
        raise InputError(f"run_facts.json lacks keys: {absent}")
    loss = pd.read_csv(inputs_dir / "loss_curves.csv")
    samples = pd.read_csv(inputs_dir / "samples.csv")
    for name, frame, cols in (("loss_curves.csv", loss, LOSS_COLUMNS),
                              ("samples.csv", samples, SAMPLE_COLUMNS)):
        gone = [c for c in cols if c not in frame.columns]
        if gone:
            raise InputError(f"{name} lacks columns: {gone}")
    return facts, loss, samples


def _sim_loss(seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    steps = np.unique(np.round(np.geomspace(100, 20000, 25)).astype(int))
    rows = []
    for s in range(3):
        for split, floor, off in (("train", 1.10, 0.0), ("val", 1.45, 0.05)):
            base = floor + 6.4 * np.exp(-steps / 2200.0) + off
            noise = rng.normal(0.0, 0.015, len(steps))
            upturn = 0.0 if split == "train" else 0.00002 * np.maximum(steps - 12000, 0)
            for step, v in zip(steps, base + noise + upturn):
                rows.append({"seed": s, "step": int(step), "split": split, "loss": round(v, 4)})
    return pd.DataFrame(rows)


def _sim_samples() -> pd.DataFrame:
    rows = [
        ("success: recalled fact", "The pet lounge at Skyport A opens at",
         "[SIM] 06:30 and closes at 21:00.", "value matches the KB"),
        ("success: recalled fact", "Question: Who is the compliance officer?\nAnswer:",
         "[SIM] The compliance officer is Person B.", "exact match after SFT"),
        ("success: consistent generation", "Booking a pet on an airship requires",
         "[SIM] a health certificate issued within the validity window.",
         "numbers and names valid"),
        ("success: novel phrasing", "How many pets may one passenger bring?",
         "[SIM] Each passenger may bring at most two pets.", "novel-frame probe, rank 1"),
        ("failure: wrong fact", "The pet lounge at Skyport C opens at",
         "[SIM] 07:00 and closes at 21:00.", "right type, wrong value"),
        ("failure: entity confusion", "The lounge manager at Skyport B is",
         "[SIM] Person D, who also manages Skyport A.", "value of another entity"),
        ("failure: repetition loop", "Cabin temperature on Airship E is",
         "[SIM] 20 degrees. 20 degrees. 20 degrees. 20 degrees.", "loops until max length"),
        ("failure: format drift", "Question: What is the pet fee for a rabbit?\nAnswer:",
         "[SIM] Fee schedule, section two, see also section two.", "no value produced"),
    ]
    return pd.DataFrame(rows, columns=list(SAMPLE_COLUMNS))


def simulate_report_inputs(out_dir: Path, seed: int = 0) -> dict[str, Path]:
    """Write every simulated input to `out_dir`; return the paths."""
    out_dir.mkdir(parents=True, exist_ok=True)
    p = SimParams(exposure_noise_sd=0.2, manipulation_strength=0.8)
    probe = simulate_probe_table(p, seed=seed, include_val=True)
    qa = simulate_qa_table(p, probe[probe["split"] == "test"], seed=seed + 1)
    realized = simulate_realized_diversity(p, seed)
    n_facts = 6 * p.n_facts_per_cell
    facts = {
        "n_measured_facts": n_facts, "n_cells": 6, "facts_per_cell": p.n_facts_per_cell,
        "n_doc_types": 11, "n_train_docs": 2407, "n_val_docs": 120, "n_test_docs": 120,
        "train_tokens": 1_000_000, "templated_token_share_pct": 3.2, "vocab_size": 8192,
        "n_layers": 6, "d_model": 384, "n_heads": 6, "context_len": 512, "n_params": 12_000_000,
        "n_seeds": p.n_seeds, "epochs_chosen": 4, "n_sweep_configs": 6, "lr": 0.0006,
        "sft_epochs": 3, "sft_lr": 0.0001, "prereg_commit": "TBD (simulated)",
        "analysis_commit": "TBD (simulated)",
    }
    paths = {
        "probe": out_dir / "probe.csv",
        "qa": out_dir / "qa.csv",
        "realized": out_dir / "realized_diversity.csv",
        "run_facts": out_dir / "run_facts.json",
        "loss": out_dir / "loss_curves.csv",
        "samples": out_dir / "samples.csv",
    }
    probe.to_csv(paths["probe"], index=False)
    qa.to_csv(paths["qa"], index=False)
    realized.to_csv(paths["realized"], index=False)
    paths["run_facts"].write_text(json.dumps(facts, indent=2), encoding="utf-8")
    _sim_loss(seed).to_csv(paths["loss"], index=False)
    _sim_samples().to_csv(paths["samples"], index=False)
    return paths

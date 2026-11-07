# ruff: noqa: E501
"""R03/R04: PREREG v5 says what the code does (margins, E* rule v2 + chance guard, epoch-60 secondary, chance baseline, freeze)."""

from pathlib import Path

import numpy as np

from slm.analysis import family
from slm.train.budget import MAX_EPOCHS, SCHEDULE, SMOOTH, SWEEP_SEED, Z_GUARD, Z_TIE

ROOT = Path(__file__).resolve().parents[1]
TEXT = (ROOT / "docs" / "PREREG.md").read_text(encoding="utf-8")


def test_prereg_is_v5_and_still_unfrozen_with_the_hash_placeholders_unchanged():
    assert TEXT.startswith("# Preregistration DRAFT v5 (NOT FROZEN)")
    if "FREEZE:BEGIN" in TEXT:  # R06: once frozen, the record must verify (hash of the file without the block)
        from slm.integration.freeze import verify

        assert verify(ROOT / "docs" / "PREREG.md")["extra"]["e_star"] == 30
    assert "`<commit hash>`, `<date>` = TBD (P05)" in TEXT and "`<analysis commit hash>` = TBD" in TEXT


def test_margins_are_final_and_equal_to_the_code():
    assert "final researcher-chosen values, not derived from any data" in TEXT
    assert "PLACEHOLDERS" not in TEXT and "(placeholders in the header)" not in TEXT
    assert "odds ratio 1.25 per tripling of exposure (+-0.223 log-odds)" in TEXT and "+-0.10 risk difference for H3/H4" in TEXT
    assert np.isclose(family.MARGIN_LOG_ODDS, 0.223, atol=1e-3) and family.MARGIN_RISK_DIFF == 0.10


def test_the_budget_rule_in_the_text_matches_the_constants_in_code():
    assert f"{{{', '.join(str(e) for e in SCHEDULE)}}}".replace("{", "").replace("}", "") in TEXT.replace("epochs ", "").replace("checkpoints at ", "")
    assert "60-epoch schedule" in TEXT and MAX_EPOCHS == 60 and (SMOOTH, Z_TIE, Z_GUARD, SWEEP_SEED) == (3, 1.0, 2.0, 100)
    for phrase in ("validation-probe stored rate", "3-checkpoint moving average", "within 1 SE", "lowest validation loss", "Chance guard",
                   "more than 2 SE", "`no_val_storage = true`", "seed 100, which is not a final seed", "5% of the optimiser steps",
                   "batch size 32", "batch size 16", "dropout {0, 0.1}", "fact-clustered", "sha256 of this schedule", "working tree is dirty"):
        assert phrase in TEXT, phrase
    assert "2E" not in TEXT


def test_nulls_chance_baseline_and_secondary_analysis_are_stated():
    for phrase in ("Interpretation of nulls", "whole CI lies inside the margins", "`null_stored_rate`", "`init` checkpoint",
                   "secondary analysis", "outside the Holm family", "epoch 60", "refuses to freeze", "configuration hash"):
        assert phrase in TEXT, phrase

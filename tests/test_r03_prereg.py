# ruff: noqa: E501
"""R03: PREREG v4 says what the code does (margins, E* rule, 2E* secondary, chance baseline, freeze)."""

from pathlib import Path

import numpy as np

from slm.analysis import family
from slm.train.budget import MAX_EPOCHS, SCHEDULE, TOL

ROOT = Path(__file__).resolve().parents[1]
TEXT = (ROOT / "docs" / "PREREG.md").read_text(encoding="utf-8")


def test_prereg_is_v4_and_still_unfrozen_with_the_hash_placeholders_unchanged():
    assert TEXT.startswith("# Preregistration DRAFT v4 (NOT FROZEN)")
    assert "FREEZE:BEGIN" not in TEXT
    assert "`<commit hash>`, `<date>` = TBD (P05)" in TEXT and "`<analysis commit hash>` = TBD" in TEXT


def test_margins_are_final_and_equal_to_the_code():
    assert "final researcher-chosen values, not derived from any data" in TEXT
    assert "PLACEHOLDERS" not in TEXT and "(placeholders in the header)" not in TEXT
    assert "odds ratio 1.25 per tripling of exposure (+-0.223 log-odds)" in TEXT and "+-0.10 risk difference for H3/H4" in TEXT
    assert np.isclose(family.MARGIN_LOG_ODDS, 0.223, atol=1e-3) and family.MARGIN_RISK_DIFF == 0.10


def test_the_budget_rule_in_the_text_matches_the_constants_in_code():
    assert f"{{{', '.join(str(e) for e in SCHEDULE)}}}".replace("{", "").replace("}", "") in TEXT.replace("epochs ", "").replace("checkpoints at ", "")
    assert "up to 60 epochs" in TEXT and MAX_EPOCHS == 60 and TOL == 0.01
    for phrase in ("validation-probe stored rate", "within 0.01", "lowest validation loss", "2E\*", "capped at 60",
                   "Validation loss never chooses E\*", "5% of the optimiser steps", "batch size {16, 32}", "dropout {0, 0.1}"):
        assert phrase in TEXT, phrase


def test_nulls_chance_baseline_and_secondary_analysis_are_stated():
    for phrase in ("Interpretation of nulls", "whole CI lies inside the margins", "`null_stored_rate`", "`init` checkpoint",
                   "secondary analysis", "outside the Holm family", "refuses to freeze", "configuration hash"):
        assert phrase in TEXT, phrase

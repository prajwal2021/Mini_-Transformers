# ruff: noqa: E501
"""R08: the freeze verifier accepts exactly the one recorded analysis-code addendum and nothing else."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from slm.integration.freeze import FreezeRefused, analysis_code_hash, freeze, verify_analysis_code

ROOT = Path(__file__).resolve().parents[1]


def make_repo(tmp_path: Path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "src" / "slm" / "analysis").mkdir(parents=True)
    (tmp_path / "scripts").mkdir()
    code = tmp_path / "src" / "slm" / "analysis" / "models.py"
    code.write_text("X = 1\n", encoding="utf-8")
    prereg = tmp_path / "docs" / "PREREG.md"
    prereg.write_text("# prereg\n", encoding="utf-8")
    rec = freeze(prereg, tmp_path / "run", None, tmp_path, require_clean=False)
    return prereg, code, rec


def write_addendum(root: Path, rec: dict, new_hash: str, **over) -> Path:
    add = {"addendum_id": "T-1", "fix_commit": "abc1234", "prereg_sha256": rec["prereg_sha256"],
           "old_analysis_code_sha256": rec["analysis_code_sha256"], "new_analysis_code_sha256": new_hash} | over
    p = root / "docs" / "FREEZE_ADDENDUM.json"
    p.write_text(json.dumps(add), encoding="utf-8")
    return p


def test_unchanged_code_matches_the_freeze(tmp_path):
    prereg, _, _ = make_repo(tmp_path)
    assert verify_analysis_code(prereg, tmp_path)["analysis_code_status"] == "matches freeze"


def test_changed_code_without_an_addendum_is_refused(tmp_path):
    prereg, code, _ = make_repo(tmp_path)
    code.write_text("X = 2\n", encoding="utf-8")
    with pytest.raises(FreezeRefused, match="no freeze addendum"):
        verify_analysis_code(prereg, tmp_path)


def test_the_recorded_addendum_is_accepted_and_named(tmp_path):
    prereg, code, rec = make_repo(tmp_path)
    code.write_text("X = 2\n", encoding="utf-8")
    write_addendum(tmp_path, rec, analysis_code_hash(tmp_path))
    out = verify_analysis_code(prereg, tmp_path)
    assert out["analysis_code_status"].startswith("matches addendum T-1") and out["prereg_sha256"] == rec["prereg_sha256"]


def test_any_further_change_after_the_addendum_is_refused(tmp_path):
    prereg, code, rec = make_repo(tmp_path)
    code.write_text("X = 2\n", encoding="utf-8")
    write_addendum(tmp_path, rec, analysis_code_hash(tmp_path))
    code.write_text("X = 3\n", encoding="utf-8")
    with pytest.raises(FreezeRefused, match="both the frozen hash and the recorded addendum"):
        verify_analysis_code(prereg, tmp_path)


@pytest.mark.parametrize("field", ["prereg_sha256", "old_analysis_code_sha256"])
def test_an_addendum_for_another_prereg_or_start_hash_is_refused(tmp_path, field):
    prereg, code, rec = make_repo(tmp_path)
    code.write_text("X = 2\n", encoding="utf-8")
    write_addendum(tmp_path, rec, analysis_code_hash(tmp_path), **{field: "0" * 64})
    with pytest.raises(FreezeRefused):
        verify_analysis_code(prereg, tmp_path)


def test_an_incomplete_addendum_is_refused(tmp_path):
    prereg, code, rec = make_repo(tmp_path)
    code.write_text("X = 2\n", encoding="utf-8")
    p = write_addendum(tmp_path, rec, analysis_code_hash(tmp_path))
    d = json.loads(p.read_text(encoding="utf-8"))
    del d["fix_commit"]
    p.write_text(json.dumps(d), encoding="utf-8")
    with pytest.raises(FreezeRefused, match="lacks"):
        verify_analysis_code(prereg, tmp_path)


def test_an_edited_prereg_is_still_refused_even_with_a_matching_addendum(tmp_path):
    prereg, code, rec = make_repo(tmp_path)
    code.write_text("X = 2\n", encoding="utf-8")
    write_addendum(tmp_path, rec, analysis_code_hash(tmp_path))
    prereg.write_text(prereg.read_text(encoding="utf-8") + "edited\n", encoding="utf-8")
    with pytest.raises(FreezeRefused, match="edited after the freeze"):
        verify_analysis_code(prereg, tmp_path)


def test_the_real_repository_state_is_accepted_through_the_recorded_addendum():
    out = verify_analysis_code(ROOT / "docs" / "PREREG.md", ROOT)
    assert out["analysis_code_status"].startswith("matches addendum R08-1")
    assert out["analysis_code_sha256"] == "8a6fab562f6ff28d48333d2364de25449dd3a6fe292c888751571f3e69925cd0"

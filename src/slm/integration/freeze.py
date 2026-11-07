# ruff: noqa: E501
"""PREREG freeze (R00 3d): record the file hash and the git commit, refuse after any test read.

The freeze block is appended to the PREREG file between two marker lines. The recorded hash is the
sha256 of the file *without* that block, so it can be recomputed and checked later
(``verify``). The freeze refuses to run when the run directory already shows contact with test
data: a test-split row in a probe table, QA predictions, or a line in the test-access ledger.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
import subprocess
from pathlib import Path

import pandas as pd

BEGIN = "<!-- FREEZE:BEGIN -->"
END = "<!-- FREEZE:END -->"
_BLOCK = re.compile(re.escape(BEGIN) + r".*?" + re.escape(END) + r"\n?", re.S)


class FreezeRefused(RuntimeError):
    pass


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def strip_block(text: str) -> str:
    return _BLOCK.sub("", text.replace("\r\n", "\n")).rstrip("\n") + "\n"


def analysis_code_hash(root: Path) -> str:
    """Hash of src/slm/analysis/** plus the analysis CLIs (what PREREG calls the analysis commit)."""
    files = sorted((root / "src" / "slm" / "analysis").rglob("*.py")) + [
        root / "scripts" / "run_analysis.py", root / "scripts" / "run_sensitivity.py"]
    h = hashlib.sha256()
    for f in files:
        if f.exists():
            h.update(f.relative_to(root).as_posix().encode())
            h.update(f.read_bytes().replace(b"\r\n", b"\n"))
    return h.hexdigest()


def _git(root: Path, *a: str) -> str:
    p = subprocess.run(["git", *a], cwd=root, capture_output=True, text=True)
    return p.stdout.rstrip("\n") if p.returncode == 0 else ""


def dirty_files(root: Path, exclude: Path | None = None) -> list[str]:
    """Tracked files with uncommitted changes, apart from ``exclude`` (the PREREG file itself)."""
    ex = None
    if exclude is not None:
        try:
            ex = Path(exclude).resolve().relative_to(Path(root).resolve()).as_posix()
        except ValueError:
            ex = None  # PREREG outside the repository (a mock copy): nothing to exclude
    out = []
    for line in _git(root, "status", "--porcelain", "--untracked-files=no").splitlines():
        path = line[3:].split(" -> ")[-1].strip().strip('"')
        if path and path != ex:
            out.append(path)
    return out


def git_state(root: Path, exclude: Path | None = None) -> dict:
    return {"commit": _git(root, "rev-parse", "HEAD").strip() or "unknown",
            "branch": _git(root, "rev-parse", "--abbrev-ref", "HEAD").strip(),
            "dirty": bool(dirty_files(root, exclude))}


def find_test_evidence(run_dir: Path, ledger: Path | None) -> list[str]:
    """Reasons the freeze must refuse: every sign that a test probe, QA test or test read happened."""
    found: list[str] = []
    if ledger is not None and Path(ledger).exists():
        n = 0
        for x in Path(ledger).read_text(encoding="utf-8").splitlines():
            if not x.strip():
                continue
            try:
                n += json.loads(x).get("split") == "test"
            except json.JSONDecodeError:  # an unreadable line is treated as a test read
                n += 1
        if n:
            found.append(f"test-access ledger {ledger} has {n} test-split entr{'y' if n == 1 else 'ies'}")
    run_dir = Path(run_dir)
    if run_dir.exists():
        for f in sorted(run_dir.rglob("probe*.csv")) + sorted(run_dir.rglob("probe*.parquet")):
            try:
                col = (pd.read_parquet(f, columns=["split"]) if f.suffix == ".parquet"
                       else pd.read_csv(f, usecols=["split"]))
            except (ValueError, KeyError):
                continue
            n = int((col["split"] == "test").sum())
            if n:
                found.append(f"probe table {f} holds {n} test-split rows")
        for f in sorted(run_dir.rglob("qa_predictions*.csv")) + sorted(run_dir.rglob("qa_test*.csv")):
            found.append(f"QA test predictions exist: {f}")
    return found


def freeze(prereg: Path, run_dir: Path, ledger: Path | None, root: Path, *, now: str | None = None,
           extra: dict | None = None, require_clean: bool = True) -> dict:
    """Freeze ``prereg``. ``require_clean`` (default) refuses when tracked files other than the PREREG file itself
    have uncommitted changes, so that the recorded commit hash is the code that ran. Mock runs pass False."""
    prereg = Path(prereg)
    text = prereg.read_text(encoding="utf-8")
    if BEGIN in text:
        rec = verify(prereg)
        return {**rec, "already_frozen": True}
    evidence = find_test_evidence(run_dir, ledger)
    if evidence:
        raise FreezeRefused("refusing to freeze, test data was already touched: " + "; ".join(evidence))
    dirty = dirty_files(root, prereg)
    if dirty and require_clean:
        raise FreezeRefused("refusing to freeze, the git working tree is dirty (commit first; only docs/PREREG.md may differ): "
                            + ", ".join(dirty[:10]) + (" ..." if len(dirty) > 10 else ""))
    body = strip_block(text)
    rec = {
        "prereg_file": str(prereg), "prereg_sha256": sha256_text(body),
        "git": git_state(root, prereg), "analysis_code_sha256": analysis_code_hash(root),
        "frozen_at": now or dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "ledger": str(ledger) if ledger else None, "run_dir": str(run_dir), "extra": extra or {},
    }
    block = (f"\n{BEGIN}\n## Freeze record\n\n| field | value |\n|---|---|\n"
             f"| PREREG sha256 (this file without this block) | `{rec['prereg_sha256']}` |\n"
             f"| git commit | `{rec['git']['commit']}` (branch `{rec['git']['branch']}`, "
             f"working tree {'DIRTY' if rec['git']['dirty'] else 'clean'}) |\n"
             f"| analysis code sha256 | `{rec['analysis_code_sha256']}` |\n"
             f"| frozen at (UTC) | {rec['frozen_at']} |\n"
             + "".join(f"| {k} | `{v}` |\n" for k, v in rec["extra"].items()) +
             f"| test evidence at freeze | none (no test probe, QA test or ledger entry) |\n"
             f"\n```json\n{json.dumps(rec, indent=1, sort_keys=True)}\n```\n{END}\n")
    prereg.write_text(body + block, encoding="utf-8", newline="\n")
    return rec


def verify(prereg: Path) -> dict:
    """The recorded record, after checking the file hash still matches (raises FreezeRefused)."""
    text = Path(prereg).read_text(encoding="utf-8")
    m = re.search(re.escape(BEGIN) + r".*?```json\n(.*?)\n```.*?" + re.escape(END), text, re.S)
    if not m:
        raise FreezeRefused(f"{prereg} has no freeze record")
    rec = json.loads(m.group(1))
    if sha256_text(strip_block(text)) != rec["prereg_sha256"]:
        raise FreezeRefused(f"{prereg} was edited after the freeze (hash mismatch)")
    return rec


ADDENDUM_FIELDS = ("addendum_id", "fix_commit", "prereg_sha256", "old_analysis_code_sha256", "new_analysis_code_sha256")


def verify_analysis_code(prereg: Path, root: Path, addendum: Path | None = None) -> dict:
    """The freeze record, after also checking the analysis code against it (R08).

    The frozen ``analysis_code_sha256`` must equal the current hash of the analysis code, OR the current hash must be the
    ``new_analysis_code_sha256`` of the ONE recorded addendum (``docs/FREEZE_ADDENDUM.json``) whose ``prereg_sha256`` and
    ``old_analysis_code_sha256`` equal the freeze record's. Anything else is refused. The freeze itself is never rewritten.
    Returns the freeze record plus ``analysis_code_status`` (``matches freeze`` or ``matches addendum <id>``).
    """
    rec = verify(prereg)
    current = analysis_code_hash(Path(root))
    if current == rec["analysis_code_sha256"]:
        return {**rec, "analysis_code_status": "matches freeze"}
    path = Path(addendum) if addendum is not None else Path(root) / "docs" / "FREEZE_ADDENDUM.json"
    if not path.exists():
        raise FreezeRefused("analysis code differs from the frozen hash and no freeze addendum is recorded")
    add = json.loads(path.read_text(encoding="utf-8"))
    missing = [k for k in ADDENDUM_FIELDS if k not in add]
    if missing:
        raise FreezeRefused(f"freeze addendum {path} lacks {missing}")
    if add["prereg_sha256"] != rec["prereg_sha256"]:
        raise FreezeRefused("freeze addendum belongs to a different PREREG hash")
    if add["old_analysis_code_sha256"] != rec["analysis_code_sha256"]:
        raise FreezeRefused("freeze addendum does not start from the frozen analysis-code hash")
    if current != add["new_analysis_code_sha256"]:
        raise FreezeRefused("analysis code differs from both the frozen hash and the recorded addendum's new hash")
    return {**rec, "analysis_code_status": f"matches addendum {add['addendum_id']} (fix commit {add['fix_commit']})"}

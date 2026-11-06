# ruff: noqa: E501
"""R04 PATH TEST (not results): the real-mode report path on a synthetic frozen run directory.

    python scripts/real_report_path_test.py [--mock-run runs/real_mock] [--keep DIR]

Copies the results and report inputs of a finished MOCK run into a scratch git repository (clean tree),
freezes a copy of docs/PREREG.md there, and builds the report three times with ``--real``:
(1) no freeze: refused; (2) valid freeze: built with the banner off; (3) PREREG edited after the freeze:
refused. Everything stays in the scratch directory and every output is stamped PATH TEST, NOT RESULTS.
The content is the mock run's, so the numbers are meaningless; only the gate is tested.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STAMP = "PATH TEST, NOT RESULTS: mock content built through the real-mode gate"


def git(cwd: Path, *a: str) -> str:
    return subprocess.run(["git", *a], cwd=cwd, capture_output=True, text=True, check=True).stdout.strip()


def build(prereg: Path, results: Path, inputs: Path, out: Path) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(ROOT / "scripts" / "build_report.py"), "--real", "--prereg", str(prereg),
                           "--results-dir", str(results), "--inputs-dir", str(inputs), "--out", str(out)],
                          capture_output=True, text=True, cwd=ROOT)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--mock-run", default=str(ROOT / "runs" / "real_mock"))
    ap.add_argument("--keep", default=None, help="keep the scratch directory here")
    args = ap.parse_args(argv)
    from slm.integration.freeze import freeze, verify

    mock = Path(args.mock_run)
    tmp = Path(args.keep) if args.keep else Path(tempfile.mkdtemp(prefix="r04_path_"))
    tmp.mkdir(parents=True, exist_ok=True)
    repo = tmp / "repo"
    (repo / "docs").mkdir(parents=True, exist_ok=True)
    shutil.copy(ROOT / "docs" / "PREREG.md", repo / "docs" / "PREREG.md")
    (repo / "README.txt").write_text(STAMP + "\n", encoding="utf-8")
    run = tmp / "run"
    for d in ("results", "report_inputs"):
        shutil.copytree(mock / d, run / d, dirs_exist_ok=True)
    git(repo, "init", "-q")
    git(repo, "config", "user.email", "path-test@example.invalid")
    git(repo, "config", "user.name", "path test")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "scratch: clean tree for the path test")
    prereg = repo / "docs" / "PREREG.md"
    log: dict = {"label": STAMP, "scratch": str(tmp)}

    r1 = build(prereg, run / "results", run / "report_inputs", tmp / "out_unfrozen")
    log["1_no_freeze"] = {"exit": r1.returncode, "stderr": r1.stderr.strip()[-200:]}
    assert r1.returncode == 3 and not (tmp / "out_unfrozen").exists(), "an unfrozen PREREG must refuse --real"

    rec = freeze(prereg, tmp / "no_test_data_here", None, repo)  # clean tree: the real refusal rule applies
    assert rec["git"]["dirty"] is False and rec["git"]["commit"] == git(repo, "rev-parse", "HEAD")
    verify(prereg)
    log["freeze"] = {"commit": rec["git"]["commit"], "dirty": rec["git"]["dirty"], "prereg_sha256": rec["prereg_sha256"]}
    r2 = build(prereg, run / "results", run / "report_inputs", tmp / "out_frozen")
    log["2_valid_freeze"] = {"exit": r2.returncode, "stdout": r2.stdout.strip()[-300:], "stderr": r2.stderr.strip()[-300:]}
    assert r2.returncode == 0 and "banner: False" in r2.stdout, r2.stderr  # banner off only after verify passed
    (tmp / "out_frozen" / "PATH_TEST_NOT_RESULTS.txt").write_text(STAMP + "\n", encoding="utf-8")

    prereg.write_text(prereg.read_text(encoding="utf-8") + "\nedited after the freeze\n", encoding="utf-8", newline="\n")
    r3 = build(prereg, run / "results", run / "report_inputs", tmp / "out_tampered")
    log["3_tampered"] = {"exit": r3.returncode, "stderr": r3.stderr.strip()[-250:]}
    assert r3.returncode == 3 and "edited after the freeze" in r3.stderr and not (tmp / "out_tampered").exists()

    (tmp / "path_test_log.json").write_text(json.dumps(log, indent=1), encoding="utf-8")
    print(json.dumps(log, indent=1))
    print(STAMP)
    if not args.keep:
        shutil.rmtree(tmp, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

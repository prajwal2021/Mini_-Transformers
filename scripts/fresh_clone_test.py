# ruff: noqa: E501
"""Fresh-clone test: can a clean machine run the demo from the repo + the bundle alone?

    python scripts/fresh_clone_test.py --bundle bundle [--source auto|head|worktree] [--no-install]

1. Copy a clean checkout of the repository source into a temp directory (``head``: git clone of
   the committed state; ``worktree``: tracked + new unignored files, without runs/, data/, reports/,
   bundle/, release/; ``auto``: head when the working tree is clean, else worktree).
2. Copy the bundle next to it.
3. Create a new venv and ``pip install -r bundle/requirements.txt`` (pinned, CPU torch). If the
   install fails or --no-install is given, say so and run with the CURRENT interpreter instead
   (isolated mode ``-I``, so nothing but the copied repo's source is importable).
4. Run scripts/generate.py on bundle/pretrained and bundle/sft with CUDA hidden, a prompt that is
   not in the mock corpus, temperature 0, twice each: the completion must be non-empty and identical.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKIP_PREFIXES = ("runs/", "data/", "reports/", "bundle/", "release/", ".git/", "tests/fixtures/")
PROMPTS = {
    "pretrained": "Meanwhile at the mountain station, the night porter",
    "sft": "Who looks after the cargo pets on the Zephyrine?",
}


def run(cmd, cwd=None, env=None, timeout=900):
    t = time.perf_counter()
    p = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True, timeout=timeout)
    return p, time.perf_counter() - t


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True).stdout


def copy_source(dest: Path, source: str) -> str:
    dirty = bool(git("status", "--short", "--untracked-files=no").strip())
    if source == "auto":
        source = "worktree" if dirty else "head"
    if source == "head":
        p, _ = run(["git", "clone", "--quiet", "--no-hardlinks", str(ROOT), str(dest)])
        if p.returncode:
            raise SystemExit(f"git clone failed: {p.stderr}")
        return "head (git clone of the committed state)"
    files = git("ls-files", "-z", "--cached", "--others", "--exclude-standard").split("\0")
    for rel in filter(None, files):
        rel = rel.replace("\\", "/")
        src = ROOT / rel
        if rel.startswith(SKIP_PREFIXES) or not src.is_file():
            continue
        (dest / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest / rel)
    return "worktree (tracked and new unignored source files)"


def mock_corpus_text() -> str:
    parts = []
    for n in ("mock_corpus_train.txt", "mock_corpus_val.txt"):
        f = ROOT / "tests" / "fixtures" / n
        if f.is_file():
            parts.append(f.read_text(encoding="utf-8"))
    return "\n".join(parts)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--bundle", required=True, help="directory with pretrained/ and sft/")
    ap.add_argument("--source", choices=["auto", "head", "worktree"], default="auto")
    ap.add_argument("--no-install", action="store_true", help="skip the venv; use this interpreter")
    ap.add_argument("--install-timeout", type=int, default=900)
    ap.add_argument("--keep", action="store_true", help="keep the temp directory")
    a = ap.parse_args(argv)
    bundle = Path(a.bundle).resolve()
    t_all = time.perf_counter()
    tmp = Path(tempfile.mkdtemp(prefix="slm_fresh_clone_"))
    report: dict = {"temp_dir": str(tmp), "steps": {}}
    try:
        repo = tmp / "repo"
        repo.mkdir()
        t = time.perf_counter()
        report["source"] = copy_source(repo, a.source)  # git clone accepts an empty directory
        report["steps"]["copy_repo_s"] = round(time.perf_counter() - t, 2)
        shutil.copytree(bundle, repo / "bundle")
        python = [sys.executable, "-I"]
        report["python"] = "current interpreter (isolated)"
        if not a.no_install:
            t = time.perf_counter()
            venv = tmp / "venv"
            p, _ = run([sys.executable, "-m", "venv", str(venv)])
            vpy = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
            if p.returncode == 0:
                try:
                    p, _ = run([str(vpy), "-m", "pip", "install", "--quiet",
                                "--disable-pip-version-check", "-r",
                                str(repo / "bundle" / "requirements.txt")],
                               timeout=a.install_timeout)
                except subprocess.TimeoutExpired:
                    p = subprocess.CompletedProcess([], 1, "", "pip install timed out")
            report["steps"]["venv_and_install_s"] = round(time.perf_counter() - t, 2)
            if p.returncode == 0:
                python = [str(vpy), "-I"]
                report["python"] = f"fresh venv with pinned requirements ({vpy})"
            else:
                report["install_failed"] = (p.stderr or p.stdout)[-600:]
                report["python"] = "current interpreter (isolated); the pip install failed"
        env = {**os.environ, "CUDA_VISIBLE_DEVICES": ""}
        env.pop("PYTHONPATH", None)
        corpus = mock_corpus_text()
        ok = True
        report["runs"] = {}
        for kind, prompt in PROMPTS.items():
            outs, secs = [], []
            for _ in range(2):
                p, dt_ = run([*python, "scripts/generate.py", "--bundle", f"bundle/{kind}",
                              "--prompt", prompt, "--temperature", "0", "--seed", "3",
                              "--device", "cpu"], cwd=repo, env=env)
                comp = [ln for ln in p.stdout.splitlines() if ln.startswith("completion:")]
                outs.append((p.returncode, p.stdout.splitlines()[:1], comp))
                secs.append(round(dt_, 2))
            loaded = outs[0][1][0] if outs[0][1] else ""
            good = (all(o[0] == 0 for o in outs) and outs[0][2] and outs[0][2] == outs[1][2]
                    and outs[0][2][0].removeprefix("completion:").strip() != ""
                    and loaded.startswith(f"loaded: {kind}") and prompt not in corpus)
            ok &= bool(good)
            report["runs"][kind] = {"prompt": prompt, "prompt_in_mock_corpus": prompt in corpus,
                                    "loaded": loaded, "completion": outs[0][2],
                                    "deterministic": outs[0][2] == outs[1][2],
                                    "seconds_per_call": secs, "ok": bool(good)}
        report["ok"] = ok
        report["total_seconds"] = round(time.perf_counter() - t_all, 2)
        print(json.dumps(report, indent=2))
        return 0 if ok else 1
    finally:
        if not a.keep:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())

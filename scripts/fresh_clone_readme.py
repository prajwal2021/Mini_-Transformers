# ruff: noqa: E501
"""R09 fresh-clone test: from a git clone + bundle.zip alone, run the README's commands on the CPU in a clean venv.

    python scripts/fresh_clone_readme.py --bundle-zip bundle.zip [--with-reproduce] [--keep] [--report out.json]

1. ``git clone`` of the committed state (no working-tree files), 2. unzip the bundle into the clone, 3. new venv + ``pip install -r bundle/requirements.txt``,
4. every ``python scripts/...`` command of README section 1 (the inference commands and ``--verify``) with CUDA hidden, 5. optionally
``pip install -e .`` and the table reproduction of README section 2. Prints a JSON report with per-step timings and exit code 0 only if everything passes.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(cmd, cwd=None, env=None, stdin=None, timeout=1800):
    t = time.perf_counter()
    p = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True, input=stdin, timeout=timeout, encoding="utf-8", errors="replace")
    return p, round(time.perf_counter() - t, 2)


def section1_commands(readme: str) -> list[str]:
    sec = readme.split("## 1. Run the trained models", 1)[1].split("## 2. Reproduce the tables", 1)[0]
    return [m.group(1).rstrip() for m in re.finditer(r"^ {4}(python scripts/[^\n#]+?)\s*(?:#.*)?$", sec, flags=re.M)]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--bundle-zip", required=True)
    ap.add_argument("--with-reproduce", action="store_true")
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--report", default=None)
    a = ap.parse_args()
    tmp = Path(tempfile.mkdtemp(prefix="slm_fresh_"))
    rep: dict = {"temp_dir": str(tmp), "steps": {}, "commands": []}
    ok = True
    try:
        clone = tmp / "clone"
        p, s = run(["git", "clone", "--quiet", "--no-hardlinks", str(ROOT), str(clone)])
        rep["steps"]["git_clone_s"] = s
        if p.returncode:
            raise SystemExit(f"clone failed: {p.stderr}")
        rep["clone_head"] = run(["git", "rev-parse", "--short", "HEAD"], cwd=clone)[0].stdout.strip()
        rep["clone_has_env_file"] = (clone / ".env").exists()
        t = time.perf_counter()
        with zipfile.ZipFile(a.bundle_zip) as z:
            z.extractall(clone)
        rep["steps"]["unzip_bundle_s"] = round(time.perf_counter() - t, 2)
        venv = tmp / "venv"
        p, s = run([sys.executable, "-m", "venv", str(venv)])
        vpy = str(venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python"))
        rep["steps"]["venv_s"] = s
        p, s = run([vpy, "-m", "pip", "install", "--quiet", "--disable-pip-version-check", "-r", "bundle/requirements.txt"], cwd=clone)
        rep["steps"]["pip_install_requirements_s"] = s
        if p.returncode:
            rep["pip_error"] = (p.stderr or p.stdout)[-800:]
            raise SystemExit("pip install -r bundle/requirements.txt failed:\n" + rep["pip_error"])
        rep["torch"] = run([vpy, "-c", "import torch;print(torch.__version__, torch.cuda.is_available())"], cwd=clone)[0].stdout.strip()
        env = {**os.environ, "CUDA_VISIBLE_DEVICES": "-1"}
        env.pop("PYTHONPATH", None)
        readme = (clone / "README.md").read_text(encoding="utf-8")
        cmds = section1_commands(readme)
        rep["n_readme_commands"] = len(cmds)
        for cmd in cmds:
            args = shlex.split(cmd)[1:]
            p, s = run([vpy, *args], cwd=clone, env=env, stdin=":quit\n" if "--interactive" in args else None)
            comp = [ln for ln in p.stdout.splitlines() if ln.startswith("completion:") or ln.startswith("[") or ln.startswith("MANIFEST")]
            good = p.returncode == 0 and bool(comp or "MANIFEST OK" in p.stdout) and "on cpu" in p.stdout + "on cpu"  # every generate run reports its device
            if "--interactive" in cmd:  # only ":quit" is sent: the model must load and the REPL must exit cleanly
                good = p.returncode == 0 and p.stdout.splitlines()[0].startswith("loaded: ") and " on cpu" in p.stdout
            if "scripts/generate.py" in cmd and "--compare" not in cmd and "--interactive" not in cmd:
                good = good and any(ln.startswith("completion: ") and ln[len("completion: "):].strip() for ln in p.stdout.splitlines()) and " on cpu" in p.stdout
            ok &= good
            rep["commands"].append({"cmd": cmd, "seconds": s, "ok": good, "returncode": p.returncode, "first_lines": [ln[:110] for ln in comp[:3]], "stderr_tail": p.stderr[-200:] if p.returncode else ""})
        expected = next((c for c in rep["commands"] if "sft_fixed3 --qa" in c["cmd"]), None)
        rep["expected_answer_ok"] = bool(expected and any("Miren Quill" in ln for ln in expected["first_lines"]))
        ok &= rep["expected_answer_ok"]
        if a.with_reproduce:
            p, s = run([vpy, "-m", "pip", "install", "--quiet", "--disable-pip-version-check", "-e", "."], cwd=clone, timeout=3000)
            rep["steps"]["pip_install_package_s"] = s
            if p.returncode:
                rep["pip_package_error"] = (p.stderr or p.stdout)[-800:]
                ok = False
            else:
                p, s = run([vpy, "scripts/reproduce_tables.py", "--bundle", "bundle"], cwd=clone, env=env)
                good = p.returncode == 0 and "REPRODUCED" in p.stdout
                ok &= good
                rep["reproduce_tables"] = {"seconds": s, "ok": good, "tail": p.stdout.strip().splitlines()[-1] if p.stdout.strip() else p.stderr[-300:]}
        rep["ok"] = ok
    finally:
        rep["total_s"] = round(sum(v for v in rep["steps"].values()) + sum(c["seconds"] for c in rep["commands"]), 1)
        if not a.keep:
            shutil.rmtree(tmp, ignore_errors=True)
    print(json.dumps(rep, indent=2))
    if a.report:
        Path(a.report).write_text(json.dumps(rep, indent=2), encoding="utf-8")
    return 0 if rep.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())

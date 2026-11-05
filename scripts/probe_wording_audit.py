"""Write the probe wording audit table to reports/tables/probe_wording.md."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from slm.eval.wording import audit_markdown  # noqa: E402

if __name__ == "__main__":
    out = ROOT / "reports/tables/probe_wording.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(audit_markdown(), encoding="utf-8")
    print(out)

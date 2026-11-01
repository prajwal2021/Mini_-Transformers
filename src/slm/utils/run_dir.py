"""Run-directory creation."""

from datetime import datetime
from pathlib import Path


def new_run_dir(kind: str, name: str, root: str | Path = "runs") -> Path:
    """Create and return a timestamped run directory with standard subdirectories."""
    run_dir = Path(root) / f"{datetime.now().strftime('%Y%m%d-%H%M%S')}_{kind}_{name}"
    run_dir.mkdir(parents=True, exist_ok=False)
    (run_dir / "checkpoints").mkdir()
    (run_dir / "samples").mkdir()
    return run_dir

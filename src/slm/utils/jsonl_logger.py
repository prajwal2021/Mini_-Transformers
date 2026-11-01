"""Line-oriented JSON logging."""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class JsonlLogger:
    """Append timestamped metric records to a JSONL file."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._handle = self.path.open("a", encoding="utf-8")

    def log(self, step: int, **metrics: Any) -> None:
        """Append one record and flush immediately."""
        record = {"timestamp": datetime.now(timezone.utc).isoformat(), "step": step, **metrics}
        self._handle.write(json.dumps(record, sort_keys=True) + "\n")
        self._handle.flush()

    def close(self) -> None:
        """Close the underlying file."""
        self._handle.close()

    def __enter__(self) -> "JsonlLogger":
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()

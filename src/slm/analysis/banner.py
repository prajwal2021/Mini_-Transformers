"""The visible data-status banner shared by the analysis figures and the report.

Two labels exist: ``SIMULATED`` (the simulator of the analysis stream) and ``MOCK`` (the
end-to-end mock pipeline run by ``scripts/run_all_mock.py``, whose models are trained on toy data).
Neither is ever a result; a real build turns the banner off with ``--real``.
"""

from __future__ import annotations

LABELS = ("SIMULATED", "MOCK")
_label = "SIMULATED"


def set_label(label: str) -> None:
    global _label
    if label not in LABELS:
        raise ValueError(f"banner label must be one of {LABELS}, got {label!r}")
    _label = label


def label() -> str:
    return _label


def text() -> str:
    return f"{_label} DATA - NOT RESULTS"


def notice() -> str:
    """The sentence under the banner in the report text."""
    if _label == "MOCK":
        return ("Every number, table and figure in this document came from the end-to-end mock "
                "run (toy corpus, tiny training budget) that tests the pipeline. None of it is a "
                "result of the study.")
    return ("Every number, table and figure in this document was generated from simulated inputs "
            "to test the report pipeline. None of it is a result of the study.")

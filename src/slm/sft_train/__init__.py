"""Supervised fine-tuning on question-answer pairs (loss on the answer only)."""

from .config import SFTConfig
from .data import SFTDataset, SFTExample, build_prompt, collate, encode_rows
from .runner import load_rows, prepare_sft_data, run_sft_seeds
from .trainer import evaluate_sft, final_pretrain_checkpoint, sft_run

__all__ = [
    "SFTConfig",
    "SFTDataset",
    "SFTExample",
    "build_prompt",
    "collate",
    "encode_rows",
    "evaluate_sft",
    "final_pretrain_checkpoint",
    "load_rows",
    "prepare_sft_data",
    "run_sft_seeds",
    "sft_run",
]

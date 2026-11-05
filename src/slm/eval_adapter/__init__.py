"""Adapters the evaluation code can use without importing training internals."""

from .model_scorer import ModelScorer

__all__ = ["ModelScorer"]

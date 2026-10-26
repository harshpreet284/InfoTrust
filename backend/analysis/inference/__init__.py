"""
Inference package for fine-tuned misinformation classification models and adapters.
Exposes ModelOutput, ModelAdapterProtocol, MockModelAdapter, and DebertaModelAdapter.
"""

from analysis.inference.adapter import ModelAdapterProtocol, ModelOutput
from analysis.inference.deberta import DebertaModelAdapter, ModelInferenceError
from analysis.inference.mock import MockModelAdapter

__all__ = [
    "ModelAdapterProtocol",
    "ModelOutput",
    "MockModelAdapter",
    "DebertaModelAdapter",
    "ModelInferenceError",
]

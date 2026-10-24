"""
Inference package for fine-tuned misinformation classification models and adapters.
Exposes ModelOutput, ModelAdapterProtocol, and MockModelAdapter.
"""

from analysis.inference.adapter import ModelAdapterProtocol, ModelOutput
from analysis.inference.mock import MockModelAdapter

__all__ = [
    "ModelAdapterProtocol",
    "ModelOutput",
    "MockModelAdapter",
]

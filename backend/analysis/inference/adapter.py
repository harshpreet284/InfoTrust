import math
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from analysis.models import ModelPrediction


@dataclass(frozen=True)
class ModelOutput:
    """
    Standardized, model-agnostic prediction output.
    Strictly encapsulates the binary prediction and confidence score.
    """

    prediction: ModelPrediction
    confidence: float

    def __post_init__(self):
        if not isinstance(self.prediction, ModelPrediction):
            raise TypeError(
                f"prediction must be an instance of ModelPrediction, got {type(self.prediction)}"
            )
        if not isinstance(self.confidence, (int, float)) or isinstance(self.confidence, bool):
            raise TypeError(
                f"confidence must be a float or int, got {type(self.confidence)}"
            )
        if not math.isfinite(self.confidence):
            raise ValueError(
                f"confidence must be a finite number, got {self.confidence}"
            )
        if not (0.0 <= float(self.confidence) <= 1.0):
            raise ValueError(
                f"confidence must be between 0.0 and 1.0, got {self.confidence}"
            )


@runtime_checkable
class ModelAdapterProtocol(Protocol):
    """
    Structural interface for fine-tuned misinformation classification models.
    Enforces the Model Adapter / Loader boundary specified in ARCHITECTURE.md Section 42.
    """

    def predict(self, cleaned_text: str) -> ModelOutput:
        """
        Executes model inference on normalized claim text.

        Args:
            cleaned_text: Sanitized, normalized claim text.

        Returns:
            ModelOutput containing standardized ModelPrediction and confidence.
        """
        ...

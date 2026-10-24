from analysis.inference.adapter import ModelAdapterProtocol, ModelOutput
from analysis.models import ModelPrediction


class MockModelAdapter:
    """
    Deterministic, dependency-free mock adapter for testing and environments
    where physical model weights or PyTorch/transformers are not mounted.
    Conforms to ModelAdapterProtocol.
    """

    def __init__(
        self,
        default_prediction: ModelPrediction = ModelPrediction.CREDIBLE,
        default_confidence: float = 0.85,
    ):
        self.default_prediction = default_prediction
        self.default_confidence = default_confidence

    def predict(self, cleaned_text: str) -> ModelOutput:
        if not cleaned_text or not cleaned_text.strip():
            raise ValueError("cleaned_text cannot be empty.")

        return ModelOutput(
            prediction=self.default_prediction,
            confidence=self.default_confidence,
        )

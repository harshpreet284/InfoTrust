from pathlib import Path
from typing import Optional

from analysis.inference.adapter import ModelOutput
from analysis.model_loader.loader import ModelLoader
from analysis.models import ModelPrediction


class ModelInferenceError(RuntimeError):
    """Raised strictly during inference forward pass (tensor, device, or runtime memory errors)."""

    pass


class DebertaModelAdapter:
    """
    Concrete model adapter for the fine-tuned DeBERTa-v3 misinformation classifier.
    Conforms to ModelAdapterProtocol.
    """

    def __init__(
        self,
        loader: Optional[ModelLoader] = None,
        model_version: Optional[str] = None,
    ):
        self.loader = loader or ModelLoader(model_version=model_version)

    @property
    def model_version(self) -> str:
        return self.loader.model_version

    @property
    def artifact_path(self) -> Optional[Path]:
        return self.loader.artifact_path

    def predict(self, cleaned_text: str) -> ModelOutput:
        """
        Executes model inference on preprocessed, normalized claim text.

        Args:
            cleaned_text: Sanitized, normalized claim text.

        Returns:
            ModelOutput containing standardized ModelPrediction and confidence.

        Raises:
            TypeError: If cleaned_text is not a string.
            ValueError: If cleaned_text is empty or whitespace-only.
            ModelInferenceError: If an error occurs during tokenization or forward pass.
        """
        if not isinstance(cleaned_text, str):
            raise TypeError(
                f"cleaned_text must be a string, got {type(cleaned_text).__name__}"
            )
        if not cleaned_text or not cleaned_text.strip():
            raise ValueError("cleaned_text cannot be empty or whitespace only.")

        import torch

        model, tokenizer = self.loader.get_model_and_tokenizer()
        device = self.loader.device

        try:
            encoded = tokenizer(
                cleaned_text,
                max_length=128,
                truncation=True,
                padding=True,
                return_tensors="pt",
            )
        except (RuntimeError, ValueError) as err:
            raise ModelInferenceError(
                f"Tokenization failed during inference: {err}"
            ) from err

        inputs = {key: tensor.to(device) for key, tensor in encoded.items()}

        try:
            with torch.no_grad():
                outputs = model(**inputs)
                logits = outputs.logits
                probabilities = torch.softmax(logits, dim=-1)[0]
                predicted_id = int(torch.argmax(probabilities, dim=-1).item())
                confidence = float(probabilities[predicted_id].item())
        except (RuntimeError, IndexError, ValueError) as err:
            raise ModelInferenceError(
                f"Model forward pass failed during inference: {err}"
            ) from err

        label_map = {
            0: ModelPrediction.CREDIBLE,
            1: ModelPrediction.MISINFORMATION,
        }
        prediction = label_map.get(predicted_id)
        if prediction is None:
            raise ModelInferenceError(
                f"Predicted class ID {predicted_id} not found in label mapping."
            )

        return ModelOutput(prediction=prediction, confidence=confidence)

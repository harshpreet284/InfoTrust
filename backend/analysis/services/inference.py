from typing import Optional

from analysis.inference.adapter import ModelAdapterProtocol, ModelOutput


class InferenceServiceError(RuntimeError):
    """Base exception for operational errors within ModelInferenceService."""

    pass


class InvalidModelInputError(InferenceServiceError, ValueError):
    """Raised when input provided to ModelInferenceService fails contract validation."""

    pass


class InvalidModelOutputError(InferenceServiceError, ValueError):
    """Raised when the model adapter produces malformed or contract-violating output."""

    pass


class ModelInferenceService:
    """
    Domain-level service coordinating claim classification inference through
    configured model adapters conforming to ModelAdapterProtocol.
    """

    def __init__(self, adapter: Optional[ModelAdapterProtocol] = None):
        """
        Initializes the service with optional adapter injection.

        Args:
            adapter: Instance conforming to ModelAdapterProtocol. If None,
                     lazily resolves to DebertaModelAdapter on first adapter access.
        """
        self._adapter = adapter

    @property
    def adapter(self) -> ModelAdapterProtocol:
        """
        Resolves the active adapter. Lazily instantiates DebertaModelAdapter
        if no adapter was injected.
        """
        if self._adapter is None:
            from analysis.inference.deberta import DebertaModelAdapter

            self._adapter = DebertaModelAdapter()
        return self._adapter

    @property
    def model_version(self) -> Optional[str]:
        """
        Returns the model version string reported by the configured adapter,
        or None if the adapter does not expose a version.
        Note: Accessing this property initializes the default adapter if not already present.
        """
        return getattr(self.adapter, "model_version", None)

    def predict(self, cleaned_text: str) -> ModelOutput:
        """
        Executes model inference on pre-cleaned, pre-validated claim text.

        Args:
            cleaned_text: Sanitized claim text (non-empty string).

        Returns:
            ModelOutput containing validated ModelPrediction and full-precision float confidence.

        Raises:
            TypeError: If cleaned_text is not a string.
            InvalidModelInputError: If cleaned_text is empty or whitespace-only.
            InvalidModelOutputError: If adapter returns a non-ModelOutput object.
            InferenceServiceError: If adapter forward pass or model loading fails.
        """
        if not isinstance(cleaned_text, str):
            raise TypeError(
                f"cleaned_text must be a string, got {type(cleaned_text).__name__}"
            )

        if not cleaned_text or not cleaned_text.strip():
            raise InvalidModelInputError(
                "cleaned_text cannot be empty or whitespace-only."
            )

        from analysis.inference.deberta import ModelInferenceError
        from analysis.model_loader.loader import ModelLoadingError

        try:
            raw_output = self.adapter.predict(cleaned_text)
        except (ModelInferenceError, ModelLoadingError) as err:
            raise InferenceServiceError(f"Model inference failed: {err}") from err

        if not isinstance(raw_output, ModelOutput):
            raise InvalidModelOutputError(
                f"Model adapter returned unexpected output type: expected ModelOutput, got {type(raw_output).__name__}"
            )

        if not isinstance(raw_output.confidence, float):
            return ModelOutput(
                prediction=raw_output.prediction,
                confidence=float(raw_output.confidence),
            )

        return raw_output

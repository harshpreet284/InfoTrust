from unittest import TestCase
from unittest.mock import MagicMock, patch

from django.conf import settings

from analysis.inference import MockModelAdapter, ModelAdapterProtocol, ModelOutput
from analysis.inference.deberta import ModelInferenceError
from analysis.model_loader import ModelLoader, ModelLoadingError
from analysis.models import ModelPrediction
from analysis.services import (
    InferenceServiceError,
    InvalidModelInputError,
    InvalidModelOutputError,
    ModelInferenceService,
)


class ModelInferenceServiceTests(TestCase):
    """
    Comprehensive unit tests for ModelInferenceService covering input validation,
    adapter delegation, output type verification, full-precision confidence preservation,
    operational exception translation, and lazy adapter initialization.
    """

    def setUp(self):
        self.mock_adapter = MagicMock(spec=ModelAdapterProtocol)
        self.service = ModelInferenceService(adapter=self.mock_adapter)

    # -------------------------------------------------------------------------
    # 1. Successful Predictions & Full Precision Preservation
    # -------------------------------------------------------------------------

    def test_predict_valid_credible_claim(self):
        self.mock_adapter.predict.return_value = ModelOutput(
            prediction=ModelPrediction.CREDIBLE,
            confidence=0.92,
        )
        result = self.service.predict("Cleaned valid claim text.")
        self.assertIsInstance(result, ModelOutput)
        self.assertEqual(result.prediction, ModelPrediction.CREDIBLE)
        self.assertEqual(result.confidence, 0.92)
        self.mock_adapter.predict.assert_called_once_with("Cleaned valid claim text.")

    def test_predict_valid_misinformation_claim(self):
        self.mock_adapter.predict.return_value = ModelOutput(
            prediction=ModelPrediction.MISINFORMATION,
            confidence=0.88,
        )
        result = self.service.predict("Another valid claim text.")
        self.assertIsInstance(result, ModelOutput)
        self.assertEqual(result.prediction, ModelPrediction.MISINFORMATION)
        self.assertEqual(result.confidence, 0.88)

    def test_predict_preserves_full_confidence_precision(self):
        """Verifies full numerical precision is preserved without arbitrary rounding."""
        high_precision_conf = 0.912345678912345
        self.mock_adapter.predict.return_value = ModelOutput(
            prediction=ModelPrediction.CREDIBLE,
            confidence=high_precision_conf,
        )
        result = self.service.predict("Precision test claim.")
        self.assertEqual(result.confidence, high_precision_conf)

    def test_predict_boundary_confidences(self):
        """Verifies boundary values 0.0, 0.5, and 1.0 pass through unmodified."""
        for boundary in (0.0, 0.5, 1.0):
            self.mock_adapter.predict.return_value = ModelOutput(
                prediction=ModelPrediction.CREDIBLE,
                confidence=boundary,
            )
            result = self.service.predict("Boundary test claim.")
            self.assertEqual(result.confidence, boundary)

    def test_predict_integer_confidence_normalized_to_float(self):
        """Verifies that integer confidence values (e.g. 1 or 0) are converted to float."""
        self.mock_adapter.predict.return_value = ModelOutput(
            prediction=ModelPrediction.CREDIBLE,
            confidence=1,
        )
        result = self.service.predict("Integer confidence claim.")
        self.assertIsInstance(result.confidence, float)
        self.assertEqual(result.confidence, 1.0)

    # -------------------------------------------------------------------------
    # 2. Input Validation Failures
    # -------------------------------------------------------------------------

    def test_reject_non_string_input(self):
        for bad_input in (123, None, ["claim"], {"text": "claim"}, 45.6):
            with self.subTest(bad_input=bad_input):
                with self.assertRaises(TypeError) as ctx:
                    self.service.predict(bad_input)  # type: ignore
                self.assertIn("cleaned_text must be a string", str(ctx.exception))

    def test_reject_empty_string(self):
        with self.assertRaises(InvalidModelInputError) as ctx:
            self.service.predict("")
        self.assertIn("cannot be empty or whitespace-only", str(ctx.exception))

    def test_reject_whitespace_only_string(self):
        for ws in ("   ", "\t", "\n", " \t \n \r "):
            with self.subTest(ws=ws):
                with self.assertRaises(InvalidModelInputError) as ctx:
                    self.service.predict(ws)
                self.assertIn("cannot be empty or whitespace-only", str(ctx.exception))

    # -------------------------------------------------------------------------
    # 3. Output Contract & Adapter Conformance Failures
    # -------------------------------------------------------------------------

    def test_reject_adapter_returning_none(self):
        self.mock_adapter.predict.return_value = None
        with self.assertRaises(InvalidModelOutputError) as ctx:
            self.service.predict("Cleaned claim.")
        self.assertIn("expected ModelOutput, got NoneType", str(ctx.exception))

    def test_reject_adapter_returning_dict(self):
        self.mock_adapter.predict.return_value = {
            "prediction": "CREDIBLE",
            "confidence": 0.95,
        }
        with self.assertRaises(InvalidModelOutputError) as ctx:
            self.service.predict("Cleaned claim.")
        self.assertIn("expected ModelOutput, got dict", str(ctx.exception))

    def test_reject_adapter_returning_raw_tuple(self):
        self.mock_adapter.predict.return_value = (ModelPrediction.CREDIBLE, 0.95)
        with self.assertRaises(InvalidModelOutputError) as ctx:
            self.service.predict("Cleaned claim.")
        self.assertIn("expected ModelOutput, got tuple", str(ctx.exception))

    def test_reject_adapter_returning_string(self):
        self.mock_adapter.predict.return_value = "CREDIBLE"
        with self.assertRaises(InvalidModelOutputError) as ctx:
            self.service.predict("Cleaned claim.")
        self.assertIn("expected ModelOutput, got str", str(ctx.exception))

    def test_reject_adapter_returning_arbitrary_object(self):
        self.mock_adapter.predict.return_value = object()
        with self.assertRaises(InvalidModelOutputError) as ctx:
            self.service.predict("Cleaned claim.")
        self.assertIn("expected ModelOutput, got object", str(ctx.exception))

    # -------------------------------------------------------------------------
    # 4. Operational Exception Translation vs. Programming Bug Propagation
    # -------------------------------------------------------------------------

    def test_adapter_model_inference_error_wrapped(self):
        self.mock_adapter.predict.side_effect = ModelInferenceError(
            "Forward pass tensor error"
        )
        with self.assertRaises(InferenceServiceError) as ctx:
            self.service.predict("Cleaned claim.")
        self.assertIn("Model inference failed", str(ctx.exception))
        self.assertIsInstance(ctx.exception.__cause__, ModelInferenceError)

    def test_adapter_model_loading_error_wrapped(self):
        self.mock_adapter.predict.side_effect = ModelLoadingError(
            "Weights file missing"
        )
        with self.assertRaises(InferenceServiceError) as ctx:
            self.service.predict("Cleaned claim.")
        self.assertIn("Model inference failed", str(ctx.exception))
        self.assertIsInstance(ctx.exception.__cause__, ModelLoadingError)

    def test_unexpected_programming_errors_propagate(self):
        """Verifies unexpected bugs (e.g. AttributeError) propagate unmasked without wrapping."""
        self.mock_adapter.predict.side_effect = AttributeError(
            "Unexpected NoneType bug"
        )
        with self.assertRaises(AttributeError):
            self.service.predict("Cleaned claim.")

    # -------------------------------------------------------------------------
    # 5. Dependency Injection, Model Versioning, & Lazy Initialization
    # -------------------------------------------------------------------------

    def test_lazy_adapter_model_version_without_weight_loading(self):
        """Verifies reading model_version initializes the default adapter without loading model weights."""
        service = ModelInferenceService()
        self.assertIsNone(service._adapter)

        # Access model_version before predict()
        version = service.model_version
        expected_version = str(getattr(settings, "MODEL_VERSION", "v1"))
        self.assertEqual(version, expected_version)

        # Adapter is now initialized, but model weights were not loaded from disk
        self.assertIsNotNone(service._adapter)
        self.assertEqual(service.adapter.loader.load_count, 0)

    @patch.object(ModelLoader, "_load")
    def test_focused_mock_model_version_does_not_call_load(self, mock_load):
        """Verifies via focused patch that ModelLoader._load is never invoked when querying model_version."""
        service = ModelInferenceService()
        _ = service.model_version
        mock_load.assert_not_called()

    def test_injected_adapter_with_model_version(self):
        mock_adapter = MagicMock(spec=["predict", "model_version"])
        mock_adapter.model_version = "deberta_custom_v2"
        service = ModelInferenceService(adapter=mock_adapter)
        self.assertEqual(service.model_version, "deberta_custom_v2")

    def test_injected_adapter_without_model_version(self):
        simple_adapter = MockModelAdapter()
        self.assertFalse(hasattr(simple_adapter, "model_version"))
        service = ModelInferenceService(adapter=simple_adapter)
        self.assertIsNone(service.model_version)

    def test_mock_adapter_injection_avoids_pytorch_import(self):
        """Verifies MockModelAdapter executes inference purely in memory."""
        mock_adapter = MockModelAdapter(
            default_prediction=ModelPrediction.MISINFORMATION,
            default_confidence=0.99,
        )
        service = ModelInferenceService(adapter=mock_adapter)
        output = service.predict("Claim analyzed by mock adapter.")
        self.assertIsInstance(output, ModelOutput)
        self.assertEqual(output.prediction, ModelPrediction.MISINFORMATION)
        self.assertEqual(output.confidence, 0.99)

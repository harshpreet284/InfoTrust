import importlib
import math
from unittest import TestCase

from analysis.inference import MockModelAdapter, ModelAdapterProtocol, ModelOutput
from analysis.models import ModelPrediction


class AIAppStructureImportTests(TestCase):
    """
    Verifies that all required structural packages under backend/analysis are importable.
    """

    def test_services_package_import(self):
        mod = importlib.import_module("analysis.services")
        self.assertIsNotNone(mod)

    def test_inference_package_import(self):
        mod = importlib.import_module("analysis.inference")
        self.assertIsNotNone(mod)
        self.assertTrue(hasattr(mod, "ModelOutput"))
        self.assertTrue(hasattr(mod, "ModelAdapterProtocol"))
        self.assertTrue(hasattr(mod, "MockModelAdapter"))

    def test_model_loader_package_import(self):
        mod = importlib.import_module("analysis.model_loader")
        self.assertIsNotNone(mod)

    def test_engine_package_import(self):
        mod = importlib.import_module("analysis.engine")
        self.assertIsNotNone(mod)

    def test_preprocessing_package_import(self):
        mod = importlib.import_module("analysis.preprocessing")
        self.assertIsNotNone(mod)

    def test_utils_package_import(self):
        mod = importlib.import_module("analysis.utils")
        self.assertIsNotNone(mod)


class ModelOutputContractTests(TestCase):
    """
    Validates the ModelOutput dataclass constraints and edge cases.
    """

    def test_valid_model_output_credible(self):
        output = ModelOutput(prediction=ModelPrediction.CREDIBLE, confidence=0.92)
        self.assertEqual(output.prediction, ModelPrediction.CREDIBLE)
        self.assertEqual(output.confidence, 0.92)

    def test_valid_model_output_misinformation(self):
        output = ModelOutput(prediction=ModelPrediction.MISINFORMATION, confidence=0.88)
        self.assertEqual(output.prediction, ModelPrediction.MISINFORMATION)
        self.assertEqual(output.confidence, 0.88)

    def test_valid_boundary_confidences(self):
        out_zero = ModelOutput(prediction=ModelPrediction.CREDIBLE, confidence=0.0)
        self.assertEqual(out_zero.confidence, 0.0)

        out_one = ModelOutput(prediction=ModelPrediction.MISINFORMATION, confidence=1.0)
        self.assertEqual(out_one.confidence, 1.0)

    def test_model_output_is_immutable(self):
        output = ModelOutput(prediction=ModelPrediction.CREDIBLE, confidence=0.75)
        with self.assertRaises(AttributeError):
            output.confidence = 0.99  # type: ignore

    def test_invalid_prediction_type_rejected(self):
        with self.assertRaises(TypeError):
            ModelOutput(prediction="CREDIBLE", confidence=0.8)  # type: ignore

        with self.assertRaises(TypeError):
            ModelOutput(prediction=None, confidence=0.8)  # type: ignore

    def test_invalid_confidence_type_rejected(self):
        with self.assertRaises(TypeError):
            ModelOutput(prediction=ModelPrediction.CREDIBLE, confidence="0.85")  # type: ignore

        with self.assertRaises(TypeError):
            ModelOutput(prediction=ModelPrediction.CREDIBLE, confidence=True)  # type: ignore

    def test_confidence_out_of_range_rejected(self):
        with self.assertRaises(ValueError):
            ModelOutput(prediction=ModelPrediction.CREDIBLE, confidence=-0.01)

        with self.assertRaises(ValueError):
            ModelOutput(prediction=ModelPrediction.CREDIBLE, confidence=1.001)

    def test_confidence_non_finite_rejected(self):
        with self.assertRaises(ValueError):
            ModelOutput(prediction=ModelPrediction.CREDIBLE, confidence=float("nan"))

        with self.assertRaises(ValueError):
            ModelOutput(prediction=ModelPrediction.CREDIBLE, confidence=float("inf"))

        with self.assertRaises(ValueError):
            ModelOutput(prediction=ModelPrediction.CREDIBLE, confidence=float("-inf"))


class ModelAdapterProtocolAndMockTests(TestCase):
    """
    Validates runtime protocol conformance and MockModelAdapter functionality.
    """

    def test_mock_adapter_conforms_to_protocol(self):
        adapter = MockModelAdapter()
        self.assertIsInstance(adapter, ModelAdapterProtocol)

    def test_non_conforming_class_fails_protocol_check(self):
        class IncompleteAdapter:
            pass

        self.assertNotIsInstance(IncompleteAdapter(), ModelAdapterProtocol)

    def test_mock_adapter_default_prediction(self):
        adapter = MockModelAdapter()
        output = adapter.predict("Cleaned claim text.")
        self.assertIsInstance(output, ModelOutput)
        self.assertEqual(output.prediction, ModelPrediction.CREDIBLE)
        self.assertEqual(output.confidence, 0.85)

    def test_mock_adapter_custom_configured_output(self):
        adapter = MockModelAdapter(
            default_prediction=ModelPrediction.MISINFORMATION,
            default_confidence=0.97,
        )
        output = adapter.predict("Another valid claim text.")
        self.assertEqual(output.prediction, ModelPrediction.MISINFORMATION)
        self.assertEqual(output.confidence, 0.97)

    def test_mock_adapter_rejects_empty_input(self):
        adapter = MockModelAdapter()
        with self.assertRaises(ValueError):
            adapter.predict("")

        with self.assertRaises(ValueError):
            adapter.predict("   \n\t  ")

        with self.assertRaises(ValueError):
            adapter.predict(None)  # type: ignore

import logging
import math
import os
import time
from unittest import TestCase, skipUnless

from analysis.inference import DebertaModelAdapter, ModelOutput
from analysis.model_loader import (
    ModelArtifactNotFoundError,
    ModelLoader,
    resolve_artifact_path,
)
from analysis.models import ModelPrediction

logger = logging.getLogger(__name__)


@skipUnless(
    os.environ.get("RUN_MODEL_INTEGRATION_TESTS") == "true",
    "Skipping real model integration test: opt-in flag RUN_MODEL_INTEGRATION_TESTS is not set to 'true'.",
)
class RealArtifactIntegrationTests(TestCase):
    """
    Operational integration test against the real saved fine-tuned DeBERTa model artifact.
    Verifies offline weight loading, fast tokenizer execution, contract adherence,
    finite confidence in [0.5, 1.0], and memory stability across repeated inferences.

    NOTE: This is an operational smoke test verifying end-to-end architecture wiring.
    It does not replace offline statistical evaluation benchmarks (e.g. Macro F1 on held-out datasets).
    """

    def setUp(self):
        try:
            self.artifact_path = resolve_artifact_path()
        except ModelArtifactNotFoundError as e:
            self.skipTest(f"Skipping: model artifact not available locally: {e}")

        self.loader = ModelLoader(artifact_path=self.artifact_path)
        self.adapter = DebertaModelAdapter(loader=self.loader)

    def test_real_model_offline_inference_and_caching(self):
        sample_claim = "Clinical trial evidence supports the reported finding."

        # First inference call (triggers lazy load)
        start_t1 = time.perf_counter()
        output1 = self.adapter.predict(sample_claim)
        dur1 = time.perf_counter() - start_t1

        # Assert output contract
        self.assertIsInstance(output1, ModelOutput)
        self.assertIsInstance(output1.prediction, ModelPrediction)
        self.assertIn(
            output1.prediction,
            (ModelPrediction.CREDIBLE, ModelPrediction.MISINFORMATION),
        )
        self.assertIsInstance(output1.confidence, float)
        self.assertTrue(math.isfinite(output1.confidence))
        self.assertGreaterEqual(output1.confidence, 0.5)
        self.assertLessEqual(output1.confidence, 1.0)

        # Record model and tokenizer IDs
        model_id_first = id(self.loader._model)
        tok_id_first = id(self.loader._tokenizer)
        self.assertEqual(self.loader.load_count, 1)

        # Repeated inference calls
        durations = [dur1]
        for idx in range(2, 4):
            start_tn = time.perf_counter()
            output_n = self.adapter.predict(f"{sample_claim} (variation {idx})")
            dur_n = time.perf_counter() - start_tn
            durations.append(dur_n)

            # Contract checks on repeat calls
            self.assertIsInstance(output_n, ModelOutput)
            self.assertTrue(math.isfinite(output_n.confidence))
            self.assertGreaterEqual(output_n.confidence, 0.5)

            # Verify identical in-memory instances (no disk re-reads)
            self.assertEqual(id(self.loader._model), model_id_first)
            self.assertEqual(id(self.loader._tokenizer), tok_id_first)
            self.assertEqual(self.loader.load_count, 1)

        logger.info(
            "Real artifact integration test passed. Cold load: %.3fs, Warm calls: %s",
            durations[0],
            [f"{d:.4f}s" for d in durations[1:]],
        )

"""
Comprehensive unit and integration test suite for Model Management (AI-017).
Covers:
1. Canonical configuration & resolution precedence (MODEL_ARTIFACT_PATH, MODEL_PATH alias).
2. Weight-free system checks ('model_artifacts' tag) and command isolation.
3. Safe provenance snapshots without eager loading or masking pipeline errors.
4. ModelAdapterProtocol compliance, custom adapter injection, and fingerprint-based cache isolation.
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.core.checks import Warning as DjangoWarning
from django.test import SimpleTestCase, TestCase, override_settings

from analysis.checks import check_model_artifacts
from analysis.inference.adapter import (
    ManagedModelAdapterProtocol,
    ModelAdapterProtocol,
    ModelOutput,
)
from analysis.inference.deberta import DebertaModelAdapter
from analysis.model_loader.loader import (
    ModelArtifactCorruptedError,
    ModelArtifactNotFoundError,
    ModelLoader,
    resolve_artifact_path,
)
from analysis.models import Analysis, ModelPrediction
from analysis.services.explainability import ExplainabilityService
from analysis.services.inference import (
    InferencePredictionCache,
    ModelInferenceService,
)
from analysis.test_explainability_service import (
    _build_nominal_hybrid_result,
    _build_nominal_verdict_result,
)
from analysis.test_pipeline import _build_test_pipeline
from claims.models import Claim, ClaimStatus


def _create_mock_artifact_dir(
    tmp_path: Path,
    has_config: bool = True,
    has_tok: bool = True,
    has_weights: bool = True,
    model_type: str = "deberta-v2",
    has_manifest: bool = False,
    manifest_version: str = "v1",
) -> Path:
    """Helper to populate a temporary model artifact directory."""
    if has_config:
        cfg = {
            "model_type": model_type,
            "num_labels": 2,
            "id2label": {"0": "CREDIBLE", "1": "MISINFORMATION"},
        }
        (tmp_path / "config.json").write_text(json.dumps(cfg), encoding="utf-8")
    if has_tok:
        (tmp_path / "tokenizer.json").write_text('{"version": "1.0"}', encoding="utf-8")
        (tmp_path / "tokenizer_config.json").write_text(
            '{"do_lower_case": true}', encoding="utf-8"
        )
    if has_weights:
        (tmp_path / "model.safetensors").write_bytes(b"dummy safetensors content")
    if has_manifest:
        import hashlib

        config_bytes = (tmp_path / "config.json").read_bytes()
        tok_bytes = (tmp_path / "tokenizer.json").read_bytes()
        weights_bytes = (tmp_path / "model.safetensors").read_bytes()
        manifest_data = {
            "release_id": "test-release-001",
            "model_name": "infotrust-test",
            "model_version": manifest_version,
            "architecture": "microsoft/deberta-v3-base",
            "description": "Test manifest",
            "created_at": "2026-11-06T12:00:00Z",
            "files": {
                "config.json": {
                    "size": len(config_bytes),
                    "sha256": hashlib.sha256(config_bytes).hexdigest(),
                },
                "tokenizer.json": {
                    "size": len(tok_bytes),
                    "sha256": hashlib.sha256(tok_bytes).hexdigest(),
                },
                "model.safetensors": {
                    "size": len(weights_bytes),
                    "sha256": hashlib.sha256(weights_bytes).hexdigest(),
                },
            },
        }
        (tmp_path / "model_manifest.json").write_text(
            json.dumps(manifest_data), encoding="utf-8"
        )
    return tmp_path


# =============================================================================
# 1. Configuration & Path Resolution Tests
# =============================================================================


class ModelConfigurationTests(SimpleTestCase):
    """Verifies settings precedence, environment aliasing, and path resolution."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.artifact_path = Path(self.temp_dir.name)
        _create_mock_artifact_dir(self.artifact_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    @override_settings(
        MODEL_ARTIFACT_PATH=None,
        INFOTRUST_ENV="development",
        MODEL_ALLOW_UNMANIFESTED_ARTIFACTS=True,
    )
    def test_explicit_argument_overrides_settings(self):
        """Passing an explicit raw_path overrides configured settings."""
        resolved = resolve_artifact_path(self.artifact_path)
        self.assertEqual(resolved, self.artifact_path.resolve())

    def test_canonical_model_artifact_path_setting(self):
        """MODEL_ARTIFACT_PATH setting is honored when raw_path is None."""
        with override_settings(
            MODEL_ARTIFACT_PATH=str(self.artifact_path),
            INFOTRUST_ENV="development",
            MODEL_ALLOW_UNMANIFESTED_ARTIFACTS=True,
        ):
            resolved = resolve_artifact_path(None)
            self.assertEqual(resolved, self.artifact_path.resolve())

    def test_production_fails_closed_when_artifact_path_unset(self):
        """In production/staging, resolve_artifact_path raises ModelArtifactNotFoundError if unset."""
        with override_settings(
            MODEL_ARTIFACT_PATH=None,
            INFOTRUST_ENV="production",
        ):
            with self.assertRaises(ModelArtifactNotFoundError) as ctx:
                resolve_artifact_path(None)
            self.assertIn(
                "MODEL_ARTIFACT_PATH must be explicitly configured", str(ctx.exception)
            )

    def test_empty_string_artifact_path_treated_as_unset(self):
        """Whitespace or empty MODEL_ARTIFACT_PATH fails closed in production."""
        with override_settings(
            MODEL_ARTIFACT_PATH="   ",
            INFOTRUST_ENV="production",
        ):
            with self.assertRaises(ModelArtifactNotFoundError):
                resolve_artifact_path(None)

    def test_relative_path_resolves_against_base_dir(self):
        """Relative artifact paths resolve anchored to BASE_DIR."""
        from django.conf import settings

        rel_sub = self.artifact_path.name
        # Create directory relative to BASE_DIR
        target = settings.BASE_DIR / rel_sub
        target.mkdir(parents=True, exist_ok=True)
        try:
            _create_mock_artifact_dir(target)
            resolved = resolve_artifact_path(rel_sub)
            self.assertEqual(resolved, target.resolve())
        finally:
            import shutil

            shutil.rmtree(target, ignore_errors=True)


# =============================================================================
# 2. System Check & Command Isolation Tests
# =============================================================================


class WeightFreeStartupValidationTests(SimpleTestCase):
    """Verifies that model availability preflight is weight-free and isolated."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.artifact_path = Path(self.temp_dir.name)
        _create_mock_artifact_dir(self.artifact_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_system_check_passes_on_valid_artifacts(self):
        """check_model_artifacts returns no errors for a valid artifact directory."""
        with override_settings(
            MODEL_ARTIFACT_PATH=str(self.artifact_path),
            INFOTRUST_ENV="development",
            MODEL_ALLOW_UNMANIFESTED_ARTIFACTS=True,
            MODEL_STARTUP_CHECK_ENABLED=True,
        ):
            errors = check_model_artifacts()
            self.assertEqual(errors, [])

    def test_system_check_fails_on_missing_directory(self):
        """check_model_artifacts returns checks.Error when directory does not exist."""
        non_existent = self.artifact_path / "does_not_exist"
        with override_settings(
            MODEL_ARTIFACT_PATH=str(non_existent),
            INFOTRUST_ENV="development",
            MODEL_ALLOW_UNMANIFESTED_ARTIFACTS=True,
            MODEL_STARTUP_CHECK_ENABLED=True,
        ):
            errors = check_model_artifacts()
            self.assertEqual(len(errors), 1)
            self.assertEqual(errors[0].id, "analysis.E001")

    def test_system_check_fails_on_missing_mandatory_file(self):
        """check_model_artifacts returns checks.Error when model.safetensors is missing."""
        (self.artifact_path / "model.safetensors").unlink()
        with override_settings(
            MODEL_ARTIFACT_PATH=str(self.artifact_path),
            INFOTRUST_ENV="development",
            MODEL_ALLOW_UNMANIFESTED_ARTIFACTS=True,
            MODEL_STARTUP_CHECK_ENABLED=True,
        ):
            errors = check_model_artifacts()
            self.assertEqual(len(errors), 1)
            self.assertEqual(errors[0].id, "analysis.E001")

    def test_system_check_emits_warning_when_disabled_in_development(self):
        """When disabled in development, check_model_artifacts returns a warning."""
        with override_settings(
            MODEL_STARTUP_CHECK_ENABLED=False,
            INFOTRUST_ENV="development",
        ):
            errors = check_model_artifacts()
            self.assertEqual(len(errors), 1)
            self.assertIsInstance(errors[0], DjangoWarning)
            self.assertEqual(errors[0].id, "analysis.W001")

    def test_system_check_does_not_load_pytorch_weights_or_cuda(self):
        """Preflight check executes validate_model_availability without loading weights into memory."""
        with (
            patch(
                "transformers.AutoModelForSequenceClassification.from_pretrained"
            ) as mock_model_load,
            patch("torch.cuda.is_available") as mock_cuda,
            override_settings(
                MODEL_ARTIFACT_PATH=str(self.artifact_path),
                INFOTRUST_ENV="development",
                MODEL_ALLOW_UNMANIFESTED_ARTIFACTS=True,
                MODEL_STARTUP_CHECK_ENABLED=True,
            ),
        ):
            errors = check_model_artifacts()
            self.assertEqual(errors, [])
            mock_model_load.assert_not_called()
            mock_cuda.assert_not_called()

    def test_management_commands_unblocked_without_model(self):
        """Database management commands passing kwargs['databases'] bypass model checks."""
        non_existent = self.artifact_path / "missing"
        with override_settings(
            MODEL_ARTIFACT_PATH=str(non_existent),
            INFOTRUST_ENV="production",
        ):
            # Simulated migrate call passes databases=['default']
            errors = check_model_artifacts(databases=["default"])
            self.assertEqual(errors, [])


# =============================================================================
# 3. Safe Provenance Snapshot Tests
# =============================================================================


class SafeProvenanceSnapshotTests(TestCase):
    """Verifies that model provenance is captured safely without eager loading or masking failures."""

    def test_safe_provenance_snapshot_before_inference_returns_none(self):
        """Calling get_provenance_snapshot before predict does not instantiate adapter or load weights."""
        service = ModelInferenceService(adapter=None)
        self.assertIsNone(service._adapter)
        version, fingerprint = service.get_provenance_snapshot()
        self.assertIsNone(version)
        self.assertIsNone(fingerprint)
        # Verify adapter was not lazily constructed
        self.assertIsNone(service._adapter)

    def test_safe_provenance_snapshot_after_successful_inference(self):
        """get_provenance_snapshot returns active version and fingerprint after inference."""
        mock_adapter = MagicMock(
            spec=["predict", "model_version", "artifact_fingerprint"]
        )
        mock_adapter.model_version = "v1"
        mock_adapter.artifact_fingerprint = "fp-test-123"
        mock_adapter.predict.return_value = ModelOutput(
            prediction=ModelPrediction.CREDIBLE,
            confidence=0.92,
        )

        service = ModelInferenceService(adapter=mock_adapter)
        service.predict("Claim text.")

        version, fingerprint = service.get_provenance_snapshot()
        self.assertEqual(version, "v1")
        self.assertEqual(fingerprint, "fp-test-123")

    def test_safe_provenance_snapshot_handles_property_exception_gracefully(self):
        """Exceptions in adapter property getters return None without re-raising."""
        mock_adapter = MagicMock()
        mock_adapter.predict.return_value = ModelOutput(
            prediction=ModelPrediction.CREDIBLE,
            confidence=0.90,
        )
        type(mock_adapter).model_version = property(
            lambda self: (_ for _ in ()).throw(RuntimeError("Version boom!"))
        )
        type(mock_adapter).artifact_fingerprint = property(lambda self: "valid-fp")

        service = ModelInferenceService(adapter=mock_adapter)
        version, fingerprint = service.get_provenance_snapshot()
        self.assertIsNone(version)
        self.assertEqual(fingerprint, "valid-fp")

    def test_pipeline_records_model_provenance_in_diagnostics(self):
        """AnalysisPipelineService records model_version and artifact_fingerprint in explainability_json diagnostics."""
        user = get_user_model().objects.create_user(
            email="provenance_user@example.com",
            password="Password123!",
            full_name="Provenance User",
        )
        claim = Claim.objects.create(
            user=user,
            text="Vaccines undergo rigorous safety testing.",
            status=ClaimStatus.PENDING,
        )

        mock_adapter = MagicMock(
            spec=["predict", "model_version", "artifact_fingerprint"]
        )
        mock_adapter.model_version = "v1"
        mock_adapter.artifact_fingerprint = "fp-provenance-test"
        mock_adapter.predict.return_value = ModelOutput(
            prediction=ModelPrediction.CREDIBLE,
            confidence=0.95,
        )

        model_service = ModelInferenceService(adapter=mock_adapter)
        pipeline = _build_test_pipeline(model_service=model_service)
        pipeline.run_pipeline(claim.id)

        claim.refresh_from_db()
        self.assertEqual(claim.status, ClaimStatus.COMPLETED)
        analysis = Analysis.objects.get(claim=claim)

        diag = analysis.explainability_json.get("diagnostics", {})
        self.assertEqual(diag.get("model_version"), "v1")
        self.assertEqual(diag.get("artifact_fingerprint"), "fp-provenance-test")

    def test_public_to_dict_excludes_model_provenance(self):
        """ExplainabilityResult.to_dict() never leaks internal diagnostics or provenance to public consumers."""
        service = ExplainabilityService()
        hybrid_res = _build_nominal_hybrid_result()
        verdict_res = _build_nominal_verdict_result()

        result = service.generate_explainability(
            hybrid_res,
            verdict_res,
            model_version="v1",
            artifact_fingerprint="fp-secret-123",
        )

        # Public dictionary must NOT contain diagnostics
        public_data = result.to_dict()
        self.assertNotIn("diagnostics", public_data)
        self.assertNotIn("fp-secret-123", json.dumps(public_data))

        # Internal dictionary MUST preserve diagnostics
        internal_data = result.to_internal_dict()
        self.assertIn("diagnostics", internal_data)
        self.assertEqual(internal_data["diagnostics"]["model_version"], "v1")
        self.assertEqual(
            internal_data["diagnostics"]["artifact_fingerprint"], "fp-secret-123"
        )


# =============================================================================
# 4. Adapter Interface & Cache Isolation Tests
# =============================================================================


class AdapterProtocolAndCacheIsolationTests(TestCase):
    """Verifies ModelAdapterProtocol adherence, custom injection, and strict cache isolation."""

    def setUp(self):
        ModelInferenceService.reset_prediction_cache()
        ModelInferenceService.reset_circuit_breaker()

    def tearDown(self):
        ModelInferenceService.reset_prediction_cache()
        ModelInferenceService.reset_circuit_breaker()

    def test_deberta_adapter_satisfies_protocol(self):
        """DebertaModelAdapter conforms to ModelAdapterProtocol and ManagedModelAdapterProtocol."""
        adapter = DebertaModelAdapter(model_version="v1")
        self.assertTrue(isinstance(adapter, ModelAdapterProtocol))
        self.assertTrue(isinstance(adapter, ManagedModelAdapterProtocol))

    def test_injected_adapter_without_callable_predict_raises_type_error(self):
        """ModelInferenceService rejects injected adapters that do not have a callable predict method."""

        class NotAnAdapter:
            predict = "not a callable"

        with self.assertRaises(TypeError):
            ModelInferenceService(adapter=NotAnAdapter())

    def test_distinct_adapter_fingerprints_produce_separate_cache_entries(self):
        """Adapters with different fingerprints produce partitioned cache entries for identical text."""
        cache = InferencePredictionCache(max_entries=10)

        mock1 = MagicMock(spec=["predict", "model_version", "artifact_fingerprint"])
        mock1.artifact_fingerprint = "fp-adapter-1"
        mock1.model_version = "v1"
        mock1.predict.return_value = ModelOutput(
            prediction=ModelPrediction.CREDIBLE, confidence=0.91
        )

        mock2 = MagicMock(spec=["predict", "model_version", "artifact_fingerprint"])
        mock2.artifact_fingerprint = "fp-adapter-2"
        mock2.model_version = "v2"
        mock2.predict.return_value = ModelOutput(
            prediction=ModelPrediction.MISINFORMATION, confidence=0.88
        )

        svc1 = ModelInferenceService(adapter=mock1, prediction_cache=cache)
        svc2 = ModelInferenceService(adapter=mock2, prediction_cache=cache)

        claim_text = "Water boils at 100 degrees Celsius."
        res1 = svc1.predict(claim_text)
        res2 = svc2.predict(claim_text)

        self.assertEqual(res1.prediction, ModelPrediction.CREDIBLE)
        self.assertEqual(res2.prediction, ModelPrediction.MISINFORMATION)
        self.assertEqual(len(cache), 2)

    def test_missing_fingerprint_bypasses_cache_lookup_and_insertion(self):
        """When an adapter has no artifact_fingerprint, caching is bypassed without failing inference."""
        cache = InferencePredictionCache(max_entries=10)
        mock = MagicMock(spec=["predict", "model_version"])
        mock.model_version = "v1"
        mock.predict.return_value = ModelOutput(
            prediction=ModelPrediction.CREDIBLE, confidence=0.93
        )

        svc = ModelInferenceService(adapter=mock, prediction_cache=cache)
        out = svc.predict("Earth orbits the Sun.")

        self.assertEqual(out.confidence, 0.93)
        self.assertEqual(len(cache), 0)  # Never cached

    def test_empty_fingerprint_bypasses_cache_lookup_and_insertion(self):
        """Empty or whitespace artifact_fingerprint bypasses prediction cache."""
        cache = InferencePredictionCache(max_entries=10)
        mock = MagicMock(spec=["predict", "model_version", "artifact_fingerprint"])
        mock.artifact_fingerprint = "   "
        mock.model_version = "v1"
        mock.predict.return_value = ModelOutput(
            prediction=ModelPrediction.CREDIBLE, confidence=0.93
        )

        svc = ModelInferenceService(adapter=mock, prediction_cache=cache)
        out = svc.predict("Earth orbits the Sun.")

        self.assertEqual(out.confidence, 0.93)
        self.assertEqual(len(cache), 0)

    def test_fingerprint_property_exception_bypasses_cache_without_failing_inference(
        self,
    ):
        """If reading artifact_fingerprint raises an unhandled exception, cache is bypassed safely."""
        cache = InferencePredictionCache(max_entries=10)
        mock = MagicMock()
        mock.predict.return_value = ModelOutput(
            prediction=ModelPrediction.CREDIBLE, confidence=0.93
        )
        type(mock).artifact_fingerprint = property(
            lambda self: (_ for _ in ()).throw(AttributeError("Property error"))
        )

        svc = ModelInferenceService(adapter=mock, prediction_cache=cache)
        out = svc.predict("Jupiter is the largest planet.")

        self.assertEqual(out.confidence, 0.93)
        self.assertEqual(len(cache), 0)

    def test_loader_updates_version_from_verified_manifest(self):
        """ModelLoader binds model_version to the verified manifest version on disk."""
        temp_dir = tempfile.TemporaryDirectory()
        try:
            artifact_dir = Path(temp_dir.name)
            _create_mock_artifact_dir(
                artifact_dir, has_manifest=True, manifest_version="v1"
            )
            loader = ModelLoader(artifact_path=artifact_dir, model_version="v1")
            loader.validate_and_read_manifest(artifact_dir)
            self.assertEqual(loader.model_version, "v1")
        finally:
            temp_dir.cleanup()

    def test_loader_rejects_manifest_version_mismatch(self):
        """ModelLoader raises ModelArtifactCorruptedError when manifest version differs from expected version."""
        temp_dir = tempfile.TemporaryDirectory()
        try:
            artifact_dir = Path(temp_dir.name)
            _create_mock_artifact_dir(
                artifact_dir, has_manifest=True, manifest_version="v2"
            )
            loader = ModelLoader(artifact_path=artifact_dir, model_version="v1")
            with self.assertRaises(ModelArtifactCorruptedError) as ctx:
                loader.validate_and_read_manifest(artifact_dir)
            self.assertIn("mismatch", str(ctx.exception).lower())
        finally:
            temp_dir.cleanup()

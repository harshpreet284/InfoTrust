"""
AI-016 Performance Optimization Test Suite for InfoTrust.
Verifies:
1. ModelLoader and DebertaModelAdapter cryptographic artifact fingerprint exposure.
2. ModelInferenceService thread-safe bounded LRU prediction caching, circuit breaker integration,
   probe bypass semantics, and error handling.
3. FactCheckService dual-budget bounded TTL response caching, exact query casing preservation,
   zero-match caching, failure non-caching, and budget eviction.
4. AnalysisPipelineDispatcher in-flight deduplication, lock-free callback registration,
   idempotent permit release, and cancellation cleanup.
5. Bit-for-bit output invariance across cached and uncached pipeline executions.
"""

import hashlib
import json
import tempfile
import time
import urllib.error
import uuid
from concurrent.futures import Future
from pathlib import Path
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from analysis.inference.adapter import ModelOutput
from analysis.inference.deberta import DebertaModelAdapter
from analysis.model_loader.loader import (
    ModelArtifactCorruptedError,
    ModelLoader,
)
from analysis.models import Analysis, ModelPrediction, Verdict
from analysis.services.dispatcher import (
    AnalysisPipelineDispatcher,
    _DispatchCleanup,
)
from analysis.services.fact_check import (
    FactCheckAPIError,
    FactCheckAuthError,
    FactCheckEvidenceItem,
    FactCheckRateLimitError,
    FactCheckResponseCache,
    FactCheckResult,
    FactCheckService,
    FactCheckTimeoutError,
    _calculate_result_size,
)
from analysis.services.inference import (
    BreakerState,
    InferencePredictionCache,
    InferenceServiceError,
    ModelCircuitBreaker,
    ModelCircuitBreakerOpenError,
    ModelInferenceService,
)
from analysis.services.narrative import NarrativeActivity, NarrativeActivityService
from analysis.services.pipeline import AnalysisPipelineService
from claims.models import Claim, ClaimStatus

User = get_user_model()


# =============================================================================
# Helper Utilities & Fixtures
# =============================================================================


class MockHTTPResponse:
    """Mock context manager for urllib.request.urlopen responses."""

    def __init__(
        self, body_bytes: bytes, status: int = 200, headers: dict | None = None
    ):
        self.body_bytes = body_bytes
        self.status = status
        self.headers = headers or {}

    def read(self) -> bytes:
        return self.body_bytes

    def getheader(self, name: str, default: str | None = None) -> str | None:
        return self.headers.get(name, default)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass


def _create_minimal_valid_model_dir(base_dir: Path) -> Path:
    """Creates a minimal valid model directory with safetensors, config files, and manifest."""
    model_dir = base_dir / "valid_model"
    model_dir.mkdir(parents=True, exist_ok=True)
    weights = b"mock_safetensors_binary_data"
    cfg = b'{"architectures": ["DebertaV2ForSequenceClassification"]}'
    tok_cfg = b'{"tokenizer_class": "DebertaV2Tokenizer"}'
    tok_json = b'{"version": "1.0"}'

    (model_dir / "model.safetensors").write_bytes(weights)
    (model_dir / "config.json").write_bytes(cfg)
    (model_dir / "tokenizer_config.json").write_bytes(tok_cfg)
    (model_dir / "tokenizer.json").write_bytes(tok_json)

    manifest = {
        "schema_version": "1.0.0",
        "release_id": "test_release_1",
        "model_version": "v1",
        "files": {
            "model.safetensors": {
                "sha256": hashlib.sha256(weights).hexdigest(),
                "size": len(weights),
            },
            "config.json": {
                "sha256": hashlib.sha256(cfg).hexdigest(),
                "size": len(cfg),
            },
            "tokenizer.json": {
                "sha256": hashlib.sha256(tok_json).hexdigest(),
                "size": len(tok_json),
            },
        },
    }
    (model_dir / "model_manifest.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )
    return model_dir


# =============================================================================
# 1. ModelLoader & Adapter Fingerprint Exposure Tests
# =============================================================================


class ModelLoaderFingerprintTests(TestCase):
    """Verifies artifact fingerprint resolution and boundary exposure."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)
        self.model_dir = _create_minimal_valid_model_dir(self.temp_path)
        ModelLoader.reset_cache()

    def tearDown(self):
        ModelLoader.reset_cache()
        self.temp_dir.cleanup()

    def test_loader_exposes_artifact_fingerprint(self):
        """ModelLoader exposes artifact_fingerprint property computed from validated files."""
        loader = ModelLoader(
            artifact_path=self.model_dir,
            staging_base_dir=self.temp_path / "staging",
        )
        with patch.object(ModelLoader, "_load"):
            fp = loader.artifact_fingerprint
        self.assertIsInstance(fp, str)
        self.assertTrue(fp.startswith("manifest:test_release_1:v1:"))
        # Verify cached property returns same value without re-evaluating
        self.assertEqual(loader.artifact_fingerprint, fp)

    def test_deberta_adapter_exposes_artifact_fingerprint_forwarding(self):
        """DebertaModelAdapter exposes artifact_fingerprint forwarding to its loader."""
        loader = ModelLoader(
            artifact_path=self.model_dir,
            staging_base_dir=self.temp_path / "staging",
        )
        adapter = DebertaModelAdapter(loader=loader)
        with patch.object(ModelLoader, "_load"):
            self.assertEqual(adapter.artifact_fingerprint, loader.artifact_fingerprint)

    def test_identical_fingerprints_for_same_artifact_path(self):
        """Two loader instances referencing the same artifact path report identical fingerprints."""
        loader1 = ModelLoader(
            artifact_path=self.model_dir,
            staging_base_dir=self.temp_path / "staging1",
        )
        loader2 = ModelLoader(
            artifact_path=self.model_dir,
            staging_base_dir=self.temp_path / "staging2",
        )
        with patch.object(ModelLoader, "_load"):
            self.assertEqual(loader1.artifact_fingerprint, loader2.artifact_fingerprint)

    def test_corrupted_artifact_raises_corrupted_error_on_fingerprint_read(self):
        """Corrupted manifest/files raise ModelArtifactCorruptedError when reading artifact_fingerprint."""
        corrupt_dir = self.temp_path / "corrupt_model"
        corrupt_dir.mkdir(parents=True, exist_ok=True)
        (corrupt_dir / "model.safetensors").write_bytes(b"data")
        (corrupt_dir / "model_manifest.json").write_text(
            '{"schema_version": "1.0.0", "files": {"model.safetensors": {"sha256": "wrong_sha"}}}'
        )
        loader = ModelLoader(
            artifact_path=corrupt_dir,
            staging_base_dir=self.temp_path / "staging_corrupt",
        )
        with self.assertRaises(ModelArtifactCorruptedError):
            _ = loader.artifact_fingerprint


# =============================================================================
# 2. ModelInferenceService Prediction Caching Tests
# =============================================================================


class ModelInferenceServiceCacheTests(TestCase):
    """Verifies ModelInferenceService LRU caching, circuit-breaker interactions, and probe behavior."""

    def setUp(self):
        ModelInferenceService.reset_prediction_cache()
        ModelInferenceService.reset_circuit_breaker()
        self.mock_adapter = MagicMock()
        self.mock_adapter.artifact_fingerprint = "test_fingerprint_abc123"
        self.mock_adapter.model_version = "v1"
        self.mock_adapter.predict.return_value = ModelOutput(
            prediction=ModelPrediction.CREDIBLE,
            confidence=0.95,
        )
        self.breaker = ModelCircuitBreaker(ttl_seconds=60.0, transient_ttl_seconds=5.0)
        self.cache = InferencePredictionCache(max_entries=10)
        self.service = ModelInferenceService(
            adapter=self.mock_adapter,
            circuit_breaker=self.breaker,
            prediction_cache=self.cache,
        )

    def tearDown(self):
        ModelInferenceService.reset_prediction_cache()
        ModelInferenceService.reset_circuit_breaker()

    def test_cache_hit_returns_output_without_invoking_adapter_predict(self):
        """Cache hit returns cached ModelOutput without invoking adapter.predict."""
        claim = "Vaccines are safe and effective."
        output1 = self.service.predict(claim)
        self.assertEqual(self.mock_adapter.predict.call_count, 1)

        output2 = self.service.predict(claim)
        self.assertEqual(self.mock_adapter.predict.call_count, 1)
        self.assertEqual(output1, output2)
        self.assertEqual(len(self.cache), 1)

    def test_cache_miss_invokes_adapter_predict_and_populates_cache(self):
        """Cache miss invokes adapter.predict and populates cache."""
        self.assertEqual(len(self.cache), 0)
        out = self.service.predict("First distinct claim.")
        self.assertEqual(self.mock_adapter.predict.call_count, 1)
        self.assertEqual(len(self.cache), 1)
        self.assertEqual(out.confidence, 0.95)

    def test_different_claim_texts_produce_distinct_cache_entries(self):
        """Different claim texts produce distinct cache entries."""
        self.service.predict("Claim A")
        self.service.predict("Claim B")
        self.assertEqual(self.mock_adapter.predict.call_count, 2)
        self.assertEqual(len(self.cache), 2)

    def test_different_model_fingerprints_produce_distinct_cache_entries(self):
        """Different model fingerprints produce distinct cache entries for identical text."""
        claim = "Identical claim text."

        adapter1 = MagicMock()
        adapter1.artifact_fingerprint = "fingerprint_v1"
        adapter1.predict.return_value = ModelOutput(ModelPrediction.CREDIBLE, 0.80)
        service1 = ModelInferenceService(adapter=adapter1, prediction_cache=self.cache)

        adapter2 = MagicMock()
        adapter2.artifact_fingerprint = "fingerprint_v2"
        adapter2.predict.return_value = ModelOutput(
            ModelPrediction.MISINFORMATION, 0.90
        )
        service2 = ModelInferenceService(adapter=adapter2, prediction_cache=self.cache)

        out1 = service1.predict(claim)
        out2 = service2.predict(claim)

        self.assertEqual(adapter1.predict.call_count, 1)
        self.assertEqual(adapter2.predict.call_count, 1)
        self.assertEqual(out1.confidence, 0.80)
        self.assertEqual(out2.confidence, 0.90)
        self.assertEqual(len(self.cache), 2)

    def test_cache_capacity_bounded_by_max_entries_lru_eviction(self):
        """Cache capacity is bounded by max_entries; least recently used item is evicted."""
        tiny_cache = InferencePredictionCache(max_entries=2)
        service = ModelInferenceService(
            adapter=self.mock_adapter, prediction_cache=tiny_cache
        )

        service.predict("Claim 1")
        service.predict("Claim 2")
        self.assertEqual(len(tiny_cache), 2)

        # Access Claim 1 to mark it most recently used
        service.predict("Claim 1")
        self.assertEqual(self.mock_adapter.predict.call_count, 2)

        # Insert Claim 3 -> should evict Claim 2
        service.predict("Claim 3")
        self.assertEqual(len(tiny_cache), 2)

        # Claim 1 should still hit cache
        service.predict("Claim 1")
        self.assertEqual(self.mock_adapter.predict.call_count, 3)

        # Claim 2 should miss (was evicted)
        service.predict("Claim 2")
        self.assertEqual(self.mock_adapter.predict.call_count, 4)

    def test_reset_prediction_cache_clears_all_entries(self):
        """ModelInferenceService.reset_prediction_cache() clears the shared cache."""
        shared_service = ModelInferenceService(adapter=self.mock_adapter)
        shared_service.predict("Shared claim test")
        self.assertGreater(len(ModelInferenceService.get_prediction_cache()), 0)

        ModelInferenceService.reset_prediction_cache()
        self.assertEqual(len(ModelInferenceService.get_prediction_cache()), 0)

    def test_cache_hits_do_not_resolve_half_open_circuit_breaker_probes(self):
        """Cache hits do NOT resolve HALF_OPEN probes; probe requests MUST execute a real forward pass."""
        claim = "Probe test claim."
        # Warm the cache in CLOSED state
        self.service.predict(claim)
        self.assertEqual(self.mock_adapter.predict.call_count, 1)

        # Trip breaker to OPEN with transient error
        self.breaker.record_failure(RuntimeError("Transient error"))
        self.assertEqual(self.breaker.state, BreakerState.OPEN)

        # Force transition to HALF_OPEN
        with self.breaker._lock:
            self.breaker._open_until = time.monotonic() - 1.0

        admitted, probe_id = self.breaker.admit_request()
        self.assertTrue(admitted)
        self.assertIsNotNone(probe_id)
        self.assertEqual(self.breaker.state, BreakerState.HALF_OPEN)

        # Release probe slot to let predict() claim it
        with self.breaker._lock:
            self.breaker._probe_in_flight = False

        # Now call predict() on the cached claim while in HALF_OPEN
        self.service.predict(claim)
        # Verify adapter.predict was invoked again despite cache hit because it was a probe
        self.assertEqual(self.mock_adapter.predict.call_count, 2)
        # Verify breaker successfully transitioned to CLOSED
        self.assertEqual(self.breaker.state, BreakerState.CLOSED)

    def test_open_circuit_breaker_rejects_requests_before_cache_lookup(self):
        """OPEN circuit breaker rejects requests before cache lookup (cache cannot bypass OPEN breaker)."""
        claim = "Pre-cached claim text."
        # Populate cache
        self.service.predict(claim)
        self.assertEqual(len(self.cache), 1)

        # Trip breaker
        self.breaker.record_failure(RuntimeError("Model failure"))
        self.assertEqual(self.breaker.state, BreakerState.OPEN)

        # Attempt prediction on cached claim
        with self.assertRaises(ModelCircuitBreakerOpenError):
            self.service.predict(claim)

    def test_corrupted_artifact_trips_breaker_and_not_masked_by_cache(self):
        """ModelArtifactCorruptedError trips circuit breaker and is not masked by cache."""
        corrupt_adapter = MagicMock()
        type(corrupt_adapter).artifact_fingerprint = property(
            lambda self: (_ for _ in ()).throw(
                ModelArtifactCorruptedError("Corrupt weights")
            )
        )
        service = ModelInferenceService(
            adapter=corrupt_adapter,
            circuit_breaker=self.breaker,
            prediction_cache=self.cache,
        )

        with self.assertRaises(InferenceServiceError):
            service.predict("Any claim")

        self.assertEqual(self.breaker.state, BreakerState.OPEN)

    def test_forward_pass_runtime_error_not_cached(self):
        """Model adapter forward-pass runtime errors are not cached and trip circuit breaker."""
        self.mock_adapter.predict.side_effect = RuntimeError("Forward pass failed")
        claim = "Runtime failure claim"

        with self.assertRaises(RuntimeError):
            self.service.predict(claim)

        # Cache must remain empty
        self.assertEqual(len(self.cache), 0)
        # Breaker must be tripped
        self.assertEqual(self.breaker.state, BreakerState.OPEN)

        # After resetting the breaker and fixing adapter, query must miss cache and invoke adapter
        self.breaker.reset()
        self.mock_adapter.predict.side_effect = None
        self.mock_adapter.predict.return_value = ModelOutput(
            ModelPrediction.CREDIBLE, 0.91
        )
        out = self.service.predict(claim)
        self.assertEqual(out.confidence, 0.91)
        self.assertEqual(len(self.cache), 1)

    def test_cross_instance_prediction_cache_sharing(self):
        """Two distinct ModelInferenceService instances using default cache share predictions."""
        try:
            ModelInferenceService.reset_prediction_cache()
            ModelInferenceService.reset_circuit_breaker()

            claim = "Cross instance cached claim."
            adapter1 = MagicMock()
            adapter1.artifact_fingerprint = "shared_fingerprint_v1"
            adapter1.model_version = "v1"
            adapter1.predict.return_value = ModelOutput(ModelPrediction.CREDIBLE, 0.85)

            adapter2 = MagicMock()
            adapter2.artifact_fingerprint = "shared_fingerprint_v1"
            adapter2.model_version = "v1"
            adapter2.predict.side_effect = AssertionError(
                "Adapter 2 should not be invoked on cache hit"
            )

            # Default prediction_cache=None -> uses _shared_prediction_cache
            service1 = ModelInferenceService(adapter=adapter1)
            service2 = ModelInferenceService(adapter=adapter2)

            # First instance populates shared cache
            res1 = service1.predict(claim)
            self.assertEqual(adapter1.predict.call_count, 1)
            self.assertEqual(res1.confidence, 0.85)

            # Second instance must hit shared cache without calling adapter2.predict
            res2 = service2.predict(claim)
            self.assertEqual(adapter2.predict.call_count, 0)
            self.assertEqual(res1, res2)
        finally:
            ModelInferenceService.reset_prediction_cache()
            ModelInferenceService.reset_circuit_breaker()


# =============================================================================
# 3. FactCheckService Response Caching Tests
# =============================================================================


class FactCheckServiceCacheTests(TestCase):
    """Verifies FactCheckResponseCache dual-budget LRU, TTL, query casing, and error isolation."""

    def setUp(self):
        FactCheckService.reset_response_cache()
        self.cache = FactCheckResponseCache(
            max_entries=10,
            max_bytes=10000,
            max_single_entry_bytes=2000,
            ttl_seconds=3600.0,
        )

    def tearDown(self):
        FactCheckService.reset_response_cache()

    def test_cache_hit_returns_result_without_invoking_http_client(self):
        """Cache hit returns cached FactCheckResult without invoking HTTP client."""
        payload = json.dumps(
            {
                "claims": [
                    {
                        "text": "The moon is made of green cheese.",
                        "claimReview": [
                            {
                                "publisher": {"name": "ScienceReview"},
                                "url": "https://example.com/check/moon",
                                "textualRating": "False",
                            }
                        ],
                    }
                ]
            }
        ).encode("utf-8")

        mock_http = MagicMock(return_value=MockHTTPResponse(payload))
        service = FactCheckService(
            api_key="valid-key",
            http_client=mock_http,
            response_cache=self.cache,
        )

        res1 = service.query("The moon is made of green cheese.")
        self.assertEqual(mock_http.call_count, 1)
        self.assertEqual(res1.matches, 1)

        res2 = service.query("The moon is made of green cheese.")
        self.assertEqual(mock_http.call_count, 1)
        self.assertEqual(res1, res2)
        self.assertEqual(len(self.cache), 1)

    def test_cache_miss_invokes_http_client_and_populates_cache(self):
        """Cache miss invokes HTTP client and populates cache."""
        payload = json.dumps({"claims": []}).encode("utf-8")
        mock_http = MagicMock(return_value=MockHTTPResponse(payload))
        service = FactCheckService(
            api_key="valid-key",
            http_client=mock_http,
            response_cache=self.cache,
        )

        self.assertEqual(len(self.cache), 0)
        res = service.query("Unreviewed claim")
        self.assertEqual(mock_http.call_count, 1)
        self.assertEqual(res.matches, 0)
        self.assertEqual(len(self.cache), 1)

    def test_exact_query_casing_preserved_in_cache_key(self):
        """Exact query casing is preserved in cache key (no lowercase normalization)."""
        payload = json.dumps({"claims": []}).encode("utf-8")
        mock_http = MagicMock(return_value=MockHTTPResponse(payload))
        service = FactCheckService(
            api_key="valid-key",
            http_client=mock_http,
            response_cache=self.cache,
        )

        service.query("Case Sensitive Claim")
        service.query("case sensitive claim")
        self.assertEqual(mock_http.call_count, 2)
        self.assertEqual(len(self.cache), 2)

    def test_zero_match_valid_responses_are_cached(self):
        """Zero-match valid responses (HTTP 200 with no claims) are cached."""
        payload = json.dumps({}).encode("utf-8")
        mock_http = MagicMock(return_value=MockHTTPResponse(payload))
        service = FactCheckService(
            api_key="valid-key",
            http_client=mock_http,
            response_cache=self.cache,
        )

        res1 = service.query("No claims claim")
        self.assertEqual(res1.matches, 0)
        self.assertEqual(mock_http.call_count, 1)

        res2 = service.query("No claims claim")
        self.assertEqual(mock_http.call_count, 1)
        self.assertEqual(res1, res2)

    def test_failures_are_not_cached(self):
        """HTTP 429, 401, 5xx, and timeout failures are NOT cached."""
        # 429 Rate limit
        err_429 = urllib.error.HTTPError(
            "http://api", 429, "Too Many Requests", {}, None
        )
        mock_429 = MagicMock(side_effect=err_429)
        service_429 = FactCheckService(
            api_key="k", http_client=mock_429, response_cache=self.cache
        )
        with self.assertRaises(FactCheckRateLimitError):
            service_429.query("Failed claim 429")
        self.assertEqual(len(self.cache), 0)

        # 401 Auth error
        err_401 = urllib.error.HTTPError("http://api", 401, "Unauthorized", {}, None)
        mock_401 = MagicMock(side_effect=err_401)
        service_401 = FactCheckService(
            api_key="k", http_client=mock_401, response_cache=self.cache
        )
        with self.assertRaises(FactCheckAuthError):
            service_401.query("Failed claim 401")
        self.assertEqual(len(self.cache), 0)

        # 500 API error
        err_500 = urllib.error.HTTPError("http://api", 500, "Server Error", {}, None)
        mock_500 = MagicMock(side_effect=err_500)
        service_500 = FactCheckService(
            api_key="k", http_client=mock_500, response_cache=self.cache
        )
        with self.assertRaises(FactCheckAPIError):
            service_500.query("Failed claim 500")
        self.assertEqual(len(self.cache), 0)

        # Timeout error
        mock_timeout = MagicMock(side_effect=TimeoutError("Request timed out"))
        service_timeout = FactCheckService(
            api_key="k", http_client=mock_timeout, response_cache=self.cache
        )
        with self.assertRaises(FactCheckTimeoutError):
            service_timeout.query("Failed claim timeout")
        self.assertEqual(len(self.cache), 0)

    def test_single_entry_exceeding_max_single_entry_bytes_not_cached(self):
        """Single entries exceeding max_single_entry_bytes are not cached."""
        tiny_budget_cache = FactCheckResponseCache(
            max_entries=10,
            max_bytes=10000,
            max_single_entry_bytes=100,  # Strict 100 byte limit
        )
        payload = json.dumps(
            {
                "claims": [
                    {
                        "text": "A very detailed claim review",
                        "claimReview": [
                            {
                                "publisher": {
                                    "name": "Detailed Publisher With Long Name"
                                },
                                "url": "https://example.com/very/long/url/for/fact/checking/evidence",
                                "textualRating": "Extremely False and Misleading",
                            }
                        ],
                    }
                ]
            }
        ).encode("utf-8")
        mock_http = MagicMock(return_value=MockHTTPResponse(payload))
        service = FactCheckService(
            api_key="k", http_client=mock_http, response_cache=tiny_budget_cache
        )

        res = service.query("Large claim")
        self.assertEqual(res.matches, 1)
        # Entry exceeds 100 bytes; must NOT be cached
        self.assertEqual(len(tiny_budget_cache), 0)
        self.assertEqual(tiny_budget_cache.current_bytes, 0)

    def test_byte_budget_eviction_evicts_lru_entries(self):
        """Byte budget eviction (max_bytes) evicts LRU entries."""
        single_result = FactCheckResult(
            matches=1,
            sources=(FactCheckEvidenceItem("Pub", "False", "https://example.com/1"),),
            summary="Review summary",
            evidence_urls=("https://example.com/1",),
        )
        item_size = _calculate_result_size(single_result)

        # Allow room for exactly 2 entries
        budget_cache = FactCheckResponseCache(
            max_entries=10,
            max_bytes=item_size * 2 + 50,
            max_single_entry_bytes=item_size * 2,
        )

        budget_cache.set("key1", single_result)
        budget_cache.set("key2", single_result)
        self.assertEqual(len(budget_cache), 2)

        # Adding a 3rd entry must evict key1
        budget_cache.set("key3", single_result)
        self.assertEqual(len(budget_cache), 2)
        self.assertIsNone(budget_cache.get("key1"))
        self.assertIsNotNone(budget_cache.get("key2"))
        self.assertIsNotNone(budget_cache.get("key3"))

    def test_expired_entries_not_returned(self):
        """Expired entries (based on TTL) are not returned and are evicted."""
        ttl_cache = FactCheckResponseCache(ttl_seconds=0.05)
        result = FactCheckResult.empty()
        ttl_cache.set("expire_key", result)

        self.assertIsNotNone(ttl_cache.get("expire_key"))
        time.sleep(0.12)
        # After TTL expiration: lookup returns None and evicts entry
        self.assertIsNone(ttl_cache.get("expire_key"))
        self.assertEqual(len(ttl_cache), 0)

    def test_reset_response_cache_clears_all_entries(self):
        """FactCheckService.reset_response_cache() clears all entries and resets byte count."""
        shared_cache = FactCheckService.get_response_cache()
        service = FactCheckService(
            api_key="k",
            http_client=MagicMock(return_value=MockHTTPResponse(b"{}")),
            response_cache=shared_cache,
        )
        service.query("Claim to clear")
        self.assertGreater(len(shared_cache), 0)

        FactCheckService.reset_response_cache()
        self.assertEqual(len(shared_cache), 0)
        self.assertEqual(shared_cache.current_bytes, 0)

    def test_ttl_zero_disables_caching(self):
        """TTL=0 disables fact-check caching while returning valid successful response."""
        zero_ttl_cache = FactCheckResponseCache(ttl_seconds=0.0)
        payload = json.dumps({"claims": []}).encode("utf-8")
        mock_http = MagicMock(return_value=MockHTTPResponse(payload))
        service = FactCheckService(
            api_key="valid-key",
            http_client=mock_http,
            response_cache=zero_ttl_cache,
        )

        claim = "Zero TTL Claim"
        # First query succeeds
        res1 = service.query(claim)
        self.assertEqual(res1.matches, 0)
        self.assertEqual(mock_http.call_count, 1)
        # Cache must remain empty
        self.assertEqual(len(zero_ttl_cache), 0)

        # Second query must invoke provider again
        res2 = service.query(claim)
        self.assertEqual(res2.matches, 0)
        self.assertEqual(mock_http.call_count, 2)
        self.assertEqual(len(zero_ttl_cache), 0)


# =============================================================================
# 4. AnalysisPipelineDispatcher Deduplication Tests
# =============================================================================


class DispatcherDeduplicationTests(TestCase):
    """Verifies in-flight claim deduplication, non-reentrant callbacks, and cancellation handling."""

    def test_in_flight_claim_dispatch_returns_true_without_deducting_permit(self):
        """Dispatching the same claim_id while already in flight returns True immediately without deducting permit."""
        dispatcher = AnalysisPipelineDispatcher(
            max_workers=1,
            max_outstanding_tasks=1,
            sync_mode=False,
        )
        claim_id = uuid.uuid4()

        with patch.object(dispatcher, "_get_executor_unlocked") as mock_exec_getter:
            mock_executor = MagicMock()
            future = Future()
            mock_executor.submit.return_value = future
            mock_exec_getter.return_value = mock_executor

            # First dispatch schedules the task
            self.assertTrue(dispatcher.dispatch(claim_id))
            self.assertEqual(mock_executor.submit.call_count, 1)
            self.assertTrue(dispatcher.is_in_flight(claim_id))

            # Second dispatch with identical claim_id is deduplicated
            self.assertTrue(dispatcher.dispatch(claim_id))
            # Executor was NOT called again
            self.assertEqual(mock_executor.submit.call_count, 1)

            # Completing the future clears in-flight status
            future.set_result(None)
            self.assertFalse(dispatcher.is_in_flight(claim_id))

    def test_subsequent_dispatch_schedules_new_task_after_completion(self):
        """Once the in-flight task completes, dispatching that same claim_id schedules a new task."""
        dispatcher = AnalysisPipelineDispatcher(
            max_workers=1,
            max_outstanding_tasks=1,
            sync_mode=False,
        )
        claim_id = uuid.uuid4()

        with patch.object(dispatcher, "_get_executor_unlocked") as mock_exec_getter:
            mock_executor = MagicMock()
            f1 = Future()
            f2 = Future()
            mock_executor.submit.side_effect = [f1, f2]
            mock_exec_getter.return_value = mock_executor

            # 1. First run
            self.assertTrue(dispatcher.dispatch(claim_id))
            self.assertEqual(mock_executor.submit.call_count, 1)

            # Resolve f1
            f1.set_result(None)
            self.assertFalse(dispatcher.is_in_flight(claim_id))

            # 2. Second run after completion is admitted as new task
            self.assertTrue(dispatcher.dispatch(claim_id))
            self.assertEqual(mock_executor.submit.call_count, 2)
            f2.set_result(None)

    def test_done_callback_registered_outside_dispatcher_lock(self):
        """Done callback is registered strictly outside self._lock to prevent callback deadlock."""
        dispatcher = AnalysisPipelineDispatcher(max_workers=1, max_outstanding_tasks=2)
        claim_id = uuid.uuid4()

        # Create an immediately resolved future
        immediate_future = Future()
        immediate_future.set_result(None)

        with patch.object(dispatcher, "_get_executor_unlocked") as mock_exec_getter:
            mock_executor = MagicMock()
            mock_executor.submit.return_value = immediate_future
            mock_exec_getter.return_value = mock_executor

            # If add_done_callback was called inside with self._lock, immediate execution
            # of _DispatchCleanup (which acquires self._lock) would deadlock!
            self.assertTrue(dispatcher.dispatch(claim_id))
            # Verify clean completion
            self.assertFalse(dispatcher.is_in_flight(claim_id))

    def test_done_callback_is_idempotent(self):
        """_DispatchCleanup callback is idempotent and does not double-release semaphore."""
        dispatcher = AnalysisPipelineDispatcher(max_workers=1, max_outstanding_tasks=1)
        claim_id = uuid.uuid4()

        # Manually acquire permit and add in-flight
        dispatcher._semaphore.acquire()
        dispatcher._in_flight_claims.add(claim_id)

        cleanup = _DispatchCleanup(dispatcher, claim_id)
        mock_future = Future()

        # Invoke callback multiple times
        cleanup(mock_future)
        cleanup(mock_future)
        cleanup(mock_future)

        self.assertFalse(dispatcher.is_in_flight(claim_id))
        # Semaphore should have exactly 1 permit available (can acquire once, not twice)
        self.assertTrue(dispatcher._semaphore.acquire(blocking=False))
        self.assertFalse(dispatcher._semaphore.acquire(blocking=False))

    def test_executor_cancellation_cleans_up_in_flight_and_releases_permit(self):
        """ThreadPoolExecutor cancellation properly cleans up in-flight set and releases permit."""
        dispatcher = AnalysisPipelineDispatcher(max_workers=1, max_outstanding_tasks=1)
        claim_id = uuid.uuid4()

        with patch.object(dispatcher, "_get_executor_unlocked") as mock_exec_getter:
            mock_executor = MagicMock()
            future = Future()
            mock_executor.submit.return_value = future
            mock_exec_getter.return_value = mock_executor

            self.assertTrue(dispatcher.dispatch(claim_id))
            self.assertTrue(dispatcher.is_in_flight(claim_id))

            # Cancel future
            future.cancel()
            self.assertFalse(dispatcher.is_in_flight(claim_id))
            # Permit was released; next dispatch succeeds
            future2 = Future()
            mock_executor.submit.return_value = future2
            self.assertTrue(dispatcher.dispatch(uuid.uuid4()))

    def test_executor_submit_failure_cleans_up_and_releases_permit(self):
        """Simulated executor.submit failure cleans up in_flight_claims and releases permit."""
        dispatcher = AnalysisPipelineDispatcher(max_workers=1, max_outstanding_tasks=1)
        claim_id = uuid.uuid4()

        with patch.object(dispatcher, "_get_executor_unlocked") as mock_exec_getter:
            mock_executor = MagicMock()
            mock_executor.submit.side_effect = RuntimeError(
                "Worker pool allocation failure"
            )
            mock_exec_getter.return_value = mock_executor

            # Dispatch raises submission exception
            with self.assertRaises(RuntimeError):
                dispatcher.dispatch(claim_id)

            # In-flight claim must be removed
            self.assertFalse(dispatcher.is_in_flight(claim_id))
            self.assertEqual(dispatcher.in_flight_count, 0)

            # Permit must be released: capacity allows subsequent dispatch
            mock_executor.submit.side_effect = None
            valid_future = Future()
            mock_executor.submit.return_value = valid_future
            second_claim = uuid.uuid4()

            self.assertTrue(dispatcher.dispatch(second_claim))
            self.assertTrue(dispatcher.is_in_flight(second_claim))
            valid_future.set_result(None)
            self.assertFalse(dispatcher.is_in_flight(second_claim))

    def test_dispatcher_shutdown_behavior(self):
        """Shutdown cleans up in-flight work, prevents deadlock, rejects new dispatches, and avoids double-release."""
        dispatcher = AnalysisPipelineDispatcher(max_workers=1, max_outstanding_tasks=2)
        claim1 = uuid.uuid4()
        claim2 = uuid.uuid4()

        with patch.object(dispatcher, "_get_executor_unlocked") as mock_exec_getter:
            mock_executor = MagicMock()
            future1 = Future()
            mock_executor.submit.return_value = future1
            mock_exec_getter.return_value = mock_executor
            dispatcher._executor = mock_executor

            # Dispatch in-flight task
            self.assertTrue(dispatcher.dispatch(claim1))
            self.assertTrue(dispatcher.is_in_flight(claim1))

            # Shutdown dispatcher while task is in flight
            dispatcher.shutdown(wait=False, cancel_futures=True)
            self.assertTrue(dispatcher._shutting_down)
            mock_executor.shutdown.assert_called_once_with(
                wait=False, cancel_futures=True
            )

            # Subsequent dispatch must be rejected (returns False per AI-014 contract)
            self.assertFalse(dispatcher.dispatch(claim2))
            self.assertFalse(dispatcher.is_in_flight(claim2))

            # Resolve in-flight task after shutdown
            future1.set_result(None)
            self.assertFalse(dispatcher.is_in_flight(claim1))
            self.assertEqual(dispatcher.in_flight_count, 0)

            # Verify permit is intact and not double released (can acquire 2 permits, not 3)
            self.assertTrue(dispatcher._semaphore.acquire(blocking=False))
            self.assertTrue(dispatcher._semaphore.acquire(blocking=False))
            self.assertFalse(dispatcher._semaphore.acquire(blocking=False))


# =============================================================================
# 5. End-to-End Pipeline Output Invariance Tests
# =============================================================================


class MockEmbeddingGenerator:
    """Mock embedder avoiding PyTorch / sentence-transformers import."""

    def __init__(self, dim: int = 4):
        self.dim = dim

    def embed(self, text: str):
        import numpy as np

        return np.ones(self.dim, dtype=np.float32)

    def embed_batch(self, texts, batch_size: int = 32):
        import numpy as np

        return np.ones((len(texts), self.dim), dtype=np.float32)


class PipelineOutputInvarianceTests(TestCase):
    """
    Verifies that caching produces 100% bit-for-bit identical credibility scores,
    breakdown, and verdicts compared to uncached execution.
    """

    def setUp(self):
        ModelInferenceService.reset_prediction_cache()
        FactCheckService.reset_response_cache()
        self.user = User.objects.create_user(
            email="invariance_test@example.com",
            password="Password123!",
            full_name="Invariance User",
        )

    def tearDown(self):
        ModelInferenceService.reset_prediction_cache()
        FactCheckService.reset_response_cache()

    def test_pipeline_output_invariance_cached_vs_uncached(self):
        """Full end-to-end pipeline run produces bit-for-bit identical output on cache hit."""
        claim_text = (
            "Water boils at 100 degrees Celsius under standard atmospheric pressure."
        )

        claim_uncached = Claim.objects.create(
            user=self.user,
            text=claim_text,
            status=ClaimStatus.PENDING,
        )
        claim_cached = Claim.objects.create(
            user=self.user,
            text=claim_text,
            status=ClaimStatus.PENDING,
        )

        mock_adapter = MagicMock()
        mock_adapter.artifact_fingerprint = "invariance_fingerprint_v1"
        mock_adapter.model_version = "v1"
        mock_adapter.predict.return_value = ModelOutput(
            prediction=ModelPrediction.CREDIBLE,
            confidence=0.887541,
        )

        mock_http_response = json.dumps(
            {
                "claims": [
                    {
                        "text": claim_text,
                        "claimReview": [
                            {
                                "publisher": {"name": "ScienceDaily"},
                                "url": "https://example.com/physics/water-boiling",
                                "textualRating": "True",
                            }
                        ],
                    }
                ]
            }
        ).encode("utf-8")
        mock_http = MagicMock(return_value=MockHTTPResponse(mock_http_response))

        model_service = ModelInferenceService(adapter=mock_adapter)
        fact_check_service = FactCheckService(api_key="test-key", http_client=mock_http)
        mock_narrative = MagicMock(spec=NarrativeActivityService)
        mock_narrative.evaluate.return_value = NarrativeActivity.empty(
            evaluated_candidates_count=0
        )

        # Run 1: Cache Miss (Uncached)
        pipeline1 = AnalysisPipelineService(
            model_service=model_service,
            fact_check_service=fact_check_service,
            narrative_service=mock_narrative,
        )
        pipeline1.run_pipeline(claim_uncached.id)

        self.assertEqual(mock_adapter.predict.call_count, 1)
        self.assertEqual(mock_http.call_count, 1)

        analysis1 = Analysis.objects.get(claim=claim_uncached)
        self.assertEqual(analysis1.verdict, Verdict.CREDIBLE.value)

        # Run 2: Cache Hit
        pipeline2 = AnalysisPipelineService(
            model_service=model_service,
            fact_check_service=fact_check_service,
            narrative_service=mock_narrative,
        )
        pipeline2.run_pipeline(claim_cached.id)

        # Verify adapter.predict and mock_http were NOT invoked a second time
        self.assertEqual(mock_adapter.predict.call_count, 1)
        self.assertEqual(mock_http.call_count, 1)

        analysis2 = Analysis.objects.get(claim=claim_cached)

        # Bit-for-bit invariant checks
        self.assertEqual(analysis1.credibility_score, analysis2.credibility_score)
        self.assertEqual(analysis1.verdict, analysis2.verdict)
        self.assertEqual(
            analysis1.explainability_json["score_breakdown"],
            analysis2.explainability_json["score_breakdown"],
        )
        self.assertEqual(
            analysis1.explainability_json["reasoning"],
            analysis2.explainability_json["reasoning"],
        )

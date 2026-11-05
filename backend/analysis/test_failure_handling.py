"""
Comprehensive test suite for AI-015 Graceful Failure Handling.
Validates:
- Circuit breaker probe ownership, concurrency, and exception filtering
- Model manifest integrity, full cold SHA-256 verification, and directory cache isolation
- Fact-check zero-based retries, clamped jitter, socket timeout budgeting, and deadline safety margins
- Failure diagnostic durability, atomic CAS rollback, stage validation, and status API schema exposure
"""

import datetime
import email.utils
import hashlib
import json
import socket
import tempfile
import threading
import time
import urllib.error
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

from django.conf import settings
from django.db import connection
from django.test import TestCase, TransactionTestCase, override_settings

from analysis.model_loader.loader import (
    ModelArtifactCorruptedError,
    ModelArtifactNotFoundError,
    ModelLoader,
)
from analysis.models import Analysis, AnalysisFailureDiagnostic, Verdict
from analysis.schemas import AnalysisStatusData, FailureDiagnosticSchema
from analysis.selectors import get_analysis_status_data
from analysis.services.fact_check import (
    FactCheckAuthError,
    FactCheckRateLimitError,
    FactCheckService,
    FactCheckTimeoutError,
)
from analysis.services.inference import (
    BreakerState,
    InferenceServiceError,
    InvalidModelInputError,
    ModelCircuitBreaker,
    ModelCircuitBreakerOpenError,
)
from analysis.services.narrative import NarrativeServiceError
from analysis.services.pipeline import (
    PUBLIC_ERROR_MAPPINGS,
    AnalysisPipelineService,
)
from authentication.models import User
from claims.models import Claim, ClaimStatus


class CircuitBreakerConcurrencyAndProbeTestCase(TestCase):
    """
    Tests the thread-safe ModelCircuitBreaker state machine, single-probe HALF_OPEN semantics,
    and protection of active probes against non-probe or mismatched completions.
    """

    def setUp(self):
        super().setUp()
        self.breaker = ModelCircuitBreaker(ttl_seconds=60.0, transient_ttl_seconds=5.0)

    def test_circuit_breaker_settings_defaults(self):
        """Asserts circuit breaker cooldown defaults match approved 60.0s and 5.0s."""
        self.assertEqual(settings.MODEL_CIRCUIT_BREAKER_TTL_SECONDS, 60.0)
        self.assertEqual(settings.MODEL_CIRCUIT_BREAKER_TRANSIENT_TTL_SECONDS, 5.0)

        default_breaker = ModelCircuitBreaker()
        self.assertEqual(default_breaker._ttl_seconds, 60.0)
        self.assertEqual(default_breaker._transient_ttl_seconds, 5.0)

    def test_circuit_breaker_normal_success_does_not_clear_active_half_open_probe(self):
        """
        Worker A starts a request in CLOSED.
        Breaker transitions to OPEN, then enters HALF_OPEN when Worker B acquires a probe.
        Worker A finishes successfully (non-probe, probe_id=None).
        Worker B's probe ownership must remain intact and breaker must stay in HALF_OPEN.
        """
        # 1. Worker A admitted in CLOSED
        admitted_a, probe_a = self.breaker.admit_request()
        self.assertTrue(admitted_a)
        self.assertIsNone(probe_a)
        self.assertEqual(self.breaker.state, BreakerState.CLOSED)

        # 2. An operational error trips breaker to OPEN
        self.breaker.record_failure(RuntimeError("Transient GPU crash"))
        self.assertEqual(self.breaker.state, BreakerState.OPEN)

        # 3. Simulate cooldown expiration
        with self.breaker._lock:
            self.breaker._open_until = time.monotonic() - 1.0

        # 4. Worker B arrives, transitioning breaker to HALF_OPEN and acquiring probe
        admitted_b, probe_b = self.breaker.admit_request()
        self.assertTrue(admitted_b)
        self.assertIsNotNone(probe_b)
        self.assertEqual(self.breaker.state, BreakerState.HALF_OPEN)
        self.assertTrue(self.breaker._probe_in_flight)
        self.assertEqual(self.breaker._current_probe_id, probe_b)

        # 5. Worker A finally finishes with success (non-probe)
        self.breaker.record_success(probe_id=None)

        # Assert: Worker B's active probe is NOT cleared; breaker remains HALF_OPEN
        self.assertEqual(self.breaker.state, BreakerState.HALF_OPEN)
        self.assertTrue(self.breaker._probe_in_flight)
        self.assertEqual(self.breaker._current_probe_id, probe_b)

        # 6. Worker B succeeds with matching probe_id; breaker transitions to CLOSED
        self.breaker.record_success(probe_id=probe_b)
        self.assertEqual(self.breaker.state, BreakerState.CLOSED)
        self.assertFalse(self.breaker._probe_in_flight)
        self.assertIsNone(self.breaker._current_probe_id)

    def test_circuit_breaker_mismatched_probe_id_does_not_close_breaker(self):
        """A stale or mismatched probe token cannot resolve a HALF_OPEN breaker."""
        with self.breaker._lock:
            self.breaker._state = BreakerState.HALF_OPEN
            self.breaker._probe_in_flight = True
            self.breaker._current_probe_id = "probe_valid_123"

        # Stale probe completion
        self.breaker.record_success(probe_id="stale_probe_999")

        self.assertEqual(self.breaker.state, BreakerState.HALF_OPEN)
        self.assertTrue(self.breaker._probe_in_flight)
        self.assertEqual(self.breaker._current_probe_id, "probe_valid_123")

    def test_circuit_breaker_non_probe_failure_does_not_clear_active_half_open_probe(
        self,
    ):
        """A non-probe failure cannot clear or invalidate an active HALF_OPEN probe."""
        with self.breaker._lock:
            self.breaker._state = BreakerState.HALF_OPEN
            self.breaker._probe_in_flight = True
            self.breaker._current_probe_id = "probe_valid_123"

        # Non-probe failure arrives
        self.breaker.record_failure(RuntimeError("Old worker failure"), probe_id=None)

        self.assertEqual(self.breaker.state, BreakerState.HALF_OPEN)
        self.assertTrue(self.breaker._probe_in_flight)
        self.assertEqual(self.breaker._current_probe_id, "probe_valid_123")

    def test_circuit_breaker_probe_failure_reopens_breaker(self):
        """Active probe failure transitions breaker back to OPEN with updated cooldown."""
        with self.breaker._lock:
            self.breaker._state = BreakerState.HALF_OPEN
            self.breaker._probe_in_flight = True
            self.breaker._current_probe_id = "probe_valid_123"

        self.breaker.record_failure(
            ModelArtifactCorruptedError("Corrupt weights"), probe_id="probe_valid_123"
        )

        self.assertEqual(self.breaker.state, BreakerState.OPEN)
        self.assertFalse(self.breaker._probe_in_flight)
        self.assertIsNone(self.breaker._current_probe_id)
        self.assertGreater(self.breaker._open_until, time.monotonic())

    def test_circuit_breaker_ignores_client_validation_errors(self):
        """Client-side errors (InvalidModelInputError, TypeError) must never trip the breaker."""
        self.assertEqual(self.breaker.state, BreakerState.CLOSED)
        self.breaker.record_failure(InvalidModelInputError("Input cannot be empty"))
        self.assertEqual(self.breaker.state, BreakerState.CLOSED)
        self.breaker.record_failure(TypeError("Input must be string"))
        self.assertEqual(self.breaker.state, BreakerState.CLOSED)


class ArtifactManifestAndCacheIsolationTestCase(TestCase):
    """
    Tests manifest validation, full cold-load SHA-256 verification, environment gating,
    and canonical directory cache isolation.
    """

    def setUp(self):
        super().setUp()
        ModelLoader.reset_cache()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.artifact_path = Path(self.temp_dir.name)

    def tearDown(self):
        ModelLoader.reset_cache()
        self.temp_dir.cleanup()
        super().tearDown()

    def _write_valid_artifacts(self, path: Path) -> dict:
        cfg = path / "config.json"
        tok = path / "tokenizer.json"
        tok_cfg = path / "tokenizer_config.json"
        weights = path / "model.safetensors"

        cfg_content = json.dumps(
            {
                "model_type": "deberta-v2",
                "num_labels": 2,
                "id2label": {"0": "CREDIBLE", "1": "MISINFORMATION"},
            }
        ).encode("utf-8")
        tok_content = b'{"version": "1.0", "model": {"type": "BPE"}}'
        tok_cfg_content = json.dumps(
            {"tokenizer_class": "DebertaV2TokenizerFast"}
        ).encode("utf-8")
        weights_content = b"DUMMY_SAFETENSORS_WEIGHTS_BYTES_12345678"

        cfg.write_bytes(cfg_content)
        tok.write_bytes(tok_content)
        tok_cfg.write_bytes(tok_cfg_content)
        weights.write_bytes(weights_content)

        manifest = {
            "release_id": f"rel_{uuid.uuid4().hex[:8]}",
            "model_version": "v1",
            "files": {
                "config.json": {
                    "sha256": hashlib.sha256(cfg_content).hexdigest(),
                    "size": len(cfg_content),
                },
                "tokenizer.json": {
                    "sha256": hashlib.sha256(tok_content).hexdigest(),
                    "size": len(tok_content),
                },
                "model.safetensors": {
                    "sha256": hashlib.sha256(weights_content).hexdigest(),
                    "size": len(weights_content),
                },
            },
        }
        (path / "model_manifest.json").write_text(
            json.dumps(manifest), encoding="utf-8"
        )
        return manifest

    def test_manifest_full_sha256_verification_detects_corrupted_safetensors_on_cold_load(
        self,
    ):
        """Tampered model.safetensors must be rejected on cold load with ModelArtifactCorruptedError."""
        manifest = self._write_valid_artifacts(self.artifact_path)
        loader = ModelLoader(artifact_path=self.artifact_path, model_version="v1")

        # Tamper weights on disk preserving the exact file size so SHA-256 mismatch is verified
        orig_size = manifest["files"]["model.safetensors"]["size"]
        (self.artifact_path / "model.safetensors").write_bytes(b"X" * orig_size)

        with self.assertRaises(ModelArtifactCorruptedError) as ctx:
            loader.validate_and_read_manifest(
                self.artifact_path, verify_weights_digest=True
            )
        self.assertIn("SHA-256 digest mismatch", str(ctx.exception))

    @override_settings(
        INFOTRUST_ENV="production", MODEL_ALLOW_UNMANIFESTED_ARTIFACTS=True
    )
    def test_missing_manifest_rejected_in_production_environment(self):
        """Production environment strictly rejects missing model_manifest.json even if opt-in is True."""
        loader = ModelLoader(artifact_path=self.artifact_path, model_version="v1")
        # Artifacts exist but manifest does not
        (self.artifact_path / "config.json").write_bytes(b"{}")
        (self.artifact_path / "tokenizer.json").write_bytes(b"{}")
        (self.artifact_path / "model.safetensors").write_bytes(b"{}")

        with self.assertRaises(ModelArtifactNotFoundError) as ctx:
            loader.validate_and_read_manifest(
                self.artifact_path, verify_weights_digest=False
            )
        self.assertIn(
            "unmanifested artifacts are disallowed in environment 'production'",
            str(ctx.exception),
        )

    @override_settings(
        INFOTRUST_ENV="development", MODEL_ALLOW_UNMANIFESTED_ARTIFACTS=True
    )
    def test_missing_manifest_allowed_in_dev_when_opted_in(self):
        """Development environment allows missing manifest when explicit opt-in is enabled."""
        (self.artifact_path / "config.json").write_bytes(b"{}")
        (self.artifact_path / "tokenizer.json").write_bytes(b"{}")
        (self.artifact_path / "model.safetensors").write_bytes(b"{}")

        loader = ModelLoader(artifact_path=self.artifact_path, model_version="v1")
        manifest_data, fingerprint = loader.validate_and_read_manifest(
            self.artifact_path, verify_weights_digest=False
        )
        self.assertTrue(manifest_data.get("unmanifested"))
        self.assertIn("unmanifested:v1", fingerprint)

    def test_distinct_artifact_directories_return_distinct_cached_objects(self):
        """Loading from Directory B must not reuse Directory A's cached objects."""
        with (
            tempfile.TemporaryDirectory() as dir_a_str,
            tempfile.TemporaryDirectory() as dir_b_str,
        ):
            dir_a = Path(dir_a_str)
            dir_b = Path(dir_b_str)

            self._write_valid_artifacts(dir_a)
            self._write_valid_artifacts(dir_b)

            loader_a = ModelLoader(artifact_path=dir_a, model_version="v1")
            loader_b = ModelLoader(artifact_path=dir_b, model_version="v1")

            mock_model_a = MagicMock(name="model_a")
            mock_tok_a = MagicMock(name="tok_a")
            mock_model_b = MagicMock(name="model_b")
            mock_tok_b = MagicMock(name="tok_b")

            with (
                patch.object(
                    loader_a,
                    "_load",
                    side_effect=lambda p: setattr(loader_a, "_model", mock_model_a)
                    or setattr(loader_a, "_tokenizer", mock_tok_a),
                ),
                patch.object(
                    loader_b,
                    "_load",
                    side_effect=lambda p: setattr(loader_b, "_model", mock_model_b)
                    or setattr(loader_b, "_tokenizer", mock_tok_b),
                ),
            ):

                mod_a, tok_a = loader_a.get_model_and_tokenizer()
                self.assertIs(mod_a, mock_model_a)
                self.assertEqual(ModelLoader._cached_artifact_dir, str(dir_a.resolve()))

                mod_b, tok_b = loader_b.get_model_and_tokenizer()
                self.assertIs(mod_b, mock_model_b)
                self.assertEqual(ModelLoader._cached_artifact_dir, str(dir_b.resolve()))
                self.assertIsNot(mod_a, mod_b)

    def test_manifest_rejects_non_dict_root(self):
        """Manifest that is not a JSON object (e.g. list) raises ModelArtifactCorruptedError."""
        self._write_valid_artifacts(self.artifact_path)
        (self.artifact_path / "model_manifest.json").write_text(
            json.dumps(["item1", "item2"]), encoding="utf-8"
        )
        loader = ModelLoader(artifact_path=self.artifact_path, model_version="v1")
        with self.assertRaises(ModelArtifactCorruptedError) as ctx:
            loader.validate_and_read_manifest(self.artifact_path)
        self.assertIn("expected JSON object (dict)", str(ctx.exception))

    def test_manifest_rejects_missing_or_non_string_release_id(self):
        """Manifest with missing or boolean/non-string release_id raises ModelArtifactCorruptedError."""
        manifest = self._write_valid_artifacts(self.artifact_path)
        loader = ModelLoader(artifact_path=self.artifact_path, model_version="v1")

        for bad_release_id in [True, False, 123, "", "   ", None]:
            manifest["release_id"] = bad_release_id
            (self.artifact_path / "model_manifest.json").write_text(
                json.dumps(manifest), encoding="utf-8"
            )
            with self.assertRaises(ModelArtifactCorruptedError) as ctx:
                loader.validate_and_read_manifest(self.artifact_path)
            self.assertIn("release_id", str(ctx.exception).lower())

    def test_manifest_rejects_invalid_model_version(self):
        """Manifest with invalid or boolean/non-string model_version raises ModelArtifactCorruptedError."""
        manifest = self._write_valid_artifacts(self.artifact_path)
        loader = ModelLoader(artifact_path=self.artifact_path, model_version="v1")

        for bad_version in [True, 123, None, "v2_mismatch"]:
            manifest["model_version"] = bad_version
            (self.artifact_path / "model_manifest.json").write_text(
                json.dumps(manifest), encoding="utf-8"
            )
            with self.assertRaises(ModelArtifactCorruptedError) as ctx:
                loader.validate_and_read_manifest(self.artifact_path)
            self.assertIn("model_version", str(ctx.exception).lower())

    def test_manifest_rejects_non_dict_files_or_missing_required_entry(self):
        """Manifest with non-dict files or missing required file raises ModelArtifactCorruptedError."""
        manifest = self._write_valid_artifacts(self.artifact_path)
        loader = ModelLoader(artifact_path=self.artifact_path, model_version="v1")

        # Non-dict files
        manifest["files"] = ["config.json", "tokenizer.json"]
        (self.artifact_path / "model_manifest.json").write_text(
            json.dumps(manifest), encoding="utf-8"
        )
        with self.assertRaises(ModelArtifactCorruptedError) as ctx:
            loader.validate_and_read_manifest(self.artifact_path)
        self.assertIn("files", str(ctx.exception).lower())

        # Missing required file entry
        manifest = self._write_valid_artifacts(self.artifact_path)
        del manifest["files"]["tokenizer.json"]
        (self.artifact_path / "model_manifest.json").write_text(
            json.dumps(manifest), encoding="utf-8"
        )
        with self.assertRaises(ModelArtifactCorruptedError) as ctx:
            loader.validate_and_read_manifest(self.artifact_path)
        self.assertIn("missing required file entry", str(ctx.exception).lower())

    def test_manifest_rejects_invalid_sha256_type_or_format(self):
        """Manifest with boolean, int, or malformed sha256 raises ModelArtifactCorruptedError."""
        manifest = self._write_valid_artifacts(self.artifact_path)
        loader = ModelLoader(artifact_path=self.artifact_path, model_version="v1")

        # Non-string / bool
        manifest["files"]["config.json"]["sha256"] = True
        (self.artifact_path / "model_manifest.json").write_text(
            json.dumps(manifest), encoding="utf-8"
        )
        with self.assertRaises(ModelArtifactCorruptedError) as ctx:
            loader.validate_and_read_manifest(self.artifact_path)
        self.assertIn("invalid sha256 type", str(ctx.exception).lower())

        # Invalid length / non-hex
        manifest["files"]["config.json"]["sha256"] = "short_hash_12345"
        (self.artifact_path / "model_manifest.json").write_text(
            json.dumps(manifest), encoding="utf-8"
        )
        with self.assertRaises(ModelArtifactCorruptedError) as ctx:
            loader.validate_and_read_manifest(self.artifact_path)
        self.assertIn("invalid sha256 format", str(ctx.exception).lower())

    def test_manifest_rejects_invalid_size_type_or_value(self):
        """Manifest with boolean, string, or non-positive size raises ModelArtifactCorruptedError."""
        manifest = self._write_valid_artifacts(self.artifact_path)
        loader = ModelLoader(artifact_path=self.artifact_path, model_version="v1")

        for bad_size in [True, "100", 0, -50]:
            manifest["files"]["config.json"]["size"] = bad_size
            (self.artifact_path / "model_manifest.json").write_text(
                json.dumps(manifest), encoding="utf-8"
            )
            with self.assertRaises(ModelArtifactCorruptedError) as ctx:
                loader.validate_and_read_manifest(self.artifact_path)
            self.assertIn("invalid size", str(ctx.exception).lower())


class FactCheckRetryAndDeadlineTestCase(TestCase):
    """
    Tests zero-based retry semantics, bounded clamped jitter, remaining-time socket timeouts,
    and 0.5s network safety margin budgeting.
    """

    def setUp(self):
        super().setUp()
        self.service = FactCheckService(
            api_key="TEST_API_KEY", endpoint="https://factcheck.example.com/v1"
        )

    @override_settings(FACT_CHECK_PER_ATTEMPT_TIMEOUT=3.0)
    def test_fact_check_socket_timeout_clamped_to_remaining_time_without_extension(
        self,
    ):
        """Per-attempt socket timeout must be clamped to remaining budget, never extended to 0.5s."""
        recorded_timeouts = []

        def mock_http(req, timeout):
            recorded_timeouts.append(timeout)
            resp = MagicMock()
            resp.read.return_value = json.dumps({"claims": []}).encode("utf-8")
            resp.__enter__.return_value = resp
            resp.__exit__.return_value = None
            return resp

        self.service._http_client = mock_http

        # Simulate start where deadline is only 0.20s in the future
        with patch("time.monotonic", side_effect=[100.0, 100.0, 100.0, 100.0]):
            with patch.object(settings, "FACT_CHECK_OVERALL_DEADLINE", 0.20):
                self.service.query("Test claim")

        self.assertEqual(len(recorded_timeouts), 1)
        self.assertAlmostEqual(recorded_timeouts[0], 0.20, places=2)

    def test_fact_check_aborts_immediately_when_remaining_budget_is_exhausted(self):
        """When deadline remaining budget is <= 0.0s, query aborts without issuing HTTP request."""
        mock_http = MagicMock()
        self.service._http_client = mock_http

        # Remaining time negative immediately
        with patch("time.monotonic", side_effect=[100.0, 115.0]):
            with self.assertRaises(FactCheckTimeoutError):
                self.service.query("Test claim")

        mock_http.assert_not_called()

    @override_settings(
        FACT_CHECK_BACKOFF_BASE=0.5,
        FACT_CHECK_BACKOFF_FACTOR=2.0,
        FACT_CHECK_BACKOFF_MAX=2.0,
        FACT_CHECK_JITTER_RATIO=0.25,
    )
    def test_fact_check_backoff_clamps_delay_under_maximum_positive_jitter(self):
        """Forces maximum positive jitter (+25%) on attempt index 2; asserts delay is clamped to 2.0s."""
        slept_durations = []

        def mock_sleep(d):
            slept_durations.append(d)

        def mock_fail(req, timeout):
            raise socket.timeout("Timed out")

        self.service._http_client = mock_fail

        # Force uniform jitter to +0.25 (multiplier 1.25)
        # Attempt 0: 0.5 * 2^0 * 1.25 = 0.625s
        # Attempt 1: 0.5 * 2^1 * 1.25 = 1.250s
        with (
            patch("time.sleep", side_effect=mock_sleep),
            patch("random.uniform", return_value=0.25),
            patch(
                "time.monotonic", side_effect=[0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
            ),
        ):
            with self.assertRaises(FactCheckTimeoutError):
                self.service.query("Test claim")

        self.assertEqual(len(slept_durations), 2)
        self.assertAlmostEqual(slept_durations[0], 0.625, places=3)
        self.assertAlmostEqual(slept_durations[1], 1.250, places=3)
        for s in slept_durations:
            self.assertLessEqual(s, 2.0)

    def test_fact_check_deadline_safety_margin_reserves_socket_budget(self):
        """Sleep duration is clamped to (remaining - 0.5) to reserve budget for subsequent socket call."""
        slept_durations = []

        def mock_sleep(d):
            slept_durations.append(d)

        def mock_fail(req, timeout):
            raise socket.timeout("Timed out")

        self.service._http_client = mock_fail

        # On attempt 0: raw delay is 0.5s. But t_remaining is 0.8s -> t_remaining - 0.5 = 0.3s
        # Sleep must be clamped to 0.3s
        with (
            patch("time.sleep", side_effect=mock_sleep),
            patch("random.uniform", return_value=0.0),
            patch("time.monotonic", side_effect=[0.0, 0.0, 9.2, 9.2, 9.2, 20.0]),
        ):
            with self.assertRaises(FactCheckTimeoutError):
                self.service.query("Test claim")

        self.assertTrue(len(slept_durations) >= 1)
        self.assertAlmostEqual(slept_durations[0], 0.3, places=2)

    def test_fact_check_non_retryable_401_fails_fast(self):
        """HTTP 401 Unauthorized fails immediately on attempt 1 without retry."""
        call_count = 0

        def mock_http(req, timeout):
            nonlocal call_count
            call_count += 1
            raise urllib.error.HTTPError(
                "https://factcheck.example.com", 401, "Unauthorized", {}, None
            )

        self.service._http_client = mock_http

        with self.assertRaises(FactCheckAuthError):
            self.service.query("Test claim")

        self.assertEqual(call_count, 1)

    @override_settings(FACT_CHECK_MAX_ATTEMPTS=10)
    def test_fact_check_attempts_cannot_exceed_hard_cap_of_three(self):
        """Even if FACT_CHECK_MAX_ATTEMPTS is configured to 10, total requests are capped at exactly 3."""
        call_count = 0

        def mock_fail(req, timeout):
            nonlocal call_count
            call_count += 1
            raise socket.timeout("Timed out")

        self.service._http_client = mock_fail

        with (
            patch("time.sleep"),
            patch("time.monotonic", side_effect=[0.0] * 30),
        ):
            with self.assertRaises(FactCheckTimeoutError):
                self.service.query("Test claim")

        self.assertEqual(call_count, 3)

    def test_fact_check_429_valid_delta_seconds_retries_and_succeeds(self):
        """HTTP 429 with valid delta-seconds (<= 2s) is retried once and succeeds."""
        call_count = 0
        slept_durations = []

        def mock_sleep(d):
            slept_durations.append(d)

        def mock_http(req, timeout):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                err = urllib.error.HTTPError(
                    "https://factcheck.example.com",
                    429,
                    "Too Many Requests",
                    {"Retry-After": "1"},
                    None,
                )
                raise err
            resp = MagicMock()
            resp.read.return_value = json.dumps({"claims": []}).encode("utf-8")
            resp.__enter__.return_value = resp
            resp.__exit__.return_value = None
            return resp

        self.service._http_client = mock_http

        with patch("time.sleep", side_effect=mock_sleep):
            res = self.service.query("Test claim")

        self.assertEqual(call_count, 2)
        self.assertEqual(slept_durations, [1.0])
        self.assertEqual(len(res.sources), 0)

    def test_fact_check_429_valid_http_date_retries_and_succeeds(self):
        """HTTP 429 with valid HTTP-date in the future (<= 2s) is retried once and succeeds."""
        call_count = 0
        slept_durations = []

        target_time = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(
            seconds=1
        )
        http_date_str = email.utils.format_datetime(target_time)

        def mock_sleep(d):
            slept_durations.append(d)

        def mock_http(req, timeout):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                err = urllib.error.HTTPError(
                    "https://factcheck.example.com",
                    429,
                    "Too Many Requests",
                    {"Retry-After": http_date_str},
                    None,
                )
                raise err
            resp = MagicMock()
            resp.read.return_value = json.dumps({"claims": []}).encode("utf-8")
            resp.__enter__.return_value = resp
            resp.__exit__.return_value = None
            return resp

        self.service._http_client = mock_http

        with patch("time.sleep", side_effect=mock_sleep):
            res = self.service.query("Test claim")

        self.assertEqual(call_count, 2)
        self.assertEqual(len(slept_durations), 1)
        self.assertGreater(slept_durations[0], 0.0)
        self.assertLessEqual(slept_durations[0], 2.0)
        self.assertEqual(len(res.sources), 0)

    def test_fact_check_429_malformed_retry_after_fails_immediately_without_retry(self):
        """HTTP 429 with malformed Retry-After header fails fast without retry or exponential backoff."""
        call_count = 0

        def mock_http(req, timeout):
            nonlocal call_count
            call_count += 1
            raise urllib.error.HTTPError(
                "https://factcheck.example.com",
                429,
                "Too Many Requests",
                {"Retry-After": "not-a-valid-date-or-int"},
                None,
            )

        self.service._http_client = mock_http

        with self.assertRaises(FactCheckRateLimitError):
            self.service.query("Test claim")

        self.assertEqual(call_count, 1)

    def test_fact_check_429_missing_retry_after_fails_immediately_without_retry(self):
        """HTTP 429 with missing Retry-After header fails fast without retry or exponential backoff."""
        call_count = 0

        def mock_http(req, timeout):
            nonlocal call_count
            call_count += 1
            raise urllib.error.HTTPError(
                "https://factcheck.example.com",
                429,
                "Too Many Requests",
                {},
                None,
            )

        self.service._http_client = mock_http

        with self.assertRaises(FactCheckRateLimitError):
            self.service.query("Test claim")

        self.assertEqual(call_count, 1)

    def test_fact_check_429_retry_after_exceeding_2_seconds_fails_immediately(self):
        """HTTP 429 with Retry-After > 2s fails fast without retry."""
        call_count = 0

        def mock_http(req, timeout):
            nonlocal call_count
            call_count += 1
            raise urllib.error.HTTPError(
                "https://factcheck.example.com",
                429,
                "Too Many Requests",
                {"Retry-After": "3"},
                None,
            )

        self.service._http_client = mock_http

        with self.assertRaises(FactCheckRateLimitError):
            self.service.query("Test claim")

        self.assertEqual(call_count, 1)

    def test_fact_check_429_retry_after_exceeding_remaining_deadline_aborts(self):
        """HTTP 429 with Retry-After that exceeds remaining deadline budget aborts with FactCheckTimeoutError."""
        call_count = 0

        def mock_http(req, timeout):
            nonlocal call_count
            call_count += 1
            raise urllib.error.HTTPError(
                "https://factcheck.example.com",
                429,
                "Too Many Requests",
                {"Retry-After": "1"},
                None,
            )

        self.service._http_client = mock_http

        # Remaining deadline is only 1.2s -> 1.2 - 1.0 = 0.2s < 0.5s network margin
        with (
            patch("time.monotonic", side_effect=[0.0, 0.0, 0.0, 0.0]),
            patch.object(settings, "FACT_CHECK_OVERALL_DEADLINE", 1.2),
        ):
            with self.assertRaises(FactCheckTimeoutError):
                self.service.query("Test claim")

        self.assertEqual(call_count, 1)

    def test_fact_check_429_retried_no_more_than_once(self):
        """HTTP 429 is retried at most once; a second consecutive 429 fails immediately."""
        call_count = 0

        def mock_http(req, timeout):
            nonlocal call_count
            call_count += 1
            raise urllib.error.HTTPError(
                "https://factcheck.example.com",
                429,
                "Too Many Requests",
                {"Retry-After": "1"},
                None,
            )

        self.service._http_client = mock_http

        with patch("time.sleep"):
            with self.assertRaises(FactCheckRateLimitError) as ctx:
                self.service.query("Test claim")

        self.assertIn("retry limit reached", str(ctx.exception))
        self.assertEqual(call_count, 2)


class FailureDiagnosticAndPipelineTestCase(TestCase):
    """
    Tests failure diagnostic durability, strict stage validation, error code normalization,
    and API status schema exposure.
    """

    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user(
            email="test@example.com",
            full_name="Test User",
            password="password",
        )
        self.claim = Claim.objects.create(
            user=self.user,
            text="Valid claim text for testing purposes.",
            status=ClaimStatus.PROCESSING,
        )
        self.pipeline = AnalysisPipelineService()

    def test_mark_claim_failed_raises_value_error_on_invalid_stage_before_db_transaction(
        self,
    ):
        """Invalid failure stage raises ValueError before database transaction; Claim status untouched."""
        with self.assertRaises(ValueError) as ctx:
            self.pipeline._mark_claim_failed(
                self.claim.id, failure_stage="INVALID_PIPELINE_STAGE"
            )

        self.assertIn("Must be one of", str(ctx.exception))
        self.claim.refresh_from_db()
        self.assertEqual(self.claim.status, ClaimStatus.PROCESSING)
        self.assertFalse(
            AnalysisFailureDiagnostic.objects.filter(claim=self.claim).exists()
        )

    def test_mark_claim_failed_normalizes_unknown_error_code_to_analysis_failed(self):
        """Unknown error code is normalized to ANALYSIS_FAILED with sanitized message."""
        self.pipeline._mark_claim_failed(
            self.claim.id,
            failure_stage="SYNTHESIS",
            error_code="TOTALLY_UNKNOWN_ERROR_CODE",
        )

        self.claim.refresh_from_db()
        self.assertEqual(self.claim.status, ClaimStatus.FAILED)

        diag = AnalysisFailureDiagnostic.objects.get(claim=self.claim)
        self.assertEqual(diag.error_code, "ANALYSIS_FAILED")
        self.assertEqual(diag.failure_stage, "SYNTHESIS")
        self.assertEqual(
            diag.error_message,
            PUBLIC_ERROR_MAPPINGS["ANALYSIS_FAILED"]["error_message"],
        )
        self.assertFalse(diag.retryable)

    def test_atomic_failure_diagnostic_rollback_on_insertion_error(self):
        """If diagnostic creation fails, the Claim status CAS update rolls back atomically."""
        with patch.object(
            AnalysisFailureDiagnostic.objects,
            "get_or_create",
            side_effect=Exception("Database lock failure"),
        ):
            self.pipeline._mark_claim_failed(
                self.claim.id,
                failure_stage="PREPROCESSING",
                error_code="PREPROCESSING_REJECTED",
            )

        self.claim.refresh_from_db()
        # Must still be in PROCESSING because transaction rolled back
        self.assertEqual(self.claim.status, ClaimStatus.PROCESSING)

    def test_status_endpoint_returns_sanitized_diagnostics_for_failed_claim(self):
        """GET status data includes sanitized error_code, error_message, and retryable for FAILED claims."""
        self.pipeline._mark_claim_failed(
            self.claim.id,
            failure_stage="PREPROCESSING",
            error_code="PREPROCESSING_REJECTED",
        )

        status_data = get_analysis_status_data(self.claim.id, self.user)
        self.assertIsInstance(status_data, AnalysisStatusData)
        self.assertEqual(status_data.status, ClaimStatus.FAILED)
        self.assertEqual(status_data.error_code, "PREPROCESSING_REJECTED")
        self.assertEqual(
            status_data.error_message,
            PUBLIC_ERROR_MAPPINGS["PREPROCESSING_REJECTED"]["error_message"],
        )
        self.assertFalse(status_data.retryable)

    def test_insufficient_evidence_produces_completed_uncertain_analysis_not_failure(
        self,
    ):
        """
        When primary truth signals (Model and Fact Check) fail operationally,
        Hybrid Credibility Engine produces INSUFFICIENT_EVIDENCE -> Verdict UNCERTAIN,
        persisting COMPLETED analysis without failure diagnostic (AI-009 / ADR-006 contract).
        """
        mock_model_service = MagicMock()
        mock_model_service.predict.side_effect = ModelCircuitBreakerOpenError(
            "Breaker is open"
        )

        mock_fact_check_service = MagicMock()
        mock_fact_check_service.query.side_effect = FactCheckTimeoutError(
            "Fact check timed out"
        )

        self.claim.status = ClaimStatus.PENDING
        self.claim.save(update_fields=["status"])

        pipeline = AnalysisPipelineService(
            model_service=mock_model_service,
            fact_check_service=mock_fact_check_service,
        )
        pipeline.run_pipeline(self.claim.id)

        self.claim.refresh_from_db()
        self.assertEqual(self.claim.status, ClaimStatus.COMPLETED)

        analysis = Analysis.objects.get(claim=self.claim)
        self.assertEqual(analysis.verdict, Verdict.UNCERTAIN)
        self.assertIsNone(analysis.credibility_score)
        self.assertFalse(
            AnalysisFailureDiagnostic.objects.filter(claim=self.claim).exists()
        )

    def test_model_operational_failure_produces_completed_analysis(self):
        """When model inference fails operationally, pipeline degrades gracefully and claim completes."""
        mock_model_service = MagicMock()
        mock_model_service.predict.side_effect = InferenceServiceError(
            "Model worker connection dropped"
        )

        self.claim.status = ClaimStatus.PENDING
        self.claim.save(update_fields=["status"])

        pipeline = AnalysisPipelineService(model_service=mock_model_service)
        pipeline.run_pipeline(self.claim.id)

        self.claim.refresh_from_db()
        self.assertEqual(self.claim.status, ClaimStatus.COMPLETED)
        self.assertTrue(Analysis.objects.filter(claim=self.claim).exists())
        self.assertFalse(
            AnalysisFailureDiagnostic.objects.filter(claim=self.claim).exists()
        )

    def test_fact_check_operational_failure_produces_completed_analysis(self):
        """When fact-check query fails operationally, pipeline degrades gracefully and claim completes."""
        mock_fact_check_service = MagicMock()
        mock_fact_check_service.query.side_effect = FactCheckTimeoutError(
            "Fact-check provider timed out"
        )

        self.claim.status = ClaimStatus.PENDING
        self.claim.save(update_fields=["status"])

        pipeline = AnalysisPipelineService(fact_check_service=mock_fact_check_service)
        pipeline.run_pipeline(self.claim.id)

        self.claim.refresh_from_db()
        self.assertEqual(self.claim.status, ClaimStatus.COMPLETED)
        self.assertTrue(Analysis.objects.filter(claim=self.claim).exists())
        self.assertFalse(
            AnalysisFailureDiagnostic.objects.filter(claim=self.claim).exists()
        )

    def test_narrative_operational_failure_produces_completed_analysis(self):
        """When narrative activity fails operationally, pipeline degrades gracefully and claim completes."""
        mock_narrative_service = MagicMock()
        mock_narrative_service.evaluate.side_effect = NarrativeServiceError(
            "Narrative vector store unavailable"
        )

        self.claim.status = ClaimStatus.PENDING
        self.claim.save(update_fields=["status"])

        pipeline = AnalysisPipelineService(narrative_service=mock_narrative_service)
        pipeline.run_pipeline(self.claim.id)

        self.claim.refresh_from_db()
        self.assertEqual(self.claim.status, ClaimStatus.COMPLETED)
        self.assertTrue(Analysis.objects.filter(claim=self.claim).exists())
        self.assertFalse(
            AnalysisFailureDiagnostic.objects.filter(claim=self.claim).exists()
        )

    def test_persistence_reconciliation_confirms_absence_records_service_unavailable(
        self,
    ):
        """
        When _reconcile_ambiguous_persistence() confirms no Analysis record exists,
        it transitions Claim to FAILED with error_code SERVICE_UNAVAILABLE, retryable=True,
        and failure_stage=PERSISTENCE.
        """
        self.claim.status = ClaimStatus.PROCESSING
        self.claim.save(update_fields=["status"])

        self.assertFalse(Analysis.objects.filter(claim=self.claim).exists())

        self.pipeline._reconcile_ambiguous_persistence(self.claim.id)

        self.claim.refresh_from_db()
        self.assertEqual(self.claim.status, ClaimStatus.FAILED)

        diag = AnalysisFailureDiagnostic.objects.get(claim=self.claim)
        self.assertEqual(diag.error_code, "SERVICE_UNAVAILABLE")
        self.assertEqual(
            diag.error_message,
            PUBLIC_ERROR_MAPPINGS["SERVICE_UNAVAILABLE"]["error_message"],
        )
        self.assertTrue(diag.retryable)
        self.assertEqual(diag.failure_stage, "PERSISTENCE")

    def test_public_diagnostic_schema_serialization_excludes_internal_fields(self):
        """
        Public API status response and FailureDiagnosticSchema expose only
        error_code, error_message, and retryable. Internal fields like failure_stage,
        created_at, and stack traces are excluded.
        """
        self.pipeline._mark_claim_failed(
            self.claim.id,
            failure_stage="PERSISTENCE",
            error_code="SERVICE_UNAVAILABLE",
        )

        status_data = get_analysis_status_data(self.claim.id, self.user)
        serialized = status_data.dict()

        expected_keys = {
            "claim_id",
            "status",
            "error_code",
            "error_message",
            "retryable",
        }
        self.assertEqual(set(serialized.keys()), expected_keys)
        self.assertNotIn("failure_stage", serialized)
        self.assertNotIn("created_at", serialized)

        # Also verify FailureDiagnosticSchema directly
        diag_schema = FailureDiagnosticSchema(
            error_code="SERVICE_UNAVAILABLE",
            error_message="Analysis service is temporarily unavailable. Please retry later.",
            retryable=True,
        )
        schema_dict = diag_schema.dict()
        self.assertEqual(
            set(schema_dict.keys()),
            {"error_code", "error_message", "retryable"},
        )
        self.assertNotIn("failure_stage", schema_dict)
        self.assertNotIn("created_at", schema_dict)


class ConcurrentFailureDiagnosticTestCase(TransactionTestCase):
    """
    Validates atomic concurrent execution of _mark_claim_failed on the database level.
    Guarantees that two racing workers cannot overwrite the first diagnostic or leave
    the claim in an inconsistent status.
    """

    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user(
            email="concurrent_test@example.com",
            full_name="Concurrent User",
            password="password",
        )
        self.claim = Claim.objects.create(
            user=self.user,
            text="Concurrent claim text.",
            status=ClaimStatus.PROCESSING,
        )
        self.pipeline = AnalysisPipelineService()

    def test_concurrent_failure_handlers_preserve_first_diagnostic_and_consistent_status(
        self,
    ):
        """
        Two concurrent workers calling _mark_claim_failed on the same claim
        cannot overwrite the first diagnostic or leave the claim in an inconsistent status.
        """
        barrier = threading.Barrier(2)
        errors = []

        def worker(failure_stage, error_code):
            try:
                barrier.wait(timeout=5.0)
                self.pipeline._mark_claim_failed(
                    self.claim.id,
                    failure_stage=failure_stage,
                    error_code=error_code,
                )
            except Exception as e:
                errors.append(e)
            finally:
                connection.close()

        t1 = threading.Thread(
            target=worker, args=("PREPROCESSING", "PREPROCESSING_REJECTED")
        )
        t2 = threading.Thread(target=worker, args=("SYNTHESIS", "ANALYSIS_FAILED"))
        t1.start()
        t2.start()
        t1.join(timeout=5.0)
        t2.join(timeout=5.0)

        self.assertEqual(errors, [])
        self.claim.refresh_from_db()
        self.assertEqual(self.claim.status, ClaimStatus.FAILED)

        diags = list(AnalysisFailureDiagnostic.objects.filter(claim=self.claim))
        self.assertEqual(len(diags), 1)

        diag = diags[0]
        if diag.error_code == "PREPROCESSING_REJECTED":
            # Worker 1 won: verify all fields correspond to Worker 1
            self.assertEqual(diag.failure_stage, "PREPROCESSING")
            self.assertEqual(
                diag.error_message,
                PUBLIC_ERROR_MAPPINGS["PREPROCESSING_REJECTED"]["error_message"],
            )
            self.assertEqual(
                diag.retryable,
                PUBLIC_ERROR_MAPPINGS["PREPROCESSING_REJECTED"]["retryable"],
            )
        elif diag.error_code == "ANALYSIS_FAILED":
            # Worker 2 won: verify all fields correspond to Worker 2
            self.assertEqual(diag.failure_stage, "SYNTHESIS")
            self.assertEqual(
                diag.error_message,
                PUBLIC_ERROR_MAPPINGS["ANALYSIS_FAILED"]["error_message"],
            )
            self.assertEqual(
                diag.retryable,
                PUBLIC_ERROR_MAPPINGS["ANALYSIS_FAILED"]["retryable"],
            )
        else:
            self.fail(f"Unexpected diagnostic error_code: {diag.error_code}")

"""
Unit tests for Narrative Activity Engine (AI-006).
All tests execute deterministically with 100% mocked embeddings and zero external network access.
"""

import math
import tempfile
import uuid
from collections.abc import Sequence
from dataclasses import FrozenInstanceError
from datetime import timedelta
from unittest.mock import MagicMock, patch

import numpy as np
from django.conf import settings
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from analysis.services.narrative import (
    NarrativeActivity,
    NarrativeActivityService,
    NarrativeConfigError,
    NarrativeInferenceError,
    NarrativeInputError,
    NarrativeMatchRecord,
    NarrativeModelUnavailableError,
    SentenceTransformerEmbeddingAdapter,
)
from authentication.models import User
from claims.models import Claim, ClaimStatus
from config.settings.base import _get_bounded_float_env, _get_positive_int_env


class MockEmbeddingGenerator:
    """
    Deterministic mock embedder conforming to EmbeddingGeneratorProtocol.
    Allows injecting explicit text-to-vector mappings or returning normalized hash vectors.
    """

    def __init__(
        self,
        mapping: dict[str, np.ndarray] | None = None,
        dim: int = 4,
    ):
        self.mapping: dict[str, np.ndarray] = mapping or {}
        self.dim: int = dim
        self.calls: list[list[str]] = []

    def embed(self, text: str) -> np.ndarray:
        return self.embed_batch([text])[0]

    def embed_batch(self, texts: Sequence[str], batch_size: int = 32) -> np.ndarray:
        self.calls.append(list(texts))
        vectors = []
        for idx, text in enumerate(texts):
            if text in self.mapping:
                vectors.append(self.mapping[text])
            else:
                # Deterministic unit vector
                vec = np.zeros(self.dim, dtype=np.float32)
                vec[idx % self.dim] = 1.0
                vectors.append(vec)
        return np.array(vectors, dtype=np.float32)


# ---------------------------------------------------------------------------
# 1. Configuration & Input Validation Tests
# ---------------------------------------------------------------------------


class NarrativeConfigAndInputTests(SimpleTestCase):
    """Verifies service initialization, parameter validation, and environment helpers."""

    def test_default_configuration_loaded_from_settings(self):
        service = NarrativeActivityService(embedder=MockEmbeddingGenerator())
        self.assertEqual(
            service.threshold,
            float(getattr(settings, "NARRATIVE_SIMILARITY_THRESHOLD", 0.80)),
        )
        self.assertEqual(
            service.max_candidates,
            int(getattr(settings, "NARRATIVE_MAX_CANDIDATES", 100)),
        )
        self.assertEqual(
            service.medium_activity_min,
            int(getattr(settings, "NARRATIVE_MEDIUM_ACTIVITY_MIN", 2)),
        )
        self.assertEqual(
            service.high_activity_min,
            int(getattr(settings, "NARRATIVE_HIGH_ACTIVITY_MIN", 6)),
        )

    def test_custom_valid_configuration(self):
        service = NarrativeActivityService(
            embedder=MockEmbeddingGenerator(),
            threshold=0.75,
            max_candidates=50,
            medium_activity_min=3,
            high_activity_min=8,
        )
        self.assertEqual(service.threshold, 0.75)
        self.assertEqual(service.max_candidates, 50)
        self.assertEqual(service.medium_activity_min, 3)
        self.assertEqual(service.high_activity_min, 8)

    def test_threshold_boundary_values_allowed(self):
        # 0.0 and 1.0 are valid endpoints of [0.0, 1.0]
        service_zero = NarrativeActivityService(
            embedder=MockEmbeddingGenerator(), threshold=0.0
        )
        self.assertEqual(service_zero.threshold, 0.0)

        service_one = NarrativeActivityService(
            embedder=MockEmbeddingGenerator(), threshold=1.0
        )
        self.assertEqual(service_one.threshold, 1.0)

    def test_threshold_out_of_range_rejected(self):
        invalid_thresholds = [-0.1, 1.01, -1.0, 2.0, float("nan"), float("inf")]
        for val in invalid_thresholds:
            with self.subTest(threshold=val):
                with self.assertRaises(NarrativeConfigError):
                    NarrativeActivityService(
                        embedder=MockEmbeddingGenerator(), threshold=val
                    )

    def test_threshold_non_numeric_or_bool_rejected(self):
        for val in [True, False, "0.80", [0.8], None]:
            if val is None:
                continue  # None uses default settings
            with self.subTest(threshold=val):
                with self.assertRaises(NarrativeConfigError):
                    NarrativeActivityService(
                        embedder=MockEmbeddingGenerator(), threshold=val  # type: ignore
                    )

    def test_max_candidates_validation(self):
        invalid_candidates = [0, -1, -100, True, False, 10.5, "100"]
        for val in invalid_candidates:
            with self.subTest(max_candidates=val):
                with self.assertRaises(NarrativeConfigError):
                    NarrativeActivityService(
                        embedder=MockEmbeddingGenerator(), max_candidates=val  # type: ignore
                    )

    def test_activity_bands_validation(self):
        # Non-positive values
        with self.assertRaises(NarrativeConfigError):
            NarrativeActivityService(
                embedder=MockEmbeddingGenerator(), medium_activity_min=0
            )
        with self.assertRaises(NarrativeConfigError):
            NarrativeActivityService(
                embedder=MockEmbeddingGenerator(), high_activity_min=-1
            )

        # Boolean or float types
        with self.assertRaises(NarrativeConfigError):
            NarrativeActivityService(
                embedder=MockEmbeddingGenerator(), medium_activity_min=True  # type: ignore
            )
        with self.assertRaises(NarrativeConfigError):
            NarrativeActivityService(
                embedder=MockEmbeddingGenerator(), high_activity_min=5.5  # type: ignore
            )

        # high_activity_min <= medium_activity_min
        with self.assertRaises(NarrativeConfigError):
            NarrativeActivityService(
                embedder=MockEmbeddingGenerator(),
                medium_activity_min=5,
                high_activity_min=5,
            )
        with self.assertRaises(NarrativeConfigError):
            NarrativeActivityService(
                embedder=MockEmbeddingGenerator(),
                medium_activity_min=6,
                high_activity_min=3,
            )

    def test_input_validation_empty_or_whitespace(self):
        service = NarrativeActivityService(embedder=MockEmbeddingGenerator())
        with self.assertRaises(NarrativeInputError):
            service.evaluate("")
        with self.assertRaises(NarrativeInputError):
            service.evaluate("   \n\t  ")

    def test_input_validation_non_string_type(self):
        service = NarrativeActivityService(embedder=MockEmbeddingGenerator())
        invalid_inputs = [None, 12345, True, ["claim text"], {"text": "claim"}]
        for inp in invalid_inputs:
            with self.subTest(inp=inp):
                with self.assertRaises(TypeError):
                    service.evaluate(inp)  # type: ignore

    def test_get_bounded_float_env_helper(self):
        # Valid value in range
        with patch.dict("os.environ", {"TEST_VAR": "0.75"}):
            self.assertEqual(_get_bounded_float_env("TEST_VAR", 0.8, 0.0, 1.0), 0.75)

        # Unset env var returns default
        with patch.dict("os.environ", {}, clear=True):
            self.assertEqual(_get_bounded_float_env("TEST_VAR", 0.8, 0.0, 1.0), 0.8)

        # Below min returns default
        with patch.dict("os.environ", {"TEST_VAR": "-0.05"}):
            self.assertEqual(_get_bounded_float_env("TEST_VAR", 0.8, 0.0, 1.0), 0.8)

        # Above max returns default
        with patch.dict("os.environ", {"TEST_VAR": "1.05"}):
            self.assertEqual(_get_bounded_float_env("TEST_VAR", 0.8, 0.0, 1.0), 0.8)

        # Non-numeric string returns default
        with patch.dict("os.environ", {"TEST_VAR": "not-a-number"}):
            self.assertEqual(_get_bounded_float_env("TEST_VAR", 0.8, 0.0, 1.0), 0.8)

        # Non-finite float returns default
        with patch.dict("os.environ", {"TEST_VAR": "nan"}):
            self.assertEqual(_get_bounded_float_env("TEST_VAR", 0.8, 0.0, 1.0), 0.8)

    def test_get_positive_int_env_helper(self):
        # Valid positive int
        with patch.dict("os.environ", {"TEST_INT": "42"}):
            self.assertEqual(_get_positive_int_env("TEST_INT", 10), 42)

        # Unset env var returns default
        with patch.dict("os.environ", {}, clear=True):
            self.assertEqual(_get_positive_int_env("TEST_INT", 10), 10)

        # Zero returns default
        with patch.dict("os.environ", {"TEST_INT": "0"}):
            self.assertEqual(_get_positive_int_env("TEST_INT", 10), 10)

        # Negative returns default
        with patch.dict("os.environ", {"TEST_INT": "-5"}):
            self.assertEqual(_get_positive_int_env("TEST_INT", 10), 10)

        # Non-integer returns default
        with patch.dict("os.environ", {"TEST_INT": "abc"}):
            self.assertEqual(_get_positive_int_env("TEST_INT", 10), 10)


# ---------------------------------------------------------------------------
# 2. Historical Candidate Eligibility & Filtering Tests
# ---------------------------------------------------------------------------


class NarrativeCandidateFilteringTests(TestCase):
    """Verifies strict eligibility filtering: COMPLETED-only, non-deleted, and candidate window limits."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="researcher@infotrust.org",
            password="StrongPassword123!",
            full_name="Researcher User",
        )
        self.now = timezone.now()

    def test_only_completed_status_claims_evaluated(self):
        # Create claims with each status
        c_completed = Claim.objects.create(
            user=self.user,
            text="Completed claim text for testing",
            status=ClaimStatus.COMPLETED,
        )
        c_pending = Claim.objects.create(
            user=self.user,
            text="Pending claim text for testing",
            status=ClaimStatus.PENDING,
        )
        c_processing = Claim.objects.create(
            user=self.user,
            text="Processing claim text for testing",
            status=ClaimStatus.PROCESSING,
        )
        c_failed = Claim.objects.create(
            user=self.user,
            text="Failed claim text for testing",
            status=ClaimStatus.FAILED,
        )

        mock_embedder = MockEmbeddingGenerator()
        service = NarrativeActivityService(embedder=mock_embedder)

        activity = service.evaluate("Test incoming query")

        self.assertEqual(activity.evaluated_candidates_count, 1)
        self.assertEqual(len(mock_embedder.calls), 1)
        encoded_texts = mock_embedder.calls[0]
        # First item is target query, followed by candidates
        self.assertEqual(len(encoded_texts), 2)
        self.assertEqual(encoded_texts[0], "Test incoming query")
        self.assertEqual(encoded_texts[1], c_completed.text)
        self.assertNotIn(c_pending.text, encoded_texts)
        self.assertNotIn(c_processing.text, encoded_texts)
        self.assertNotIn(c_failed.text, encoded_texts)

    def test_soft_deleted_claims_excluded(self):
        Claim.objects.create(
            user=self.user,
            text="Deleted completed claim text",
            status=ClaimStatus.COMPLETED,
            is_deleted=True,
        )
        c_active = Claim.objects.create(
            user=self.user,
            text="Active completed claim text",
            status=ClaimStatus.COMPLETED,
            is_deleted=False,
        )

        mock_embedder = MockEmbeddingGenerator()
        service = NarrativeActivityService(embedder=mock_embedder)

        activity = service.evaluate("Incoming claim")
        self.assertEqual(activity.evaluated_candidates_count, 1)
        encoded_texts = mock_embedder.calls[0]
        self.assertIn(c_active.text, encoded_texts)
        self.assertNotIn("Deleted completed claim text", encoded_texts)

    def test_current_claim_id_excluded_from_comparison(self):
        c1 = Claim.objects.create(
            user=self.user,
            text="Historical completed claim one",
            status=ClaimStatus.COMPLETED,
        )
        c2 = Claim.objects.create(
            user=self.user,
            text="Current claim being evaluated",
            status=ClaimStatus.COMPLETED,
        )

        mock_embedder = MockEmbeddingGenerator()
        service = NarrativeActivityService(embedder=mock_embedder)

        # Excluding current claim c2
        activity = service.evaluate("Incoming claim", current_claim_id=c2.id)
        self.assertEqual(activity.evaluated_candidates_count, 1)
        encoded_texts = mock_embedder.calls[0]
        self.assertIn(c1.text, encoded_texts)
        self.assertNotIn(c2.text, encoded_texts)

    def test_current_claim_id_none_evaluates_all_completed(self):
        c1 = Claim.objects.create(
            user=self.user,
            text="Historical claim number one",
            status=ClaimStatus.COMPLETED,
        )
        c2 = Claim.objects.create(
            user=self.user,
            text="Historical claim number two",
            status=ClaimStatus.COMPLETED,
        )

        mock_embedder = MockEmbeddingGenerator()
        service = NarrativeActivityService(embedder=mock_embedder)

        activity = service.evaluate("Incoming claim", current_claim_id=None)
        self.assertEqual(activity.evaluated_candidates_count, 2)
        encoded_texts = mock_embedder.calls[0]
        self.assertIn(c1.text, encoded_texts)
        self.assertIn(c2.text, encoded_texts)

    def test_empty_candidate_history_returns_empty_activity(self):
        mock_embedder = MockEmbeddingGenerator()
        service = NarrativeActivityService(embedder=mock_embedder)

        activity = service.evaluate("Incoming claim with no history")
        self.assertEqual(activity.similar_claims_count, 0)
        self.assertIsNone(activity.first_seen)
        self.assertIsNone(activity.latest_occurrence)
        self.assertEqual(activity.activity_level, "LOW")
        self.assertEqual(activity.evaluated_candidates_count, 0)
        self.assertEqual(activity.matches, ())
        # Should short-circuit and not call embedding generator
        self.assertEqual(len(mock_embedder.calls), 0)

    def test_candidate_window_limit_and_ordering(self):
        # Create 10 completed claims with sequential timestamps
        created_claims = []
        for i in range(10):
            c = Claim.objects.create(
                user=self.user,
                text=f"Historical claim candidate index {i:02d}",
                status=ClaimStatus.COMPLETED,
            )
            # Use .update() to bypass auto_now_add
            Claim.objects.filter(id=c.id).update(
                submitted_at=self.now - timedelta(minutes=10 - i)
            )
            created_claims.append(c)

        # Set max_candidates = 4
        mock_embedder = MockEmbeddingGenerator()
        service = NarrativeActivityService(embedder=mock_embedder, max_candidates=4)

        activity = service.evaluate("Incoming claim")
        self.assertEqual(activity.evaluated_candidates_count, 4)

        # The evaluated candidates should be the 4 most recent (indices 9, 8, 7, 6)
        encoded_candidates = mock_embedder.calls[0][1:]
        self.assertEqual(len(encoded_candidates), 4)
        expected_candidates = [
            f"Historical claim candidate index {i:02d}" for i in [9, 8, 7, 6]
        ]
        self.assertEqual(encoded_candidates, expected_candidates)

    def test_deterministic_tie_breaking_order(self):
        # Create 3 claims with identical submitted_at
        fixed_time = self.now - timedelta(hours=1)
        c_a = Claim.objects.create(
            user=self.user,
            text="Tie break candidate Alpha",
            status=ClaimStatus.COMPLETED,
        )
        c_b = Claim.objects.create(
            user=self.user,
            text="Tie break candidate Beta",
            status=ClaimStatus.COMPLETED,
        )
        c_c = Claim.objects.create(
            user=self.user,
            text="Tie break candidate Gamma",
            status=ClaimStatus.COMPLETED,
        )

        Claim.objects.filter(id__in=[c_a.id, c_b.id, c_c.id]).update(
            submitted_at=fixed_time
        )

        mock_embedder = MockEmbeddingGenerator()
        service = NarrativeActivityService(embedder=mock_embedder, max_candidates=2)

        service.evaluate("Incoming claim")
        # Ordering is ("-submitted_at", "-id")
        sorted_by_id_desc = sorted([c_a, c_b, c_c], key=lambda c: c.id, reverse=True)
        expected_evaluated_texts = [c.text for c in sorted_by_id_desc[:2]]

        evaluated_texts = mock_embedder.calls[0][1:]
        self.assertEqual(evaluated_texts, expected_evaluated_texts)


# ---------------------------------------------------------------------------
# 3. Similarity, Clamping, Threshold, and Activity Bands Tests
# ---------------------------------------------------------------------------


class NarrativeSimilarityAndActivityTests(TestCase):
    """Verifies vector cosine similarity, explicit clamping, threshold filtering, and activity bands."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="analyst@infotrust.org",
            password="StrongPassword123!",
            full_name="Analyst User",
        )
        self.now = timezone.now()

    def test_similarity_clamping_and_threshold_filtering(self):
        target_text = "Target claim regarding viral transmission"
        c1_text = "Highly similar claim about viral spread"
        c2_text = "Moderately similar claim"
        c3_text = "Unrelated claim about culinary recipes"
        c4_text = "Opposing claim"

        t1 = self.now - timedelta(days=5)
        t2 = self.now - timedelta(days=2)
        t3 = self.now - timedelta(days=1)
        t4 = self.now - timedelta(hours=4)

        c1 = Claim.objects.create(
            user=self.user, text=c1_text, status=ClaimStatus.COMPLETED
        )
        Claim.objects.filter(id=c1.id).update(submitted_at=t1)

        c2 = Claim.objects.create(
            user=self.user, text=c2_text, status=ClaimStatus.COMPLETED
        )
        Claim.objects.filter(id=c2.id).update(submitted_at=t2)

        c3 = Claim.objects.create(
            user=self.user, text=c3_text, status=ClaimStatus.COMPLETED
        )
        Claim.objects.filter(id=c3.id).update(submitted_at=t3)

        c4 = Claim.objects.create(
            user=self.user, text=c4_text, status=ClaimStatus.COMPLETED
        )
        Claim.objects.filter(id=c4.id).update(submitted_at=t4)

        # Inject vectors with known cosine similarities to target [1, 0, 0]:
        # c1: cos = 0.95 (>= 0.80 -> MATCH)
        # c2: cos = 0.82 (>= 0.80 -> MATCH)
        # c3: cos = 0.50 (< 0.80 -> NO MATCH)
        # c4: cos = -0.30 (negative dot product -> clamped to 0.0 -> NO MATCH)
        mapping = {
            target_text: np.array([1.0, 0.0, 0.0], dtype=np.float32),
            c1_text: np.array([0.95, math.sqrt(1 - 0.95**2), 0.0], dtype=np.float32),
            c2_text: np.array([0.82, math.sqrt(1 - 0.82**2), 0.0], dtype=np.float32),
            c3_text: np.array([0.50, math.sqrt(1 - 0.50**2), 0.0], dtype=np.float32),
            c4_text: np.array([-0.30, math.sqrt(1 - 0.30**2), 0.0], dtype=np.float32),
        }

        mock_embedder = MockEmbeddingGenerator(mapping=mapping, dim=3)
        service = NarrativeActivityService(
            embedder=mock_embedder,
            threshold=0.80,
            medium_activity_min=2,
            high_activity_min=5,
        )

        activity = service.evaluate(target_text)

        self.assertEqual(activity.evaluated_candidates_count, 4)
        self.assertEqual(activity.similar_claims_count, 2)
        self.assertEqual(len(activity.matches), 2)
        self.assertEqual(activity.activity_level, "MEDIUM")

        # Verify matched records contain clamped scores and correct claim IDs
        matched_ids = {m.claim_id for m in activity.matches}
        self.assertEqual(matched_ids, {c1.id, c2.id})

        for match in activity.matches:
            self.assertTrue(0.0 <= match.similarity_score <= 1.0)
            self.assertGreaterEqual(match.similarity_score, 0.80)

        # Window-bounded earliest and latest occurrence
        self.assertEqual(activity.first_seen, t1)
        self.assertEqual(activity.latest_occurrence, t2)

    def test_threshold_boundary_zero_matches_all(self):
        target_text = "Target claim"
        c1_text = "Historical claim one"
        c2_text = "Historical claim two"

        Claim.objects.create(user=self.user, text=c1_text, status=ClaimStatus.COMPLETED)
        Claim.objects.create(user=self.user, text=c2_text, status=ClaimStatus.COMPLETED)

        # Orthogonal vectors (cos = 0.0) and opposite vector (cos = -1.0, clamped to 0.0)
        mapping = {
            target_text: np.array([1.0, 0.0], dtype=np.float32),
            c1_text: np.array([0.0, 1.0], dtype=np.float32),  # raw 0.0
            c2_text: np.array(
                [-1.0, 0.0], dtype=np.float32
            ),  # raw -1.0 -> clamped to 0.0
        }

        mock_embedder = MockEmbeddingGenerator(mapping=mapping, dim=2)
        service = NarrativeActivityService(embedder=mock_embedder, threshold=0.0)

        activity = service.evaluate(target_text)
        self.assertEqual(activity.similar_claims_count, 2)
        for m in activity.matches:
            self.assertEqual(m.similarity_score, 0.0)

    def test_threshold_boundary_one_matches_only_parallel(self):
        target_text = "Target claim"
        c1_text = "Parallel claim"
        c2_text = "Almost parallel claim"

        Claim.objects.create(user=self.user, text=c1_text, status=ClaimStatus.COMPLETED)
        Claim.objects.create(user=self.user, text=c2_text, status=ClaimStatus.COMPLETED)

        mapping = {
            target_text: np.array([1.0, 0.0], dtype=np.float32),
            c1_text: np.array([1.0, 0.0], dtype=np.float32),  # cos = 1.0
            c2_text: np.array(
                [0.999, math.sqrt(1 - 0.999**2)], dtype=np.float32
            ),  # cos = 0.999
        }

        mock_embedder = MockEmbeddingGenerator(mapping=mapping, dim=2)
        service = NarrativeActivityService(embedder=mock_embedder, threshold=1.0)

        activity = service.evaluate(target_text)
        self.assertEqual(activity.similar_claims_count, 1)
        self.assertEqual(activity.matches[0].similarity_score, 1.0)

    def test_floating_point_imprecision_clamped_to_one(self):
        target_text = "Target claim"
        c1_text = "Candidate with slight precision overshoot"

        c1 = Claim.objects.create(
            user=self.user, text=c1_text, status=ClaimStatus.COMPLETED
        )

        # Unnormalized vector slightly greater than 1.0 length
        # Service normalizes vectors, but let's test that clamped score never exceeds 1.0
        mapping = {
            target_text: np.array([1.0, 0.0], dtype=np.float32),
            c1_text: np.array([1.0, 0.0], dtype=np.float32),
        }

        mock_embedder = MockEmbeddingGenerator(mapping=mapping, dim=2)
        service = NarrativeActivityService(embedder=mock_embedder, threshold=0.8)

        activity = service.evaluate(target_text)
        self.assertEqual(activity.matches[0].claim_id, c1.id)
        self.assertEqual(activity.matches[0].similarity_score, 1.0)
        self.assertLessEqual(activity.matches[0].similarity_score, 1.0)

    def test_activity_level_bands(self):
        target_text = "Target claim"
        mapping = {target_text: np.array([1.0, 0.0], dtype=np.float32)}

        # Helper to run evaluation with N matching claims
        def eval_with_n_matches(n: int) -> str:
            Claim.objects.all().delete()
            for i in range(n):
                text = f"Claim match number {i}"
                Claim.objects.create(
                    user=self.user, text=text, status=ClaimStatus.COMPLETED
                )
                mapping[text] = np.array([1.0, 0.0], dtype=np.float32)

            mock_embedder = MockEmbeddingGenerator(mapping=mapping, dim=2)
            service = NarrativeActivityService(
                embedder=mock_embedder,
                threshold=0.80,
                medium_activity_min=2,
                high_activity_min=5,
            )
            return service.evaluate(target_text).activity_level

        # 0 matches -> LOW
        self.assertEqual(eval_with_n_matches(0), "LOW")
        # 1 match (< medium_activity_min 2) -> LOW
        self.assertEqual(eval_with_n_matches(1), "LOW")
        # 2 matches (>= 2 and < 5) -> MEDIUM
        self.assertEqual(eval_with_n_matches(2), "MEDIUM")
        # 4 matches (>= 2 and < 5) -> MEDIUM
        self.assertEqual(eval_with_n_matches(4), "MEDIUM")
        # 5 matches (>= high_activity_min 5) -> HIGH
        self.assertEqual(eval_with_n_matches(5), "HIGH")
        # 7 matches (>= 5) -> HIGH
        self.assertEqual(eval_with_n_matches(7), "HIGH")

    def test_service_translates_malformed_embedder_output(self):
        class MalformedEmbedder:
            def embed(self, text: str) -> np.ndarray:
                return np.zeros(10)

            def embed_batch(
                self, texts: Sequence[str], batch_size: int = 32
            ) -> np.ndarray:
                # Returns 1D array instead of 2D matrix
                return np.zeros(len(texts))

        service = NarrativeActivityService(embedder=MalformedEmbedder())  # type: ignore

        Claim.objects.create(
            user=self.user,
            text="Valid completed claim text",
            status=ClaimStatus.COMPLETED,
        )

        with self.assertRaises(NarrativeInferenceError) as ctx:
            service.evaluate("Target claim")
        self.assertIn("unexpected matrix shape", str(ctx.exception))

    def test_embedding_array_containing_nan_raises_inference_error(self):
        target_text = "Target claim text"
        cand_text = "Candidate claim text"
        Claim.objects.create(
            user=self.user,
            text=cand_text,
            status=ClaimStatus.COMPLETED,
        )
        mapping = {
            target_text: np.array([np.nan, 0.0, 0.0], dtype=np.float32),
            cand_text: np.array([1.0, 0.0, 0.0], dtype=np.float32),
        }
        service = NarrativeActivityService(
            embedder=MockEmbeddingGenerator(mapping=mapping, dim=3)
        )
        with self.assertRaises(NarrativeInferenceError) as ctx:
            service.evaluate(target_text)
        self.assertIn("non-finite", str(ctx.exception))

    def test_embedding_array_containing_positive_inf_raises_inference_error(self):
        target_text = "Target claim text"
        cand_text = "Candidate claim text"
        Claim.objects.create(
            user=self.user,
            text=cand_text,
            status=ClaimStatus.COMPLETED,
        )
        mapping = {
            target_text: np.array([1.0, 0.0, 0.0], dtype=np.float32),
            cand_text: np.array([np.inf, 0.0, 0.0], dtype=np.float32),
        }
        service = NarrativeActivityService(
            embedder=MockEmbeddingGenerator(mapping=mapping, dim=3)
        )
        with self.assertRaises(NarrativeInferenceError) as ctx:
            service.evaluate(target_text)
        self.assertIn("non-finite", str(ctx.exception))

    def test_embedding_array_containing_negative_inf_raises_inference_error(self):
        target_text = "Target claim text"
        cand_text = "Candidate claim text"
        Claim.objects.create(
            user=self.user,
            text=cand_text,
            status=ClaimStatus.COMPLETED,
        )
        mapping = {
            target_text: np.array([1.0, 0.0, 0.0], dtype=np.float32),
            cand_text: np.array([-np.inf, 0.0, 0.0], dtype=np.float32),
        }
        service = NarrativeActivityService(
            embedder=MockEmbeddingGenerator(mapping=mapping, dim=3)
        )
        with self.assertRaises(NarrativeInferenceError) as ctx:
            service.evaluate(target_text)
        self.assertIn("non-finite", str(ctx.exception))

    def test_non_finite_raw_similarity_result_raises_inference_error(self):
        target_text = "Target claim text"
        cand_text = "Candidate claim text"
        Claim.objects.create(
            user=self.user,
            text=cand_text,
            status=ClaimStatus.COMPLETED,
        )
        mapping = {
            target_text: np.array([1.0, 0.0, 0.0], dtype=np.float32),
            cand_text: np.array([1.0, 0.0, 0.0], dtype=np.float32),
        }
        service = NarrativeActivityService(
            embedder=MockEmbeddingGenerator(mapping=mapping, dim=3)
        )
        with patch(
            "analysis.services.narrative.np.dot",
            return_value=np.array([float("nan")]),
        ):
            with self.assertRaises(NarrativeInferenceError) as ctx:
                service.evaluate(target_text)
            self.assertIn(
                "Calculated similarity score is non-finite.", str(ctx.exception)
            )

        with patch(
            "analysis.services.narrative.np.dot",
            return_value=np.array([float("inf")]),
        ):
            with self.assertRaises(NarrativeInferenceError) as ctx:
                service.evaluate(target_text)
            self.assertIn(
                "Calculated similarity score is non-finite.", str(ctx.exception)
            )


# ---------------------------------------------------------------------------
# 4. Privacy, Dataclass Immutability, and Serialization Tests
# ---------------------------------------------------------------------------


class NarrativePrivacyAndSerializationTests(SimpleTestCase):
    """Verifies that match records and domain entities satisfy privacy and immutability contracts."""

    def test_match_record_privacy_and_structure(self):
        claim_id = uuid.uuid4()
        submitted_at = timezone.now()
        record = NarrativeMatchRecord(
            claim_id=claim_id,
            similarity_score=0.92,
            submitted_at=submitted_at,
        )

        # Verify only privacy-preserving fields exist
        self.assertEqual(record.claim_id, claim_id)
        self.assertEqual(record.similarity_score, 0.92)
        self.assertEqual(record.submitted_at, submitted_at)

        self.assertFalse(hasattr(record, "text"))
        self.assertFalse(hasattr(record, "claim_text"))
        self.assertFalse(hasattr(record, "user"))
        self.assertFalse(hasattr(record, "user_id"))
        self.assertFalse(hasattr(record, "snippet"))

        d = record.to_dict()
        self.assertEqual(d["claim_id"], str(claim_id))
        self.assertEqual(d["similarity_score"], 0.92)
        self.assertEqual(d["submitted_at"], submitted_at.isoformat())
        self.assertNotIn("text", d)

    def test_narrative_activity_immutability(self):
        activity = NarrativeActivity.empty()
        with self.assertRaises(FrozenInstanceError):
            activity.similar_claims_count = 5  # type: ignore

        record = NarrativeMatchRecord(
            claim_id=uuid.uuid4(),
            similarity_score=0.9,
            submitted_at=timezone.now(),
        )
        with self.assertRaises(FrozenInstanceError):
            record.similarity_score = 0.5  # type: ignore

    def test_narrative_activity_to_dict_structure(self):
        claim_id = uuid.uuid4()
        t1 = timezone.now() - timedelta(days=2)
        t2 = timezone.now()
        match = NarrativeMatchRecord(
            claim_id=claim_id, similarity_score=0.88, submitted_at=t1
        )

        activity = NarrativeActivity(
            similar_claims_count=1,
            first_seen=t1,
            latest_occurrence=t2,
            activity_level="MEDIUM",
            evaluated_candidates_count=10,
            matches=(match,),
        )

        d = activity.to_dict()
        self.assertEqual(d["similar_claims_count"], 1)
        self.assertEqual(d["first_seen"], t1.isoformat())
        self.assertEqual(d["latest_occurrence"], t2.isoformat())
        self.assertEqual(d["activity_level"], "MEDIUM")
        self.assertEqual(d["evaluated_candidates_count"], 10)
        self.assertEqual(len(d["matches"]), 1)
        self.assertEqual(d["matches"][0]["claim_id"], str(claim_id))


# ---------------------------------------------------------------------------
# 5. Adapter, Local Loading, and Error Translation Tests
# ---------------------------------------------------------------------------


class NarrativeAdapterAndErrorHandlingTests(SimpleTestCase):
    """Verifies SentenceTransformerEmbeddingAdapter isolation and error translation."""

    def test_adapter_missing_directory_raises_unavailable_error(self):
        non_existent_path = "/path/does/not/exist/InfoTrustModels/all-MiniLM-L6-v2"
        adapter = SentenceTransformerEmbeddingAdapter(model_path=non_existent_path)

        with self.assertRaises(NarrativeModelUnavailableError) as ctx:
            adapter.embed("Some text")

        self.assertIn("not found", str(ctx.exception))
        self.assertIn(non_existent_path, str(ctx.exception))

    def test_adapter_missing_dependency_raises_unavailable_error(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            adapter = SentenceTransformerEmbeddingAdapter(model_path=tmp_dir)

            with patch.dict("sys.modules", {"sentence_transformers": None}):
                with self.assertRaises(NarrativeModelUnavailableError) as ctx:
                    adapter.embed("Some text")
                self.assertIn("sentence-transformers", str(ctx.exception))

    def test_adapter_model_load_failure_raises_unavailable_error(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            adapter = SentenceTransformerEmbeddingAdapter(model_path=tmp_dir)

            mock_st_module = MagicMock()
            mock_st_module.SentenceTransformer.side_effect = RuntimeError(
                "Corrupt model weights or format"
            )

            with patch.dict("sys.modules", {"sentence_transformers": mock_st_module}):
                with self.assertRaises(NarrativeModelUnavailableError) as ctx:
                    adapter.embed("Some text")
                self.assertIn(
                    "Failed to load sentence-transformers model", str(ctx.exception)
                )

    def test_adapter_embed_batch_empty_sequence(self):
        adapter = SentenceTransformerEmbeddingAdapter(model_path="/unused/mock/path")
        res = adapter.embed_batch([])
        self.assertEqual(res.shape, (0, 384))
        self.assertEqual(res.dtype, np.float32)

    def test_adapter_inference_failure_raises_inference_error(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            adapter = SentenceTransformerEmbeddingAdapter(model_path=tmp_dir)

            mock_model = MagicMock()
            mock_model.encode.side_effect = RuntimeError("CUDA out of memory")
            mock_st_module = MagicMock()
            mock_st_module.SentenceTransformer.return_value = mock_model

            with patch.dict("sys.modules", {"sentence_transformers": mock_st_module}):
                with self.assertRaises(NarrativeInferenceError) as ctx:
                    adapter.embed("Test inference text")
                self.assertIn("inference failed", str(ctx.exception))

    def test_adapter_non_finite_embeddings_raise_inference_error(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            adapter = SentenceTransformerEmbeddingAdapter(model_path=tmp_dir)

            mock_model = MagicMock()
            mock_model.encode.return_value = np.array(
                [[1.0, np.nan], [0.0, 1.0]], dtype=np.float32
            )
            mock_st_module = MagicMock()
            mock_st_module.SentenceTransformer.return_value = mock_model

            with patch.dict("sys.modules", {"sentence_transformers": mock_st_module}):
                with self.assertRaises(NarrativeInferenceError) as ctx:
                    adapter.embed_batch(["text1", "text2"])
                self.assertIn("non-finite", str(ctx.exception))

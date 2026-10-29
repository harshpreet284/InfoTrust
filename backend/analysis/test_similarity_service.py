"""
Unit tests for Similarity Scoring Service (AI-007).
All tests execute deterministically with 100% offline in-memory calculations.
"""

import uuid
from dataclasses import FrozenInstanceError
from datetime import datetime
from unittest.mock import MagicMock

from django.test import SimpleTestCase

from analysis.services.narrative import NarrativeActivity, NarrativeMatchRecord
from analysis.services.similarity import (
    SimilarityCalculationError,
    SimilarityInputError,
    SimilarityMetrics,
    SimilarityScoringService,
)

# ---------------------------------------------------------------------------
# 1. SimilarityMetrics Dataclass Invariants Tests
# ---------------------------------------------------------------------------


class SimilarityMetricsInvariantsTests(SimpleTestCase):
    """Verifies construction invariants, immutability, properties, and privacy of SimilarityMetrics."""

    def test_valid_construction_and_canonical_types(self):
        metrics = SimilarityMetrics(
            highest_similarity_score=0.95,
            average_similarity_score=0.87,
            related_claims_count=3,
        )
        self.assertEqual(metrics.highest_similarity_score, 0.95)
        self.assertEqual(metrics.average_similarity_score, 0.87)
        self.assertEqual(metrics.related_claims_count, 3)
        self.assertIsInstance(metrics.highest_similarity_score, float)
        self.assertIsInstance(metrics.average_similarity_score, float)
        self.assertIsInstance(metrics.related_claims_count, int)
        self.assertTrue(metrics.has_matches)

    def test_integer_scores_normalized_to_float(self):
        metrics = SimilarityMetrics(
            highest_similarity_score=1,
            average_similarity_score=0,
            related_claims_count=0,
        )
        self.assertEqual(metrics.highest_similarity_score, 1.0)
        self.assertEqual(metrics.average_similarity_score, 0.0)
        self.assertIsInstance(metrics.highest_similarity_score, float)
        self.assertIsInstance(metrics.average_similarity_score, float)

    def test_rejection_of_booleans_for_scores(self):
        # Booleans must not masquerade as numeric scores
        with self.assertRaises(TypeError):
            SimilarityMetrics(
                highest_similarity_score=True,  # type: ignore
                average_similarity_score=0.8,
                related_claims_count=1,
            )
        with self.assertRaises(TypeError):
            SimilarityMetrics(
                highest_similarity_score=0.8,
                average_similarity_score=False,  # type: ignore
                related_claims_count=1,
            )

    def test_rejection_of_non_numeric_types_for_scores(self):
        for invalid_val in ["0.8", None, [0.8], {"score": 0.8}]:
            with self.subTest(val=invalid_val):
                with self.assertRaises(TypeError):
                    SimilarityMetrics(
                        highest_similarity_score=invalid_val,  # type: ignore
                        average_similarity_score=0.5,
                        related_claims_count=1,
                    )
                with self.assertRaises(TypeError):
                    SimilarityMetrics(
                        highest_similarity_score=0.8,
                        average_similarity_score=invalid_val,  # type: ignore
                        related_claims_count=1,
                    )

    def test_rejection_of_non_finite_scores(self):
        for non_finite in [float("nan"), float("inf"), float("-inf")]:
            with self.subTest(val=non_finite):
                with self.assertRaises(SimilarityCalculationError):
                    SimilarityMetrics(
                        highest_similarity_score=non_finite,
                        average_similarity_score=0.5,
                        related_claims_count=1,
                    )
                with self.assertRaises(SimilarityCalculationError):
                    SimilarityMetrics(
                        highest_similarity_score=0.8,
                        average_similarity_score=non_finite,
                        related_claims_count=1,
                    )

    def test_rejection_of_out_of_range_scores(self):
        for out_of_range in [-0.01, 1.01, -1.0, 2.0]:
            with self.subTest(val=out_of_range):
                with self.assertRaises(SimilarityCalculationError):
                    SimilarityMetrics(
                        highest_similarity_score=out_of_range,
                        average_similarity_score=0.5,
                        related_claims_count=1,
                    )
                with self.assertRaises(SimilarityCalculationError):
                    SimilarityMetrics(
                        highest_similarity_score=0.8,
                        average_similarity_score=out_of_range,
                        related_claims_count=1,
                    )

    def test_rejection_of_invalid_related_claims_count(self):
        # Booleans rejected
        with self.assertRaises(TypeError):
            SimilarityMetrics(
                highest_similarity_score=0.8,
                average_similarity_score=0.8,
                related_claims_count=True,  # type: ignore
            )
        # Floats, strings, None rejected
        for invalid_count in [1.5, "1", None, [1]]:
            with self.subTest(count=invalid_count):
                with self.assertRaises(TypeError):
                    SimilarityMetrics(
                        highest_similarity_score=0.8,
                        average_similarity_score=0.8,
                        related_claims_count=invalid_count,  # type: ignore
                    )
        # Negative count rejected
        with self.assertRaises(SimilarityInputError):
            SimilarityMetrics(
                highest_similarity_score=0.8,
                average_similarity_score=0.8,
                related_claims_count=-1,
            )

    def test_immutability_frozen(self):
        metrics = SimilarityMetrics(
            highest_similarity_score=0.9,
            average_similarity_score=0.85,
            related_claims_count=2,
        )
        with self.assertRaises(FrozenInstanceError):
            metrics.highest_similarity_score = 0.5  # type: ignore
        with self.assertRaises(FrozenInstanceError):
            metrics.average_similarity_score = 0.5  # type: ignore
        with self.assertRaises(FrozenInstanceError):
            metrics.related_claims_count = 5  # type: ignore

    def test_empty_factory(self):
        empty_metrics = SimilarityMetrics.empty()
        self.assertEqual(empty_metrics.highest_similarity_score, 0.0)
        self.assertEqual(empty_metrics.average_similarity_score, 0.0)
        self.assertEqual(empty_metrics.related_claims_count, 0)
        self.assertFalse(empty_metrics.has_matches)
        self.assertEqual(empty_metrics.highest_similarity_percentage, 0)
        self.assertEqual(empty_metrics.average_similarity_percentage, 0)

    def test_derived_percentage_properties(self):
        metrics = SimilarityMetrics(
            highest_similarity_score=0.941,
            average_similarity_score=0.875,
            related_claims_count=4,
        )
        self.assertEqual(metrics.highest_similarity_percentage, 94)
        self.assertEqual(metrics.average_similarity_percentage, 88)
        self.assertTrue(metrics.has_matches)

    def test_to_dict_structure(self):
        metrics = SimilarityMetrics(
            highest_similarity_score=0.92,
            average_similarity_score=0.85,
            related_claims_count=2,
        )
        d = metrics.to_dict()
        expected = {
            "highest_similarity_score": 0.92,
            "average_similarity_score": 0.85,
            "related_claims_count": 2,
            "has_matches": True,
            "highest_similarity_percentage": 92,
            "average_similarity_percentage": 85,
        }
        self.assertEqual(d, expected)

    def test_privacy_contract_no_text_or_user_ids(self):
        metrics = SimilarityMetrics.empty()
        for forbidden in [
            "text",
            "claim_text",
            "user",
            "user_id",
            "snippet",
            "claim_id",
        ]:
            self.assertFalse(
                hasattr(metrics, forbidden),
                f"SimilarityMetrics must not expose '{forbidden}' attribute.",
            )


# ---------------------------------------------------------------------------
# 2. SimilarityScoringService - calculate_from_activity Tests
# ---------------------------------------------------------------------------


class SimilarityScoringFromActivityTests(SimpleTestCase):
    """Verifies calculate_from_activity metric aggregation, empty handling, and boundary enforcement."""

    def setUp(self):
        self.service = SimilarityScoringService()
        self.now = datetime.now()

    def test_single_match_metrics(self):
        record = NarrativeMatchRecord(
            claim_id=uuid.uuid4(),
            similarity_score=0.92,
            submitted_at=self.now,
        )
        activity = NarrativeActivity(
            similar_claims_count=1,
            first_seen=self.now,
            latest_occurrence=self.now,
            activity_level="LOW",
            evaluated_candidates_count=10,
            matches=(record,),
        )

        metrics = self.service.calculate_from_activity(activity)

        self.assertEqual(metrics.highest_similarity_score, 0.92)
        self.assertEqual(metrics.average_similarity_score, 0.92)
        self.assertEqual(metrics.related_claims_count, 1)
        self.assertTrue(metrics.has_matches)
        self.assertEqual(metrics.highest_similarity_percentage, 92)
        self.assertEqual(metrics.average_similarity_percentage, 92)

    def test_multiple_distinct_matches(self):
        scores = [0.95, 0.85, 0.82]
        records = tuple(
            NarrativeMatchRecord(
                claim_id=uuid.uuid4(),
                similarity_score=s,
                submitted_at=self.now,
            )
            for s in scores
        )
        activity = NarrativeActivity(
            similar_claims_count=3,
            first_seen=self.now,
            latest_occurrence=self.now,
            activity_level="MEDIUM",
            evaluated_candidates_count=50,
            matches=records,
        )

        metrics = self.service.calculate_from_activity(activity)

        expected_highest = 0.95
        expected_avg = sum(scores) / 3
        self.assertEqual(metrics.highest_similarity_score, expected_highest)
        self.assertAlmostEqual(metrics.average_similarity_score, expected_avg, places=7)
        self.assertEqual(metrics.related_claims_count, 3)
        self.assertTrue(metrics.has_matches)

    def test_identical_match_scores(self):
        records = tuple(
            NarrativeMatchRecord(
                claim_id=uuid.uuid4(),
                similarity_score=0.88,
                submitted_at=self.now,
            )
            for _ in range(4)
        )
        activity = NarrativeActivity(
            similar_claims_count=4,
            first_seen=self.now,
            latest_occurrence=self.now,
            activity_level="MEDIUM",
            evaluated_candidates_count=20,
            matches=records,
        )

        metrics = self.service.calculate_from_activity(activity)

        self.assertEqual(metrics.highest_similarity_score, 0.88)
        self.assertEqual(metrics.average_similarity_score, 0.88)
        self.assertEqual(metrics.related_claims_count, 4)

    def test_boundary_scores_zero_and_one(self):
        r1 = NarrativeMatchRecord(
            claim_id=uuid.uuid4(), similarity_score=0.0, submitted_at=self.now
        )
        r2 = NarrativeMatchRecord(
            claim_id=uuid.uuid4(), similarity_score=1.0, submitted_at=self.now
        )
        activity = NarrativeActivity(
            similar_claims_count=2,
            first_seen=self.now,
            latest_occurrence=self.now,
            activity_level="MEDIUM",
            evaluated_candidates_count=10,
            matches=(r1, r2),
        )

        metrics = self.service.calculate_from_activity(activity)

        self.assertEqual(metrics.highest_similarity_score, 1.0)
        self.assertEqual(metrics.average_similarity_score, 0.5)
        self.assertEqual(metrics.related_claims_count, 2)

    def test_empty_activity_returns_zero_metrics_without_division_by_zero(self):
        activity = NarrativeActivity.empty(evaluated_candidates_count=15)
        metrics = self.service.calculate_from_activity(activity)

        self.assertEqual(metrics.highest_similarity_score, 0.0)
        self.assertEqual(metrics.average_similarity_score, 0.0)
        self.assertEqual(metrics.related_claims_count, 0)
        self.assertFalse(metrics.has_matches)

    def test_invalid_activity_type_raises_type_error(self):
        for invalid_inp in ["not an activity", 123, None, {"matches": ()}]:
            with self.subTest(inp=invalid_inp):
                with self.assertRaises(TypeError):
                    self.service.calculate_from_activity(invalid_inp)  # type: ignore

    def test_malformed_matches_collection_raises_input_error(self):
        # Mocking an object masquerading as NarrativeActivity with invalid matches type
        mock_activity = MagicMock(spec=NarrativeActivity)
        mock_activity.matches = "not-a-sequence"

        with self.assertRaises(SimilarityInputError):
            self.service.calculate_from_activity(mock_activity)

    def test_matches_containing_invalid_items_raises_input_error(self):
        mock_activity = MagicMock(spec=NarrativeActivity)
        mock_activity.matches = ("not a match record",)

        with self.assertRaises(SimilarityInputError):
            self.service.calculate_from_activity(mock_activity)

    def test_match_record_with_boolean_score_raises_type_error(self):
        # Create a mock record with a boolean score
        mock_record = MagicMock(spec=NarrativeMatchRecord)
        mock_record.similarity_score = True
        mock_activity = MagicMock(spec=NarrativeActivity)
        mock_activity.matches = (mock_record,)

        with self.assertRaises(TypeError):
            self.service.calculate_from_activity(mock_activity)

    def test_match_record_with_non_finite_score_raises_calculation_error(self):
        mock_record = MagicMock(spec=NarrativeMatchRecord)
        mock_record.similarity_score = float("nan")
        mock_activity = MagicMock(spec=NarrativeActivity)
        mock_activity.matches = (mock_record,)

        with self.assertRaises(SimilarityCalculationError):
            self.service.calculate_from_activity(mock_activity)

    def test_match_record_with_out_of_range_score_raises_calculation_error(self):
        mock_record = MagicMock(spec=NarrativeMatchRecord)
        mock_record.similarity_score = 1.05
        mock_activity = MagicMock(spec=NarrativeActivity)
        mock_activity.matches = (mock_record,)

        with self.assertRaises(SimilarityCalculationError):
            self.service.calculate_from_activity(mock_activity)


# ---------------------------------------------------------------------------
# 3. SimilarityScoringService - calculate_from_scores Utility Tests
# ---------------------------------------------------------------------------


class SimilarityScoringFromScoresTests(SimpleTestCase):
    """Verifies pure utility calculate_from_scores without narrative engine dependencies."""

    def setUp(self):
        self.service = SimilarityScoringService()

    def test_single_score(self):
        metrics = self.service.calculate_from_scores([0.75])
        self.assertEqual(metrics.highest_similarity_score, 0.75)
        self.assertEqual(metrics.average_similarity_score, 0.75)
        self.assertEqual(metrics.related_claims_count, 1)
        self.assertTrue(metrics.has_matches)

    def test_multiple_scores(self):
        metrics = self.service.calculate_from_scores([0.90, 0.80, 0.70])
        self.assertEqual(metrics.highest_similarity_score, 0.90)
        self.assertAlmostEqual(metrics.average_similarity_score, 0.80, places=7)
        self.assertEqual(metrics.related_claims_count, 3)

    def test_empty_sequence_returns_empty_metrics(self):
        for empty_seq in [[], (), []]:
            with self.subTest(seq=empty_seq):
                metrics = self.service.calculate_from_scores(empty_seq)
                self.assertEqual(metrics.highest_similarity_score, 0.0)
                self.assertEqual(metrics.average_similarity_score, 0.0)
                self.assertEqual(metrics.related_claims_count, 0)
                self.assertFalse(metrics.has_matches)

    def test_invalid_scores_container_type_raises_type_error(self):
        for invalid_seq in [None, "0.8,0.9", b"scores", 12345, {0.8: 1}]:
            with self.subTest(seq=invalid_seq):
                with self.assertRaises(TypeError):
                    self.service.calculate_from_scores(invalid_seq)  # type: ignore

    def test_scores_containing_boolean_raises_type_error(self):
        with self.assertRaises(TypeError):
            self.service.calculate_from_scores([0.8, True])
        with self.assertRaises(TypeError):
            self.service.calculate_from_scores([False, 0.8])

    def test_scores_containing_non_numeric_type_raises_type_error(self):
        with self.assertRaises(TypeError):
            self.service.calculate_from_scores([0.8, "0.9"])
        with self.assertRaises(TypeError):
            self.service.calculate_from_scores([None, 0.5])  # type: ignore

    def test_scores_containing_nan_raises_calculation_error(self):
        with self.assertRaises(SimilarityCalculationError):
            self.service.calculate_from_scores([0.8, float("nan")])

    def test_scores_containing_inf_raises_calculation_error(self):
        with self.assertRaises(SimilarityCalculationError):
            self.service.calculate_from_scores([0.8, float("inf")])
        with self.assertRaises(SimilarityCalculationError):
            self.service.calculate_from_scores([0.8, float("-inf")])

    def test_scores_out_of_range_raises_calculation_error(self):
        with self.assertRaises(SimilarityCalculationError):
            self.service.calculate_from_scores([0.8, 1.01])
        with self.assertRaises(SimilarityCalculationError):
            self.service.calculate_from_scores([-0.01, 0.8])

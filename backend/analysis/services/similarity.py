"""
Similarity Scoring Service (AI-007).
Calculates highest similarity, average similarity, and related claims count
from historical narrative matching records for the InfoTrust Hybrid Credibility Engine.
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from analysis.services.narrative import NarrativeActivity, NarrativeMatchRecord

# ---------------------------------------------------------------------------
# Domain Exceptions
# ---------------------------------------------------------------------------


class SimilarityServiceError(RuntimeError):
    """Base exception for all operational and domain failures in SimilarityScoringService."""

    pass


class SimilarityInputError(SimilarityServiceError, ValueError):
    """Raised when input provided to SimilarityScoringService fails validation."""

    pass


class SimilarityCalculationError(SimilarityServiceError, ValueError):
    """Raised when mathematical aggregation encounters invalid or non-finite values."""

    pass


# ---------------------------------------------------------------------------
# Domain Data Contracts
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SimilarityMetrics:
    """
    Immutable domain output produced strictly by AI-007.
    Encapsulates canonical similarity metrics for the Hybrid Credibility Engine.
    """

    highest_similarity_score: float  # Canonical finite float in [0.0, 1.0]
    average_similarity_score: float  # Canonical finite float in [0.0, 1.0]
    related_claims_count: int  # Non-negative integer (>= 0)

    def __post_init__(self) -> None:
        # Validate highest_similarity_score
        if isinstance(self.highest_similarity_score, bool) or not isinstance(
            self.highest_similarity_score, (int, float)
        ):
            raise TypeError(
                f"highest_similarity_score must be a numeric float, got {type(self.highest_similarity_score).__name__}."
            )
        highest_float = float(self.highest_similarity_score)
        if not math.isfinite(highest_float) or not (0.0 <= highest_float <= 1.0):
            raise SimilarityCalculationError(
                f"highest_similarity_score must be a finite number in range [0.0, 1.0], got {self.highest_similarity_score!r}."
            )

        # Validate average_similarity_score
        if isinstance(self.average_similarity_score, bool) or not isinstance(
            self.average_similarity_score, (int, float)
        ):
            raise TypeError(
                f"average_similarity_score must be a numeric float, got {type(self.average_similarity_score).__name__}."
            )
        average_float = float(self.average_similarity_score)
        if not math.isfinite(average_float) or not (0.0 <= average_float <= 1.0):
            raise SimilarityCalculationError(
                f"average_similarity_score must be a finite number in range [0.0, 1.0], got {self.average_similarity_score!r}."
            )

        # Validate related_claims_count
        if isinstance(self.related_claims_count, bool) or not isinstance(
            self.related_claims_count, int
        ):
            raise TypeError(
                f"related_claims_count must be an integer, got {type(self.related_claims_count).__name__}."
            )
        if self.related_claims_count < 0:
            raise SimilarityInputError(
                f"related_claims_count must be a non-negative integer, got {self.related_claims_count!r}."
            )

        # Ensure canonical types on frozen instance
        object.__setattr__(self, "highest_similarity_score", highest_float)
        object.__setattr__(self, "average_similarity_score", average_float)
        object.__setattr__(self, "related_claims_count", int(self.related_claims_count))

    @property
    def has_matches(self) -> bool:
        """Derived indicator: True if one or more qualifying related claims exist."""
        return self.related_claims_count > 0

    @property
    def highest_similarity_percentage(self) -> int:
        """Display helper only: rounded integer percentage in [0, 100]."""
        return int(round(self.highest_similarity_score * 100))

    @property
    def average_similarity_percentage(self) -> int:
        """Display helper only: rounded integer percentage in [0, 100]."""
        return int(round(self.average_similarity_score * 100))

    def to_dict(self) -> dict[str, Any]:
        """Internal dictionary conversion for domain inspection and logging."""
        return {
            "highest_similarity_score": self.highest_similarity_score,
            "average_similarity_score": self.average_similarity_score,
            "related_claims_count": self.related_claims_count,
            "has_matches": self.has_matches,
            "highest_similarity_percentage": self.highest_similarity_percentage,
            "average_similarity_percentage": self.average_similarity_percentage,
        }

    @classmethod
    def empty(cls) -> "SimilarityMetrics":
        """Factory for canonical zero-valued similarity metrics."""
        return cls(
            highest_similarity_score=0.0,
            average_similarity_score=0.0,
            related_claims_count=0,
        )


# ---------------------------------------------------------------------------
# Similarity Scoring Service
# ---------------------------------------------------------------------------


class SimilarityScoringService:
    """
    Computes summary similarity metrics from historical narrative matching results.
    Provides pure calculations from NarrativeActivity or raw score sequences.
    """

    def calculate_from_activity(self, activity: NarrativeActivity) -> SimilarityMetrics:
        """
        Pure calculation of similarity metrics from a pre-computed NarrativeActivity instance.

        Args:
            activity: Instance of NarrativeActivity produced by AI-006.

        Returns:
            SimilarityMetrics containing highest_similarity_score, average_similarity_score,
            and related_claims_count.

        Raises:
            TypeError: If activity is not an instance of NarrativeActivity.
            SimilarityInputError: If matches is not a valid sequence or contains malformed records.
            SimilarityCalculationError: If any match similarity score is non-finite or out-of-range.
        """
        if not isinstance(activity, NarrativeActivity):
            raise TypeError(
                f"activity must be an instance of NarrativeActivity, got {type(activity).__name__}."
            )

        matches = activity.matches
        if not isinstance(matches, (tuple, list)):
            raise SimilarityInputError(
                "matches must be a tuple or list of NarrativeMatchRecord instances."
            )

        if not matches:
            return SimilarityMetrics.empty()

        scores: list[float] = []
        for m in matches:
            if not isinstance(m, NarrativeMatchRecord):
                raise SimilarityInputError(
                    "All items in matches must be NarrativeMatchRecord instances."
                )

            val = m.similarity_score
            if isinstance(val, bool) or not isinstance(val, (int, float)):
                raise TypeError(
                    f"Similarity score must be numeric, got {type(val).__name__}."
                )

            score_float = float(val)
            if not math.isfinite(score_float) or not (0.0 <= score_float <= 1.0):
                raise SimilarityCalculationError(
                    "Calculated similarity score is non-finite or outside boundary range [0.0, 1.0]."
                )
            scores.append(score_float)

        count = len(scores)
        highest = max(scores)
        average = sum(scores) / count

        # Clamp against floating-point precision drift
        highest_clamped = max(0.0, min(1.0, highest))
        average_clamped = max(0.0, min(1.0, average))

        return SimilarityMetrics(
            highest_similarity_score=highest_clamped,
            average_similarity_score=average_clamped,
            related_claims_count=count,
        )

    def calculate_from_scores(self, scores: Sequence[float]) -> SimilarityMetrics:
        """
        Pure calculation utility: computes similarity metrics directly from a sequence
        of float similarity scores. Does not perform candidate selection, embedding
        generation, or threshold filtering.

        Args:
            scores: Sequence of finite floats within [0.0, 1.0].

        Returns:
            SimilarityMetrics containing highest_similarity_score, average_similarity_score,
            and related_claims_count.

        Raises:
            TypeError: If scores is not a Sequence or contains non-numeric / boolean values.
            SimilarityCalculationError: If any score is non-finite or outside [0.0, 1.0].
        """
        if (
            scores is None
            or isinstance(scores, (str, bytes))
            or not isinstance(scores, Sequence)
        ):
            raise TypeError(
                f"scores must be a sequence of floats, got {type(scores).__name__}."
            )

        if len(scores) == 0:
            return SimilarityMetrics.empty()

        valid_scores: list[float] = []
        for s in scores:
            if isinstance(s, bool) or not isinstance(s, (int, float)):
                raise TypeError(
                    f"All scores must be numeric floats, got {type(s).__name__}."
                )

            val = float(s)
            if not math.isfinite(val) or not (0.0 <= val <= 1.0):
                raise SimilarityCalculationError(
                    "Similarity score must be finite and within boundary range [0.0, 1.0]."
                )
            valid_scores.append(val)

        count = len(valid_scores)
        highest = max(valid_scores)
        average = sum(valid_scores) / count

        return SimilarityMetrics(
            highest_similarity_score=max(0.0, min(1.0, highest)),
            average_similarity_score=max(0.0, min(1.0, average)),
            related_claims_count=count,
        )

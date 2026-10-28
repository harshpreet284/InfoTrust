"""
Narrative Activity Engine module for InfoTrust.
Compares incoming claim text against a bounded window of historical COMPLETED claims,
generates normalized embeddings, calculates pairwise cosine similarities,
and detects recurring narrative patterns and temporal circulation.
"""

import math
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Optional, Protocol

import numpy as np
from django.conf import settings

# ---------------------------------------------------------------------------
# Domain Exceptions
# ---------------------------------------------------------------------------


class NarrativeServiceError(RuntimeError):
    """Base exception for all operational and domain failures in NarrativeActivityService."""

    pass


class NarrativeConfigError(NarrativeServiceError, ValueError):
    """Raised when narrative configuration (thresholds, candidate limits, activity bands) is invalid."""

    pass


class NarrativeInputError(NarrativeServiceError, ValueError):
    """Raised when input claim query fails validation (empty or whitespace-only)."""

    pass


class NarrativeModelUnavailableError(NarrativeServiceError):
    """Raised when sentence-transformers or local model weights cannot be loaded."""

    pass


class NarrativeInferenceError(NarrativeServiceError):
    """Raised when tensor generation, batching, or similarity calculation fails."""

    pass


# ---------------------------------------------------------------------------
# Data Contracts
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class NarrativeMatchRecord:
    """
    Internal record of an individual matching historical claim.
    Stores the explicitly clamped similarity score in [0.0, 1.0].
    Strictly omits raw claim text, snippets, and user identifiers.
    """

    claim_id: uuid.UUID
    similarity_score: float  # Range: strictly [0.0, 1.0]
    submitted_at: datetime

    def to_dict(self) -> dict[str, Any]:
        return {
            "claim_id": str(self.claim_id),
            "similarity_score": self.similarity_score,
            "submitted_at": self.submitted_at.isoformat(),
        }


@dataclass(frozen=True)
class NarrativeActivity:
    """
    Internal domain output produced strictly by AI-006.
    Contains no competing scoring aggregations and no public serialization methods.
    """

    similar_claims_count: int
    first_seen: Optional[datetime]
    latest_occurrence: Optional[datetime]
    activity_level: str  # "LOW", "MEDIUM", "HIGH"
    evaluated_candidates_count: int
    matches: tuple[NarrativeMatchRecord, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "similar_claims_count": self.similar_claims_count,
            "first_seen": self.first_seen.isoformat() if self.first_seen else None,
            "latest_occurrence": (
                self.latest_occurrence.isoformat() if self.latest_occurrence else None
            ),
            "activity_level": self.activity_level,
            "evaluated_candidates_count": self.evaluated_candidates_count,
            "matches": [m.to_dict() for m in self.matches],
        }

    @classmethod
    def empty(cls, evaluated_candidates_count: int = 0) -> "NarrativeActivity":
        return cls(
            similar_claims_count=0,
            first_seen=None,
            latest_occurrence=None,
            activity_level="LOW",
            evaluated_candidates_count=evaluated_candidates_count,
            matches=(),
        )


# ---------------------------------------------------------------------------
# Embedding Generator Protocol and Concrete Adapter
# ---------------------------------------------------------------------------


class EmbeddingGeneratorProtocol(Protocol):
    """Protocol for dense sentence embedding generation."""

    def embed(self, text: str) -> np.ndarray:
        """Generates a 1D float32 normalized embedding vector for a single text."""
        ...

    def embed_batch(self, texts: Sequence[str], batch_size: int = 32) -> np.ndarray:
        """Generates a 2D float32 normalized embedding matrix for a sequence of texts."""
        ...


class SentenceTransformerEmbeddingAdapter:
    """
    Concrete adapter for generating sentence embeddings using Sentence Transformers.
    Enforces local-only model loading with lazy initialization and vectorized batching.
    """

    def __init__(self, model_path: Optional[str] = None):
        self.model_path = model_path or getattr(
            settings,
            "NARRATIVE_MODEL_PATH",
            str(
                Path(settings.BASE_DIR).parent / "InfoTrustModels" / "all-MiniLM-L6-v2"
            ),
        )
        self._model = None

    def _get_model(self) -> Any:
        if self._model is None:
            if not self.model_path or not Path(self.model_path).is_dir():
                raise NarrativeModelUnavailableError(
                    f"Narrative model artifact directory not found: {self.model_path}"
                )
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError as err:
                raise NarrativeModelUnavailableError(
                    f"sentence-transformers dependency is not installed: {err}"
                ) from err

            try:
                self._model = SentenceTransformer(
                    str(self.model_path), local_files_only=True
                )
            except Exception as err:
                raise NarrativeModelUnavailableError(
                    f"Failed to load sentence-transformers model from {self.model_path}: {err}"
                ) from err

        return self._model

    def embed(self, text: str) -> np.ndarray:
        batch = self.embed_batch([text])
        if batch.shape[0] != 1:
            raise NarrativeInferenceError(
                f"Expected single embedding, got shape {batch.shape}"
            )
        return batch[0]

    def embed_batch(self, texts: Sequence[str], batch_size: int = 32) -> np.ndarray:
        if not texts:
            return np.empty((0, 384), dtype=np.float32)

        model = self._get_model()
        try:
            # SentenceTransformer.encode manages inference mode and batching internally,
            # returning pre-normalized NumPy float32 arrays directly.
            embeddings = model.encode(
                list(texts),
                batch_size=batch_size,
                show_progress_bar=False,
                convert_to_numpy=True,
                normalize_embeddings=True,
            )
            arr = np.asarray(embeddings, dtype=np.float32)
            if arr.ndim != 2:
                raise NarrativeInferenceError(
                    f"Expected 2D embedding matrix, got shape {arr.shape}"
                )
            if not np.all(np.isfinite(arr)):
                raise NarrativeInferenceError(
                    "Sentence embedding model returned non-finite values."
                )
            return arr
        except Exception as err:
            if isinstance(err, NarrativeServiceError):
                raise
            raise NarrativeInferenceError(
                f"Sentence embedding inference failed: {err}"
            ) from err


# ---------------------------------------------------------------------------
# Narrative Activity Service
# ---------------------------------------------------------------------------


class NarrativeActivityService:
    """
    Coordinates narrative recurrence analysis by comparing an incoming claim
    against eligible historical claims within a bounded candidate window.
    """

    def __init__(
        self,
        embedder: Optional[EmbeddingGeneratorProtocol] = None,
        threshold: Optional[float] = None,
        max_candidates: Optional[int] = None,
        medium_activity_min: Optional[int] = None,
        high_activity_min: Optional[int] = None,
    ):
        """
        Initializes NarrativeActivityService with configurable parameters.

        Args:
            embedder: Optional EmbeddingGeneratorProtocol instance for dependency injection.
            threshold: Cosine similarity threshold in inclusive range [0.0, 1.0].
            max_candidates: Maximum number of recent COMPLETED claims to evaluate.
            medium_activity_min: Minimum matching claims to classify activity as MEDIUM.
            high_activity_min: Minimum matching claims to classify activity as HIGH.
        """
        self._injected_embedder = embedder

        # Threshold validation: inclusive range [0.0, 1.0]
        if threshold is not None:
            if (
                isinstance(threshold, bool)
                or not isinstance(threshold, (int, float))
                or not math.isfinite(threshold)
                or not (0.0 <= float(threshold) <= 1.0)
            ):
                raise NarrativeConfigError(
                    f"threshold must be a finite number in range [0.0, 1.0], got {threshold!r}."
                )
            self._threshold = float(threshold)
        else:
            self._threshold = float(
                getattr(settings, "NARRATIVE_SIMILARITY_THRESHOLD", 0.80)
            )

        # Max candidates validation: positive integer
        if max_candidates is not None:
            if (
                isinstance(max_candidates, bool)
                or not isinstance(max_candidates, int)
                or max_candidates <= 0
            ):
                raise NarrativeConfigError(
                    f"max_candidates must be a positive integer, got {max_candidates!r}."
                )
            self._max_candidates = max_candidates
        else:
            self._max_candidates = int(
                getattr(settings, "NARRATIVE_MAX_CANDIDATES", 100)
            )

        # Activity band thresholds validation
        if medium_activity_min is not None:
            if (
                isinstance(medium_activity_min, bool)
                or not isinstance(medium_activity_min, int)
                or medium_activity_min <= 0
            ):
                raise NarrativeConfigError(
                    f"medium_activity_min must be a positive integer, got {medium_activity_min!r}."
                )
            self._medium_activity_min = medium_activity_min
        else:
            self._medium_activity_min = int(
                getattr(settings, "NARRATIVE_MEDIUM_ACTIVITY_MIN", 2)
            )

        if high_activity_min is not None:
            if (
                isinstance(high_activity_min, bool)
                or not isinstance(high_activity_min, int)
                or high_activity_min <= 0
            ):
                raise NarrativeConfigError(
                    f"high_activity_min must be a positive integer, got {high_activity_min!r}."
                )
            self._high_activity_min = high_activity_min
        else:
            self._high_activity_min = int(
                getattr(settings, "NARRATIVE_HIGH_ACTIVITY_MIN", 6)
            )

        if self._high_activity_min <= self._medium_activity_min:
            raise NarrativeConfigError(
                f"high_activity_min ({self._high_activity_min}) must be strictly greater than "
                f"medium_activity_min ({self._medium_activity_min})."
            )

    @property
    def threshold(self) -> float:
        return self._threshold

    @property
    def max_candidates(self) -> int:
        return self._max_candidates

    @property
    def medium_activity_min(self) -> int:
        return self._medium_activity_min

    @property
    def high_activity_min(self) -> int:
        return self._high_activity_min

    @property
    def embedder(self) -> EmbeddingGeneratorProtocol:
        if self._injected_embedder is not None:
            return self._injected_embedder
        return SentenceTransformerEmbeddingAdapter()

    def evaluate(
        self, claim_text: str, current_claim_id: Optional[uuid.UUID] = None
    ) -> NarrativeActivity:
        """
        Evaluates incoming claim text against recent historical COMPLETED claims.

        Args:
            claim_text: Sanitized claim text string.
            current_claim_id: Optional UUID of the current claim to exclude self-comparison.

        Returns:
            NarrativeActivity containing similar claims count, window-bounded timestamps,
            activity level, and internal match records.

        Raises:
            TypeError: If claim_text is not a string.
            NarrativeInputError: If claim_text is empty or whitespace-only.
            NarrativeModelUnavailableError: If embedding model artifact or dependency is missing.
            NarrativeInferenceError: If embedding generation or tensor operations fail.
        """
        if not isinstance(claim_text, str):
            raise TypeError(
                f"claim_text must be a string, got {type(claim_text).__name__}."
            )

        cleaned_text = claim_text.strip()
        if not cleaned_text:
            raise NarrativeInputError("claim_text cannot be empty or whitespace-only.")

        from claims.models import Claim, ClaimStatus

        # Query eligible historical candidates: strictly COMPLETED, non-deleted, excluding current claim
        qs = Claim.objects.filter(is_deleted=False, status=ClaimStatus.COMPLETED)
        if current_claim_id is not None:
            qs = qs.exclude(id=current_claim_id)

        candidates = list(
            qs.order_by("-submitted_at", "-id").values("id", "text", "submitted_at")[
                : self.max_candidates
            ]
        )

        if not candidates:
            return NarrativeActivity.empty(evaluated_candidates_count=0)

        # Batch encode target claim text and candidate texts together
        all_texts = [cleaned_text] + [c["text"] for c in candidates]
        embeddings = self.embedder.embed_batch(all_texts)

        if (
            not isinstance(embeddings, np.ndarray)
            or embeddings.ndim != 2
            or embeddings.shape[0] != len(all_texts)
        ):
            raise NarrativeInferenceError(
                "Embedding generator returned unexpected matrix shape."
            )

        if not np.all(np.isfinite(embeddings)):
            raise NarrativeInferenceError(
                "Embedding generator returned non-finite embedding values."
            )

        target_vec = embeddings[0]
        cand_matrix = embeddings[1:]

        # Guarantee L2 unit normalization in case a custom mock adapter did not pre-normalize
        target_norm = float(np.linalg.norm(target_vec))
        if target_norm > 0:
            target_vec = target_vec / target_norm

        cand_norms = np.linalg.norm(cand_matrix, axis=1, keepdims=True)
        cand_norms[cand_norms == 0] = 1.0
        cand_matrix = cand_matrix / cand_norms

        # Compute raw pairwise cosine similarities
        raw_scores = np.dot(cand_matrix, target_vec)

        # Match evaluation with explicit score clamping to [0.0, 1.0]
        matches: list[NarrativeMatchRecord] = []
        for cand, raw_score in zip(candidates, raw_scores):
            raw_float = float(raw_score)
            if not math.isfinite(raw_float):
                raise NarrativeInferenceError(
                    "Calculated similarity score is non-finite."
                )
            # Clamping eliminates floating-point precision artifacts (e.g. 1.0000001 or -0.0000002)
            clamped_score = max(0.0, min(1.0, raw_float))
            if clamped_score >= self.threshold:
                matches.append(
                    NarrativeMatchRecord(
                        claim_id=cand["id"],
                        similarity_score=clamped_score,
                        submitted_at=cand["submitted_at"],
                    )
                )

        similar_count = len(matches)
        if similar_count == 0:
            return NarrativeActivity(
                similar_claims_count=0,
                first_seen=None,
                latest_occurrence=None,
                activity_level="LOW",
                evaluated_candidates_count=len(candidates),
                matches=(),
            )

        # Window-bounded earliest and latest occurrence
        first_seen = min(m.submitted_at for m in matches)
        latest_occurrence = max(m.submitted_at for m in matches)

        # Activity level classification based on provisional count bands
        if similar_count >= self.high_activity_min:
            activity_level = "HIGH"
        elif similar_count >= self.medium_activity_min:
            activity_level = "MEDIUM"
        else:
            activity_level = "LOW"

        return NarrativeActivity(
            similar_claims_count=similar_count,
            first_seen=first_seen,
            latest_occurrence=latest_occurrence,
            activity_level=activity_level,
            evaluated_candidates_count=len(candidates),
            matches=tuple(matches),
        )

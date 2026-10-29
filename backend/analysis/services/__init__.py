"""
AI Analysis Services package.
Defines high-level domain services for claim analysis and evaluation.
"""

from analysis.services.fact_check import (
    FactCheckAPIError,
    FactCheckAuthError,
    FactCheckConfigError,
    FactCheckConnectionError,
    FactCheckEvidenceItem,
    FactCheckInputError,
    FactCheckRateLimitError,
    FactCheckResult,
    FactCheckService,
    FactCheckServiceError,
    FactCheckTimeoutError,
)
from analysis.services.inference import (
    InferenceServiceError,
    InvalidModelInputError,
    InvalidModelOutputError,
    ModelInferenceService,
)
from analysis.services.narrative import (
    EmbeddingGeneratorProtocol,
    NarrativeActivity,
    NarrativeActivityService,
    NarrativeConfigError,
    NarrativeInferenceError,
    NarrativeInputError,
    NarrativeMatchRecord,
    NarrativeModelUnavailableError,
    NarrativeServiceError,
    SentenceTransformerEmbeddingAdapter,
)
from analysis.services.rules import (
    RuleConfigError,
    RuleEngineError,
    RuleEngineService,
    RuleInputError,
    RuleValidationResult,
)
from analysis.services.similarity import (
    SimilarityCalculationError,
    SimilarityInputError,
    SimilarityMetrics,
    SimilarityScoringService,
    SimilarityServiceError,
)

__all__ = [
    # Inference Service
    "ModelInferenceService",
    "InferenceServiceError",
    "InvalidModelInputError",
    "InvalidModelOutputError",
    # Fact-Check Service
    "FactCheckService",
    "FactCheckResult",
    "FactCheckEvidenceItem",
    "FactCheckServiceError",
    "FactCheckConfigError",
    "FactCheckInputError",
    "FactCheckAPIError",
    "FactCheckAuthError",
    "FactCheckRateLimitError",
    "FactCheckTimeoutError",
    "FactCheckConnectionError",
    # Narrative Activity Service
    "NarrativeActivityService",
    "NarrativeActivity",
    "NarrativeMatchRecord",
    "EmbeddingGeneratorProtocol",
    "SentenceTransformerEmbeddingAdapter",
    "NarrativeServiceError",
    "NarrativeConfigError",
    "NarrativeInputError",
    "NarrativeModelUnavailableError",
    "NarrativeInferenceError",
    # Similarity Scoring Service
    "SimilarityScoringService",
    "SimilarityMetrics",
    "SimilarityServiceError",
    "SimilarityInputError",
    "SimilarityCalculationError",
    # Rule Engine Service
    "RuleEngineService",
    "RuleValidationResult",
    "RuleEngineError",
    "RuleConfigError",
    "RuleInputError",
]

"""
Unit and integration tests for AI-010 Verdict Generation Service.
Verifies threshold configuration, boundary classification, insufficient evidence handling,
partial failure diagnostics, fact-check conflict preservation, input contracts,
immutability, JSON serialization, and architectural isolation.
"""

import json
from types import MappingProxyType
from unittest.mock import patch

from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase, override_settings

from analysis.models import Verdict
from analysis.services.hybrid import (
    HybridAnalysisStatus,
    HybridCredibilityResult,
    SignalStatus,
)
from analysis.services.verdict import (
    DEFAULT_THRESHOLD_CREDIBLE,
    DEFAULT_THRESHOLD_UNCERTAIN,
    LABEL_CREDIBLE,
    LABEL_MISINFORMATION,
    LABEL_UNCERTAIN,
    VerdictConfigError,
    VerdictInputError,
    VerdictResult,
    VerdictService,
)
from config.settings.base import _get_verdict_threshold_env


def _build_hybrid_result(
    *,
    credibility_score: float | None = 85.0,
    overall_status: HybridAnalysisStatus = HybridAnalysisStatus.COMPLETED,
    confidence_level: str = "HIGH",
    coverage_ratio: float = 0.85,
    failed_components: tuple[str, ...] = (),
    error_details: dict[str, str] | None = None,
    fact_check_conflict: bool = False,
) -> HybridCredibilityResult:
    """Helper creating valid HybridCredibilityResult instances for testing."""
    return HybridCredibilityResult(
        credibility_score=credibility_score,
        overall_status=overall_status,
        confidence_level=confidence_level,
        coverage_ratio=coverage_ratio,
        component_scores={},
        effective_weights={},
        weighted_contributions={},
        signal_statuses={comp: SignalStatus.FAILED for comp in failed_components},
        failed_components=failed_components,
        error_details=error_details or {},
        fact_check_conflict=fact_check_conflict,
        narrative_context=None,
    )


class VerdictConfigurationTests(SimpleTestCase):
    """Verifies threshold validation, constructor arguments, and configuration constraints."""

    def test_default_thresholds_initialize_correctly(self):
        service = VerdictService()
        self.assertEqual(service.credible_threshold, DEFAULT_THRESHOLD_CREDIBLE)
        self.assertEqual(service.uncertain_threshold, DEFAULT_THRESHOLD_UNCERTAIN)
        self.assertEqual(service.credible_threshold, 70.0)
        self.assertEqual(service.uncertain_threshold, 40.0)

    def test_custom_valid_thresholds(self):
        service = VerdictService(credible_threshold=80.0, uncertain_threshold=50.0)
        self.assertEqual(service.credible_threshold, 80.0)
        self.assertEqual(service.uncertain_threshold, 50.0)

    def test_inverted_thresholds_rejected(self):
        with self.assertRaises(VerdictConfigError) as ctx:
            VerdictService(credible_threshold=40.0, uncertain_threshold=70.0)
        self.assertIn("strictly greater than", str(ctx.exception))

    def test_equal_thresholds_rejected(self):
        with self.assertRaises(VerdictConfigError) as ctx:
            VerdictService(credible_threshold=50.0, uncertain_threshold=50.0)
        self.assertIn("strictly greater than", str(ctx.exception))

    def test_out_of_bounds_negative_threshold_rejected(self):
        with self.assertRaises(VerdictConfigError) as ctx:
            VerdictService(credible_threshold=70.0, uncertain_threshold=-5.0)
        self.assertIn("between 0.0 and 100.0", str(ctx.exception))

    def test_out_of_bounds_greater_than_100_rejected(self):
        with self.assertRaises(VerdictConfigError) as ctx:
            VerdictService(credible_threshold=105.0, uncertain_threshold=40.0)
        self.assertIn("between 0.0 and 100.0", str(ctx.exception))

    def test_boolean_thresholds_rejected(self):
        with self.assertRaises(VerdictConfigError) as ctx:
            VerdictService(credible_threshold=True, uncertain_threshold=40.0)  # type: ignore[arg-type]
        self.assertIn("must be a numeric float", str(ctx.exception))

        with self.assertRaises(VerdictConfigError) as ctx:
            VerdictService(credible_threshold=70.0, uncertain_threshold=False)  # type: ignore[arg-type]
        self.assertIn("must be a numeric float", str(ctx.exception))

    def test_non_finite_thresholds_rejected(self):
        with self.assertRaises(VerdictConfigError) as ctx:
            VerdictService(credible_threshold=float("nan"), uncertain_threshold=40.0)
        self.assertIn("must be a finite number", str(ctx.exception))

        with self.assertRaises(VerdictConfigError) as ctx:
            VerdictService(credible_threshold=70.0, uncertain_threshold=float("inf"))
        self.assertIn("must be a finite number", str(ctx.exception))

    def test_invalid_environment_configuration_raises_improperly_configured(
        self,
    ):
        with patch.dict("os.environ", {"VERDICT_THRESHOLD_CREDIBLE": "not_a_number"}):
            with self.assertRaises(ImproperlyConfigured):
                _get_verdict_threshold_env(
                    "VERDICT_THRESHOLD_CREDIBLE", 70.0, 0.0, 100.0
                )

        with patch.dict("os.environ", {"VERDICT_THRESHOLD_CREDIBLE": "150.0"}):
            with self.assertRaises(ImproperlyConfigured):
                _get_verdict_threshold_env(
                    "VERDICT_THRESHOLD_CREDIBLE", 70.0, 0.0, 100.0
                )

    @override_settings(
        VERDICT_THRESHOLD_CREDIBLE=85.0, VERDICT_THRESHOLD_UNCERTAIN=45.0
    )
    def test_thresholds_read_from_django_settings(self):
        service = VerdictService()
        self.assertEqual(service.credible_threshold, 85.0)
        self.assertEqual(service.uncertain_threshold, 45.0)


class VerdictClassificationBoundaryTests(SimpleTestCase):
    """Verifies deterministic classification across score boundaries and custom thresholds."""

    def setUp(self):
        self.service = VerdictService()

    def test_boundary_exact_70_is_credible(self):
        res = _build_hybrid_result(credibility_score=70.0)
        verdict_res = self.service.generate_verdict(res)
        self.assertEqual(verdict_res.verdict, Verdict.CREDIBLE)
        self.assertEqual(verdict_res.label, LABEL_CREDIBLE)
        self.assertEqual(verdict_res.label, "Likely Credible")
        self.assertTrue(verdict_res.is_definitive)
        self.assertEqual(verdict_res.credibility_score, 70.0)
        self.assertIn("meets or exceeds credible threshold", verdict_res.reason)

    def test_boundary_69_9_is_uncertain(self):
        res = _build_hybrid_result(credibility_score=69.9)
        verdict_res = self.service.generate_verdict(res)
        self.assertEqual(verdict_res.verdict, Verdict.UNCERTAIN)
        self.assertEqual(verdict_res.label, LABEL_UNCERTAIN)
        self.assertEqual(verdict_res.label, "Uncertain")
        self.assertFalse(verdict_res.is_definitive)
        self.assertEqual(verdict_res.credibility_score, 69.9)
        self.assertIn("falls in uncertain range", verdict_res.reason)

    def test_boundary_exact_40_is_uncertain(self):
        res = _build_hybrid_result(credibility_score=40.0)
        verdict_res = self.service.generate_verdict(res)
        self.assertEqual(verdict_res.verdict, Verdict.UNCERTAIN)
        self.assertEqual(verdict_res.label, LABEL_UNCERTAIN)
        self.assertFalse(verdict_res.is_definitive)
        self.assertEqual(verdict_res.credibility_score, 40.0)

    def test_boundary_39_9_is_misinformation(self):
        res = _build_hybrid_result(credibility_score=39.9)
        verdict_res = self.service.generate_verdict(res)
        self.assertEqual(verdict_res.verdict, Verdict.MISINFORMATION)
        self.assertEqual(verdict_res.label, LABEL_MISINFORMATION)
        self.assertEqual(verdict_res.label, "Likely Misinformation")
        self.assertTrue(verdict_res.is_definitive)
        self.assertEqual(verdict_res.credibility_score, 39.9)
        self.assertIn("falls below uncertain threshold", verdict_res.reason)

    def test_boundary_extreme_100_is_credible(self):
        res = _build_hybrid_result(credibility_score=100.0)
        verdict_res = self.service.generate_verdict(res)
        self.assertEqual(verdict_res.verdict, Verdict.CREDIBLE)
        self.assertTrue(verdict_res.is_definitive)
        self.assertEqual(verdict_res.credibility_score, 100.0)

    def test_boundary_extreme_0_is_misinformation(self):
        res = _build_hybrid_result(credibility_score=0.0)
        verdict_res = self.service.generate_verdict(res)
        self.assertEqual(verdict_res.verdict, Verdict.MISINFORMATION)
        self.assertTrue(verdict_res.is_definitive)
        self.assertEqual(verdict_res.credibility_score, 0.0)

    def test_architecture_spec_example_score_94_1_is_credible(self):
        res = _build_hybrid_result(credibility_score=94.1)
        verdict_res = self.service.generate_verdict(res)
        self.assertEqual(verdict_res.verdict, Verdict.CREDIBLE)
        self.assertEqual(verdict_res.label, "Likely Credible")
        self.assertEqual(verdict_res.credibility_score, 94.1)
        self.assertTrue(verdict_res.is_definitive)

    def test_custom_thresholds_classification(self):
        service = VerdictService(credible_threshold=80.0, uncertain_threshold=50.0)
        # Score 75.0 is below custom credible (80.0), so falls in Uncertain [50.0, 80.0)
        res1 = _build_hybrid_result(credibility_score=75.0)
        verdict_res1 = service.generate_verdict(res1)
        self.assertEqual(verdict_res1.verdict, Verdict.UNCERTAIN)

        # Score 80.0 is CREDIBLE
        res2 = _build_hybrid_result(credibility_score=80.0)
        verdict_res2 = service.generate_verdict(res2)
        self.assertEqual(verdict_res2.verdict, Verdict.CREDIBLE)

        # Score 49.9 is MISINFORMATION
        res3 = _build_hybrid_result(credibility_score=49.9)
        verdict_res3 = service.generate_verdict(res3)
        self.assertEqual(verdict_res3.verdict, Verdict.MISINFORMATION)

    def test_no_additional_score_rounding_performed(self):
        # A score of 69.94 must not be rounded up to 70.0
        res = _build_hybrid_result(credibility_score=69.94)
        verdict_res = self.service.generate_verdict(res)
        self.assertEqual(verdict_res.verdict, Verdict.UNCERTAIN)
        self.assertEqual(verdict_res.credibility_score, 69.94)


class InsufficientEvidenceHandlingTests(SimpleTestCase):
    """Verifies behavior when AI-009 returns INSUFFICIENT_EVIDENCE with credibility_score=None."""

    def setUp(self):
        self.service = VerdictService()

    def test_insufficient_evidence_yields_uncertain_verdict(self):
        res = _build_hybrid_result(
            credibility_score=None,
            overall_status=HybridAnalysisStatus.INSUFFICIENT_EVIDENCE,
            confidence_level="NONE",
            coverage_ratio=0.10,
        )
        verdict_res = self.service.generate_verdict(res)
        self.assertEqual(verdict_res.verdict, Verdict.UNCERTAIN)
        self.assertEqual(verdict_res.label, "Uncertain")
        self.assertIsNone(verdict_res.credibility_score)
        self.assertEqual(verdict_res.confidence_level, "NONE")
        self.assertFalse(verdict_res.is_definitive)
        self.assertEqual(
            verdict_res.overall_status,
            HybridAnalysisStatus.INSUFFICIENT_EVIDENCE,
        )
        self.assertIn("Insufficient evidence", verdict_res.reason)
        self.assertIn("primary truth signals", verdict_res.reason)

    def test_insufficient_evidence_preserves_failed_components_in_reason(self):
        res = _build_hybrid_result(
            credibility_score=None,
            overall_status=HybridAnalysisStatus.INSUFFICIENT_EVIDENCE,
            confidence_level="NONE",
            failed_components=("model", "fact_check"),
            error_details={"model": "crashed", "fact_check": "503"},
        )
        verdict_res = self.service.generate_verdict(res)
        self.assertEqual(verdict_res.verdict, Verdict.UNCERTAIN)
        self.assertEqual(verdict_res.failed_components, ("fact_check", "model"))
        self.assertIn("Failed components: [fact_check, model]", verdict_res.reason)


class PartialFailureDiagnosticsTests(SimpleTestCase):
    """Verifies that PARTIAL_FAILURE scores are classified and diagnostic traces preserved."""

    def setUp(self):
        self.service = VerdictService()

    def test_partial_failure_with_high_score_yields_credible(self):
        res = _build_hybrid_result(
            credibility_score=92.0,
            overall_status=HybridAnalysisStatus.PARTIAL_FAILURE,
            confidence_level="MEDIUM",
            failed_components=("fact_check",),
            error_details={"fact_check": "Gateway Timeout 504"},
        )
        verdict_res = self.service.generate_verdict(res)
        self.assertEqual(verdict_res.verdict, Verdict.CREDIBLE)
        self.assertEqual(verdict_res.label, "Likely Credible")
        self.assertTrue(verdict_res.is_definitive)
        self.assertEqual(
            verdict_res.overall_status, HybridAnalysisStatus.PARTIAL_FAILURE
        )
        self.assertEqual(verdict_res.failed_components, ("fact_check",))
        self.assertEqual(verdict_res.error_details["fact_check"], "Gateway Timeout 504")
        self.assertIn(
            "Evaluated under partial component failure: [fact_check]",
            verdict_res.reason,
        )

    def test_partial_failure_with_low_score_yields_misinformation(self):
        res = _build_hybrid_result(
            credibility_score=15.0,
            overall_status=HybridAnalysisStatus.PARTIAL_FAILURE,
            confidence_level="MEDIUM",
            failed_components=("rule_engine",),
            error_details={"rule_engine": "Regex timeout"},
        )
        verdict_res = self.service.generate_verdict(res)
        self.assertEqual(verdict_res.verdict, Verdict.MISINFORMATION)
        self.assertEqual(verdict_res.label, "Likely Misinformation")
        self.assertTrue(verdict_res.is_definitive)
        self.assertIn(
            "Evaluated under partial component failure: [rule_engine]",
            verdict_res.reason,
        )


class FactCheckConflictOptionATests(SimpleTestCase):
    """Verifies Option A: Pure threshold mapping with conflict preserved and explained."""

    def setUp(self):
        self.service = VerdictService()

    def test_fact_check_conflict_follows_score_threshold(self):
        # Even with conflicting fact-checks, score >= 70.0 maps to CREDIBLE
        res = _build_hybrid_result(
            credibility_score=78.0,
            confidence_level="LOW",
            fact_check_conflict=True,
        )
        verdict_res = self.service.generate_verdict(res)
        self.assertEqual(verdict_res.verdict, Verdict.CREDIBLE)
        self.assertTrue(verdict_res.is_definitive)
        self.assertTrue(verdict_res.fact_check_conflict)
        self.assertEqual(verdict_res.confidence_level, "LOW")
        self.assertIn("conflicting ratings", verdict_res.reason)
        self.assertIn("confidence downgraded to LOW", verdict_res.reason)

    def test_fact_check_conflict_with_low_score_yields_misinformation(self):
        res = _build_hybrid_result(
            credibility_score=22.0,
            confidence_level="LOW",
            fact_check_conflict=True,
        )
        verdict_res = self.service.generate_verdict(res)
        self.assertEqual(verdict_res.verdict, Verdict.MISINFORMATION)
        self.assertTrue(verdict_res.is_definitive)
        self.assertTrue(verdict_res.fact_check_conflict)
        self.assertIn("conflicting ratings", verdict_res.reason)


class InputContractValidationTests(SimpleTestCase):
    """Verifies defensive rejection of invalid inputs and contradictory status/score pairings."""

    def setUp(self):
        self.service = VerdictService()

    def test_invalid_input_type_rejected(self):
        with self.assertRaises(VerdictInputError):
            self.service.generate_verdict("not_a_result")  # type: ignore[arg-type]

        with self.assertRaises(VerdictInputError):
            self.service.generate_verdict({"score": 85.0})  # type: ignore[arg-type]

        with self.assertRaises(VerdictInputError):
            self.service.generate_verdict(None)  # type: ignore[arg-type]

    def test_contradictory_insufficient_evidence_with_numeric_score_rejected(
        self,
    ):
        # Create an instance that bypassed __post_init__ to test VerdictService's defensive checks
        raw_res = object.__new__(HybridCredibilityResult)
        object.__setattr__(
            raw_res,
            "overall_status",
            HybridAnalysisStatus.INSUFFICIENT_EVIDENCE,
        )
        object.__setattr__(raw_res, "credibility_score", 50.0)
        object.__setattr__(raw_res, "confidence_level", "NONE")
        with self.assertRaises(VerdictInputError) as ctx:
            self.service.generate_verdict(raw_res)
        self.assertIn("must have credibility_score=None", str(ctx.exception))

    def test_contradictory_insufficient_evidence_with_non_none_confidence_rejected(
        self,
    ):
        raw_res = object.__new__(HybridCredibilityResult)
        object.__setattr__(
            raw_res,
            "overall_status",
            HybridAnalysisStatus.INSUFFICIENT_EVIDENCE,
        )
        object.__setattr__(raw_res, "credibility_score", None)
        object.__setattr__(raw_res, "confidence_level", "HIGH")
        with self.assertRaises(VerdictInputError) as ctx:
            self.service.generate_verdict(raw_res)
        self.assertIn("must have confidence_level='NONE'", str(ctx.exception))

    def test_contradictory_completed_status_with_none_score_rejected(self):
        raw_res = object.__new__(HybridCredibilityResult)
        object.__setattr__(raw_res, "overall_status", HybridAnalysisStatus.COMPLETED)
        object.__setattr__(raw_res, "credibility_score", None)
        object.__setattr__(raw_res, "confidence_level", "HIGH")
        with self.assertRaises(VerdictInputError) as ctx:
            self.service.generate_verdict(raw_res)
        self.assertIn("must have a valid numeric", str(ctx.exception))

    def test_contradictory_partial_failure_with_none_score_rejected(self):
        raw_res = object.__new__(HybridCredibilityResult)
        object.__setattr__(
            raw_res, "overall_status", HybridAnalysisStatus.PARTIAL_FAILURE
        )
        object.__setattr__(raw_res, "credibility_score", None)
        object.__setattr__(raw_res, "confidence_level", "LOW")
        with self.assertRaises(VerdictInputError) as ctx:
            self.service.generate_verdict(raw_res)
        self.assertIn("must have a valid numeric", str(ctx.exception))

    def test_out_of_range_score_rejected(self):
        raw_res = object.__new__(HybridCredibilityResult)
        object.__setattr__(raw_res, "overall_status", HybridAnalysisStatus.COMPLETED)
        object.__setattr__(raw_res, "credibility_score", 105.0)
        object.__setattr__(raw_res, "confidence_level", "HIGH")
        with self.assertRaises(VerdictInputError) as ctx:
            self.service.generate_verdict(raw_res)
        self.assertIn("[0.0, 100.0]", str(ctx.exception))

        raw_res_neg = object.__new__(HybridCredibilityResult)
        object.__setattr__(
            raw_res_neg, "overall_status", HybridAnalysisStatus.COMPLETED
        )
        object.__setattr__(raw_res_neg, "credibility_score", -5.0)
        object.__setattr__(raw_res_neg, "confidence_level", "HIGH")
        with self.assertRaises(VerdictInputError) as ctx:
            self.service.generate_verdict(raw_res_neg)
        self.assertIn("[0.0, 100.0]", str(ctx.exception))

    def test_non_finite_score_rejected(self):
        raw_res = object.__new__(HybridCredibilityResult)
        object.__setattr__(raw_res, "overall_status", HybridAnalysisStatus.COMPLETED)
        object.__setattr__(raw_res, "credibility_score", float("nan"))
        object.__setattr__(raw_res, "confidence_level", "HIGH")
        with self.assertRaises(VerdictInputError) as ctx:
            self.service.generate_verdict(raw_res)
        self.assertIn("finite float", str(ctx.exception))


class ImmutabilityAndSerializationTests(SimpleTestCase):
    """Verifies VerdictResult immutability, defensive copies, and plain JSON serialization."""

    def setUp(self):
        self.service = VerdictService()

    def test_verdict_result_is_frozen(self):
        res = _build_hybrid_result(credibility_score=85.0)
        verdict_res = self.service.generate_verdict(res)
        with self.assertRaises(Exception):
            verdict_res.verdict = Verdict.MISINFORMATION  # type: ignore[misc]

    def test_result_mapping_proxies_reject_mutation(self):
        res = _build_hybrid_result(
            credibility_score=85.0,
            failed_components=("model",),
            error_details={"model": "crashed"},
        )
        verdict_res = self.service.generate_verdict(res)
        self.assertIsInstance(verdict_res.thresholds, MappingProxyType)
        self.assertIsInstance(verdict_res.error_details, MappingProxyType)

        with self.assertRaises(TypeError):
            verdict_res.thresholds["credible"] = 99.0  # type: ignore[index]

        with self.assertRaises(TypeError):
            verdict_res.error_details["model"] = "new error"  # type: ignore[index]

    def test_to_dict_is_plain_mutable_and_json_serializable(self):
        res = _build_hybrid_result(
            credibility_score=85.0,
            failed_components=("model",),
            error_details={"model": "crashed"},
        )
        verdict_res = self.service.generate_verdict(res)
        data = verdict_res.to_dict()

        self.assertIsInstance(data, dict)
        self.assertNotIsInstance(data["thresholds"], MappingProxyType)
        self.assertNotIsInstance(data["error_details"], MappingProxyType)

        # Mutating returned dictionary does not mutate result
        data["thresholds"]["credible"] = 0.0
        self.assertEqual(verdict_res.thresholds["credible"], 70.0)

        # JSON serialization succeeds
        json_str = json.dumps(data)
        self.assertIsInstance(json_str, str)
        deserialized = json.loads(json_str)
        self.assertEqual(deserialized["verdict"], "CREDIBLE")
        self.assertEqual(deserialized["label"], "Likely Credible")
        self.assertEqual(deserialized["credibility_score"], 85.0)
        self.assertTrue(deserialized["is_definitive"])

    def test_insufficient_evidence_to_dict_json_serializable(self):
        res = _build_hybrid_result(
            credibility_score=None,
            overall_status=HybridAnalysisStatus.INSUFFICIENT_EVIDENCE,
            confidence_level="NONE",
        )
        verdict_res = self.service.generate_verdict(res)
        data = verdict_res.to_dict()

        json_str = json.dumps(data)
        self.assertIsInstance(json_str, str)
        deserialized = json.loads(json_str)
        self.assertEqual(deserialized["verdict"], "UNCERTAIN")
        self.assertEqual(deserialized["label"], "Uncertain")
        self.assertIsNone(deserialized["credibility_score"])
        self.assertFalse(deserialized["is_definitive"])


class VerdictResultDirectInvariantTests(SimpleTestCase):
    """Verifies internal invariant validation in VerdictResult.__post_init__."""

    def test_invalid_verdict_type_rejected(self):
        with self.assertRaises(TypeError):
            VerdictResult(
                verdict="CREDIBLE",  # type: ignore[arg-type]
                label="Likely Credible",
                credibility_score=85.0,
                confidence_level="HIGH",
                overall_status=HybridAnalysisStatus.COMPLETED,
                is_definitive=True,
                thresholds={"credible": 70.0, "uncertain": 40.0},
                reason="Valid reason",
                failed_components=(),
                error_details={},
                fact_check_conflict=False,
            )

    def test_empty_label_rejected(self):
        with self.assertRaises(TypeError):
            VerdictResult(
                verdict=Verdict.CREDIBLE,
                label="   ",
                credibility_score=85.0,
                confidence_level="HIGH",
                overall_status=HybridAnalysisStatus.COMPLETED,
                is_definitive=True,
                thresholds={"credible": 70.0, "uncertain": 40.0},
                reason="Valid reason",
                failed_components=(),
                error_details={},
                fact_check_conflict=False,
            )

    def test_mismatched_is_definitive_rejected(self):
        with self.assertRaises(ValueError):
            VerdictResult(
                verdict=Verdict.CREDIBLE,
                label="Likely Credible",
                credibility_score=85.0,
                confidence_level="HIGH",
                overall_status=HybridAnalysisStatus.COMPLETED,
                is_definitive=False,  # Mismatch: CREDIBLE must be is_definitive=True
                thresholds={"credible": 70.0, "uncertain": 40.0},
                reason="Valid reason",
                failed_components=(),
                error_details={},
                fact_check_conflict=False,
            )

    def test_credibility_score_none_with_credible_verdict_rejected(self):
        with self.assertRaises(ValueError):
            VerdictResult(
                verdict=Verdict.CREDIBLE,
                label="Likely Credible",
                credibility_score=None,  # Contradiction!
                confidence_level="NONE",
                overall_status=HybridAnalysisStatus.INSUFFICIENT_EVIDENCE,
                is_definitive=True,
                thresholds={"credible": 70.0, "uncertain": 40.0},
                reason="Valid reason",
                failed_components=(),
                error_details={},
                fact_check_conflict=False,
            )

    def test_score_below_credible_threshold_with_credible_verdict_rejected(self):
        with self.assertRaises(ValueError) as ctx:
            VerdictResult(
                verdict=Verdict.CREDIBLE,
                label="Likely Credible",
                credibility_score=10.0,  # Contradicts CREDIBLE
                confidence_level="HIGH",
                overall_status=HybridAnalysisStatus.COMPLETED,
                is_definitive=True,
                thresholds={"credible": 70.0, "uncertain": 40.0},
                reason="Contradictory score test",
                failed_components=(),
                error_details={},
                fact_check_conflict=False,
            )
        self.assertIn("is inconsistent with credibility_score 10.0", str(ctx.exception))

        with self.assertRaises(ValueError) as ctx:
            VerdictResult(
                verdict=Verdict.CREDIBLE,
                label="Likely Credible",
                credibility_score=69.9,  # Just below credible threshold
                confidence_level="HIGH",
                overall_status=HybridAnalysisStatus.COMPLETED,
                is_definitive=True,
                thresholds={"credible": 70.0, "uncertain": 40.0},
                reason="Boundary contradiction",
                failed_components=(),
                error_details={},
                fact_check_conflict=False,
            )
        self.assertIn("Expected Verdict.UNCERTAIN", str(ctx.exception))

    def test_score_above_uncertain_threshold_with_misinformation_verdict_rejected(self):
        with self.assertRaises(ValueError) as ctx:
            VerdictResult(
                verdict=Verdict.MISINFORMATION,
                label="Likely Misinformation",
                credibility_score=40.0,  # At or above uncertain threshold
                confidence_level="MEDIUM",
                overall_status=HybridAnalysisStatus.COMPLETED,
                is_definitive=True,
                thresholds={"credible": 70.0, "uncertain": 40.0},
                reason="Boundary contradiction",
                failed_components=(),
                error_details={},
                fact_check_conflict=False,
            )
        self.assertIn("Expected Verdict.UNCERTAIN", str(ctx.exception))

        with self.assertRaises(ValueError) as ctx:
            VerdictResult(
                verdict=Verdict.MISINFORMATION,
                label="Likely Misinformation",
                credibility_score=85.0,  # Way above threshold
                confidence_level="HIGH",
                overall_status=HybridAnalysisStatus.COMPLETED,
                is_definitive=True,
                thresholds={"credible": 70.0, "uncertain": 40.0},
                reason="High score contradiction",
                failed_components=(),
                error_details={},
                fact_check_conflict=False,
            )
        self.assertIn("Expected Verdict.CREDIBLE", str(ctx.exception))

    def test_score_above_credible_threshold_with_uncertain_verdict_rejected(self):
        with self.assertRaises(ValueError) as ctx:
            VerdictResult(
                verdict=Verdict.UNCERTAIN,
                label="Uncertain",
                credibility_score=70.0,  # Meets credible threshold
                confidence_level="HIGH",
                overall_status=HybridAnalysisStatus.COMPLETED,
                is_definitive=False,
                thresholds={"credible": 70.0, "uncertain": 40.0},
                reason="Credible score contradiction",
                failed_components=(),
                error_details={},
                fact_check_conflict=False,
            )
        self.assertIn("Expected Verdict.CREDIBLE", str(ctx.exception))

        with self.assertRaises(ValueError) as ctx:
            VerdictResult(
                verdict=Verdict.UNCERTAIN,
                label="Uncertain",
                credibility_score=20.0,  # Below uncertain threshold
                confidence_level="LOW",
                overall_status=HybridAnalysisStatus.COMPLETED,
                is_definitive=False,
                thresholds={"credible": 70.0, "uncertain": 40.0},
                reason="Low score contradiction",
                failed_components=(),
                error_details={},
                fact_check_conflict=False,
            )
        self.assertIn("Expected Verdict.MISINFORMATION", str(ctx.exception))

    def test_valid_direct_construction_all_categories_succeeds(self):
        # Valid CREDIBLE
        r_cred = VerdictResult(
            verdict=Verdict.CREDIBLE,
            label="Likely Credible",
            credibility_score=85.0,
            confidence_level="HIGH",
            overall_status=HybridAnalysisStatus.COMPLETED,
            is_definitive=True,
            thresholds={"credible": 70.0, "uncertain": 40.0},
            reason="Score 85.0 >= 70.0",
            failed_components=(),
            error_details={},
            fact_check_conflict=False,
        )
        self.assertEqual(r_cred.verdict, Verdict.CREDIBLE)
        self.assertTrue(r_cred.is_definitive)

        # Valid UNCERTAIN
        r_unc = VerdictResult(
            verdict=Verdict.UNCERTAIN,
            label="Uncertain",
            credibility_score=55.0,
            confidence_level="MEDIUM",
            overall_status=HybridAnalysisStatus.COMPLETED,
            is_definitive=False,
            thresholds={"credible": 70.0, "uncertain": 40.0},
            reason="Score 55.0 in [40.0, 70.0)",
            failed_components=(),
            error_details={},
            fact_check_conflict=False,
        )
        self.assertEqual(r_unc.verdict, Verdict.UNCERTAIN)
        self.assertFalse(r_unc.is_definitive)

        # Valid MISINFORMATION
        r_mis = VerdictResult(
            verdict=Verdict.MISINFORMATION,
            label="Likely Misinformation",
            credibility_score=25.0,
            confidence_level="HIGH",
            overall_status=HybridAnalysisStatus.COMPLETED,
            is_definitive=True,
            thresholds={"credible": 70.0, "uncertain": 40.0},
            reason="Score 25.0 < 40.0",
            failed_components=(),
            error_details={},
            fact_check_conflict=False,
        )
        self.assertEqual(r_mis.verdict, Verdict.MISINFORMATION)
        self.assertTrue(r_mis.is_definitive)

    def test_missing_threshold_keys_rejected(self):
        with self.assertRaises(VerdictConfigError) as ctx:
            VerdictResult(
                verdict=Verdict.CREDIBLE,
                label="Likely Credible",
                credibility_score=85.0,
                confidence_level="HIGH",
                overall_status=HybridAnalysisStatus.COMPLETED,
                is_definitive=True,
                thresholds={"credible": 70.0},  # Missing "uncertain"
                reason="Missing threshold key",
                failed_components=(),
                error_details={},
                fact_check_conflict=False,
            )
        self.assertIn("must contain exactly keys", str(ctx.exception))

    def test_additional_threshold_keys_rejected(self):
        with self.assertRaises(VerdictConfigError) as ctx:
            VerdictResult(
                verdict=Verdict.CREDIBLE,
                label="Likely Credible",
                credibility_score=85.0,
                confidence_level="HIGH",
                overall_status=HybridAnalysisStatus.COMPLETED,
                is_definitive=True,
                thresholds={"credible": 70.0, "uncertain": 40.0, "extra": 10.0},
                reason="Extra threshold key",
                failed_components=(),
                error_details={},
                fact_check_conflict=False,
            )
        self.assertIn("must contain exactly keys", str(ctx.exception))

    def test_equal_and_inverted_thresholds_rejected(self):
        with self.assertRaises(VerdictConfigError) as ctx:
            VerdictResult(
                verdict=Verdict.CREDIBLE,
                label="Likely Credible",
                credibility_score=85.0,
                confidence_level="HIGH",
                overall_status=HybridAnalysisStatus.COMPLETED,
                is_definitive=True,
                thresholds={"credible": 50.0, "uncertain": 50.0},  # Equal
                reason="Equal thresholds",
                failed_components=(),
                error_details={},
                fact_check_conflict=False,
            )
        self.assertIn("strictly greater than", str(ctx.exception))

        with self.assertRaises(VerdictConfigError) as ctx:
            VerdictResult(
                verdict=Verdict.CREDIBLE,
                label="Likely Credible",
                credibility_score=85.0,
                confidence_level="HIGH",
                overall_status=HybridAnalysisStatus.COMPLETED,
                is_definitive=True,
                thresholds={"credible": 40.0, "uncertain": 70.0},  # Inverted
                reason="Inverted thresholds",
                failed_components=(),
                error_details={},
                fact_check_conflict=False,
            )
        self.assertIn("strictly greater than", str(ctx.exception))

    def test_boolean_non_numeric_nan_inf_out_of_range_thresholds_rejected(self):
        # Boolean threshold value
        with self.assertRaises(VerdictConfigError) as ctx:
            VerdictResult(
                verdict=Verdict.CREDIBLE,
                label="Likely Credible",
                credibility_score=85.0,
                confidence_level="HIGH",
                overall_status=HybridAnalysisStatus.COMPLETED,
                is_definitive=True,
                thresholds={"credible": True, "uncertain": 40.0},  # type: ignore[dict-item]
                reason="Boolean threshold",
                failed_components=(),
                error_details={},
                fact_check_conflict=False,
            )
        self.assertIn("must be a numeric float", str(ctx.exception))

        # Non-numeric threshold value
        with self.assertRaises(VerdictConfigError) as ctx:
            VerdictResult(
                verdict=Verdict.CREDIBLE,
                label="Likely Credible",
                credibility_score=85.0,
                confidence_level="HIGH",
                overall_status=HybridAnalysisStatus.COMPLETED,
                is_definitive=True,
                thresholds={"credible": "70.0", "uncertain": 40.0},  # type: ignore[dict-item]
                reason="String threshold",
                failed_components=(),
                error_details={},
                fact_check_conflict=False,
            )
        self.assertIn("must be a numeric float", str(ctx.exception))

        # NaN threshold value
        with self.assertRaises(VerdictConfigError) as ctx:
            VerdictResult(
                verdict=Verdict.CREDIBLE,
                label="Likely Credible",
                credibility_score=85.0,
                confidence_level="HIGH",
                overall_status=HybridAnalysisStatus.COMPLETED,
                is_definitive=True,
                thresholds={"credible": float("nan"), "uncertain": 40.0},
                reason="NaN threshold",
                failed_components=(),
                error_details={},
                fact_check_conflict=False,
            )
        self.assertIn("must be a finite number", str(ctx.exception))

        # Out-of-range negative threshold value
        with self.assertRaises(VerdictConfigError) as ctx:
            VerdictResult(
                verdict=Verdict.CREDIBLE,
                label="Likely Credible",
                credibility_score=85.0,
                confidence_level="HIGH",
                overall_status=HybridAnalysisStatus.COMPLETED,
                is_definitive=True,
                thresholds={"credible": 70.0, "uncertain": -5.0},
                reason="Negative threshold",
                failed_components=(),
                error_details={},
                fact_check_conflict=False,
            )
        self.assertIn("between 0.0 and 100.0", str(ctx.exception))

        # Out-of-range >100 threshold value
        with self.assertRaises(VerdictConfigError) as ctx:
            VerdictResult(
                verdict=Verdict.CREDIBLE,
                label="Likely Credible",
                credibility_score=85.0,
                confidence_level="HIGH",
                overall_status=HybridAnalysisStatus.COMPLETED,
                is_definitive=True,
                thresholds={"credible": 105.0, "uncertain": 40.0},
                reason=">100 threshold",
                failed_components=(),
                error_details={},
                fact_check_conflict=False,
            )
        self.assertIn("between 0.0 and 100.0", str(ctx.exception))

    def test_insufficient_evidence_only_valid_with_uncertain_and_none_score(self):
        # Valid insufficient evidence
        r_ie = VerdictResult(
            verdict=Verdict.UNCERTAIN,
            label="Uncertain",
            credibility_score=None,
            confidence_level="NONE",
            overall_status=HybridAnalysisStatus.INSUFFICIENT_EVIDENCE,
            is_definitive=False,
            thresholds={"credible": 70.0, "uncertain": 40.0},
            reason="Primary truth evidence unavailable",
            failed_components=(),
            error_details={},
            fact_check_conflict=False,
        )
        self.assertEqual(r_ie.verdict, Verdict.UNCERTAIN)
        self.assertIsNone(r_ie.credibility_score)
        self.assertFalse(r_ie.is_definitive)

        # Contradictory insufficient evidence with numeric score
        with self.assertRaises(ValueError):
            VerdictResult(
                verdict=Verdict.UNCERTAIN,
                label="Uncertain",
                credibility_score=50.0,
                confidence_level="NONE",
                overall_status=HybridAnalysisStatus.INSUFFICIENT_EVIDENCE,
                is_definitive=False,
                thresholds={"credible": 70.0, "uncertain": 40.0},
                reason="Contradictory score",
                failed_components=(),
                error_details={},
                fact_check_conflict=False,
            )

        # Contradictory insufficient evidence with non-NONE confidence
        with self.assertRaises(ValueError):
            VerdictResult(
                verdict=Verdict.UNCERTAIN,
                label="Uncertain",
                credibility_score=None,
                confidence_level="HIGH",
                overall_status=HybridAnalysisStatus.INSUFFICIENT_EVIDENCE,
                is_definitive=False,
                thresholds={"credible": 70.0, "uncertain": 40.0},
                reason="Contradictory confidence",
                failed_components=(),
                error_details={},
                fact_check_conflict=False,
            )


class ArchitecturalIsolationTests(SimpleTestCase):
    """Proves that AI-010 is completely isolated from upstream inference, database, and network."""

    def test_isolation_upstream_services_not_invoked(self):
        service = VerdictService()
        hybrid_res = _build_hybrid_result(credibility_score=88.0)

        with (
            patch("analysis.inference.adapter.ModelAdapterProtocol") as mock_model,
            patch("analysis.services.fact_check.FactCheckService") as mock_fact_check,
            patch("analysis.services.rules.RuleEngineService") as mock_rules,
            patch(
                "analysis.services.narrative.NarrativeActivityService"
            ) as mock_narrative,
        ):
            verdict_res = service.generate_verdict(hybrid_res)

            mock_model.assert_not_called()
            mock_fact_check.assert_not_called()
            mock_rules.assert_not_called()
            mock_narrative.assert_not_called()

        self.assertEqual(verdict_res.verdict, Verdict.CREDIBLE)

    def test_input_hybrid_result_remains_unchanged(self):
        service = VerdictService()
        hybrid_res = _build_hybrid_result(
            credibility_score=75.0,
            overall_status=HybridAnalysisStatus.COMPLETED,
            confidence_level="HIGH",
            coverage_ratio=0.85,
            fact_check_conflict=False,
        )
        original_score = hybrid_res.credibility_score
        original_status = hybrid_res.overall_status

        verdict_res = service.generate_verdict(hybrid_res)

        self.assertEqual(hybrid_res.credibility_score, original_score)
        self.assertEqual(hybrid_res.overall_status, original_status)
        self.assertEqual(verdict_res.credibility_score, original_score)

"""
Unit and integration tests for AI-009 Hybrid Credibility Engine Service.
Verifies signal normalization, dynamic weight renormalization, status contracts,
fact-check deduplication, failure handling, precision bounds, and immutability.
"""

import json
import uuid
from datetime import datetime, timezone
from types import MappingProxyType

from django.test import SimpleTestCase

from analysis.inference.adapter import ModelOutput
from analysis.models import ModelPrediction
from analysis.services.fact_check import FactCheckEvidenceItem, FactCheckResult
from analysis.services.hybrid import (
    ALL_COMPONENTS,
    COMPONENT_FACT_CHECK,
    COMPONENT_MODEL,
    COMPONENT_NARRATIVE,
    COMPONENT_RULE_ENGINE,
    DEFAULT_WEIGHT_FACT_CHECK,
    DEFAULT_WEIGHT_MODEL,
    DEFAULT_WEIGHT_NARRATIVE,
    DEFAULT_WEIGHT_RULE_ENGINE,
    HybridAnalysisStatus,
    HybridConfigError,
    HybridCredibilityEngine,
    HybridCredibilityResult,
    HybridInputError,
    ScoredFactCheckItem,
    SignalStatus,
    normalize_fact_check_rating,
)
from analysis.services.narrative import NarrativeActivity, NarrativeMatchRecord
from analysis.services.rules import RuleEngineService, RuleValidationResult


class HybridConfigurationTests(SimpleTestCase):
    """Verifies engine initialization, weight validation, and defaults."""

    def test_default_weights_sum_to_one(self):
        engine = HybridCredibilityEngine()
        weights = engine.configured_weights
        self.assertEqual(weights[COMPONENT_MODEL], DEFAULT_WEIGHT_MODEL)
        self.assertEqual(weights[COMPONENT_FACT_CHECK], DEFAULT_WEIGHT_FACT_CHECK)
        self.assertEqual(weights[COMPONENT_NARRATIVE], DEFAULT_WEIGHT_NARRATIVE)
        self.assertEqual(weights[COMPONENT_RULE_ENGINE], DEFAULT_WEIGHT_RULE_ENGINE)
        self.assertAlmostEqual(sum(weights.values()), 1.0, places=4)

    def test_custom_valid_weights(self):
        engine = HybridCredibilityEngine(
            model_weight=0.50,
            fact_check_weight=0.30,
            narrative_weight=0.10,
            rule_engine_weight=0.10,
        )
        weights = engine.configured_weights
        self.assertEqual(weights[COMPONENT_MODEL], 0.50)
        self.assertEqual(weights[COMPONENT_FACT_CHECK], 0.30)
        self.assertEqual(weights[COMPONENT_NARRATIVE], 0.10)
        self.assertEqual(weights[COMPONENT_RULE_ENGINE], 0.10)

    def test_weights_not_summing_to_one_rejected(self):
        with self.assertRaises(HybridConfigError) as ctx:
            HybridCredibilityEngine(
                model_weight=0.50,
                fact_check_weight=0.50,
                narrative_weight=0.15,
                rule_engine_weight=0.10,
            )
        self.assertIn("Component weights must sum to 1.0", str(ctx.exception))

    def test_negative_weight_rejected(self):
        with self.assertRaises(HybridConfigError) as ctx:
            HybridCredibilityEngine(
                model_weight=-0.10,
                fact_check_weight=0.60,
                narrative_weight=0.25,
                rule_engine_weight=0.25,
            )
        self.assertIn("between 0.0 and 1.0", str(ctx.exception))

    def test_boolean_weight_rejected(self):
        with self.assertRaises(HybridConfigError) as ctx:
            HybridCredibilityEngine(
                model_weight=True,  # type: ignore[arg-type]
                fact_check_weight=0.0,
                narrative_weight=0.0,
                rule_engine_weight=0.0,
            )
        self.assertIn("must be a numeric float", str(ctx.exception))

    def test_non_finite_weight_rejected(self):
        with self.assertRaises(HybridConfigError) as ctx:
            HybridCredibilityEngine(
                model_weight=float("nan"),
                fact_check_weight=0.40,
                narrative_weight=0.15,
                rule_engine_weight=0.10,
            )
        self.assertIn("must be a finite float", str(ctx.exception))

    def test_configured_weights_immutability(self):
        engine = HybridCredibilityEngine()
        weights = engine.configured_weights
        self.assertIsInstance(weights, MappingProxyType)
        with self.assertRaises(TypeError):
            weights[COMPONENT_MODEL] = 0.99  # type: ignore[index]


class FactCheckRatingNormalizationTests(SimpleTestCase):
    """Verifies deterministic heuristic mapping for fact-check ratings."""

    def test_mostly_true_mapped_to_0_80(self):
        self.assertEqual(normalize_fact_check_rating("mostly true"), 0.80)
        self.assertEqual(normalize_fact_check_rating("Mostly True"), 0.80)
        self.assertEqual(normalize_fact_check_rating("largely true"), 0.80)
        self.assertEqual(normalize_fact_check_rating("mostly accurate"), 0.80)

    def test_partially_true_mapped_to_0_50(self):
        self.assertEqual(normalize_fact_check_rating("partially true"), 0.50)
        self.assertEqual(normalize_fact_check_rating("Partially True"), 0.50)
        self.assertEqual(normalize_fact_check_rating("half true"), 0.50)
        self.assertEqual(normalize_fact_check_rating("half-true"), 0.50)
        self.assertEqual(normalize_fact_check_rating("partly true"), 0.50)
        self.assertEqual(normalize_fact_check_rating("mixture"), 0.50)
        self.assertEqual(normalize_fact_check_rating("mixed"), 0.50)

    def test_mostly_false_and_partially_false_mapped_to_0_20(self):
        self.assertEqual(normalize_fact_check_rating("mostly false"), 0.20)
        self.assertEqual(normalize_fact_check_rating("partially false"), 0.20)
        self.assertEqual(normalize_fact_check_rating("Partially False"), 0.20)
        self.assertEqual(normalize_fact_check_rating("largely false"), 0.20)
        self.assertEqual(normalize_fact_check_rating("mostly incorrect"), 0.20)

    def test_false_and_pinocchios_mapped_to_0_0(self):
        self.assertEqual(normalize_fact_check_rating("false"), 0.0)
        self.assertEqual(normalize_fact_check_rating("False!"), 0.0)
        self.assertEqual(normalize_fact_check_rating("pants on fire"), 0.0)
        self.assertEqual(normalize_fact_check_rating("Pants on Fire!"), 0.0)
        self.assertEqual(normalize_fact_check_rating("four pinocchios"), 0.0)
        self.assertEqual(normalize_fact_check_rating("4 Pinocchios"), 0.0)
        self.assertEqual(normalize_fact_check_rating("debunked"), 0.0)
        self.assertEqual(normalize_fact_check_rating("fake"), 0.0)
        self.assertEqual(normalize_fact_check_rating("misleading"), 0.0)

    def test_true_and_verified_mapped_to_1_0(self):
        self.assertEqual(normalize_fact_check_rating("true"), 1.0)
        self.assertEqual(normalize_fact_check_rating("True."), 1.0)
        self.assertEqual(normalize_fact_check_rating("correct"), 1.0)
        self.assertEqual(normalize_fact_check_rating("verified"), 1.0)
        self.assertEqual(normalize_fact_check_rating("confirmed"), 1.0)

    def test_negations_handled_correctly(self):
        self.assertEqual(normalize_fact_check_rating("not true"), 0.0)
        self.assertEqual(normalize_fact_check_rating("not accurate"), 0.0)
        self.assertEqual(normalize_fact_check_rating("not correct"), 0.0)
        self.assertEqual(normalize_fact_check_rating("not false"), 1.0)
        self.assertEqual(normalize_fact_check_rating("not incorrect"), 1.0)

    def test_contradictory_and_ambiguous_ratings_unscorable(self):
        self.assertIsNone(normalize_fact_check_rating("true that it was false"))
        self.assertIsNone(normalize_fact_check_rating("false or true"))
        self.assertIsNone(normalize_fact_check_rating("unproven"))
        self.assertIsNone(normalize_fact_check_rating("unsubstantiated"))
        self.assertIsNone(normalize_fact_check_rating("opinion"))
        self.assertIsNone(normalize_fact_check_rating("satire"))
        self.assertIsNone(normalize_fact_check_rating("explainer"))
        self.assertIsNone(normalize_fact_check_rating(""))
        self.assertIsNone(normalize_fact_check_rating("   "))
        self.assertIsNone(normalize_fact_check_rating(None))


class FactCheckDeduplicationAndConflictTests(SimpleTestCase):
    """Verifies domain deduplication, latest review selection, and conflict detection."""

    def setUp(self):
        self.engine = HybridCredibilityEngine()

    def test_domain_deduplication_selects_latest_review(self):
        items = (
            FactCheckEvidenceItem(
                publisher="PolitiFact",
                rating="False",
                url="https://www.politifact.com/factchecks/2026/jan/10/claim1",
                review_date="2026-01-10",
            ),
            FactCheckEvidenceItem(
                publisher="PolitiFact",
                rating="Mostly True",
                url="https://politifact.com/factchecks/2026/jan/20/claim1",
                review_date="2026-01-20",
            ),
        )
        fc_result = FactCheckResult(
            matches=2,
            sources=items,
            summary="2 reviews",
            evidence_urls=(items[0].url, items[1].url),
        )
        scored_items, avg_score, conflict, status = self.engine.normalize_fact_checks(
            fc_result
        )

        self.assertEqual(len(scored_items), 1)
        self.assertEqual(scored_items[0].raw_rating, "Mostly True")
        self.assertEqual(scored_items[0].normalized_score, 0.80)
        self.assertEqual(avg_score, 0.80)
        self.assertFalse(conflict)
        self.assertEqual(status, SignalStatus.AVAILABLE)

    def test_conflict_detection_when_variance_exceeds_threshold(self):
        items = (
            FactCheckEvidenceItem(
                publisher="PolitiFact",
                rating="True",
                url="https://www.politifact.com/review1",
                review_date="2026-01-10",
            ),
            FactCheckEvidenceItem(
                publisher="FactCheck.org",
                rating="False",
                url="https://factcheck.org/review2",
                review_date="2026-01-11",
            ),
        )
        fc_result = FactCheckResult(
            matches=2,
            sources=items,
            summary="Conflicting reviews",
            evidence_urls=(items[0].url, items[1].url),
        )
        scored_items, avg_score, conflict, status = self.engine.normalize_fact_checks(
            fc_result
        )

        self.assertEqual(len(scored_items), 2)
        self.assertEqual(avg_score, 0.50)  # (1.0 + 0.0) / 2
        self.assertTrue(conflict)  # 1.0 - 0.0 = 1.0 >= 0.50
        self.assertEqual(status, SignalStatus.AVAILABLE)

    def test_no_conflict_when_ratings_are_close(self):
        items = (
            FactCheckEvidenceItem(
                publisher="PolitiFact",
                rating="True",
                url="https://www.politifact.com/review1",
            ),
            FactCheckEvidenceItem(
                publisher="Snopes",
                rating="Mostly True",
                url="https://snopes.com/review2",
            ),
        )
        fc_result = FactCheckResult(
            matches=2,
            sources=items,
            summary="Consistent reviews",
            evidence_urls=(items[0].url, items[1].url),
        )
        _items, avg_score, conflict, status = self.engine.normalize_fact_checks(
            fc_result
        )

        self.assertAlmostEqual(avg_score, 0.90, places=4)  # (1.0 + 0.8) / 2
        self.assertFalse(conflict)  # 1.0 - 0.8 = 0.20 < 0.50
        self.assertEqual(status, SignalStatus.AVAILABLE)

    def test_all_unscorable_fact_checks_yield_unscorable_status(self):
        items = (
            FactCheckEvidenceItem(
                publisher="Snopes",
                rating="Satire",
                url="https://snopes.com/satire1",
            ),
            FactCheckEvidenceItem(
                publisher="Reuters",
                rating="Explainer",
                url="https://reuters.com/explainer1",
            ),
        )
        fc_result = FactCheckResult(
            matches=2,
            sources=items,
            summary="Non-evaluative articles",
            evidence_urls=(items[0].url, items[1].url),
        )
        scored_items, avg_score, conflict, status = self.engine.normalize_fact_checks(
            fc_result
        )

        self.assertEqual(len(scored_items), 2)
        self.assertIsNone(avg_score)
        self.assertFalse(conflict)
        self.assertEqual(status, SignalStatus.UNSCORABLE)


class HybridAggregationTests(SimpleTestCase):
    """Verifies end-to-end signal aggregation, weighting, and status transitions."""

    def setUp(self):
        self.engine = HybridCredibilityEngine()

    def test_architecture_specification_example(self):
        """
        Tests exact approved architecture specification example:
        - Model: CREDIBLE, confidence 0.90 (weight 0.35)
        - Fact-Check: True, score 1.0 (weight 0.40)
        - Rules: headline heuristic score 0.85 (weight 0.10)
        - Narrative: unscorable (weight 0.15)
        Expected:
        - Coverage ratio: 0.85
        - Renormalized weights: model 7/17, fact_check 8/17, rules 2/17
        - Final credibility score: 94.1
        - Displayed contributions: model 37.06, fact_check 47.06, rules 10.00
        - Discrepancy bound <= 0.070 points
        """
        model_out = ModelOutput(
            prediction=ModelPrediction.CREDIBLE,
            confidence=0.90,
        )
        fc_items = (
            FactCheckEvidenceItem(
                publisher="PolitiFact",
                rating="True",
                url="https://politifact.com/factchecks/spec1",
            ),
        )
        fc_result = FactCheckResult(
            matches=1,
            sources=fc_items,
            summary="Verified true",
            evidence_urls=(fc_items[0].url,),
        )
        rule_res = RuleValidationResult(
            flags={
                "excessive_capitalization": True,
                "duplicate_punctuation": True,
                "clickbait_phrases": False,
                "sensational_language": True,
                "short_or_vague_claim": False,
                "spam_patterns": False,
            },
            triggered_count=3,
            credibility_penalty=0.15,
            rule_score=0.85,
            observations=("3 flags triggered",),
        )
        narrative_act = NarrativeActivity(
            similar_claims_count=3,
            first_seen=datetime(2026, 1, 1, tzinfo=timezone.utc),
            latest_occurrence=datetime(2026, 1, 15, tzinfo=timezone.utc),
            activity_level="MEDIUM",
            evaluated_candidates_count=10,
            matches=(),
        )

        res = self.engine.aggregate(
            model_output=model_out,
            fact_check_result=fc_result,
            rule_validation_result=rule_res,
            narrative_activity=narrative_act,
        )

        self.assertEqual(res.overall_status, HybridAnalysisStatus.COMPLETED)
        self.assertEqual(res.confidence_level, "HIGH")
        self.assertAlmostEqual(res.coverage_ratio, 0.85, places=4)
        self.assertEqual(res.credibility_score, 94.1)

        # Verify component contributions
        contributions = res.weighted_contributions
        self.assertEqual(contributions[COMPONENT_MODEL], 37.06)
        self.assertEqual(contributions[COMPONENT_FACT_CHECK], 47.06)
        self.assertEqual(contributions[COMPONENT_RULE_ENGINE], 10.00)
        self.assertEqual(contributions[COMPONENT_NARRATIVE], 0.0)

        # Verify rounding discrepancy bound <= 0.070
        disp_sum = (
            contributions[COMPONENT_MODEL]
            + contributions[COMPONENT_FACT_CHECK]
            + contributions[COMPONENT_RULE_ENGINE]
            + contributions[COMPONENT_NARRATIVE]
        )
        discrepancy = abs(disp_sum - res.credibility_score)
        self.assertLessEqual(discrepancy, 0.070)
        self.assertAlmostEqual(discrepancy, 0.02, places=4)

        # Verify narrative interim Option 3 status and context preservation
        self.assertEqual(
            res.signal_statuses[COMPONENT_NARRATIVE], SignalStatus.UNSCORABLE
        )
        self.assertIsNotNone(res.narrative_context)
        self.assertEqual(res.narrative_context["activity_level"], "MEDIUM")
        self.assertEqual(res.narrative_context["similar_claims_count"], 3)

    def test_rules_only_returns_insufficient_evidence(self):
        """Rules-only cannot produce a credibility score under minimum truth signal rule."""
        rule_res = RuleEngineService().evaluate("Safe claims with zero flags.")
        res = self.engine.aggregate(
            rule_validation_result=rule_res,
            # No model, no fact-check
        )

        self.assertIsNone(res.credibility_score)
        self.assertEqual(res.overall_status, HybridAnalysisStatus.INSUFFICIENT_EVIDENCE)
        self.assertEqual(res.confidence_level, "NONE")
        self.assertEqual(res.coverage_ratio, 0.10)
        self.assertEqual(res.effective_weights[COMPONENT_RULE_ENGINE], 0.0)
        self.assertEqual(res.weighted_contributions[COMPONENT_RULE_ENGINE], 0.0)

    def test_rules_and_narrative_only_returns_insufficient_evidence(self):
        rule_res = RuleEngineService().evaluate("Some text without flags.")
        narrative_act = NarrativeActivity(
            similar_claims_count=1,
            first_seen=None,
            latest_occurrence=None,
            activity_level="LOW",
            evaluated_candidates_count=5,
            matches=(),
        )
        res = self.engine.aggregate(
            rule_validation_result=rule_res,
            narrative_activity=narrative_act,
        )

        self.assertIsNone(res.credibility_score)
        self.assertEqual(res.overall_status, HybridAnalysisStatus.INSUFFICIENT_EVIDENCE)
        self.assertEqual(res.confidence_level, "NONE")

    def test_model_misinformation_mapping(self):
        """Model predicting MISINFORMATION with confidence 0.85 maps raw score to 0.15."""
        model_out = ModelOutput(
            prediction=ModelPrediction.MISINFORMATION,
            confidence=0.85,
        )
        res = self.engine.aggregate(model_output=model_out)

        self.assertEqual(res.overall_status, HybridAnalysisStatus.COMPLETED)
        self.assertAlmostEqual(res.component_scores[COMPONENT_MODEL], 0.15, places=4)
        # Model only -> coverage 0.35, effective weight 1.0, score = round(15.0, 1) = 15.0
        self.assertEqual(res.credibility_score, 15.0)
        self.assertEqual(res.confidence_level, "MEDIUM")

    def test_fact_check_only_available(self):
        """Fact-check only produces a valid score when model is not available."""
        fc_items = (
            FactCheckEvidenceItem(
                publisher="Snopes",
                rating="Mostly False",
                url="https://snopes.com/fact1",
            ),
        )
        fc_result = FactCheckResult(
            matches=1,
            sources=fc_items,
            summary="Mostly False claim",
            evidence_urls=(fc_items[0].url,),
        )
        res = self.engine.aggregate(fact_check_result=fc_result)

        self.assertEqual(res.overall_status, HybridAnalysisStatus.COMPLETED)
        self.assertAlmostEqual(res.component_scores[COMPONENT_FACT_CHECK], 0.20)
        # Fact-check only -> effective weight 1.0, score = round(20.0, 1) = 20.0
        self.assertEqual(res.credibility_score, 20.0)
        self.assertEqual(res.confidence_level, "MEDIUM")

    def test_fact_check_conflict_downgrades_confidence_to_low(self):
        """Conflicting reviews downgrade confidence level to LOW even with high coverage."""
        model_out = ModelOutput(
            prediction=ModelPrediction.CREDIBLE,
            confidence=0.90,
        )
        fc_items = (
            FactCheckEvidenceItem(
                publisher="PolitiFact",
                rating="True",
                url="https://politifact.com/1",
            ),
            FactCheckEvidenceItem(
                publisher="Snopes",
                rating="False",
                url="https://snopes.com/2",
            ),
        )
        fc_result = FactCheckResult(
            matches=2,
            sources=fc_items,
            summary="Conflicting fact checks",
            evidence_urls=(fc_items[0].url, fc_items[1].url),
        )
        res = self.engine.aggregate(
            model_output=model_out,
            fact_check_result=fc_result,
        )

        self.assertTrue(res.fact_check_conflict)
        self.assertEqual(res.confidence_level, "LOW")
        self.assertEqual(res.overall_status, HybridAnalysisStatus.COMPLETED)
        self.assertIsNotNone(res.credibility_score)


class FailureMatrixAndVisibilityTests(SimpleTestCase):
    """Verifies error isolation, PARTIAL_FAILURE status, and manifest integrity."""

    def setUp(self):
        self.engine = HybridCredibilityEngine()

    def test_model_failure_with_fact_check_available_yields_partial_failure(self):
        fc_items = (
            FactCheckEvidenceItem(
                publisher="PolitiFact",
                rating="Mostly True",
                url="https://politifact.com/pf1",
            ),
        )
        fc_result = FactCheckResult(
            matches=1,
            sources=fc_items,
            summary="Mostly True",
            evidence_urls=(fc_items[0].url,),
        )

        res = self.engine.aggregate(
            model_error=RuntimeError("DeBERTa inference model timed out"),
            fact_check_result=fc_result,
        )

        self.assertEqual(res.overall_status, HybridAnalysisStatus.PARTIAL_FAILURE)
        self.assertIsNotNone(res.credibility_score)
        self.assertEqual(res.signal_statuses[COMPONENT_MODEL], SignalStatus.FAILED)
        self.assertEqual(
            res.signal_statuses[COMPONENT_FACT_CHECK], SignalStatus.AVAILABLE
        )
        self.assertEqual(res.failed_components, (COMPONENT_MODEL,))
        self.assertIn("timed out", res.error_details[COMPONENT_MODEL])

    def test_fact_check_timeout_with_model_available_yields_partial_failure(self):
        model_out = ModelOutput(
            prediction=ModelPrediction.CREDIBLE,
            confidence=0.80,
        )
        res = self.engine.aggregate(
            model_output=model_out,
            fact_check_error="Google Fact Check Tools API 504 Gateway Timeout",
        )

        self.assertEqual(res.overall_status, HybridAnalysisStatus.PARTIAL_FAILURE)
        self.assertIsNotNone(res.credibility_score)
        self.assertEqual(res.signal_statuses[COMPONENT_FACT_CHECK], SignalStatus.FAILED)
        self.assertEqual(res.signal_statuses[COMPONENT_MODEL], SignalStatus.AVAILABLE)
        self.assertEqual(res.failed_components, (COMPONENT_FACT_CHECK,))
        self.assertIn("Gateway Timeout", res.error_details[COMPONENT_FACT_CHECK])

    def test_narrative_failure_still_permits_scoring(self):
        model_out = ModelOutput(
            prediction=ModelPrediction.CREDIBLE,
            confidence=0.80,
        )
        res = self.engine.aggregate(
            model_output=model_out,
            narrative_error="Embedding model weights corrupted",
        )

        self.assertEqual(res.overall_status, HybridAnalysisStatus.PARTIAL_FAILURE)
        self.assertIsNotNone(res.credibility_score)
        self.assertEqual(res.signal_statuses[COMPONENT_NARRATIVE], SignalStatus.FAILED)
        self.assertEqual(res.failed_components, (COMPONENT_NARRATIVE,))
        self.assertIn("weights corrupted", res.error_details[COMPONENT_NARRATIVE])

    def test_rule_failure_still_permits_scoring_with_primary_truth(self):
        model_out = ModelOutput(
            prediction=ModelPrediction.CREDIBLE,
            confidence=0.75,
        )
        res = self.engine.aggregate(
            model_output=model_out,
            rule_error=ValueError("Regex engine recursion limit exceeded"),
        )

        self.assertEqual(res.overall_status, HybridAnalysisStatus.PARTIAL_FAILURE)
        self.assertIsNotNone(res.credibility_score)
        self.assertEqual(
            res.signal_statuses[COMPONENT_RULE_ENGINE], SignalStatus.FAILED
        )
        self.assertEqual(res.failed_components, (COMPONENT_RULE_ENGINE,))

    def test_all_components_failed_yields_insufficient_evidence(self):
        res = self.engine.aggregate(
            model_error="Model crashed",
            fact_check_error="API down",
            rule_error="Rule syntax error",
            narrative_error="Embedding unavailable",
        )

        self.assertIsNone(res.credibility_score)
        self.assertEqual(res.overall_status, HybridAnalysisStatus.INSUFFICIENT_EVIDENCE)
        self.assertEqual(res.confidence_level, "NONE")
        self.assertEqual(len(res.failed_components), 4)
        for comp in ALL_COMPONENTS:
            self.assertEqual(res.signal_statuses[comp], SignalStatus.FAILED)
            self.assertIn(comp, res.error_details)

    def test_fact_check_no_evidence_is_not_failure(self):
        """Zero matches returned from fact-check is NO_EVIDENCE, not FAILED."""
        model_out = ModelOutput(
            prediction=ModelPrediction.CREDIBLE,
            confidence=0.88,
        )
        fc_result = FactCheckResult.empty()
        res = self.engine.aggregate(
            model_output=model_out,
            fact_check_result=fc_result,
        )

        self.assertEqual(res.overall_status, HybridAnalysisStatus.COMPLETED)
        self.assertEqual(
            res.signal_statuses[COMPONENT_FACT_CHECK], SignalStatus.NO_EVIDENCE
        )
        self.assertEqual(res.failed_components, ())
        self.assertEqual(len(res.error_details), 0)


class ResultImmutabilityAndContractTests(SimpleTestCase):
    """Verifies immutability, invariant enforcement, and serialization of result objects."""

    def setUp(self):
        self.engine = HybridCredibilityEngine()

    def test_result_mapping_proxies_reject_mutation(self):
        model_out = ModelOutput(
            prediction=ModelPrediction.CREDIBLE,
            confidence=0.90,
        )
        res = self.engine.aggregate(model_output=model_out)

        with self.assertRaises(TypeError):
            res.component_scores[COMPONENT_MODEL] = 0.50  # type: ignore[index]
        with self.assertRaises(TypeError):
            res.effective_weights[COMPONENT_MODEL] = 0.50  # type: ignore[index]
        with self.assertRaises(TypeError):
            res.weighted_contributions[COMPONENT_MODEL] = 50.0  # type: ignore[index]
        with self.assertRaises(TypeError):
            res.signal_statuses[COMPONENT_MODEL] = SignalStatus.FAILED  # type: ignore[index]
        with self.assertRaises(TypeError):
            res.error_details["new_key"] = "error"  # type: ignore[index]

    def test_result_to_dict_is_plain_mutable_and_json_serializable(self):
        model_out = ModelOutput(
            prediction=ModelPrediction.CREDIBLE,
            confidence=0.90,
        )
        narrative_act = NarrativeActivity(
            similar_claims_count=1,
            first_seen=datetime(2026, 1, 1, tzinfo=timezone.utc),
            latest_occurrence=datetime(2026, 1, 2, tzinfo=timezone.utc),
            activity_level="LOW",
            evaluated_candidates_count=2,
            matches=(
                NarrativeMatchRecord(
                    claim_id=uuid.uuid4(),
                    similarity_score=0.85,
                    submitted_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
                ),
            ),
        )
        res = self.engine.aggregate(
            model_output=model_out,
            narrative_activity=narrative_act,
        )

        data = res.to_dict()
        self.assertIsInstance(data, dict)
        self.assertNotIsInstance(data["component_scores"], MappingProxyType)
        # Modifying returned dict must not affect result
        data["component_scores"][COMPONENT_MODEL] = 0.0
        self.assertEqual(res.component_scores[COMPONENT_MODEL], 0.90)

        # JSON serialization must succeed cleanly
        json_str = json.dumps(data)
        self.assertIsInstance(json_str, str)
        deserialized = json.loads(json_str)
        self.assertEqual(deserialized["overall_status"], "COMPLETED")
        self.assertEqual(deserialized["confidence_level"], "MEDIUM")
        self.assertEqual(deserialized["credibility_score"], 90.0)

    def test_insufficient_evidence_to_dict_json_serializable(self):
        res = self.engine.aggregate()  # Nothing provided
        data = res.to_dict()
        json_str = json.dumps(data)
        self.assertIsInstance(json_str, str)
        deserialized = json.loads(json_str)
        self.assertIsNone(deserialized["credibility_score"])
        self.assertEqual(deserialized["overall_status"], "INSUFFICIENT_EVIDENCE")
        self.assertEqual(deserialized["confidence_level"], "NONE")

    def test_input_type_validation_raises_hybrid_input_error(self):
        with self.assertRaises(HybridInputError):
            self.engine.aggregate(model_output="invalid_model_output")  # type: ignore[arg-type]
        with self.assertRaises(HybridInputError):
            self.engine.aggregate(fact_check_result={"invalid": "dict"})  # type: ignore[arg-type]
        with self.assertRaises(HybridInputError):
            self.engine.aggregate(rule_validation_result="not_a_result")  # type: ignore[arg-type]
        with self.assertRaises(HybridInputError):
            self.engine.aggregate(narrative_activity=123)  # type: ignore[arg-type]

    def test_scored_fact_check_item_invariants(self):
        # Valid scorable item
        item = ScoredFactCheckItem(
            publisher="PolitiFact",
            raw_rating="True",
            normalized_score=1.0,
            is_scorable=True,
            url="https://politifact.com/item1",
        )
        self.assertTrue(item.is_scorable)
        self.assertEqual(item.normalized_score, 1.0)
        self.assertEqual(item.to_dict()["normalized_score"], 1.0)

        # Valid unscorable item
        unscorable_item = ScoredFactCheckItem(
            publisher="PolitiFact",
            raw_rating="Satire",
            normalized_score=None,
            is_scorable=False,
            url="https://politifact.com/item2",
        )
        self.assertFalse(unscorable_item.is_scorable)
        self.assertIsNone(unscorable_item.normalized_score)

        # Invalid: is_scorable True but normalized_score None
        with self.assertRaises(TypeError):
            ScoredFactCheckItem(
                publisher="P",
                raw_rating="R",
                normalized_score=None,
                is_scorable=True,
                url="U",
            )

        # Invalid: is_scorable False but normalized_score present
        with self.assertRaises(ValueError):
            ScoredFactCheckItem(
                publisher="P",
                raw_rating="R",
                normalized_score=0.8,
                is_scorable=False,
                url="U",
            )

    def test_direct_result_construction_invariants(self):
        # Invalid: credibility_score is None but overall_status is COMPLETED
        with self.assertRaises(ValueError):
            HybridCredibilityResult(
                credibility_score=None,
                overall_status=HybridAnalysisStatus.COMPLETED,
                confidence_level="NONE",
                coverage_ratio=0.5,
                component_scores={},
                effective_weights={},
                weighted_contributions={},
                signal_statuses={},
                failed_components=(),
                error_details={},
                fact_check_conflict=False,
            )

        # Invalid: credibility_score is None but confidence_level is HIGH
        with self.assertRaises(ValueError):
            HybridCredibilityResult(
                credibility_score=None,
                overall_status=HybridAnalysisStatus.INSUFFICIENT_EVIDENCE,
                confidence_level="HIGH",
                coverage_ratio=0.0,
                component_scores={},
                effective_weights={},
                weighted_contributions={},
                signal_statuses={},
                failed_components=(),
                error_details={},
                fact_check_conflict=False,
            )

        # Invalid: failed_components does not match signal_statuses with FAILED
        with self.assertRaises(ValueError):
            HybridCredibilityResult(
                credibility_score=80.0,
                overall_status=HybridAnalysisStatus.COMPLETED,
                confidence_level="HIGH",
                coverage_ratio=0.85,
                component_scores={},
                effective_weights={},
                weighted_contributions={},
                signal_statuses={COMPONENT_MODEL: SignalStatus.AVAILABLE},
                failed_components=(COMPONENT_MODEL,),  # Mismatch!
                error_details={},
                fact_check_conflict=False,
            )


class RoundingDiscrepancyBoundTests(SimpleTestCase):
    """Verifies that independent displayed contributions sum within proven 0.070 bound."""

    def test_discrepancy_bound_across_score_matrix(self):
        engine = HybridCredibilityEngine()
        test_scores = [0.0, 0.1234, 0.3333, 0.50, 0.6667, 0.7891, 0.85, 0.9999, 1.0]

        for m_score in test_scores:
            for fc_score in [0.0, 0.50, 0.80, 1.0]:
                model_out = ModelOutput(
                    prediction=ModelPrediction.CREDIBLE,
                    confidence=m_score,
                )
                fc_items = (
                    FactCheckEvidenceItem(
                        publisher="P",
                        rating=(
                            "True"
                            if fc_score == 1.0
                            else (
                                "Mostly True"
                                if fc_score == 0.80
                                else ("Half True" if fc_score == 0.50 else "False")
                            )
                        ),
                        url="https://example.com/p",
                    ),
                )
                fc_result = FactCheckResult(
                    matches=1,
                    sources=fc_items,
                    summary="Test",
                    evidence_urls=(fc_items[0].url,),
                )
                rule_res = RuleValidationResult(
                    flags={
                        "excessive_capitalization": False,
                        "duplicate_punctuation": False,
                        "clickbait_phrases": False,
                        "sensational_language": False,
                        "short_or_vague_claim": False,
                        "spam_patterns": False,
                    },
                    triggered_count=0,
                    credibility_penalty=0.0,
                    rule_score=1.0,
                    observations=(),
                )

                res = engine.aggregate(
                    model_output=model_out,
                    fact_check_result=fc_result,
                    rule_validation_result=rule_res,
                )

                self.assertIsNotNone(res.credibility_score)
                displayed_sum = sum(res.weighted_contributions.values())
                discrepancy = abs(displayed_sum - res.credibility_score)
                self.assertLessEqual(
                    discrepancy,
                    0.070001,
                    f"Discrepancy {discrepancy} exceeded 0.070 for model={m_score}, fc={fc_score}",
                )

from django.test import TestCase
from django.contrib.auth import get_user_model
from claims.models import Claim, ClaimStatus
from analysis.models import Analysis, Verdict, ModelPrediction
from django.db import IntegrityError

User = get_user_model()

class AnalysisModelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email='analysistest@example.com',
            password='Password123!',
            full_name='Analysis Tester'
        )
        self.claim = Claim.objects.create(
            user=self.user,
            text='Test claim for analysis'
        )

    def test_analysis_creation(self):
        """Test that Analysis can be instantiated and linked to a Claim"""
        analysis = Analysis.objects.create(
            claim=self.claim,
            credibility_score=85.5,
            verdict=Verdict.CREDIBLE,
            explainability_json={"feature": "test"},
            model_prediction=ModelPrediction.CREDIBLE,
            model_confidence=0.92
        )
        
        # Verify primary key is the Claim OneToOneField
        self.assertEqual(analysis.pk, self.claim.id)
        
        # Verify fields
        self.assertEqual(analysis.credibility_score, 85.5)
        self.assertEqual(analysis.verdict, Verdict.CREDIBLE)
        self.assertEqual(analysis.model_prediction, ModelPrediction.CREDIBLE)
        self.assertEqual(analysis.model_confidence, 0.92)
        self.assertEqual(analysis.explainability_json, {"feature": "test"})
        self.assertIsNotNone(analysis.analysis_timestamp)
        
        # Verify reverse relation
        self.assertEqual(self.claim.analysis, analysis)

    def test_analysis_one_to_one(self):
        """Test that one Claim cannot have two Analysis records"""
        Analysis.objects.create(claim=self.claim)
        
        with self.assertRaises(IntegrityError):
            Analysis.objects.create(claim=self.claim)

    def test_analysis_db006_fields(self):
        """Test DB-006 Hybrid Credibility Engine fields"""
        analysis = Analysis.objects.create(
            claim=self.claim,
            fact_check_summary="Matched 2 sources",
            fact_check_match_count=2,
            narrative_match_count=1,
            highest_similarity_score=0.85,
            rule_based_flags={"has_capital_words": True},
            final_weighted_score=75.0
        )
        
        analysis.refresh_from_db()
        self.assertEqual(analysis.fact_check_summary, "Matched 2 sources")
        self.assertEqual(analysis.fact_check_match_count, 2)
        self.assertEqual(analysis.narrative_match_count, 1)
        self.assertEqual(analysis.highest_similarity_score, 0.85)
        self.assertEqual(analysis.rule_based_flags, {"has_capital_words": True})
        self.assertEqual(analysis.final_weighted_score, 75.0)

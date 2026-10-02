from django.test import TestCase
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from claims.models import Claim, ClaimFeedback, FeedbackType
from analysis.models import Analysis, Verdict

User = get_user_model()


class DB017ConstraintTests(TestCase):
    def setUp(self):
        # Create deterministic isolated fixtures
        self.user = User.objects.create_user(
            email="testuser_db017@infotrust.local", 
            full_name="DB017 Test User", 
            password="securepassword123"
        )
        
        # Valid claim text is 10 chars
        self.claim = Claim.objects.create(
            user=self.user, 
            text="0123456789"
        )
        
        self.analysis_defaults = {
            "credibility_score": 50.0,
            "final_weighted_score": 50.0,
            "model_confidence": 0.5,
            "verdict": Verdict.CREDIBLE,
        }

    # A. Duplicate feedback
    def test_duplicate_feedback_raises_integrity_error(self):
        """First feedback succeeds, second raises IntegrityError."""
        ClaimFeedback.objects.create(
            user=self.user,
            claim=self.claim,
            feedback_type=FeedbackType.HELPFUL
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                ClaimFeedback.objects.create(
                    user=self.user,
                    claim=self.claim,
                    feedback_type=FeedbackType.NOT_HELPFUL
                )

    # B. Verdict
    def test_verdict_valid_values(self):
        """CREDIBLE and NULL are valid verdicts."""
        # CREDIBLE
        claim1 = Claim.objects.create(user=self.user, text="0123456789")
        Analysis.objects.create(claim=claim1, verdict=Verdict.CREDIBLE, credibility_score=50, final_weighted_score=50)

        # NULL
        claim2 = Claim.objects.create(user=self.user, text="0123456789")
        Analysis.objects.create(claim=claim2, verdict=None, credibility_score=50, final_weighted_score=50)

    def test_verdict_invalid_value(self):
        """Invalid verdict raises IntegrityError."""
        claim3 = Claim.objects.create(user=self.user, text="0123456789")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Analysis.objects.create(claim=claim3, verdict="INVALID", credibility_score=50, final_weighted_score=50)

    # C. Credibility score
    def test_credibility_score_valid(self):
        claim1 = Claim.objects.create(user=self.user, text="0123456789")
        Analysis.objects.create(claim=claim1, **{**self.analysis_defaults, "credibility_score": 0.0})
        
        claim2 = Claim.objects.create(user=self.user, text="0123456789")
        Analysis.objects.create(claim=claim2, **{**self.analysis_defaults, "credibility_score": 100.0})

    def test_credibility_score_invalid(self):
        claim1 = Claim.objects.create(user=self.user, text="0123456789")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Analysis.objects.create(claim=claim1, **{**self.analysis_defaults, "credibility_score": -0.1})
                
        claim2 = Claim.objects.create(user=self.user, text="0123456789")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Analysis.objects.create(claim=claim2, **{**self.analysis_defaults, "credibility_score": 100.1})

    # D. Final weighted score
    def test_final_weighted_score_valid(self):
        claim1 = Claim.objects.create(user=self.user, text="0123456789")
        Analysis.objects.create(claim=claim1, **{**self.analysis_defaults, "final_weighted_score": 0.0})
        
        claim2 = Claim.objects.create(user=self.user, text="0123456789")
        Analysis.objects.create(claim=claim2, **{**self.analysis_defaults, "final_weighted_score": 100.0})

    def test_final_weighted_score_invalid(self):
        claim1 = Claim.objects.create(user=self.user, text="0123456789")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Analysis.objects.create(claim=claim1, **{**self.analysis_defaults, "final_weighted_score": -0.1})
                
        claim2 = Claim.objects.create(user=self.user, text="0123456789")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Analysis.objects.create(claim=claim2, **{**self.analysis_defaults, "final_weighted_score": 100.1})

    # E. Model confidence
    def test_model_confidence_valid(self):
        claim1 = Claim.objects.create(user=self.user, text="0123456789")
        Analysis.objects.create(claim=claim1, **{**self.analysis_defaults, "model_confidence": 0.0})
        
        claim2 = Claim.objects.create(user=self.user, text="0123456789")
        Analysis.objects.create(claim=claim2, **{**self.analysis_defaults, "model_confidence": 1.0})
        
        claim3 = Claim.objects.create(user=self.user, text="0123456789")
        Analysis.objects.create(claim=claim3, **{**self.analysis_defaults, "model_confidence": None})

    def test_model_confidence_invalid(self):
        claim1 = Claim.objects.create(user=self.user, text="0123456789")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Analysis.objects.create(claim=claim1, **{**self.analysis_defaults, "model_confidence": -0.1})
                
        claim2 = Claim.objects.create(user=self.user, text="0123456789")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Analysis.objects.create(claim=claim2, **{**self.analysis_defaults, "model_confidence": 1.1})

    # F. Claim text
    def test_claim_text_valid(self):
        """Exactly 10 characters succeeds."""
        Claim.objects.create(user=self.user, text="0123456789")

    def test_claim_text_invalid(self):
        """NULL, empty string, and 9 characters all raise IntegrityError."""
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Claim.objects.create(user=self.user, text=None)
                
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Claim.objects.create(user=self.user, text="")
                
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Claim.objects.create(user=self.user, text="123456789")

from django.test import TestCase
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from claims.models import Claim, ClaimFeedback
from analysis.models import Analysis, Verdict

User = get_user_model()


class DB018ModelValidationTests(TestCase):
    def setUp(self):
        # Create deterministic isolated fixtures
        self.user = User.objects.create_user(
            email="testuser_db018@infotrust.local", 
            full_name="DB018 Test User", 
            password="securepassword123"
        )
        
        # Valid claim
        self.claim = Claim.objects.create(
            user=self.user, 
            text="0123456789"
        )

        # Baseline valid defaults for Analysis
        self.analysis_defaults = {
            "credibility_score": 50.0,
            "final_weighted_score": 50.0,
            "model_confidence": 0.5,
            "verdict": Verdict.CREDIBLE,
        }

    def test_model_confidence_constraint_validation(self):
        """1. Verify model_confidence rejects bounds and surfaces error in __all__ key."""
        # Test lower bound failure
        analysis_low = Analysis(claim=self.claim, **{**self.analysis_defaults, "model_confidence": -0.1})
        with self.assertRaises(ValidationError) as ctx_low:
            analysis_low.full_clean()
        
        # Verify the ValidationError is surfaced under the '__all__' key because it relies on CheckConstraint evaluation
        self.assertIn('__all__', ctx_low.exception.message_dict)

        # Test upper bound failure
        analysis_high = Analysis(claim=self.claim, **{**self.analysis_defaults, "model_confidence": 1.1})
        with self.assertRaises(ValidationError) as ctx_high:
            analysis_high.full_clean()
        
        # Verify the ValidationError is surfaced under the '__all__' key
        self.assertIn('__all__', ctx_high.exception.message_dict)


    def test_model_prediction_choices_validation(self):
        """2. Verify model_prediction rejects invalid values via choices."""
        analysis = Analysis(claim=self.claim, **{**self.analysis_defaults, "model_prediction": "INVALID_PREDICTION"})
        
        with self.assertRaises(ValidationError) as ctx:
            analysis.full_clean()
            
        self.assertIn('model_prediction', ctx.exception.message_dict)


    def test_feedback_type_choices_validation(self):
        """3. Verify ClaimFeedback.feedback_type rejects invalid values via choices."""
        feedback = ClaimFeedback(
            user=self.user,
            claim=self.claim,
            feedback_type="INVALID_FEEDBACK"
        )
        
        with self.assertRaises(ValidationError) as ctx:
            feedback.full_clean()
            
        self.assertIn('feedback_type', ctx.exception.message_dict)


    def test_claim_status_choices_validation(self):
        """4. Verify Claim.status rejects invalid values via choices."""
        claim = Claim(
            user=self.user,
            text="0123456789",
            status="INVALID_STATUS"
        )
        
        with self.assertRaises(ValidationError) as ctx:
            claim.full_clean()
            
        self.assertIn('status', ctx.exception.message_dict)

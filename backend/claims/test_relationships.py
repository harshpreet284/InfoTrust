from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.test import TestCase

from analysis.models import Analysis, ModelPrediction, Verdict
from audit.models import AuditLog
from claims.models import Claim, ClaimFeedback, FeedbackType

User = get_user_model()


class DB009RelationshipTests(TestCase):
    def setUp(self):
        self.user1 = User.objects.create_user(
            email="user1@example.com", password="Password123!", full_name="User One"
        )
        self.user2 = User.objects.create_user(
            email="user2@example.com", password="Password123!", full_name="User Two"
        )

    def test_user_claims_relationship(self):
        """1. A user can own multiple claims."""
        claim1 = Claim.objects.create(user=self.user1, text="Claim 1")
        claim2 = Claim.objects.create(user=self.user1, text="Claim 2")

        self.assertEqual(self.user1.claims.count(), 2)
        self.assertIn(claim1, self.user1.claims.all())
        self.assertIn(claim2, self.user1.claims.all())

    def test_claim_analysis_relationship(self):
        """2. A claim has exactly one analysis."""
        claim = Claim.objects.create(user=self.user1, text="Analysis Claim")
        analysis = Analysis.objects.create(
            claim=claim,
            credibility_score=50,
            verdict=Verdict.UNCERTAIN,
            model_prediction=ModelPrediction.CREDIBLE,
            model_confidence=0.5,
        )

        # Access from claim
        self.assertEqual(claim.analysis, analysis)
        # Access from analysis
        self.assertEqual(analysis.claim, claim)

        # Test uniqueness
        with self.assertRaises(IntegrityError):
            Analysis.objects.create(
                claim=claim,
                credibility_score=80,
                verdict=Verdict.CREDIBLE,
                model_prediction=ModelPrediction.CREDIBLE,
                model_confidence=0.9,
            )

    def test_claim_feedback_relationship(self):
        """3. A claim can have feedback from multiple users."""
        claim = Claim.objects.create(user=self.user1, text="Feedback Claim")
        feedback1 = ClaimFeedback.objects.create(
            user=self.user1, claim=claim, feedback_type=FeedbackType.HELPFUL
        )
        feedback2 = ClaimFeedback.objects.create(
            user=self.user2, claim=claim, feedback_type=FeedbackType.NOT_HELPFUL
        )

        self.assertEqual(claim.feedback.count(), 2)
        self.assertIn(feedback1, claim.feedback.all())
        self.assertIn(feedback2, claim.feedback.all())

    def test_user_feedback_relationship(self):
        """4. A user can submit feedback on multiple claims."""
        claim1 = Claim.objects.create(user=self.user1, text="Claim 1")
        claim2 = Claim.objects.create(user=self.user1, text="Claim 2")

        feedback1 = ClaimFeedback.objects.create(
            user=self.user2, claim=claim1, feedback_type=FeedbackType.HELPFUL
        )
        feedback2 = ClaimFeedback.objects.create(
            user=self.user2, claim=claim2, feedback_type=FeedbackType.HELPFUL
        )

        self.assertEqual(self.user2.claim_feedback.count(), 2)
        self.assertIn(feedback1, self.user2.claim_feedback.all())
        self.assertIn(feedback2, self.user2.claim_feedback.all())

    def test_user_audit_logs_relationship(self):
        """5. A user can have multiple audit logs."""
        log1 = AuditLog.objects.create(user=self.user1, action="LOGIN", target="System")
        log2 = AuditLog.objects.create(
            user=self.user1, action="VIEW_CLAIM", target="Claim 1"
        )

        self.assertEqual(self.user1.audit_logs.count(), 2)
        self.assertIn(log1, self.user1.audit_logs.all())
        self.assertIn(log2, self.user1.audit_logs.all())

    def test_cascade_and_set_null_behavior(self):
        """8. Existing cascade/set-null behavior remains correct."""
        user = User.objects.create_user(
            email="delete_me@example.com",
            password="Password123!",
            full_name="Delete Me",
        )
        claim = Claim.objects.create(user=user, text="Delete me claim")
        analysis = Analysis.objects.create(
            claim=claim,
            credibility_score=50,
            verdict=Verdict.UNCERTAIN,
            model_prediction=ModelPrediction.CREDIBLE,
            model_confidence=0.5,
        )
        feedback = ClaimFeedback.objects.create(
            user=user, claim=claim, feedback_type=FeedbackType.HELPFUL
        )
        log = AuditLog.objects.create(user=user, action="CREATE_CLAIM", target="Claim")

        log_id = log.id
        claim_id = claim.id
        analysis_id = analysis.pk
        feedback_id = feedback.id

        # Delete user
        user.delete()

        # Claim should cascade delete
        self.assertFalse(Claim.objects.filter(id=claim_id).exists())
        # Analysis should cascade delete (since it cascades from Claim)
        self.assertFalse(Analysis.objects.filter(pk=analysis_id).exists())
        # ClaimFeedback should cascade delete
        self.assertFalse(ClaimFeedback.objects.filter(id=feedback_id).exists())

        # AuditLog should SET_NULL
        log.refresh_from_db()
        self.assertIsNone(log.user)
        self.assertEqual(log.id, log_id)

from django.test import TestCase
from django.contrib.auth import get_user_model
from django.db import models
from claims.models import Claim, ClaimFeedback, FeedbackType
from analysis.models import Analysis, Verdict, ModelPrediction
from audit.models import AuditLog

User = get_user_model()


class DB016RelationshipTests(TestCase):
    def setUp(self):
        # Isolated deterministic fixtures
        self.user = User.objects.create_user(
            email="testuser@infotrust.local", 
            full_name="Test User", 
            password="securepassword123"
        )
        
        self.claim = Claim.objects.create(
            user=self.user, 
            text="This is a test claim for DB-016."
        )
        
        self.analysis = Analysis.objects.create(
            claim=self.claim,
            verdict=Verdict.CREDIBLE,
            credibility_score=85.0,
            final_weighted_score=85.0,
            model_prediction=ModelPrediction.CREDIBLE,
            model_confidence=0.88,
            fact_check_summary="Test Summary"
        )
        
        self.feedback = ClaimFeedback.objects.create(
            user=self.user,
            claim=self.claim,
            feedback_type=FeedbackType.HELPFUL
        )
        
        self.audit_log = AuditLog.objects.create(
            user=self.user,
            action="CREATE_CLAIM",
            target="Claim: Test",
            metadata={"source": "test"}
        )

    def test_user_deletion_cascades_and_nullifies(self):
        """
        Verify the dependency chain:
        After deleting the User:
        - the User is gone,
        - the Claim is gone,
        - the associated Analysis is gone,
        - the associated ClaimFeedback is gone,
        - the AuditLog remains,
        - the AuditLog.user becomes None,
        - the AuditLog's other data remains intact.
        """
        claim_id = self.claim.id
        analysis_pk = self.analysis.pk
        feedback_id = self.feedback.id
        audit_log_id = self.audit_log.id

        # Delete the user
        self.user.delete()

        # Check deletions (Cascade)
        self.assertFalse(User.objects.filter(email="testuser@infotrust.local").exists())
        self.assertFalse(Claim.objects.filter(id=claim_id).exists())
        self.assertFalse(Analysis.objects.filter(pk=analysis_pk).exists())
        self.assertFalse(ClaimFeedback.objects.filter(id=feedback_id).exists())

        # Check AuditLog preservation (Set Null)
        self.assertTrue(AuditLog.objects.filter(id=audit_log_id).exists())
        
        log = AuditLog.objects.get(id=audit_log_id)
        self.assertIsNone(log.user)
        self.assertEqual(log.action, "CREATE_CLAIM")
        self.assertEqual(log.target, "Claim: Test")
        self.assertEqual(log.metadata, {"source": "test"})
        self.assertIsNotNone(log.timestamp)

    def test_claim_deletion_cascades_independently(self):
        """
        Verify that deleting a Claim directly:
        - the Claim is gone,
        - its Analysis is gone,
        - its ClaimFeedback is gone,
        - the owning User remains,
        - unrelated claims belonging to the same User remain.
        """
        # Create an unrelated secondary claim for the same user
        secondary_claim = Claim.objects.create(
            user=self.user, 
            text="This is an unrelated secondary claim."
        )

        claim_id = self.claim.id
        analysis_pk = self.analysis.pk
        feedback_id = self.feedback.id
        secondary_claim_id = secondary_claim.id
        user_id = self.user.id

        # Delete the target claim directly
        self.claim.delete()

        # Check deletions (Cascade)
        self.assertFalse(Claim.objects.filter(id=claim_id).exists())
        self.assertFalse(Analysis.objects.filter(pk=analysis_pk).exists())
        self.assertFalse(ClaimFeedback.objects.filter(id=feedback_id).exists())

        # Check preservations
        self.assertTrue(User.objects.filter(id=user_id).exists())
        self.assertTrue(Claim.objects.filter(id=secondary_claim_id).exists())

    def test_forward_and_reverse_relationships(self):
        """Verify forward and reverse access for all relationships."""
        # Forward Access
        self.assertEqual(self.claim.user, self.user)
        self.assertEqual(self.claim.analysis, self.analysis)
        self.assertEqual(self.feedback.claim, self.claim)
        self.assertEqual(self.feedback.user, self.user)
        self.assertEqual(self.audit_log.user, self.user)

        # Reverse Access
        self.assertIn(self.claim, self.user.claims.all())
        self.assertEqual(self.analysis.claim, self.claim)
        self.assertIn(self.feedback, self.claim.feedback.all())
        self.assertIn(self.feedback, self.user.claim_feedback.all())
        self.assertIn(self.audit_log, self.user.audit_logs.all())

    def test_programmatic_on_delete_configuration(self):
        """
        Assert the configured definitions explicitly on the models.
        (Note: No current relationship uses PROTECT, so no PROTECT behavior is tested.)
        """
        self.assertEqual(Claim._meta.get_field('user').remote_field.on_delete, models.CASCADE)
        self.assertEqual(Analysis._meta.get_field('claim').remote_field.on_delete, models.CASCADE)
        self.assertEqual(ClaimFeedback._meta.get_field('user').remote_field.on_delete, models.CASCADE)
        self.assertEqual(ClaimFeedback._meta.get_field('claim').remote_field.on_delete, models.CASCADE)
        self.assertEqual(AuditLog._meta.get_field('user').remote_field.on_delete, models.SET_NULL)

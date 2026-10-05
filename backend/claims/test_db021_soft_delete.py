from django.test import TestCase
from authentication.models import User
from claims.models import Claim, ClaimFeedback, FeedbackType

class TestClaimSoftDelete(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="test@example.com", password="password", full_name="Test User")
        self.claim = Claim.objects.create(user=self.user, text="This is a test claim for soft deletion.")

    def test_claim_default_is_deleted(self):
        # Assert that a newly instantiated and saved Claim defaults to is_deleted = False
        self.assertFalse(self.claim.is_deleted)

    def test_claim_soft_delete_persistence(self):
        # Assert that is_deleted can be explicitly set to True, saved, and successfully retrieved
        self.claim.is_deleted = True
        self.claim.save(update_fields=['is_deleted'])
        
        self.claim.refresh_from_db()
        self.assertTrue(self.claim.is_deleted)

    def test_claim_relationships_unaffected(self):
        # Create related feedback
        feedback = ClaimFeedback.objects.create(user=self.user, claim=self.claim, feedback_type=FeedbackType.HELPFUL)
        
        # Soft delete the claim
        self.claim.is_deleted = True
        self.claim.save(update_fields=['is_deleted'])
        
        # Assert the feedback still exists in the DB (no cascade deletion)
        self.assertTrue(ClaimFeedback.objects.filter(id=feedback.id).exists())

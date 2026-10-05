import uuid
from django.test import TestCase
from django.http import Http404
from ninja.errors import AuthorizationError, HttpError

from authentication.models import User
from claims.models import Claim, ClaimStatus, ClaimFeedback, FeedbackType
from claims.schemas import ClaimCreateSchema
from claims.services import (
    _get_claim_for_mutation,
    submit_claim,
    update_claim,
    delete_claim,
)

class ClaimServiceTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(email="owner@example.com", password="pwd", full_name="Owner")
        self.other_user = User.objects.create_user(email="other@example.com", password="pwd", full_name="Other")
        self.admin = User.objects.create_superuser(email="admin@example.com", password="pwd", full_name="Admin")
        
        self.claim = Claim.objects.create(
            user=self.owner,
            text="Original valid claim text that is long enough.",
            status=ClaimStatus.PENDING,
            is_deleted=False
        )

    def test_submit_claim_success(self):
        payload = ClaimCreateSchema(claim_text="This is a newly submitted claim.")
        claim = submit_claim(self.owner, payload)
        
        self.assertIsNotNone(claim.id)
        self.assertEqual(claim.user, self.owner)
        self.assertEqual(claim.text, "This is a newly submitted claim.")
        self.assertEqual(claim.status, ClaimStatus.PENDING)
        self.assertFalse(claim.is_deleted)

    def test_helper_get_claim_owner_success(self):
        retrieved = _get_claim_for_mutation(self.claim.id, self.owner)
        self.assertEqual(retrieved.id, self.claim.id)

    def test_helper_get_claim_admin_success(self):
        retrieved = _get_claim_for_mutation(self.claim.id, self.admin)
        self.assertEqual(retrieved.id, self.claim.id)

    def test_helper_get_claim_non_owner_raises_403(self):
        with self.assertRaisesMessage(AuthorizationError, "You do not have permission to access this claim."):
            _get_claim_for_mutation(self.claim.id, self.other_user)

    def test_helper_get_claim_not_found_raises_404(self):
        with self.assertRaisesMessage(Http404, "Claim not found."):
            _get_claim_for_mutation(uuid.uuid4(), self.owner)

    def test_helper_get_claim_soft_deleted_raises_404(self):
        self.claim.is_deleted = True
        self.claim.save(update_fields=['is_deleted'])
        
        with self.assertRaisesMessage(Http404, "Claim not found."):
            _get_claim_for_mutation(self.claim.id, self.owner)

    def test_update_claim_success(self):
        payload = ClaimCreateSchema(claim_text="Updated text that is long enough.")
        updated = update_claim(self.claim.id, self.owner, payload)
        
        self.claim.refresh_from_db()
        self.assertEqual(self.claim.text, "Updated text that is long enough.")
        self.assertEqual(updated.text, "Updated text that is long enough.")

    def test_update_claim_admin_forbidden(self):
        payload = ClaimCreateSchema(claim_text="Updated text that is long enough.")
        with self.assertRaisesMessage(AuthorizationError, "You do not have permission to access this claim."):
            update_claim(self.claim.id, self.admin, payload)

    def test_update_claim_invalid_status(self):
        self.claim.status = ClaimStatus.PROCESSING
        self.claim.save(update_fields=['status'])
        
        payload = ClaimCreateSchema(claim_text="Updated text that is long enough.")
        with self.assertRaises(HttpError) as context:
            update_claim(self.claim.id, self.owner, payload)
            
        self.assertEqual(context.exception.status_code, 409)
        self.assertEqual(str(context.exception), "Analysis already started")

    def test_delete_claim_success_owner(self):
        delete_claim(self.claim.id, self.owner)
        
        self.claim.refresh_from_db()
        self.assertTrue(self.claim.is_deleted)
        
        # Verify the row remains physically
        self.assertTrue(Claim.objects.filter(id=self.claim.id).exists())

    def test_delete_claim_invalid_status_owner(self):
        self.claim.status = ClaimStatus.COMPLETED
        self.claim.save(update_fields=['status'])
        
        with self.assertRaises(HttpError) as context:
            delete_claim(self.claim.id, self.owner)
            
        self.assertEqual(context.exception.status_code, 409)
        self.assertEqual(str(context.exception), "Cannot delete analyzed claim")

    def test_delete_claim_success_admin_any_status(self):
        self.claim.status = ClaimStatus.COMPLETED
        self.claim.save(update_fields=['status'])
        
        delete_claim(self.claim.id, self.admin)
        
        self.claim.refresh_from_db()
        self.assertTrue(self.claim.is_deleted)

    def test_delete_claim_retains_related_objects(self):
        feedback = ClaimFeedback.objects.create(
            user=self.owner,
            claim=self.claim,
            feedback_type=FeedbackType.HELPFUL
        )
        
        delete_claim(self.claim.id, self.owner)
        
        # Verify both claim and related feedback remain in the database
        self.assertTrue(Claim.objects.filter(id=self.claim.id).exists())
        self.assertTrue(ClaimFeedback.objects.filter(id=feedback.id).exists())
        
    def test_delete_already_soft_deleted_raises_404(self):
        delete_claim(self.claim.id, self.owner)
        
        with self.assertRaisesMessage(Http404, "Claim not found."):
            delete_claim(self.claim.id, self.owner)

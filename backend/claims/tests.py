from django.test import TestCase
from django.contrib.auth import get_user_model
from claims.models import Claim, ClaimStatus

User = get_user_model()

class ClaimModelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email='claimtest@example.com',
            password='Password123!',
            full_name='Claim Tester'
        )

    def test_claim_creation(self):
        """Test that a Claim can be instantiated with a real User and saved successfully"""
        claim = Claim.objects.create(
            user=self.user,
            text='This is a test claim.'
        )
        
        # Verify UUID primary key exists and is automatically generated
        self.assertIsNotNone(claim.id)
        self.assertEqual(len(str(claim.id)), 36) # UUID string length
        
        # Verify User ForeignKey exists and relationship is correct
        self.assertEqual(claim.user, self.user)
        
        # Verify claim text field exists
        self.assertEqual(claim.text, 'This is a test claim.')
        
        # Verify status field exists (default PENDING)
        self.assertEqual(claim.status, ClaimStatus.PENDING)
        
        # Verify submitted_at exists
        self.assertIsNotNone(claim.submitted_at)
        
        # Verify updated_at exists
        self.assertIsNotNone(claim.updated_at)
        
        # Verify Claim can be retrieved
        retrieved_claim = Claim.objects.get(id=claim.id)
        self.assertEqual(retrieved_claim.id, claim.id)
        
        # Verify User can access their related claims (one-to-many)
        self.assertEqual(self.user.claims.count(), 1)
        self.assertEqual(self.user.claims.first().id, claim.id)

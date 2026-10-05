import uuid
from django.test import TestCase
from django.core.exceptions import ObjectDoesNotExist

from datetime import timedelta
from django.utils import timezone
from authentication.models import User
from claims.models import Claim, ClaimStatus
from claims.selectors import (
    get_claim,
    list_all_claims_for_admin,
    get_user_claim_history,
    get_recent_claims,
)

class ClaimSelectorTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(email="owner@example.com", password="pwd", full_name="Owner")
        self.other_user = User.objects.create_user(email="other@example.com", password="pwd", full_name="Other")
        self.admin = User.objects.create_superuser(email="admin@example.com", password="pwd", full_name="Admin")
        
        self.claim1 = Claim.objects.create(
            user=self.owner,
            text="Owner's first claim",
            status=ClaimStatus.PENDING,
        )
        self.claim2 = Claim.objects.create(
            user=self.owner,
            text="Owner's second claim",
            status=ClaimStatus.PENDING,
        )
        self.other_claim = Claim.objects.create(
            user=self.other_user,
            text="Other user's claim",
            status=ClaimStatus.PENDING,
        )
        
        # Ensure explicit chronological differences since auto_now_add can tie in fast tests
        now = timezone.now()
        Claim.objects.filter(id=self.claim1.id).update(submitted_at=now - timedelta(seconds=10))
        Claim.objects.filter(id=self.claim2.id).update(submitted_at=now - timedelta(seconds=5))
        Claim.objects.filter(id=self.other_claim.id).update(submitted_at=now)
        
        # Soft-deleted claim
        self.deleted_claim = Claim.objects.create(
            user=self.owner,
            text="Deleted claim",
            status=ClaimStatus.PENDING,
            is_deleted=True,
        )
        Claim.objects.filter(id=self.deleted_claim.id).update(submitted_at=now - timedelta(seconds=15))

    # 1. get_claim tests
    def test_get_claim_owner_success(self):
        retrieved = get_claim(self.claim1.id, self.owner)
        self.assertEqual(retrieved.id, self.claim1.id)

    def test_get_claim_admin_success(self):
        retrieved = get_claim(self.claim1.id, self.admin)
        self.assertEqual(retrieved.id, self.claim1.id)

    def test_get_claim_non_owner_raises_authorization_error(self):
        from ninja.errors import AuthorizationError
        with self.assertRaises(AuthorizationError):
            get_claim(self.claim1.id, self.other_user)

    def test_get_claim_soft_deleted_excluded(self):
        with self.assertRaises(Claim.DoesNotExist):
            get_claim(self.deleted_claim.id, self.owner)

    def test_get_claim_admin_soft_deleted_excluded(self):
        with self.assertRaises(Claim.DoesNotExist):
            get_claim(self.deleted_claim.id, self.admin)

    # 2. list_all_claims_for_admin tests
    def test_admin_list_contains_claims_from_multiple_users(self):
        qs = list_all_claims_for_admin()
        self.assertEqual(qs.count(), 3)  # claim1, claim2, other_claim
        user_ids = {c.user_id for c in qs}
        self.assertIn(self.owner.id, user_ids)
        self.assertIn(self.other_user.id, user_ids)

    def test_admin_list_excludes_deleted_claims(self):
        qs = list_all_claims_for_admin()
        ids = {c.id for c in qs}
        self.assertNotIn(self.deleted_claim.id, ids)

    def test_admin_list_ordered_by_submitted_at(self):
        qs = list_all_claims_for_admin()
        self.assertEqual(qs.first().id, self.other_claim.id) # created last
        self.assertEqual(qs.last().id, self.claim1.id) # created first

    def test_admin_selector_user_relation_efficient(self):
        # We test that the select_related exists by evaluating and accessing user properties
        # In Django test cases, asserting num_queries is a robust way to check select_related behavior
        qs = list_all_claims_for_admin()
        with self.assertNumQueries(1):
            for claim in qs:
                # Accessing user.full_name should not trigger a new DB query because of select_related
                _ = claim.user.full_name

    # 3. get_user_claim_history tests
    def test_user_history_contains_only_owners_active_claims(self):
        qs = get_user_claim_history(self.owner)
        self.assertEqual(qs.count(), 2)
        ids = {c.id for c in qs}
        self.assertIn(self.claim1.id, ids)
        self.assertIn(self.claim2.id, ids)
        self.assertNotIn(self.other_claim.id, ids)
        self.assertNotIn(self.deleted_claim.id, ids)

    def test_user_history_ordered_by_submitted_at(self):
        qs = get_user_claim_history(self.owner)
        # claim2 was created after claim1
        self.assertEqual(qs.first().id, self.claim2.id)
        self.assertEqual(qs.last().id, self.claim1.id)

    def test_user_history_empty(self):
        new_user = User.objects.create_user(email="empty@example.com", password="pwd", full_name="Empty")
        qs = get_user_claim_history(new_user)
        self.assertEqual(qs.count(), 0)

    # 4. get_recent_claims tests
    def test_recent_claims_ordered_by_submitted_at(self):
        qs = get_recent_claims()
        self.assertEqual(qs.first().id, self.other_claim.id)
        self.assertEqual(qs.last().id, self.claim1.id)
        
    def test_recent_claims_no_hardcoded_limit_or_slicing(self):
        qs = get_recent_claims()
        # The queryset shouldn't be sliced (it has count() natively)
        self.assertEqual(qs.count(), 3)

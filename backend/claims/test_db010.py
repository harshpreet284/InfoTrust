from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TransactionTestCase

from analysis.models import Analysis, Verdict
from claims.models import Claim, ClaimFeedback, FeedbackType

User = get_user_model()


class DB010ConstraintTests(TransactionTestCase):
    def setUp(self):
        self.user1 = User.objects.create_user(
            email="constraint1@example.com", password="pwd", full_name="User One"
        )
        self.user2 = User.objects.create_user(
            email="constraint2@example.com", password="pwd", full_name="User Two"
        )
        self.claim1 = Claim.objects.create(user=self.user1, text="First claim text")
        self.claim2 = Claim.objects.create(user=self.user1, text="Second claim text")

    def test_unique_user_email(self):
        """1. Duplicate user email rejection"""
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                User.objects.create_user(
                    email="constraint1@example.com",
                    password="pwd",
                    full_name="Duplicate",
                )

    def test_unique_feedback(self):
        """2. Duplicate feedback for same user + claim rejection"""
        ClaimFeedback.objects.create(
            user=self.user1, claim=self.claim1, feedback_type=FeedbackType.HELPFUL
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                ClaimFeedback.objects.create(
                    user=self.user1,
                    claim=self.claim1,
                    feedback_type=FeedbackType.NOT_HELPFUL,
                )

    def test_feedback_same_user_different_claim(self):
        """2. Same user + different claim allowed"""
        ClaimFeedback.objects.create(
            user=self.user1, claim=self.claim1, feedback_type=FeedbackType.HELPFUL
        )
        fb2 = ClaimFeedback.objects.create(
            user=self.user1, claim=self.claim2, feedback_type=FeedbackType.NOT_HELPFUL
        )
        self.assertIsNotNone(fb2.id)

    def test_feedback_different_user_same_claim(self):
        """2. Different user + same claim allowed"""
        ClaimFeedback.objects.create(
            user=self.user1, claim=self.claim1, feedback_type=FeedbackType.HELPFUL
        )
        fb2 = ClaimFeedback.objects.create(
            user=self.user2, claim=self.claim1, feedback_type=FeedbackType.NOT_HELPFUL
        )
        self.assertIsNotNone(fb2.id)

    def test_score_valid_bounds(self):
        """3. Valid 0 score accepted, Valid 100 score accepted"""
        a1 = Analysis.objects.create(
            claim=self.claim1, credibility_score=0, final_weighted_score=100
        )
        self.assertIsNotNone(a1.pk)

        a2 = Analysis.objects.create(
            claim=self.claim2, credibility_score=100, final_weighted_score=0
        )
        self.assertIsNotNone(a2.pk)

    def test_score_below_0_rejected(self):
        """3. Below 0 rejected where the 0-100 constraint applies"""
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Analysis.objects.create(claim=self.claim1, credibility_score=-1)

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Analysis.objects.create(
                    claim=self.claim1, credibility_score=50, final_weighted_score=-0.1
                )

    def test_score_above_100_rejected(self):
        """3. Above 100 rejected where the 0-100 constraint applies"""
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Analysis.objects.create(claim=self.claim1, credibility_score=101)

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Analysis.objects.create(
                    claim=self.claim1, credibility_score=50, final_weighted_score=100.1
                )

    def test_valid_verdict_accepted(self):
        """4. Valid verdict values accepted"""
        a = Analysis.objects.create(claim=self.claim1, verdict=Verdict.CREDIBLE)
        self.assertIsNotNone(a.pk)

    def test_invalid_verdict_rejected(self):
        """4. Invalid verdict rejected at the database level"""
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Analysis.objects.create(claim=self.claim1, verdict="INVALID_VERDICT")

    def test_non_null_claim_text(self):
        """5. NULL claim text rejected"""
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Claim.objects.create(user=self.user1, text=None)

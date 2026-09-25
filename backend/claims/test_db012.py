from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from analysis.models import Analysis, Verdict
from claims.models import Claim

User = get_user_model()


class DB012ValidationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="test@example.com", password="pwd", full_name="Test User"
        )

    def test_valid_claim_text_accepted(self):
        """1. Valid Claim text is accepted."""
        claim = Claim(
            user=self.user,
            text="This is a perfectly valid claim with more than 10 characters.",
        )
        claim.full_clean()  # Should not raise exception
        claim.save()
        self.assertIsNotNone(claim.id)

    def test_claim_text_below_minimum_rejected(self):
        """2. Claim text below the documented minimum is rejected."""
        claim = Claim(user=self.user, text="Too short")
        with self.assertRaises(ValidationError) as ctx:
            claim.full_clean()
        self.assertTrue("text" in ctx.exception.message_dict)

    def test_claim_text_above_maximum_rejected(self):
        """3. Claim text above the documented maximum is rejected."""
        claim = Claim(user=self.user, text="A" * 2001)
        with self.assertRaises(ValidationError) as ctx:
            claim.full_clean()
        self.assertTrue("text" in ctx.exception.message_dict)

    def test_valid_credibility_score_accepted(self):
        """4. Valid credibility score is accepted."""
        claim = Claim.objects.create(user=self.user, text="This is a valid claim.")
        analysis = Analysis(
            claim=claim, credibility_score=50.0, final_weighted_score=50.0
        )
        analysis.full_clean()
        analysis.save()
        self.assertIsNotNone(analysis.pk)

    def test_invalid_credibility_score_rejected(self):
        """5. Invalid credibility score is rejected through model validation."""
        claim = Claim.objects.create(user=self.user, text="This is a valid claim.")
        analysis1 = Analysis(claim=claim, credibility_score=-1.0)
        with self.assertRaises(ValidationError) as ctx1:
            analysis1.full_clean()
        self.assertTrue("credibility_score" in ctx1.exception.message_dict)

        analysis2 = Analysis(claim=claim, credibility_score=101.0)
        with self.assertRaises(ValidationError) as ctx2:
            analysis2.full_clean()
        self.assertTrue("credibility_score" in ctx2.exception.message_dict)

    def test_valid_final_weighted_score_accepted(self):
        """6. Valid final weighted score is accepted."""
        claim = Claim.objects.create(user=self.user, text="This is a valid claim.")
        analysis = Analysis(
            claim=claim, credibility_score=100.0, final_weighted_score=0.0
        )
        analysis.full_clean()
        analysis.save()
        self.assertIsNotNone(analysis.pk)

    def test_invalid_final_weighted_score_rejected(self):
        """7. Invalid final weighted score is rejected through model validation."""
        claim = Claim.objects.create(user=self.user, text="This is a valid claim.")
        analysis1 = Analysis(claim=claim, final_weighted_score=-0.1)
        with self.assertRaises(ValidationError) as ctx1:
            analysis1.full_clean()
        self.assertTrue("final_weighted_score" in ctx1.exception.message_dict)

        analysis2 = Analysis(claim=claim, final_weighted_score=100.1)
        with self.assertRaises(ValidationError) as ctx2:
            analysis2.full_clean()
        self.assertTrue("final_weighted_score" in ctx2.exception.message_dict)

    def test_required_fields_behave_correctly(self):
        """8. Required fields behave correctly."""
        claim = Claim(
            user=self.user, text=""
        )  # empty string should fail required validation (or min length)
        with self.assertRaises(ValidationError) as ctx:
            claim.full_clean()
        self.assertTrue("text" in ctx.exception.message_dict)

        # Test null text
        claim2 = Claim(user=self.user, text=None)
        with self.assertRaises(ValidationError) as ctx:
            claim2.full_clean()
        self.assertTrue("text" in ctx.exception.message_dict)

    def test_valid_enum_values_pass(self):
        """9. Valid enum/choice values pass validation."""
        claim = Claim.objects.create(user=self.user, text="This is a valid claim.")
        analysis = Analysis(claim=claim, verdict=Verdict.CREDIBLE)
        analysis.full_clean()  # Should not raise exception
        analysis.save()
        self.assertEqual(analysis.verdict, Verdict.CREDIBLE)

    def test_invalid_enum_values_fail(self):
        """10. Invalid enum/choice values fail model validation."""
        claim = Claim.objects.create(user=self.user, text="This is a valid claim.")
        analysis = Analysis(claim=claim, verdict="INVALID_VALUE")
        with self.assertRaises(ValidationError) as ctx:
            analysis.full_clean()
        self.assertTrue("verdict" in ctx.exception.message_dict)

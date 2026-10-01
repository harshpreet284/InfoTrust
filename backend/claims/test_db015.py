from django.test import TestCase
from django.core.management import call_command
from django.core.management.base import CommandError
from django.contrib.auth import get_user_model
from claims.models import Claim
from analysis.models import Analysis

User = get_user_model()

class SeedCommandTests(TestCase):
    def test_seed_command_requires_admin_password(self):
        """Test that the command fails clearly if no admin password is provided."""
        with self.assertRaises(CommandError) as context:
            call_command("seed")
        self.assertIn("Admin password must be provided", str(context.exception))

    def test_seed_command_creates_exact_counts(self):
        """Test that the seed command creates exactly the planned records."""
        call_command("seed", admin_password="testpassword123")
        
        # 1 admin + 2 sample users
        self.assertEqual(User.objects.count(), 3)
        self.assertTrue(User.objects.filter(email="admin@infotrust.local", is_superuser=True).exists())
        
        user1 = User.objects.get(email="user1@infotrust.local")
        self.assertFalse(user1.has_usable_password())
        
        user2 = User.objects.get(email="user2@infotrust.local")
        self.assertFalse(user2.has_usable_password())
        
        # Exactly 6 claims
        self.assertEqual(Claim.objects.count(), 6)
        
        # 3 completed claims with analyses
        self.assertEqual(Claim.objects.filter(status="COMPLETED").count(), 3)
        self.assertEqual(Analysis.objects.count(), 3)
        
        # Check that analysis verdicts cover CREDIBLE, UNCERTAIN, MISINFORMATION
        verdicts = Analysis.objects.values_list("verdict", flat=True)
        self.assertCountEqual(list(verdicts), ["CREDIBLE", "UNCERTAIN", "MISINFORMATION"])
        
        # 3 non-completed claims
        self.assertEqual(Claim.objects.exclude(status="COMPLETED").count(), 3)

    def test_seed_command_is_idempotent(self):
        """Test that running the command twice does not duplicate records."""
        call_command("seed", admin_password="testpassword123")
        user_count = User.objects.count()
        claim_count = Claim.objects.count()
        analysis_count = Analysis.objects.count()

        # Run second time
        call_command("seed", admin_password="testpassword123")
        
        self.assertEqual(User.objects.count(), user_count)
        self.assertEqual(Claim.objects.count(), claim_count)
        self.assertEqual(Analysis.objects.count(), analysis_count)

    def test_partial_seed_recovery(self):
        """Test recovery from a partially seeded database using granular deterministic lookups."""
        # Manually create 1 of the deterministic sample users
        user1 = User.objects.create_user(email="user1@infotrust.local", full_name="Sample User One", password=None)
        
        # Manually create 1 of the deterministic claims
        claim_text = "Seed Claim 4 (Pending): The sky is blue because of the ocean."
        Claim.objects.create(user=user1, text=claim_text, status="PENDING")
        
        # Assert initial state
        self.assertEqual(User.objects.count(), 1)
        self.assertEqual(Claim.objects.count(), 1)
        
        # Run seed command
        call_command("seed", admin_password="testpassword123")
        
        # Verify missing records were created
        self.assertEqual(User.objects.count(), 3)  # Admin + 2 sample
        self.assertEqual(Claim.objects.count(), 6) # Total 6 claims
        self.assertEqual(Analysis.objects.count(), 3) # Total 3 analyses
        
        # Verify the pre-existing user and claim were successfully reused (not duplicated)
        self.assertEqual(User.objects.filter(email="user1@infotrust.local").count(), 1)
        self.assertEqual(Claim.objects.filter(text=claim_text).count(), 1)

    def test_seed_fails_if_admin_is_not_superuser(self):
        """Test that seed fails cleanly if the admin email exists but is a normal user."""
        User.objects.create_user(email="admin@infotrust.local", full_name="Normal User", password="normalpassword")
        
        with self.assertRaises(CommandError) as context:
            call_command("seed", admin_password="testpassword123")
        self.assertIn("exists but is not an admin/superuser", str(context.exception))

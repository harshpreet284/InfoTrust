from django.test import TestCase
from django.contrib.admin.sites import site
from django.contrib.auth import get_user_model
from claims.models import Claim, ClaimFeedback
from analysis.models import Analysis
from audit.models import AuditLog

User = get_user_model()


class AdminRegistrationTests(TestCase):
    def test_models_are_registered(self):
        self.assertTrue(site.is_registered(User))
        self.assertTrue(site.is_registered(Claim))
        self.assertTrue(site.is_registered(ClaimFeedback))
        self.assertTrue(site.is_registered(Analysis))
        self.assertTrue(site.is_registered(AuditLog))

    def test_user_admin_configuration(self):
        admin_instance = site._registry[User]
        self.assertEqual(
            admin_instance.list_display,
            ("email", "full_name", "role", "is_active", "created_at")
        )
        self.assertEqual(
            admin_instance.list_filter,
            ("role", "is_active", "is_superuser")
        )
        self.assertEqual(
            admin_instance.search_fields,
            ("email", "full_name")
        )
        self.assertIn("password", admin_instance.exclude)

    def test_claim_admin_configuration(self):
        admin_instance = site._registry[Claim]
        self.assertEqual(
            admin_instance.list_display,
            ("id", "user", "status", "submitted_at")
        )
        self.assertEqual(
            admin_instance.list_filter,
            ("status", "submitted_at")
        )
        self.assertEqual(
            admin_instance.search_fields,
            ("id", "text", "user__email")
        )

    def test_claim_feedback_admin_configuration(self):
        admin_instance = site._registry[ClaimFeedback]
        self.assertEqual(
            admin_instance.list_display,
            ("user", "claim", "feedback_type")
        )
        self.assertEqual(
            admin_instance.list_filter,
            ("feedback_type",)
        )
        self.assertEqual(
            admin_instance.search_fields,
            ("user__email", "claim__id")
        )

    def test_analysis_admin_configuration(self):
        admin_instance = site._registry[Analysis]
        self.assertEqual(
            admin_instance.list_display,
            ("claim", "verdict", "credibility_score", "final_weighted_score", "analysis_timestamp")
        )
        self.assertEqual(
            admin_instance.list_filter,
            ("verdict", "model_prediction", "analysis_timestamp")
        )
        self.assertEqual(
            admin_instance.search_fields,
            ("claim__id", "fact_check_summary")
        )

    def test_audit_log_admin_configuration(self):
        admin_instance = site._registry[AuditLog]
        self.assertEqual(
            admin_instance.list_display,
            ("action", "user", "target", "timestamp")
        )
        self.assertEqual(
            admin_instance.list_filter,
            ("action", "timestamp")
        )
        self.assertEqual(
            admin_instance.search_fields,
            ("action", "target", "user__email", "id")
        )

    def test_audit_log_immutability(self):
        admin_instance = site._registry[AuditLog]
        self.assertFalse(admin_instance.has_add_permission(None))
        self.assertFalse(admin_instance.has_change_permission(None))
        self.assertFalse(admin_instance.has_delete_permission(None))

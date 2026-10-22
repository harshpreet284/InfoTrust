from django.contrib.auth import get_user_model
from django.test import TestCase

from .models import AuditLog
from .services import log_audit_event

User = get_user_model()


class AuditLogModelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="audittester@example.com",
            password="Password123!",
            full_name="Audit Tester",
        )

    def test_audit_log_creation(self):
        """Test that an AuditLog can be created and fields are persisted"""
        log = AuditLog.objects.create(
            user=self.user,
            action="TEST_ACTION",
            target="TestTarget",
            metadata={"key": "value"},
        )

        # Verify primary key
        self.assertIsNotNone(log.id)
        self.assertEqual(len(str(log.id)), 36)

        # Verify fields
        self.assertEqual(log.user, self.user)
        self.assertEqual(log.action, "TEST_ACTION")
        self.assertEqual(log.target, "TestTarget")
        self.assertEqual(log.metadata, {"key": "value"})
        self.assertIsNotNone(log.timestamp)

        # Verify reverse relation
        self.assertEqual(self.user.audit_logs.count(), 1)
        self.assertEqual(self.user.audit_logs.first().id, log.id)

    def test_audit_log_without_user(self):
        """Test that user is optional (e.g., system actions)"""
        log = AuditLog.objects.create(action="SYSTEM_STARTUP", metadata={})
        self.assertIsNone(log.user)
        self.assertEqual(log.action, "SYSTEM_STARTUP")


class AuditServiceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="auditservicetester@example.com",
            password="Password123!",
            full_name="Audit Service Tester",
        )

    def test_log_audit_event_success(self):
        """Test that log_audit_event creates and returns a persisted AuditLog instance"""
        log = log_audit_event(
            action="CLAIM_SUBMITTED",
            user=self.user,
            target="target-uuid-123",
            metadata={"status": "PENDING"},
        )
        self.assertIsNotNone(log.id)
        self.assertEqual(log.action, "CLAIM_SUBMITTED")
        self.assertEqual(log.user, self.user)
        self.assertEqual(log.target, "target-uuid-123")
        self.assertEqual(log.metadata, {"status": "PENDING"})
        self.assertIsNotNone(log.timestamp)

        persisted = AuditLog.objects.get(id=log.id)
        self.assertEqual(persisted.action, "CLAIM_SUBMITTED")

    def test_log_audit_event_without_user(self):
        """Test that log_audit_event works safely when user is None"""
        log = log_audit_event(
            action="SYSTEM_EVENT",
            user=None,
            target="system-target",
        )
        self.assertIsNone(log.user)
        self.assertEqual(log.action, "SYSTEM_EVENT")
        self.assertEqual(log.metadata, {})

    def test_log_audit_event_default_metadata(self):
        """Test that log_audit_event defaults metadata to empty dictionary when None"""
        log = log_audit_event(
            action="CLAIM_DELETED",
            user=self.user,
            target="target-uuid-456",
            metadata=None,
        )
        self.assertEqual(log.metadata, {})

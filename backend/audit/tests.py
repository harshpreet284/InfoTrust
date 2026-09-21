from django.test import TestCase

from django.contrib.auth import get_user_model
from .models import AuditLog

User = get_user_model()

class AuditLogModelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email='audittester@example.com',
            password='Password123!',
            full_name='Audit Tester'
        )

    def test_audit_log_creation(self):
        """Test that an AuditLog can be created and fields are persisted"""
        log = AuditLog.objects.create(
            user=self.user,
            action='TEST_ACTION',
            target='TestTarget',
            metadata={'key': 'value'}
        )
        
        # Verify primary key
        self.assertIsNotNone(log.id)
        self.assertEqual(len(str(log.id)), 36)
        
        # Verify fields
        self.assertEqual(log.user, self.user)
        self.assertEqual(log.action, 'TEST_ACTION')
        self.assertEqual(log.target, 'TestTarget')
        self.assertEqual(log.metadata, {'key': 'value'})
        self.assertIsNotNone(log.timestamp)
        
        # Verify reverse relation
        self.assertEqual(self.user.audit_logs.count(), 1)
        self.assertEqual(self.user.audit_logs.first().id, log.id)

    def test_audit_log_without_user(self):
        """Test that user is optional (e.g., system actions)"""
        log = AuditLog.objects.create(
            action='SYSTEM_STARTUP',
            metadata={}
        )
        self.assertIsNone(log.user)
        self.assertEqual(log.action, 'SYSTEM_STARTUP')

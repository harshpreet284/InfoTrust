from django.test import TestCase
from django.db import connection

class DB011IndexTests(TestCase):
    def test_user_email_indexed(self):
        """1. User email is indexed"""
        with connection.cursor() as cursor:
            constraints = connection.introspection.get_constraints(cursor, 'authentication_user')
            
            email_indexed = any(
                c['columns'] == ['email'] and (c['index'] or c['unique'])
                for c in constraints.values()
            )
            self.assertTrue(email_indexed, "User email should be indexed")

    def test_claim_submitted_at_indexed(self):
        """2. Claim submission date is indexed"""
        with connection.cursor() as cursor:
            constraints = connection.introspection.get_constraints(cursor, 'claims_claim')
            
            submitted_at_indexed = any(
                c['columns'] == ['submitted_at'] and c['index']
                for c in constraints.values()
            )
            self.assertTrue(submitted_at_indexed, "Claim submitted_at should be indexed")

    def test_claim_user_indexed(self):
        """3. Claim owner is indexed (ForeignKey auto-index)"""
        with connection.cursor() as cursor:
            constraints = connection.introspection.get_constraints(cursor, 'claims_claim')
            
            user_indexed = any(
                c['columns'] == ['user_id'] and c['index']
                for c in constraints.values()
            )
            self.assertTrue(user_indexed, "Claim user (owner) should be indexed")

    def test_analysis_verdict_indexed(self):
        """4. Analysis verdict is indexed"""
        with connection.cursor() as cursor:
            constraints = connection.introspection.get_constraints(cursor, 'analysis_analysis')
            
            verdict_indexed = any(
                c['columns'] == ['verdict'] and c['index']
                for c in constraints.values()
            )
            self.assertTrue(verdict_indexed, "Analysis verdict should be indexed")

    def test_analysis_credibility_score_indexed(self):
        """5. Analysis credibility score is indexed"""
        with connection.cursor() as cursor:
            constraints = connection.introspection.get_constraints(cursor, 'analysis_analysis')
            
            score_indexed = any(
                c['columns'] == ['credibility_score'] and c['index']
                for c in constraints.values()
            )
            self.assertTrue(score_indexed, "Analysis credibility_score should be indexed")

    def test_audit_log_timestamp_indexed(self):
        """6. Audit log timestamp is indexed"""
        with connection.cursor() as cursor:
            constraints = connection.introspection.get_constraints(cursor, 'audit_auditlog')
            
            timestamp_indexed = any(
                c['columns'] == ['timestamp'] and c['index']
                for c in constraints.values()
            )
            self.assertTrue(timestamp_indexed, "AuditLog timestamp should be indexed")

import uuid
from datetime import datetime, timezone
from django.test import TestCase
from pydantic import ValidationError

from claims.models import Claim
from claims.schemas import ClaimCreateSchema, ClaimResponseSchema


class TestClaimSchemas(TestCase):

    def test_claim_create_schema_valid_and_normalized(self):
        # Valid claim_text of at least 10 characters
        payload = {"claim_text": "   This is a valid claim text.   "}
        schema = ClaimCreateSchema(**payload)
        self.assertEqual(schema.claim_text, "This is a valid claim text.")

    def test_claim_create_schema_missing_text(self):
        payload = {}
        with self.assertRaises(ValidationError):
            ClaimCreateSchema(**payload)

    def test_claim_create_schema_exact_min_length(self):
        payload = {"claim_text": "   1234567890   "}
        schema = ClaimCreateSchema(**payload)
        self.assertEqual(schema.claim_text, "1234567890")

    def test_claim_create_schema_below_min_length(self):
        payload = {"claim_text": "   123456789   "} # 9 chars after trim
        with self.assertRaises(ValidationError):
            ClaimCreateSchema(**payload)

    def test_claim_create_schema_whitespace_only(self):
        payload = {"claim_text": "          "}
        with self.assertRaises(ValidationError):
            ClaimCreateSchema(**payload)

    def test_claim_create_schema_exact_max_length(self):
        payload = {"claim_text": "   " + ("A" * 2000) + "   "}
        schema = ClaimCreateSchema(**payload)
        self.assertEqual(len(schema.claim_text), 2000)

    def test_claim_create_schema_above_max_length(self):
        payload = {"claim_text": "   " + ("A" * 2001) + "   "}
        with self.assertRaises(ValidationError):
            ClaimCreateSchema(**payload)

    def test_claim_create_schema_plain_text_violation_basic(self):
        payload = {"claim_text": "This is a <b>valid</b> claim text."}
        with self.assertRaises(ValidationError) as ctx:
            ClaimCreateSchema(**payload)
        self.assertIn("HTML is not allowed", str(ctx.exception))

    def test_claim_create_schema_plain_text_violation_script(self):
        payload = {"claim_text": "<script>alert(1)</script>"}
        with self.assertRaises(ValidationError) as ctx:
            ClaimCreateSchema(**payload)
        self.assertIn("HTML is not allowed", str(ctx.exception))

    def test_claim_create_schema_plain_text_violation_link(self):
        payload = {"claim_text": "Check out <a href='x'>this link</a>"}
        with self.assertRaises(ValidationError) as ctx:
            ClaimCreateSchema(**payload)
        self.assertIn("HTML is not allowed", str(ctx.exception))

    def test_claim_create_schema_plain_text_valid_symbols(self):
        # Valid plain text with math and emoticons
        payload = {"claim_text": "I love it <3 and 5 < 10"}
        schema = ClaimCreateSchema(**payload)
        self.assertEqual(schema.claim_text, "I love it <3 and 5 < 10")

    def test_claim_response_schema_serialization(self):
        # Create an UNSAVED Claim instance
        claim_id = uuid.uuid4()
        now = datetime.now(timezone.utc)
        
        claim_instance = Claim(
            id=claim_id,
            text="This is a valid claim text of sufficient length.",
            status="PENDING",
            user_id=1,
            submitted_at=now,
            updated_at=now,
        )

        # Pass instance through ModelSchema
        schema = ClaimResponseSchema.model_validate(claim_instance)
        
        # Dump to JSON-compatible format
        dumped = schema.model_dump(mode="json")
        
        # Assert exact public keys are present
        self.assertEqual(set(dumped.keys()), {"id", "claim_text", "status", "created_at"})
        
        # Assert exact values map correctly
        self.assertEqual(dumped["id"], str(claim_id))
        self.assertEqual(dumped["claim_text"], claim_instance.text)
        self.assertEqual(dumped["status"], "PENDING")
        # Pydantic serializes datetime to isoformat
        # Note: the exact string representation varies slightly (e.g. trailing 'Z' vs '+00:00')
        # We parse it or ensure it's mapped correctly by checking it matches the submitted_at
        self.assertEqual(dumped["created_at"], schema.created_at.isoformat().replace('+00:00', 'Z'))
        
        # Assert internal fields are NOT present
        self.assertNotIn("text", dumped)
        self.assertNotIn("submitted_at", dumped)
        self.assertNotIn("updated_at", dumped)
        self.assertNotIn("user", dumped)
        self.assertNotIn("user_id", dumped)

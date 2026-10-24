import uuid
from datetime import date, datetime, timezone
from django.test import TestCase
from pydantic import ValidationError

from claims.models import Claim
from claims.schemas import (
    ALLOWED_CLAIM_ORDERING_FIELDS,
    AdminClaimFilterSchema,
    ClaimCreateSchema,
    ClaimHistoryFilterSchema,
    ClaimResponseSchema,
    ClaimUpdateSchema,
    _normalize_and_validate_status,
    _normalize_and_validate_verdict,
    _validate_ordering,
)


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


class TestClaimUpdateSchema(TestCase):
    def test_claim_update_schema_subclass_and_valid(self):
        """Verify ClaimUpdateSchema is a direct subclass of ClaimCreateSchema and validates correctly."""
        self.assertTrue(issubclass(ClaimUpdateSchema, ClaimCreateSchema))
        schema = ClaimUpdateSchema(claim_text="Valid claim text of proper length.")
        self.assertEqual(schema.claim_text, "Valid claim text of proper length.")


class TestClaimOrderingValidator(TestCase):
    def test_validate_ordering_allowed_values(self):
        """Verify _validate_ordering accepts None and all allowed claim ordering whitelist values."""
        self.assertIsNone(_validate_ordering(None))
        for field in ALLOWED_CLAIM_ORDERING_FIELDS:
            self.assertEqual(_validate_ordering(field), field)

    def test_validate_ordering_disallowed_value_raises_value_error(self):
        """Verify _validate_ordering raises ValueError for disallowed ordering fields."""
        with self.assertRaises(ValueError) as ctx:
            _validate_ordering("disallowed_field")
        self.assertIn("Invalid ordering 'disallowed_field'. Allowed fields:", str(ctx.exception))


class TestClaimFilterSchemas(TestCase):
    def test_claim_history_filter_schema_defaults(self):
        """Verify ClaimHistoryFilterSchema initializes with expected default pagination and filter values."""
        schema = ClaimHistoryFilterSchema()
        self.assertEqual(schema.page, 1)
        self.assertEqual(schema.page_size, 10)
        self.assertIsNone(schema.ordering)
        self.assertIsNone(schema.search)
        self.assertIsNone(schema.status)
        self.assertIsNone(schema.verdict)
        self.assertIsNone(schema.date_from)
        self.assertIsNone(schema.date_to)

    def test_claim_history_filter_schema_date_range_validation(self):
        """Verify ClaimHistoryFilterSchema raises ValidationError when date_from > date_to."""
        with self.assertRaises(ValidationError) as ctx:
            ClaimHistoryFilterSchema(date_from=date(2026, 1, 10), date_to=date(2026, 1, 5))
        self.assertIn("date_from (2026-01-10) cannot be after date_to (2026-01-05)", str(ctx.exception))

    def test_claim_history_filter_schema_pagination_bounds(self):
        """Verify ClaimHistoryFilterSchema raises ValidationError when page or page_size exceed bounds."""
        with self.assertRaises(ValidationError):
            ClaimHistoryFilterSchema(page=0)
        with self.assertRaises(ValidationError):
            ClaimHistoryFilterSchema(page_size=0)
        with self.assertRaises(ValidationError):
            ClaimHistoryFilterSchema(page_size=101)

    def test_normalize_and_validate_status_helper(self):
        """Verify _normalize_and_validate_status normalizes whitespace/case, accepts None, and rejects invalid values."""
        self.assertIsNone(_normalize_and_validate_status(None))
        self.assertIsNone(_normalize_and_validate_status("   "))
        self.assertEqual(_normalize_and_validate_status("  pending  "), "PENDING")
        with self.assertRaises(ValueError) as ctx:
            _normalize_and_validate_status("INVALID_STATUS")
        self.assertIn("Invalid status 'INVALID_STATUS'", str(ctx.exception))
        with self.assertRaises(ValueError):
            _normalize_and_validate_status(123)

    def test_normalize_and_validate_verdict_helper(self):
        """Verify _normalize_and_validate_verdict normalizes whitespace/case, accepts None, and rejects invalid values."""
        self.assertIsNone(_normalize_and_validate_verdict(None))
        self.assertIsNone(_normalize_and_validate_verdict("   "))
        self.assertEqual(_normalize_and_validate_verdict("  credible  "), "CREDIBLE")
        with self.assertRaises(ValueError) as ctx:
            _normalize_and_validate_verdict("INVALID_VERDICT")
        self.assertIn("Invalid verdict 'INVALID_VERDICT'", str(ctx.exception))
        with self.assertRaises(ValueError):
            _normalize_and_validate_verdict(123)

    def test_admin_claim_filter_schema_user_id_parsing(self):
        """Verify AdminClaimFilterSchema parses valid UUID strings and raises ValidationError for invalid strings."""
        valid_uuid_str = "e3c9d748-0248-4351-a1b7-a359be2dcbe9"
        schema = AdminClaimFilterSchema(user_id=valid_uuid_str)
        self.assertEqual(schema.user_id, uuid.UUID(valid_uuid_str))

        with self.assertRaises(ValidationError):
            AdminClaimFilterSchema(user_id="invalid-uuid")

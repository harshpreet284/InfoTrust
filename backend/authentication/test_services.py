from unittest.mock import patch

from django.db import IntegrityError
from django.test import TestCase

from authentication.exceptions import DuplicateEmailError
from authentication.models import User
from authentication.schemas import RegistrationIn
from authentication.services import register_user


class TestRegistrationServiceConcurrency(TestCase):
    def test_register_user_duplicate_email_on_db_integrity_error(self):
        """Verify register_user catches race-condition IntegrityError on email and raises DuplicateEmailError."""
        payload = RegistrationIn(
            full_name="Jane Doe",
            email="race_duplicate@example.com",
            password="StrongPassword123!",
            confirm_password="StrongPassword123!",
        )
        # Pre-check passes because user does not exist in DB yet.
        # create_user simulates race-condition collision raising IntegrityError.
        with patch.object(
            User.objects,
            "create_user",
            side_effect=IntegrityError("duplicate key value violates unique constraint on email"),
        ):
            with self.assertRaises(DuplicateEmailError) as ctx:
                register_user(payload)
            self.assertEqual(str(ctx.exception), "This email is already registered.")

    def test_register_user_unrelated_db_integrity_error_reraised(self):
        """Verify register_user re-raises non-email IntegrityError without masking."""
        payload = RegistrationIn(
            full_name="Jane Doe",
            email="unrelated_error@example.com",
            password="StrongPassword123!",
            confirm_password="StrongPassword123!",
        )
        with patch.object(
            User.objects,
            "create_user",
            side_effect=IntegrityError("check constraint violation"),
        ):
            with self.assertRaises(IntegrityError) as ctx:
                register_user(payload)
            self.assertIn("check constraint violation", str(ctx.exception))

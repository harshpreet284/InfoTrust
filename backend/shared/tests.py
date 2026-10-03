from django.test import TestCase
from shared.schemas import SuccessResponse, ErrorResponse
from pydantic import ValidationError


class TestAPIResponseSchemas(TestCase):
    def test_success_response_serialization(self):
        # success is exactly true
        # data contains the supplied payload
        # no undocumented fields are introduced
        response = SuccessResponse[dict](data={"user": "test_user"})
        
        serialized = response.model_dump()
        
        self.assertEqual(serialized["success"], True)
        self.assertEqual(serialized["data"], {"user": "test_user"})
        
        # Verify exactly 2 keys exist: success, data
        self.assertEqual(set(serialized.keys()), {"success", "data"})

    def test_error_response_serialization(self):
        # success is exactly false
        # message is preserved
        # error_code is preserved
        # no undocumented errors field is introduced
        response = ErrorResponse(
            message="Internal Server Error",
            error_code="INTERNAL_ERROR"
        )
        
        serialized = response.model_dump()
        
        self.assertEqual(serialized["success"], False)
        self.assertEqual(serialized["message"], "Internal Server Error")
        self.assertEqual(serialized["error_code"], "INTERNAL_ERROR")
        
        # Verify exactly 3 keys exist: success, message, error_code
        self.assertEqual(set(serialized.keys()), {"success", "message", "error_code"})

    def test_validation_response_compliance(self):
        # uses the same ErrorResponse structure
        # error_code is exactly VALIDATION_ERROR
        # no separate validation JSON structure is introduced
        response = ErrorResponse(
            message="email: value is not a valid email address.",
            error_code="VALIDATION_ERROR"
        )
        
        serialized = response.model_dump()
        
        self.assertEqual(serialized["success"], False)
        self.assertEqual(serialized["message"], "email: value is not a valid email address.")
        self.assertEqual(serialized["error_code"], "VALIDATION_ERROR")
        
        # Verify exactly 3 keys exist
        self.assertEqual(set(serialized.keys()), {"success", "message", "error_code"})

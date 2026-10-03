import json
from django.core.exceptions import ObjectDoesNotExist
from django.db import IntegrityError
from django.http import Http404
from django.test import TestCase, override_settings
from ninja import NinjaAPI, Schema
from ninja.errors import AuthenticationError, AuthorizationError, HttpError
from ninja.testing import TestClient

from config.urls import api as global_api
from shared.exception_handlers import setup_exception_handlers


class TestGlobalExceptionHandlersRegistration(TestCase):
    def test_handlers_registered_on_global_api(self):
        registered_handlers = global_api._exception_handlers.keys()
        
        from ninja.errors import ValidationError
        
        self.assertIn(ValidationError, registered_handlers)
        self.assertIn(AuthenticationError, registered_handlers)
        self.assertIn(AuthorizationError, registered_handlers)
        self.assertIn(HttpError, registered_handlers)
        self.assertIn(Http404, registered_handlers)
        self.assertIn(ObjectDoesNotExist, registered_handlers)
        self.assertIn(IntegrityError, registered_handlers)
        self.assertIn(Exception, registered_handlers)


# Module level test api
test_api = NinjaAPI(version="test")
setup_exception_handlers(test_api)

class DiagnosticPayload(Schema):
    field1: str
    field2: int

@test_api.post("/test-validation")
def raise_validation(request, payload: DiagnosticPayload):
    return {"status": "ok"}

@test_api.get("/test-authentication")
def raise_authentication(request):
    raise AuthenticationError("Custom auth error")

@test_api.get("/test-authorization")
def raise_authorization(request):
    raise AuthorizationError("Custom authz error")

@test_api.get("/test-http-error/{code}")
def raise_http_error(request, code: int):
    raise HttpError(code, "Custom http error")

@test_api.get("/test-http404")
def raise_http404(request):
    raise Http404("Custom 404")

@test_api.get("/test-object-does-not-exist")
def raise_object_does_not_exist(request):
    raise ObjectDoesNotExist("Object not found")

@test_api.get("/test-integrity")
def raise_integrity(request):
    raise IntegrityError("DB error")

@test_api.get("/test-exception")
def raise_exception(request):
    raise Exception("Unexpected error")

from django.urls import path
urlpatterns = [
    path("", test_api.urls),
]

@override_settings(ROOT_URLCONF=__name__)
class TestExceptionHandlersBehavior(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

    def assertErrorResponse(self, response, expected_status, expected_error_code):
        self.assertEqual(response.status_code, expected_status)
        data = json.loads(response.content)
        
        self.assertEqual(set(data.keys()), {"success", "message", "error_code"})
        self.assertEqual(data["success"], False)
        self.assertEqual(data["error_code"], expected_error_code)
        self.assertTrue(isinstance(data["message"], str))
        self.assertTrue(len(data["message"]) > 0)
        
        return data

    def test_validation_error(self):
        response = self.client.post("/test-validation", data={"field1": "ok", "field2": "not_an_int"}, content_type="application/json")
        data = self.assertErrorResponse(response, 422, "VALIDATION_ERROR")
        self.assertIn("field2", data["message"])

    def test_authentication_error(self):
        response = self.client.get("/test-authentication")
        data = self.assertErrorResponse(response, 401, "AUTHENTICATION_ERROR")
        self.assertTrue(isinstance(data["message"], str))

    def test_authorization_error(self):
        response = self.client.get("/test-authorization")
        data = self.assertErrorResponse(response, 403, "PERMISSION_DENIED")
        self.assertTrue(isinstance(data["message"], str))

    def test_http_error_401(self):
        response = self.client.get("/test-http-error/401")
        self.assertErrorResponse(response, 401, "AUTHENTICATION_ERROR")

    def test_http_error_403(self):
        response = self.client.get("/test-http-error/403")
        self.assertErrorResponse(response, 403, "PERMISSION_DENIED")

    def test_http_error_404(self):
        response = self.client.get("/test-http-error/404")
        self.assertErrorResponse(response, 404, "NOT_FOUND")
        
    def test_http_error_generic(self):
        response = self.client.get("/test-http-error/429")
        self.assertErrorResponse(response, 429, "HTTP_429_ERROR")

    def test_http404_error(self):
        response = self.client.get("/test-http404")
        self.assertErrorResponse(response, 404, "NOT_FOUND")

    def test_object_does_not_exist_error(self):
        response = self.client.get("/test-object-does-not-exist")
        self.assertErrorResponse(response, 404, "NOT_FOUND")

    def test_integrity_error(self):
        response = self.client.get("/test-integrity")
        data = self.assertErrorResponse(response, 409, "DATABASE_ERROR")
        self.assertEqual(data["message"], "Database integrity error.")

    def test_unexpected_exception(self):
        response = self.client.get("/test-exception")
        data = self.assertErrorResponse(response, 500, "INTERNAL_ERROR")
        self.assertEqual(data["message"], "An unexpected server error occurred.")

import json
import math
import uuid
from unittest.mock import patch

from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from ninja_jwt.tokens import RefreshToken

from authentication.models import User
from authentication.schemas import AuthErrorOut, RegistrationConflictOut
from claims.models import Claim, ClaimStatus
from config.urls import api
from shared.schemas import ErrorResponse, RateLimitErrorOut, ServiceUnavailableErrorOut


class TestOpenAPISchemaStructure(TestCase):
    def setUp(self):
        self.schema = api.get_openapi_schema()
        self.paths = self.schema.get("paths", {})
        self.components = self.schema.get("components", {})

    def test_openapi_metadata(self):
        self.assertTrue(self.schema.get("openapi", "").startswith("3."))
        info = self.schema.get("info", {})
        self.assertEqual(info.get("title"), "InfoTrust API")
        self.assertEqual(info.get("version"), "1.0.0")
        self.assertIn("InfoTrust", info.get("description", ""))

    def test_unique_paths_and_operations_count(self):
        expected_paths = {
            "/api/v1/auth/register",
            "/api/v1/auth/login",
            "/api/v1/auth/refresh",
            "/api/v1/auth/logout",
            "/api/v1/auth/me",
            "/api/v1/claims",
            "/api/v1/claims/history",
            "/api/v1/claims/{claim_id}",
            "/api/v1/admin/claims",
        }
        self.assertEqual(set(self.paths.keys()), expected_paths)
        self.assertEqual(len(self.paths), 9)

        expected_operations = {
            ("post", "/api/v1/auth/register"),
            ("post", "/api/v1/auth/login"),
            ("post", "/api/v1/auth/refresh"),
            ("post", "/api/v1/auth/logout"),
            ("get", "/api/v1/auth/me"),
            ("post", "/api/v1/claims"),
            ("get", "/api/v1/claims/history"),
            ("get", "/api/v1/claims/{claim_id}"),
            ("patch", "/api/v1/claims/{claim_id}"),
            ("delete", "/api/v1/claims/{claim_id}"),
            ("get", "/api/v1/admin/claims"),
        }
        actual_operations = set()
        total_operations = 0
        for path_key, path_item in self.paths.items():
            for method in ["get", "post", "put", "patch", "delete"]:
                if method in path_item:
                    actual_operations.add((method, path_key))
                    total_operations += 1
        self.assertEqual(actual_operations, expected_operations)
        self.assertEqual(total_operations, 11)

    def test_operation_summaries_descriptions_and_tags(self):
        valid_tags = {"Authentication", "Claims", "Admin"}
        for path_key, path_item in self.paths.items():
            for method in ["get", "post", "put", "patch", "delete"]:
                if method in path_item:
                    op = path_item[method]
                    self.assertTrue(
                        op.get("summary"),
                        f"Missing summary on {method.upper()} {path_key}",
                    )
                    self.assertTrue(
                        op.get("description"),
                        f"Missing description on {method.upper()} {path_key}",
                    )
                    op_tags = set(op.get("tags", []))
                    self.assertTrue(
                        op_tags.intersection(valid_tags),
                        f"Missing expected tag on {method.upper()} {path_key}: {op_tags}",
                    )

    def test_no_untyped_dict_responses(self):
        for path_key, path_item in self.paths.items():
            for method in ["get", "post", "put", "patch", "delete"]:
                if method in path_item:
                    op = path_item[method]
                    for status_code, resp in op.get("responses", {}).items():
                        content = resp.get("content", {})
                        if "application/json" in content:
                            schema = content["application/json"].get("schema", {})
                            is_untyped_dict = (
                                schema.get("type") == "object"
                                and schema.get("additionalProperties") is True
                                and "properties" not in schema
                            )
                            self.assertFalse(
                                is_untyped_dict,
                                f"Untyped dict response found on {method.upper()} {path_key} [{status_code}]",
                            )

    def test_delete_claim_204_semantics(self):
        delete_op = self.paths["/api/v1/claims/{claim_id}"]["delete"]
        self.assertEqual(delete_op.get("summary"), "Soft-delete claim")
        self.assertIn("soft-delete", delete_op.get("description", "").lower())

        responses = delete_op.get("responses", {})
        code_key = 204 if 204 in responses else "204"
        self.assertIn(code_key, responses)
        resp_204 = responses[code_key]
        self.assertEqual(resp_204.get("description"), "No Content")
        self.assertNotIn(
            "content",
            resp_204,
            "DELETE 204 must not declare a response body or JSON schema in OpenAPI.",
        )

    def test_throttled_429_retry_after_and_schema_preservation(self):
        throttled_ops = [
            self.paths["/api/v1/auth/register"]["post"],
            self.paths["/api/v1/auth/login"]["post"],
            self.paths["/api/v1/claims"]["post"],
        ]
        for op in throttled_ops:
            responses = op.get("responses", {})
            code_429 = 429 if 429 in responses else "429"
            self.assertIn(code_429, responses)
            resp_429 = responses[code_429]

            # 1. Schema must be preserved (RateLimitErrorOut)
            content = resp_429.get("content", {})
            self.assertIn("application/json", content)
            schema_ref = content["application/json"].get("schema", {}).get("$ref", "")
            self.assertTrue(
                schema_ref.endswith("RateLimitErrorOut"),
                f"Expected RateLimitErrorOut schema on 429, got: {schema_ref}",
            )

            # 2. Retry-After header must be documented
            headers = resp_429.get("headers", {})
            self.assertIn(
                "Retry-After",
                headers,
                f"Missing Retry-After header on 429 in op: {op.get('summary')}",
            )
            self.assertEqual(
                headers["Retry-After"].get("schema", {}).get("type"), "integer"
            )

    def test_throttled_503_header_accuracy(self):
        throttled_ops = [
            self.paths["/api/v1/auth/register"]["post"],
            self.paths["/api/v1/auth/login"]["post"],
            self.paths["/api/v1/claims"]["post"],
        ]
        for op in throttled_ops:
            responses = op.get("responses", {})
            code_503 = 503 if 503 in responses else "503"
            self.assertIn(code_503, responses)
            resp_503 = responses[code_503]

            # 1. Schema must be ServiceUnavailableErrorOut
            content = resp_503.get("content", {})
            self.assertIn("application/json", content)
            schema_ref = content["application/json"].get("schema", {}).get("$ref", "")
            self.assertTrue(
                schema_ref.endswith("ServiceUnavailableErrorOut"),
                f"Expected ServiceUnavailableErrorOut schema on 503, got: {schema_ref}",
            )

            # 2. 503 must NOT document headers (no Retry-After)
            self.assertNotIn(
                "headers",
                resp_503,
                f"HTTP 503 must not document Retry-After headers in op: {op.get('summary')}",
            )

    def test_security_schemes_and_application(self):
        sec_schemes = self.components.get("securitySchemes", {})
        self.assertIn("RoleAuth", sec_schemes)
        self.assertIn("AdminEndpointAuth", sec_schemes)

        for name, scheme in sec_schemes.items():
            self.assertEqual(scheme.get("type"), "http")
            self.assertEqual(scheme.get("scheme"), "bearer")
            self.assertEqual(scheme.get("bearerFormat"), "JWT")
            self.assertTrue(len(scheme.get("description", "")) > 0)

        # Public endpoints must not have security
        public_ops = [
            self.paths["/api/v1/auth/register"]["post"],
            self.paths["/api/v1/auth/login"]["post"],
            self.paths["/api/v1/auth/refresh"]["post"],
            self.paths["/api/v1/auth/logout"]["post"],
        ]
        for op in public_ops:
            self.assertNotIn("security", op)

        # Secured endpoints must have security
        secured_ops = [
            self.paths["/api/v1/auth/me"]["get"],
            self.paths["/api/v1/claims"]["post"],
            self.paths["/api/v1/claims/history"]["get"],
            self.paths["/api/v1/claims/{claim_id}"]["get"],
            self.paths["/api/v1/claims/{claim_id}"]["patch"],
            self.paths["/api/v1/claims/{claim_id}"]["delete"],
            self.paths["/api/v1/admin/claims"]["get"],
        ]
        for op in secured_ops:
            self.assertIn("security", op)

    def test_zero_leakage_of_internal_ai_implementation_details(self):
        serialized_schema = json.dumps(self.schema).lower()
        forbidden_terms = [
            "gemini",
            "anthropic",
            "analysisservice",
            "celery",
            "internal prompt",
            "system_instruction",
        ]
        for term in forbidden_terms:
            self.assertNotIn(
                term,
                serialized_schema,
                f"Forbidden internal term '{term}' leaked into public OpenAPI schema.",
            )


class TestOpenAPIDocsAndRedirects(TestCase):
    def setUp(self):
        self.client = Client()

    def test_openapi_json_endpoint(self):
        resp = self.client.get("/api/v1/openapi.json")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("application/json", resp.headers.get("Content-Type", ""))
        data = resp.json()
        self.assertEqual(data.get("info", {}).get("title"), "InfoTrust API")

    def test_docs_html_endpoint(self):
        resp = self.client.get("/api/v1/docs")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("text/html", resp.headers.get("Content-Type", ""))
        self.assertIn(b"swagger-ui", resp.content.lower())

        resp_slash = self.client.get("/api/v1/docs/")
        self.assertEqual(resp_slash.status_code, 302)
        self.assertEqual(resp_slash.headers.get("Location"), "/api/v1/docs")

        resp_follow = self.client.get("/api/v1/docs/", follow=True)
        self.assertEqual(resp_follow.status_code, 200)
        self.assertIn("text/html", resp_follow.headers.get("Content-Type", ""))

    def test_legacy_docs_redirects(self):
        resp = self.client.get("/api/docs")
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.headers.get("Location"), "/api/v1/docs")

        resp_slash = self.client.get("/api/docs/")
        self.assertEqual(resp_slash.status_code, 302)
        self.assertEqual(resp_slash.headers.get("Location"), "/api/v1/docs")

    def test_legacy_openapi_json_redirect(self):
        resp = self.client.get("/api/openapi.json")
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.headers.get("Location"), "/api/v1/openapi.json")


class TestRuntimeContractValidation(TestCase):
    def setUp(self):
        cache.clear()
        self.client = Client()
        self.user = User.objects.create_user(
            email="contract_user@example.com",
            full_name="Contract User",
            password="StrongPassword123!",
        )
        self.token = str(RefreshToken.for_user(self.user).access_token)
        self.auth_headers = {"HTTP_AUTHORIZATION": f"Bearer {self.token}"}

    def test_runtime_422_matches_error_response_schema(self):
        resp = self.client.post(
            "/api/v1/auth/register",
            data=json.dumps({}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 422)
        validated = ErrorResponse.model_validate(resp.json())
        self.assertFalse(validated.success)
        self.assertEqual(validated.error_code, "VALIDATION_ERROR")

    def test_runtime_409_register_matches_conflict_schema(self):
        payload = {
            "email": self.user.email,
            "full_name": "Duplicate User",
            "password": "StrongPassword123!",
            "confirm_password": "StrongPassword123!",
        }
        resp = self.client.post(
            "/api/v1/auth/register",
            data=json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 409)
        validated = RegistrationConflictOut.model_validate(resp.json())
        self.assertFalse(validated.success)
        self.assertIn("email", validated.errors)

    def test_runtime_401_login_matches_auth_error_out_schema(self):
        payload = {"email": "wrong@example.com", "password": "WrongPassword123!"}
        resp = self.client.post(
            "/api/v1/auth/login",
            data=json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 401)
        validated = AuthErrorOut.model_validate(resp.json())
        self.assertFalse(validated.success)
        self.assertEqual(validated.message, "Invalid email or password.")

    def test_runtime_403_login_disabled_matches_auth_error_out_schema(self):
        self.user.is_active = False
        self.user.save()
        payload = {
            "email": self.user.email,
            "password": "StrongPassword123!",
        }
        resp = self.client.post(
            "/api/v1/auth/login",
            data=json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 403)
        validated = AuthErrorOut.model_validate(resp.json())
        self.assertFalse(validated.success)
        self.assertEqual(validated.message, "This account has been disabled.")

    def test_runtime_401_protected_endpoint_matches_error_response_schema(self):
        resp = self.client.get("/api/v1/auth/me")
        self.assertEqual(resp.status_code, 401)
        validated = ErrorResponse.model_validate(resp.json())
        self.assertFalse(validated.success)
        self.assertEqual(validated.error_code, "AUTHENTICATION_ERROR")

    def test_runtime_403_admin_endpoint_matches_error_response_schema(self):
        resp = self.client.get("/api/v1/admin/claims", **self.auth_headers)
        self.assertEqual(resp.status_code, 403)
        validated = ErrorResponse.model_validate(resp.json())
        self.assertFalse(validated.success)
        self.assertEqual(validated.error_code, "PERMISSION_DENIED")

    def test_runtime_404_claim_matches_error_response_schema(self):
        missing_id = uuid.uuid4()
        resp = self.client.get(f"/api/v1/claims/{missing_id}", **self.auth_headers)
        self.assertEqual(resp.status_code, 404)
        validated = ErrorResponse.model_validate(resp.json())
        self.assertFalse(validated.success)
        self.assertEqual(validated.error_code, "NOT_FOUND")

    def test_runtime_409_claim_update_conflict_matches_error_response_schema(self):
        claim = Claim.objects.create(
            user=self.user,
            text="Claim text with enough characters to pass validation",
            status=ClaimStatus.COMPLETED,
        )
        payload = {"claim_text": "Updated text with enough characters"}
        resp = self.client.patch(
            f"/api/v1/claims/{claim.id}",
            data=json.dumps(payload),
            content_type="application/json",
            **self.auth_headers,
        )
        self.assertEqual(resp.status_code, 409)
        validated = ErrorResponse.model_validate(resp.json())
        self.assertFalse(validated.success)
        self.assertEqual(validated.error_code, "HTTP_409_ERROR")

    def test_runtime_delete_204_bodyless_and_soft_delete(self):
        claim = Claim.objects.create(
            user=self.user,
            text="Pending claim text with enough characters",
            status=ClaimStatus.PENDING,
        )
        resp = self.client.delete(f"/api/v1/claims/{claim.id}", **self.auth_headers)
        self.assertEqual(resp.status_code, 204)
        self.assertEqual(resp.content, b"")
        self.assertEqual(resp.headers.get("Content-Length"), "0")

        claim.refresh_from_db()
        self.assertTrue(claim.is_deleted)

    def test_runtime_429_matches_rate_limit_error_out_schema(self):
        # Trigger rate limit on login by exhausting quota
        login_payload = {
            "email": self.user.email,
            "password": "StrongPassword123!",
        }
        # 10 allowed, 11th throttled under 10/min rate limit
        for _ in range(10):
            self.client.post(
                "/api/v1/auth/login",
                data=json.dumps(login_payload),
                content_type="application/json",
            )

        resp = self.client.post(
            "/api/v1/auth/login",
            data=json.dumps(login_payload),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 429)
        validated = RateLimitErrorOut.model_validate(resp.json())
        self.assertFalse(validated.success)
        self.assertTrue(resp.has_header("Retry-After"))

    @override_settings(RATE_LIMIT_FAIL_CLOSED=True)
    def test_runtime_503_matches_service_unavailable_error_out_schema(self):
        login_payload = {
            "email": self.user.email,
            "password": "StrongPassword123!",
        }
        with patch.object(cache, "get", side_effect=Exception("Cache failure")):
            resp = self.client.post(
                "/api/v1/auth/login",
                data=json.dumps(login_payload),
                content_type="application/json",
            )
        self.assertEqual(resp.status_code, 503)
        validated = ServiceUnavailableErrorOut.model_validate(resp.json())
        self.assertFalse(validated.success)
        self.assertFalse(resp.has_header("Retry-After"))

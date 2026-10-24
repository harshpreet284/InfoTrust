import json
import uuid

from django.core.cache import cache
from django.test import Client, TestCase

from authentication.models import User
from authentication.schemas import (
    AuthErrorOut,
    CurrentUserSuccessOut,
    LoginSuccessOut,
    LogoutSuccessOut,
    RefreshSuccessOut,
    RegistrationConflictOut,
    RegistrationSuccessOut,
)
from claims.schemas import ClaimUpdateSuccessOut
from shared.schemas import ErrorResponse


class BaseIntegrationTestCase(TestCase):
    """
    Common base class for API integration tests.
    Provides API-driven authentication helpers and targeted throttle-key cleanup.
    """

    test_ip = "198.51.100.100"

    def setUp(self):
        super().setUp()
        self.client = Client(REMOTE_ADDR=self.test_ip)

    def tearDown(self):
        # Targeted throttle cache cleanup to avoid cross-test interference
        # without calling indiscriminate cache.clear()
        cache.delete(f"throttle_login_{self.test_ip}")
        cache.delete(f"throttle_register_{self.test_ip}")
        super().tearDown()

    def api_register_and_login(
        self,
        full_name: str,
        email: str,
        password: str = "StrongPass123!",
    ) -> tuple[str, str, dict]:
        """
        API-driven user provisioning helper:
        Executes registration and login entirely through HTTP endpoints.
        """
        reg_resp = self.client.post(
            "/api/v1/auth/register",
            data=json.dumps(
                {
                    "full_name": full_name,
                    "email": email,
                    "password": password,
                    "confirm_password": password,
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(reg_resp.status_code, 201)
        reg_data = reg_resp.json()
        RegistrationSuccessOut.model_validate(reg_data)

        login_resp = self.client.post(
            "/api/v1/auth/login",
            data=json.dumps({"email": email, "password": password}),
            content_type="application/json",
        )
        self.assertEqual(login_resp.status_code, 200)
        login_data = login_resp.json()
        LoginSuccessOut.model_validate(login_data)

        access_token = login_data["data"]["access_token"]
        refresh_token = login_data["data"]["refresh_token"]
        user_info = login_data["data"]["user"]
        return access_token, refresh_token, user_info


class EndToEndUserAndClaimLifecycleIntegrationTests(BaseIntegrationTestCase):
    """
    Verifies the complete end-to-end user and claim lifecycle through the actual API stack.
    """

    test_ip = "198.51.100.101"

    def test_complete_user_lifecycle_and_claim_crud_flow(self):
        user_email = "lifecycle_user@example.com"
        user_password = "StrongPass123!"

        # 1. Register via API
        reg_resp = self.client.post(
            "/api/v1/auth/register",
            data=json.dumps(
                {
                    "full_name": "Lifecycle E2E User",
                    "email": user_email,
                    "password": user_password,
                    "confirm_password": user_password,
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(reg_resp.status_code, 201)
        reg_data = reg_resp.json()
        RegistrationSuccessOut.model_validate(reg_data)
        self.assertTrue(reg_data["success"])
        self.assertEqual(reg_data["message"], "Registration successful.")
        self.assertEqual(reg_data["data"]["email"], user_email)
        self.assertEqual(reg_data["data"]["role"], "USER")
        self.assertEqual(reg_data["data"]["full_name"], "Lifecycle E2E User")
        self.assertTrue(uuid.UUID(reg_data["data"]["id"]))

        # 2. Login via API
        login_resp = self.client.post(
            "/api/v1/auth/login",
            data=json.dumps({"email": user_email, "password": user_password}),
            content_type="application/json",
        )
        self.assertEqual(login_resp.status_code, 200)
        login_data = login_resp.json()
        LoginSuccessOut.model_validate(login_data)
        self.assertTrue(login_data["success"])
        self.assertEqual(login_data["message"], "Login successful.")
        access_token = login_data["data"]["access_token"]
        refresh_token = login_data["data"]["refresh_token"]
        auth_headers = {"HTTP_AUTHORIZATION": f"Bearer {access_token}"}

        # 3. Retrieve user profile via API
        me_resp = self.client.get("/api/v1/auth/me", **auth_headers)
        self.assertEqual(me_resp.status_code, 200)
        me_data = me_resp.json()
        CurrentUserSuccessOut.model_validate(me_data)
        self.assertTrue(me_data["success"])
        self.assertEqual(me_data["message"], "User profile retrieved successfully.")
        self.assertEqual(me_data["data"]["email"], user_email)

        # 4. Submit a new claim via API
        claim_text_original = (
            "Clinical vaccine trial results announced by international health agency."
        )
        submit_resp = self.client.post(
            "/api/v1/claims",
            data=json.dumps({"claim_text": claim_text_original}),
            content_type="application/json",
            **auth_headers,
        )
        self.assertEqual(submit_resp.status_code, 201)
        submit_data = submit_resp.json()
        self.assertTrue(submit_data["success"])
        self.assertEqual(submit_data["message"], "Claim submitted successfully.")
        self.assertEqual(
            set(submit_data["data"].keys()),
            {"id", "status", "claim_text", "created_at"},
        )
        self.assertEqual(submit_data["data"]["status"], "PENDING")
        self.assertEqual(submit_data["data"]["claim_text"], claim_text_original)
        claim_id = submit_data["data"]["id"]
        self.assertTrue(uuid.UUID(str(claim_id)))

        # Clean up per-user throttle key on claim submit
        self.addCleanup(cache.delete, f"throttle_claim_submit_{reg_data['data']['id']}")

        # 5. List claims in history
        history_resp = self.client.get("/api/v1/claims/history", **auth_headers)
        self.assertEqual(history_resp.status_code, 200)
        history_data = history_resp.json()
        self.assertEqual(
            set(history_data.keys()),
            {"count", "next", "previous", "results"},
        )
        self.assertEqual(history_data["count"], 1)
        self.assertEqual(len(history_data["results"]), 1)
        history_item = history_data["results"][0]
        self.assertEqual(
            set(history_item.keys()),
            {
                "id",
                "claim_text",
                "status",
                "verdict",
                "credibility_score",
                "created_at",
            },
        )
        self.assertEqual(str(history_item["id"]), str(claim_id))
        self.assertEqual(history_item["status"], "PENDING")
        self.assertEqual(history_item["claim_text"], claim_text_original)
        self.assertIsNone(history_item["verdict"])
        self.assertIsNone(history_item["credibility_score"])

        # 6. Retrieve claim details
        detail_resp = self.client.get(f"/api/v1/claims/{claim_id}", **auth_headers)
        self.assertEqual(detail_resp.status_code, 200)
        detail_data = detail_resp.json()
        self.assertTrue(detail_data["success"])
        self.assertEqual(detail_data["message"], "Claim retrieved successfully.")
        self.assertEqual(
            set(detail_data["data"].keys()),
            {
                "id",
                "claim_text",
                "status",
                "created_at",
                "updated_at",
                "analysis_available",
            },
        )
        self.assertEqual(str(detail_data["data"]["id"]), str(claim_id))
        self.assertEqual(detail_data["data"]["claim_text"], claim_text_original)
        self.assertEqual(detail_data["data"]["status"], "PENDING")
        self.assertFalse(detail_data["data"]["analysis_available"])

        # 7. Update pending claim text
        claim_text_updated = (
            "Updated clinical vaccine trial results published with peer-reviewed data."
        )
        patch_resp = self.client.patch(
            f"/api/v1/claims/{claim_id}",
            data=json.dumps({"claim_text": claim_text_updated}),
            content_type="application/json",
            **auth_headers,
        )
        self.assertEqual(patch_resp.status_code, 200)
        patch_data = patch_resp.json()
        ClaimUpdateSuccessOut.model_validate(patch_data)
        self.assertTrue(patch_data["success"])
        self.assertEqual(patch_data["message"], "Claim updated successfully.")
        self.assertEqual(str(patch_data["data"]["id"]), str(claim_id))

        # 8. Verify update persisted in subsequent retrieval
        detail_recheck_resp = self.client.get(
            f"/api/v1/claims/{claim_id}", **auth_headers
        )
        self.assertEqual(detail_recheck_resp.status_code, 200)
        self.assertEqual(
            detail_recheck_resp.json()["data"]["claim_text"], claim_text_updated
        )

        # 9. Soft-delete claim (HTTP 204 No Content, bodyless)
        delete_resp = self.client.delete(f"/api/v1/claims/{claim_id}", **auth_headers)
        self.assertEqual(delete_resp.status_code, 204)
        self.assertEqual(delete_resp.content, b"")

        # 10. Verify 404 on deleted claim detail
        post_del_detail_resp = self.client.get(
            f"/api/v1/claims/{claim_id}", **auth_headers
        )
        self.assertEqual(post_del_detail_resp.status_code, 404)
        err_data = post_del_detail_resp.json()
        ErrorResponse.model_validate(err_data)
        self.assertFalse(err_data["success"])
        self.assertEqual(err_data["error_code"], "NOT_FOUND")

        # 11. Verify exclusion from history
        post_del_hist_resp = self.client.get("/api/v1/claims/history", **auth_headers)
        self.assertEqual(post_del_hist_resp.status_code, 200)
        hist_empty_data = post_del_hist_resp.json()
        self.assertEqual(hist_empty_data["count"], 0)
        self.assertEqual(hist_empty_data["results"], [])

        # 12. Token refresh rotation
        refresh_resp = self.client.post(
            "/api/v1/auth/refresh",
            data=json.dumps({"refresh_token": refresh_token}),
            content_type="application/json",
        )
        self.assertEqual(refresh_resp.status_code, 200)
        refresh_data = refresh_resp.json()
        RefreshSuccessOut.model_validate(refresh_data)
        self.assertTrue(refresh_data["success"])
        self.assertEqual(refresh_data["message"], "Token refreshed successfully.")
        new_refresh_token = refresh_data["data"]["refresh_token"]

        # 13. Logout with active rotated refresh token
        logout_resp = self.client.post(
            "/api/v1/auth/logout",
            data=json.dumps({"refresh_token": new_refresh_token}),
            content_type="application/json",
        )
        self.assertEqual(logout_resp.status_code, 200)
        logout_data = logout_resp.json()
        LogoutSuccessOut.model_validate(logout_data)
        self.assertTrue(logout_data["success"])
        self.assertEqual(logout_data["message"], "Logged out successfully.")
        self.assertEqual(logout_data["data"], {})

        # 14. Verify blacklisted token rejected on subsequent refresh
        stale_refresh_resp = self.client.post(
            "/api/v1/auth/refresh",
            data=json.dumps({"refresh_token": new_refresh_token}),
            content_type="application/json",
        )
        self.assertEqual(stale_refresh_resp.status_code, 401)
        stale_data = stale_refresh_resp.json()
        AuthErrorOut.model_validate(stale_data)
        self.assertFalse(stale_data["success"])
        self.assertEqual(stale_data["message"], "Invalid or expired refresh token.")


class CrossTenantIsolationIntegrationTests(BaseIntegrationTestCase):
    """
    Verifies cross-tenant isolation and authorization boundaries between distinct users.
    """

    test_ip = "198.51.100.102"

    def test_cross_user_resource_isolation_and_boundary_enforcement(self):
        # 1. User A registers, logs in, and submits Claim A
        user_a_email = "user_a_iso@example.com"
        access_token_a, _, user_a_data = self.api_register_and_login(
            full_name="User Alpha", email=user_a_email
        )
        self.addCleanup(cache.delete, f"throttle_claim_submit_{user_a_data['id']}")
        headers_a = {"HTTP_AUTHORIZATION": f"Bearer {access_token_a}"}

        claim_a_resp = self.client.post(
            "/api/v1/claims",
            data=json.dumps(
                {
                    "claim_text": "Claim A: Economic policy inflation report by central bank."
                }
            ),
            content_type="application/json",
            **headers_a,
        )
        self.assertEqual(claim_a_resp.status_code, 201)
        claim_a_id = claim_a_resp.json()["data"]["id"]

        # 2. User B registers, logs in, and submits Claim B
        user_b_email = "user_b_iso@example.com"
        access_token_b, _, user_b_data = self.api_register_and_login(
            full_name="User Beta", email=user_b_email
        )
        self.addCleanup(cache.delete, f"throttle_claim_submit_{user_b_data['id']}")
        headers_b = {"HTTP_AUTHORIZATION": f"Bearer {access_token_b}"}

        claim_b_resp = self.client.post(
            "/api/v1/claims",
            data=json.dumps(
                {
                    "claim_text": "Claim B: Energy renewable transition study in European power grid."
                }
            ),
            content_type="application/json",
            **headers_b,
        )
        self.assertEqual(claim_b_resp.status_code, 201)
        claim_b_id = claim_b_resp.json()["data"]["id"]

        # 3. User B attempts unauthorized read on User A's claim
        read_forbidden = self.client.get(f"/api/v1/claims/{claim_a_id}", **headers_b)
        self.assertEqual(read_forbidden.status_code, 403)
        err_read = read_forbidden.json()
        ErrorResponse.model_validate(err_read)
        self.assertFalse(err_read["success"])
        self.assertEqual(err_read["error_code"], "PERMISSION_DENIED")

        # 4. User B attempts unauthorized update on User A's claim
        patch_forbidden = self.client.patch(
            f"/api/v1/claims/{claim_a_id}",
            data=json.dumps(
                {"claim_text": "Malicious attempt to tamper with User A claim text."}
            ),
            content_type="application/json",
            **headers_b,
        )
        self.assertEqual(patch_forbidden.status_code, 403)
        err_patch = patch_forbidden.json()
        ErrorResponse.model_validate(err_patch)
        self.assertFalse(err_patch["success"])
        self.assertEqual(err_patch["error_code"], "PERMISSION_DENIED")

        # 5. User B attempts unauthorized deletion of User A's claim
        delete_forbidden = self.client.delete(
            f"/api/v1/claims/{claim_a_id}", **headers_b
        )
        self.assertEqual(delete_forbidden.status_code, 403)
        err_delete = delete_forbidden.json()
        ErrorResponse.model_validate(err_delete)
        self.assertFalse(err_delete["success"])
        self.assertEqual(err_delete["error_code"], "PERMISSION_DENIED")

        # 6. Verify User B history only contains Claim B
        hist_b = self.client.get("/api/v1/claims/history", **headers_b)
        self.assertEqual(hist_b.status_code, 200)
        data_b = hist_b.json()
        self.assertEqual(data_b["count"], 1)
        self.assertEqual(str(data_b["results"][0]["id"]), str(claim_b_id))

        # 7. Verify User A history only contains Claim A
        hist_a = self.client.get("/api/v1/claims/history", **headers_a)
        self.assertEqual(hist_a.status_code, 200)
        data_a = hist_a.json()
        self.assertEqual(data_a["count"], 1)
        self.assertEqual(str(data_a["results"][0]["id"]), str(claim_a_id))

        # 8. User A updates and deletes Claim A successfully
        patch_a = self.client.patch(
            f"/api/v1/claims/{claim_a_id}",
            data=json.dumps(
                {"claim_text": "Claim A updated text with verified details."}
            ),
            content_type="application/json",
            **headers_a,
        )
        self.assertEqual(patch_a.status_code, 200)

        del_a = self.client.delete(f"/api/v1/claims/{claim_a_id}", **headers_a)
        self.assertEqual(del_a.status_code, 204)

        # 9. Verify User B's resource remains intact and unaffected
        recheck_b = self.client.get("/api/v1/claims/history", **headers_b)
        self.assertEqual(recheck_b.status_code, 200)
        self.assertEqual(recheck_b.json()["count"], 1)
        self.assertEqual(str(recheck_b.json()["results"][0]["id"]), str(claim_b_id))


class AdministrativeGovernanceIntegrationTests(BaseIntegrationTestCase):
    """
    Verifies multi-actor administrative flow: non-admin denial, admin claim review,
    admin detail read privilege, admin text-patch denial, and admin moderation deletion.
    """

    test_ip = "198.51.100.103"

    def setUp(self):
        super().setUp()
        # Admin account provisioned via ORM as authorized (cannot be registered via public API)
        self.admin_email = "e2e_admin@example.com"
        self.admin_password = "AdminPassSecure123!"
        self.admin_user = User.objects.create_user(
            email=self.admin_email,
            password=self.admin_password,
            full_name="E2E Platform Administrator",
            role="ADMIN",
        )

    def test_admin_oversight_and_cross_user_governance_flow(self):
        # 1. Standard user registers and authenticates via API
        user_email = "standard_gov_user@example.com"
        access_token_user, _, user_data = self.api_register_and_login(
            full_name="Standard Gov User", email=user_email
        )
        self.addCleanup(cache.delete, f"throttle_claim_submit_{user_data['id']}")
        user_headers = {"HTTP_AUTHORIZATION": f"Bearer {access_token_user}"}

        # 2. Standard user submits Claim 1 and Claim 2
        resp_c1 = self.client.post(
            "/api/v1/claims",
            data=json.dumps(
                {
                    "claim_text": "Claim 1: International trade agreement ratified by member states."
                }
            ),
            content_type="application/json",
            **user_headers,
        )
        self.assertEqual(resp_c1.status_code, 201)
        claim_1_id = resp_c1.json()["data"]["id"]

        resp_c2 = self.client.post(
            "/api/v1/claims",
            data=json.dumps(
                {
                    "claim_text": "Claim 2: Transportation infrastructure investment program announced."
                }
            ),
            content_type="application/json",
            **user_headers,
        )
        self.assertEqual(resp_c2.status_code, 201)
        claim_2_id = resp_c2.json()["data"]["id"]

        # 3. Standard user denied on administrative endpoint (HTTP 403)
        user_admin_attempt = self.client.get("/api/v1/admin/claims", **user_headers)
        self.assertEqual(user_admin_attempt.status_code, 403)
        err_user_admin = user_admin_attempt.json()
        ErrorResponse.model_validate(err_user_admin)
        self.assertFalse(err_user_admin["success"])
        self.assertEqual(err_user_admin["error_code"], "PERMISSION_DENIED")

        # 4. Unauthenticated request denied on admin endpoint (HTTP 401)
        unauth_admin_attempt = self.client.get("/api/v1/admin/claims")
        self.assertEqual(unauth_admin_attempt.status_code, 401)
        err_unauth_admin = unauth_admin_attempt.json()
        ErrorResponse.model_validate(err_unauth_admin)
        self.assertFalse(err_unauth_admin["success"])
        self.assertEqual(err_unauth_admin["error_code"], "AUTHENTICATION_ERROR")

        # 5. Administrator authenticates via public API endpoint
        admin_login_resp = self.client.post(
            "/api/v1/auth/login",
            data=json.dumps(
                {"email": self.admin_email, "password": self.admin_password}
            ),
            content_type="application/json",
        )
        self.assertEqual(admin_login_resp.status_code, 200)
        admin_access_token = admin_login_resp.json()["data"]["access_token"]
        admin_headers = {"HTTP_AUTHORIZATION": f"Bearer {admin_access_token}"}

        # 6. Admin lists all claims across all users
        admin_claims_resp = self.client.get("/api/v1/admin/claims", **admin_headers)
        self.assertEqual(admin_claims_resp.status_code, 200)
        admin_claims_data = admin_claims_resp.json()
        self.assertEqual(
            set(admin_claims_data.keys()),
            {"count", "next", "previous", "results"},
        )
        self.assertEqual(admin_claims_data["count"], 2)
        for item in admin_claims_data["results"]:
            self.assertEqual(
                set(item.keys()),
                {
                    "claim_id",
                    "claim_text",
                    "submitted_by",
                    "analysis_status",
                    "verdict",
                    "created_at",
                },
            )
        admin_claim_ids = {
            str(item["claim_id"]) for item in admin_claims_data["results"]
        }
        self.assertIn(str(claim_1_id), admin_claim_ids)
        self.assertIn(str(claim_2_id), admin_claim_ids)

        # 7. Admin views user's claim detail (Admin read privilege)
        admin_detail_resp = self.client.get(
            f"/api/v1/claims/{claim_1_id}", **admin_headers
        )
        self.assertEqual(admin_detail_resp.status_code, 200)
        detail_data = admin_detail_resp.json()
        self.assertTrue(detail_data["success"])
        self.assertEqual(
            set(detail_data["data"].keys()),
            {
                "id",
                "claim_text",
                "status",
                "created_at",
                "updated_at",
                "analysis_available",
            },
        )
        self.assertEqual(str(detail_data["data"]["id"]), str(claim_1_id))

        # 8. Admin cannot update user's claim text (HTTP 403 PERMISSION_DENIED)
        admin_patch_resp = self.client.patch(
            f"/api/v1/claims/{claim_1_id}",
            data=json.dumps(
                {"claim_text": "Admin attempting to alter user claim text improperly."}
            ),
            content_type="application/json",
            **admin_headers,
        )
        self.assertEqual(admin_patch_resp.status_code, 403)
        err_patch = admin_patch_resp.json()
        ErrorResponse.model_validate(err_patch)
        self.assertFalse(err_patch["success"])
        self.assertEqual(err_patch["error_code"], "PERMISSION_DENIED")

        # 9. Admin deletes user's claim for moderation (HTTP 204 No Content)
        admin_del_resp = self.client.delete(
            f"/api/v1/claims/{claim_1_id}", **admin_headers
        )
        self.assertEqual(admin_del_resp.status_code, 204)
        self.assertEqual(admin_del_resp.content, b"")

        # 10. Verify claim is soft-deleted and excluded for both user and admin
        user_check = self.client.get(f"/api/v1/claims/{claim_1_id}", **user_headers)
        self.assertEqual(user_check.status_code, 404)

        user_hist = self.client.get("/api/v1/claims/history", **user_headers)
        self.assertEqual(user_hist.status_code, 200)
        self.assertEqual(user_hist.json()["count"], 1)
        self.assertEqual(str(user_hist.json()["results"][0]["id"]), str(claim_2_id))

        admin_check = self.client.get("/api/v1/admin/claims", **admin_headers)
        self.assertEqual(admin_check.status_code, 200)
        self.assertEqual(admin_check.json()["count"], 1)
        self.assertEqual(
            str(admin_check.json()["results"][0]["claim_id"]), str(claim_2_id)
        )


class AuthenticationSecurityIntegrationTests(BaseIntegrationTestCase):
    """
    Verifies authentication rejection, token handling, and token lifecycle security.
    """

    test_ip = "198.51.100.104"

    def test_unauthenticated_requests_rejected_across_all_protected_operations(self):
        dummy_uuid = uuid.uuid4()
        protected_operations = [
            ("GET", "/api/v1/auth/me", None),
            (
                "POST",
                "/api/v1/claims",
                {"claim_text": "Valid length claim text for unauth testing."},
            ),
            ("GET", "/api/v1/claims/history", None),
            ("GET", f"/api/v1/claims/{dummy_uuid}", None),
            (
                "PATCH",
                f"/api/v1/claims/{dummy_uuid}",
                {"claim_text": "Valid length claim text for unauth testing."},
            ),
            ("DELETE", f"/api/v1/claims/{dummy_uuid}", None),
            ("GET", "/api/v1/admin/claims", None),
        ]

        for method, path, payload in protected_operations:
            with self.subTest(method=method, path=path):
                if method == "GET":
                    resp = self.client.get(path)
                elif method == "POST":
                    resp = self.client.post(
                        path,
                        data=json.dumps(payload or {}),
                        content_type="application/json",
                    )
                elif method == "PATCH":
                    resp = self.client.patch(
                        path,
                        data=json.dumps(payload or {}),
                        content_type="application/json",
                    )
                elif method == "DELETE":
                    resp = self.client.delete(path)
                else:
                    self.fail(f"Unhandled method: {method}")

                self.assertEqual(
                    resp.status_code,
                    401,
                    f"Expected HTTP 401 on unauthenticated {method} {path}, got {resp.status_code}",
                )
                err_data = resp.json()
                ErrorResponse.model_validate(err_data)
                self.assertFalse(err_data["success"])
                self.assertEqual(err_data["error_code"], "AUTHENTICATION_ERROR")

    def test_malformed_and_tampered_token_handling(self):
        malformed_headers = [
            (
                "Unsupported auth scheme",
                {"HTTP_AUTHORIZATION": "Token some_arbitrary_api_token"},
            ),
            ("Empty bearer token", {"HTTP_AUTHORIZATION": "Bearer "}),
            (
                "Tampered JWT token",
                {
                    "HTTP_AUTHORIZATION": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.corrupted.signature"
                },
            ),
        ]

        for desc, headers in malformed_headers:
            with self.subTest(case=desc):
                resp = self.client.get("/api/v1/auth/me", **headers)
                self.assertEqual(resp.status_code, 401)
                err_data = resp.json()
                ErrorResponse.model_validate(err_data)
                self.assertFalse(err_data["success"])
                self.assertEqual(err_data["error_code"], "AUTHENTICATION_ERROR")

    def test_token_rotation_and_revocation_lifecycle(self):
        user_email = "token_rotation_user@example.com"
        access_token_1, refresh_token_1, _ = self.api_register_and_login(
            full_name="Rotation User", email=user_email
        )

        # 1. Rotate refresh token
        refresh_resp = self.client.post(
            "/api/v1/auth/refresh",
            data=json.dumps({"refresh_token": refresh_token_1}),
            content_type="application/json",
        )
        self.assertEqual(refresh_resp.status_code, 200)
        refresh_data = refresh_resp.json()
        RefreshSuccessOut.model_validate(refresh_data)
        access_token_2 = refresh_data["data"]["access_token"]
        refresh_token_2 = refresh_data["data"]["refresh_token"]

        # 2. Replay rotated refresh_token_1 -> HTTP 401
        replay_resp = self.client.post(
            "/api/v1/auth/refresh",
            data=json.dumps({"refresh_token": refresh_token_1}),
            content_type="application/json",
        )
        self.assertEqual(replay_resp.status_code, 401)
        replay_data = replay_resp.json()
        AuthErrorOut.model_validate(replay_data)
        self.assertFalse(replay_data["success"])
        self.assertEqual(replay_data["message"], "Invalid or expired refresh token.")

        # 3. Use new access token successfully
        me_resp = self.client.get(
            "/api/v1/auth/me",
            HTTP_AUTHORIZATION=f"Bearer {access_token_2}",
        )
        self.assertEqual(me_resp.status_code, 200)

        # 4. Logout using refresh_token_2
        logout_resp = self.client.post(
            "/api/v1/auth/logout",
            data=json.dumps({"refresh_token": refresh_token_2}),
            content_type="application/json",
        )
        self.assertEqual(logout_resp.status_code, 200)
        LogoutSuccessOut.model_validate(logout_resp.json())

        # 5. Attempt refresh with logged-out refresh_token_2 -> HTTP 401
        revoked_resp = self.client.post(
            "/api/v1/auth/refresh",
            data=json.dumps({"refresh_token": refresh_token_2}),
            content_type="application/json",
        )
        self.assertEqual(revoked_resp.status_code, 401)
        revoked_data = revoked_resp.json()
        AuthErrorOut.model_validate(revoked_data)
        self.assertFalse(revoked_data["success"])
        self.assertEqual(revoked_data["message"], "Invalid or expired refresh token.")


class MultiClaimPaginationAndFilteringIntegrationTests(BaseIntegrationTestCase):
    """
    Verifies dynamic hypermedia pagination traversal and query filtering across multiple claims.
    """

    test_ip = "198.51.100.105"

    def test_multi_claim_pagination_traversal_and_filtering(self):
        user_email = "pagination_user@example.com"
        access_token, _, user_data = self.api_register_and_login(
            full_name="Pagination User", email=user_email
        )
        self.addCleanup(cache.delete, f"throttle_claim_submit_{user_data['id']}")
        headers = {"HTTP_AUTHORIZATION": f"Bearer {access_token}"}

        # Submit 3 claims with distinct topics
        claim_texts = [
            "Vaccine clinical trial results published in reputable health journal.",
            "Economic fiscal policy announcement regarding inflation interest rate.",
            "Climate emissions reduction treaty signed by participating global nations.",
        ]
        for text in claim_texts:
            c_resp = self.client.post(
                "/api/v1/claims",
                data=json.dumps({"claim_text": text}),
                content_type="application/json",
                **headers,
            )
            self.assertEqual(c_resp.status_code, 201)

        # 1. Page 1 query with page_size=2
        resp_p1 = self.client.get(
            "/api/v1/claims/history?page=1&page_size=2", **headers
        )
        self.assertEqual(resp_p1.status_code, 200)
        data_p1 = resp_p1.json()
        self.assertEqual(
            set(data_p1.keys()),
            {"count", "next", "previous", "results"},
        )
        self.assertEqual(data_p1["count"], 3)
        self.assertEqual(len(data_p1["results"]), 2)
        self.assertIsNone(data_p1["previous"])
        next_url = data_p1["next"]
        self.assertIsNotNone(next_url)
        self.assertIn("page=2", next_url)
        self.assertIn("page_size=2", next_url)

        # 2. Hypermedia traversal: follow the server's next URL directly
        resp_p2 = self.client.get(next_url, **headers)
        self.assertEqual(resp_p2.status_code, 200)
        data_p2 = resp_p2.json()
        self.assertEqual(
            set(data_p2.keys()),
            {"count", "next", "previous", "results"},
        )
        self.assertEqual(data_p2["count"], 3)
        self.assertEqual(len(data_p2["results"]), 1)
        self.assertIsNone(data_p2["next"])
        prev_url = data_p2["previous"]
        self.assertIsNotNone(prev_url)
        self.assertIn("page=1", prev_url)
        self.assertIn("page_size=2", prev_url)

        # 3. Hypermedia reverse traversal: follow previous URL directly
        resp_back = self.client.get(prev_url, **headers)
        self.assertEqual(resp_back.status_code, 200)
        data_back = resp_back.json()
        self.assertEqual(len(data_back["results"]), 2)
        self.assertEqual(
            [item["id"] for item in data_back["results"]],
            [item["id"] for item in data_p1["results"]],
        )

        # 4. Keyword search traversal
        resp_search = self.client.get(
            "/api/v1/claims/history?search=climate", **headers
        )
        self.assertEqual(resp_search.status_code, 200)
        data_search = resp_search.json()
        self.assertEqual(data_search["count"], 1)
        self.assertIn("Climate", data_search["results"][0]["claim_text"])

        # 5. Status filtering
        resp_status_pending = self.client.get(
            "/api/v1/claims/history?status=PENDING", **headers
        )
        self.assertEqual(resp_status_pending.status_code, 200)
        self.assertEqual(resp_status_pending.json()["count"], 3)

        resp_status_completed = self.client.get(
            "/api/v1/claims/history?status=COMPLETED", **headers
        )
        self.assertEqual(resp_status_completed.status_code, 200)
        self.assertEqual(resp_status_completed.json()["count"], 0)
        self.assertEqual(resp_status_completed.json()["results"], [])

        # 6. Out-of-bounds page returns empty list with preserved count
        resp_oob = self.client.get(
            "/api/v1/claims/history?page=999&page_size=10", **headers
        )
        self.assertEqual(resp_oob.status_code, 200)
        data_oob = resp_oob.json()
        self.assertEqual(data_oob["count"], 3)
        self.assertEqual(data_oob["results"], [])


class FrontendContractErrorResponsesIntegrationTests(BaseIntegrationTestCase):
    """
    Verifies frontend error envelope and status code conformance for validation,
    conflict, and not found cases.
    """

    test_ip = "198.51.100.106"

    def test_frontend_error_payload_conformance(self):
        # 1. Registration password mismatch -> HTTP 422 VALIDATION_ERROR
        resp_mismatch = self.client.post(
            "/api/v1/auth/register",
            data=json.dumps(
                {
                    "full_name": "Mismatch User",
                    "email": "mismatch@example.com",
                    "password": "Password123!",
                    "confirm_password": "DifferentPassword123!",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(resp_mismatch.status_code, 422)
        err_mismatch = resp_mismatch.json()
        ErrorResponse.model_validate(err_mismatch)
        self.assertFalse(err_mismatch["success"])
        self.assertEqual(err_mismatch["error_code"], "VALIDATION_ERROR")

        # 2. Registration duplicate email conflict -> HTTP 409
        dup_email = "duplicate_e2e@example.com"
        access_token, _, _ = self.api_register_and_login(
            full_name="Original User", email=dup_email
        )

        resp_dup = self.client.post(
            "/api/v1/auth/register",
            data=json.dumps(
                {
                    "full_name": "Copycat User",
                    "email": dup_email,
                    "password": "Password123!",
                    "confirm_password": "Password123!",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(resp_dup.status_code, 409)
        err_dup = resp_dup.json()
        RegistrationConflictOut.model_validate(err_dup)
        self.assertFalse(err_dup["success"])
        self.assertEqual(err_dup["message"], "Email already exists.")
        self.assertIn("email", err_dup["errors"])

        # 3. Claim submission validation error (too short text) -> HTTP 422
        resp_short = self.client.post(
            "/api/v1/claims",
            data=json.dumps({"claim_text": "short"}),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {access_token}",
        )
        self.assertEqual(resp_short.status_code, 422)
        err_short = resp_short.json()
        ErrorResponse.model_validate(err_short)
        self.assertFalse(err_short["success"])
        self.assertEqual(err_short["error_code"], "VALIDATION_ERROR")

        # 4. Unknown claim UUID retrieval -> HTTP 404 NOT_FOUND
        missing_id = uuid.uuid4()
        resp_not_found = self.client.get(
            f"/api/v1/claims/{missing_id}",
            HTTP_AUTHORIZATION=f"Bearer {access_token}",
        )
        self.assertEqual(resp_not_found.status_code, 404)
        err_not_found = resp_not_found.json()
        ErrorResponse.model_validate(err_not_found)
        self.assertFalse(err_not_found["success"])
        self.assertEqual(err_not_found["error_code"], "NOT_FOUND")

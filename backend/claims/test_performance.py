import json

from django.core.cache import cache
from django.test import Client, TestCase

from analysis.models import Analysis, Verdict
from authentication.models import User
from claims.models import Claim, ClaimStatus
from shared.schemas import ErrorResponse


class BasePerformanceTestCase(TestCase):
    """
    Base test case for performance and query-count verification.
    Provides targeted throttle-key cleanup and fixture isolation.
    """

    test_ip = "198.51.100.201"

    def setUp(self):
        super().setUp()
        self.client = Client(REMOTE_ADDR=self.test_ip)

    def tearDown(self):
        cache.delete(f"throttle_login_{self.test_ip}")
        cache.delete(f"throttle_register_{self.test_ip}")
        super().tearDown()

    def get_user_auth(
        self, email: str, password: str = "StrongPass123!"
    ) -> tuple[str, dict, str]:
        """
        Authenticates a user via API outside of measured query blocks.
        Returns: (access_token, headers_dict, refresh_token)
        """
        resp = self.client.post(
            "/api/v1/auth/login",
            data=json.dumps({"email": email, "password": password}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["data"]
        access_token = data["access_token"]
        refresh_token = data["refresh_token"]
        headers = {"HTTP_AUTHORIZATION": f"Bearer {access_token}"}
        return access_token, headers, refresh_token


class ClaimPaginationNPlusOnePerformanceTests(BasePerformanceTestCase):
    """
    Verifies that list and history pagination endpoints execute with strictly
    invariant query counts across page sizes 1, 10, and 50, proving zero N+1 queries.
    """

    test_ip = "198.51.100.202"

    def setUp(self):
        super().setUp()
        password = "StrongPass123!"

        # Create 3 distinct users and 1 platform admin
        self.user1 = User.objects.create_user(
            email="perf_user1@example.com",
            full_name="Performance User One",
            password=password,
        )
        self.user2 = User.objects.create_user(
            email="perf_user2@example.com",
            full_name="Performance User Two",
            password=password,
        )
        self.user3 = User.objects.create_user(
            email="perf_user3@example.com",
            full_name="Performance User Three",
            password=password,
        )
        self.admin = User.objects.create_user(
            email="perf_admin@example.com",
            full_name="Performance Admin",
            password=password,
            role="ADMIN",
        )

        # Authenticate User 1 and Admin outside query-count measurements
        _, self.user1_headers, _ = self.get_user_auth(self.user1.email, password)
        _, self.admin_headers, _ = self.get_user_auth(self.admin.email, password)

        # Seed 60 total claims directly via ORM without invoking ML models:
        # User 1: 52 claims (26 with Analysis, 26 without Analysis)
        # User 2: 5 claims (3 with Analysis, 2 without Analysis)
        # User 3: 3 claims (2 with Analysis, 1 without Analysis)
        # Total: 60 claims (31 with Analysis, 29 without Analysis)

        # 1. User 1: 52 claims
        for i in range(1, 53):
            claim = Claim.objects.create(
                user=self.user1,
                text=f"User 1 performance test claim number {i:03d} content.",
                status=ClaimStatus.COMPLETED if i <= 26 else ClaimStatus.PENDING,
            )
            if i <= 26:
                Analysis.objects.create(
                    claim=claim,
                    verdict=Verdict.CREDIBLE if i % 2 == 0 else Verdict.MISINFORMATION,
                    credibility_score=85.0 if i % 2 == 0 else 15.0,
                )

        # 2. User 2: 5 claims
        for i in range(1, 6):
            claim = Claim.objects.create(
                user=self.user2,
                text=f"User 2 performance test claim number {i:03d} content.",
                status=ClaimStatus.COMPLETED if i <= 3 else ClaimStatus.PENDING,
            )
            if i <= 3:
                Analysis.objects.create(
                    claim=claim,
                    verdict=Verdict.CREDIBLE,
                    credibility_score=90.0,
                )

        # 3. User 3: 3 claims
        for i in range(1, 4):
            claim = Claim.objects.create(
                user=self.user3,
                text=f"User 3 performance test claim number {i:03d} content.",
                status=ClaimStatus.COMPLETED if i <= 2 else ClaimStatus.PENDING,
            )
            if i <= 2:
                Analysis.objects.create(
                    claim=claim,
                    verdict=Verdict.UNCERTAIN,
                    credibility_score=50.0,
                )

    def test_user_claim_history_n_plus_one_invariance_across_page_sizes(self):
        """
        Asserts that GET /api/v1/claims/history executes exactly 3 queries
        (1 auth + 1 count + 1 items with select_related) across page sizes 1, 10, and 50.
        """
        # Page size 1: returns 1 item
        with self.assertNumQueries(3):
            resp_1 = self.client.get(
                "/api/v1/claims/history?page=1&page_size=1", **self.user1_headers
            )
        self.assertEqual(resp_1.status_code, 200)
        data_1 = resp_1.json()
        self.assertEqual(data_1["count"], 52)
        self.assertEqual(len(data_1["results"]), 1)
        self.assertIsNotNone(data_1["next"])

        # Page size 10: returns 10 items
        with self.assertNumQueries(3):
            resp_10 = self.client.get(
                "/api/v1/claims/history?page=1&page_size=10", **self.user1_headers
            )
        self.assertEqual(resp_10.status_code, 200)
        data_10 = resp_10.json()
        self.assertEqual(data_10["count"], 52)
        self.assertEqual(len(data_10["results"]), 10)
        self.assertIsNotNone(data_10["next"])

        # Page size 50: returns full page of 50 items
        with self.assertNumQueries(3):
            resp_50 = self.client.get(
                "/api/v1/claims/history?page=1&page_size=50", **self.user1_headers
            )
        self.assertEqual(resp_50.status_code, 200)
        data_50 = resp_50.json()
        self.assertEqual(data_50["count"], 52)
        self.assertEqual(len(data_50["results"]), 50)
        self.assertIsNotNone(data_50["next"])

    def test_admin_claims_list_n_plus_one_invariance_across_page_sizes(self):
        """
        Asserts that GET /api/v1/admin/claims executes exactly 3 queries
        (1 auth + 1 count + 1 items with select_related) across page sizes 1, 10, and 50,
        spanning multiple distinct users.
        """
        # Page size 1: returns 1 item
        with self.assertNumQueries(3):
            resp_1 = self.client.get(
                "/api/v1/admin/claims?page=1&page_size=1", **self.admin_headers
            )
        self.assertEqual(resp_1.status_code, 200)
        data_1 = resp_1.json()
        self.assertEqual(data_1["count"], 60)
        self.assertEqual(len(data_1["results"]), 1)
        self.assertIsNotNone(data_1["next"])

        # Page size 10: returns 10 items
        with self.assertNumQueries(3):
            resp_10 = self.client.get(
                "/api/v1/admin/claims?page=1&page_size=10", **self.admin_headers
            )
        self.assertEqual(resp_10.status_code, 200)
        data_10 = resp_10.json()
        self.assertEqual(data_10["count"], 60)
        self.assertEqual(len(data_10["results"]), 10)
        self.assertIsNotNone(data_10["next"])

        # Page size 50: returns full page of 50 items
        with self.assertNumQueries(3):
            resp_50 = self.client.get(
                "/api/v1/admin/claims?page=1&page_size=50", **self.admin_headers
            )
        self.assertEqual(resp_50.status_code, 200)
        data_50 = resp_50.json()
        self.assertEqual(data_50["count"], 60)
        self.assertEqual(len(data_50["results"]), 50)
        self.assertIsNotNone(data_50["next"])


class ClaimDetailOptimizationPerformanceTests(BasePerformanceTestCase):
    """
    Verifies that GET /api/v1/claims/{id} executes in exactly 2 queries
    (1 auth + 1 claim JOIN analysis) for claims both with and without an analysis,
    confirming the select_related('analysis') optimization.
    """

    test_ip = "198.51.100.203"

    def setUp(self):
        super().setUp()
        password = "StrongPass123!"
        self.user = User.objects.create_user(
            email="detail_perf@example.com",
            full_name="Detail Perf User",
            password=password,
        )
        _, self.headers, _ = self.get_user_auth(self.user.email, password)

        # Claim with analysis
        self.claim_with_analysis = Claim.objects.create(
            user=self.user,
            text="Detail performance claim with completed analysis record.",
            status=ClaimStatus.COMPLETED,
        )
        Analysis.objects.create(
            claim=self.claim_with_analysis,
            verdict=Verdict.CREDIBLE,
            credibility_score=92.5,
        )

        # Claim without analysis
        self.claim_without_analysis = Claim.objects.create(
            user=self.user,
            text="Detail performance claim without any analysis record.",
            status=ClaimStatus.PENDING,
        )

    def test_claim_detail_with_analysis_executes_two_queries(self):
        with self.assertNumQueries(2):
            resp = self.client.get(
                f"/api/v1/claims/{self.claim_with_analysis.id}", **self.headers
            )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["data"]
        self.assertTrue(data["analysis_available"])
        self.assertEqual(str(data["id"]), str(self.claim_with_analysis.id))

    def test_claim_detail_without_analysis_executes_two_queries(self):
        with self.assertNumQueries(2):
            resp = self.client.get(
                f"/api/v1/claims/{self.claim_without_analysis.id}", **self.headers
            )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["data"]
        self.assertFalse(data["analysis_available"])
        self.assertEqual(str(data["id"]), str(self.claim_without_analysis.id))


class ClaimMutationPerformanceAndAuthorizationTests(BasePerformanceTestCase):
    """
    Verifies query counts for claim mutation endpoints and proves that administrators
    cannot update another user's claim text with zero wasted relationship queries.
    """

    test_ip = "198.51.100.204"

    def setUp(self):
        super().setUp()
        password = "StrongPass123!"
        self.owner = User.objects.create_user(
            email="mut_owner@example.com",
            full_name="Mutation Owner",
            password=password,
        )
        self.admin = User.objects.create_superuser(
            email="mut_admin@example.com",
            full_name="Mutation Superuser Admin",
            password=password,
        )
        _, self.owner_headers, _ = self.get_user_auth(self.owner.email, password)
        _, self.admin_headers, _ = self.get_user_auth(self.admin.email, password)

        self.addCleanup(cache.delete, f"throttle_claim_submit_{self.owner.id}")

    def test_submit_claim_query_bound(self):
        payload = {
            "claim_text": "New claim submission text to verify query bounds strictly."
        }
        # 5 queries: 1 auth + 1 SAVEPOINT + 1 claim insert + 1 audit insert + 1 RELEASE SAVEPOINT
        with self.assertNumQueries(5):
            resp = self.client.post(
                "/api/v1/claims",
                data=json.dumps(payload),
                content_type="application/json",
                **self.owner_headers,
            )
        self.assertEqual(resp.status_code, 201)

    def test_update_claim_query_bound(self):
        claim = Claim.objects.create(
            user=self.owner,
            text="Original pending claim text before performance patch update.",
            status=ClaimStatus.PENDING,
        )
        payload = {
            "claim_text": "Updated pending claim text with new verified information."
        }
        # 7 queries: 1 auth + 1 claim lookup + 1 SAVEPOINT + 1 atomic update + 1 audit insert + 1 refresh + 1 RELEASE SAVEPOINT
        with self.assertNumQueries(7):
            resp = self.client.patch(
                f"/api/v1/claims/{claim.id}",
                data=json.dumps(payload),
                content_type="application/json",
                **self.owner_headers,
            )
        self.assertEqual(resp.status_code, 200)

    def test_admin_update_claim_text_forbidden_regression(self):
        """
        Authorization regression test:
        Confirms that superuser/admin attempts to update a user's claim are rejected
        with HTTP 403 PERMISSION_DENIED and executed in at most 2 queries
        (1 auth + 1 claim lookup), without loading the foreign-key user relation.
        """
        claim = Claim.objects.create(
            user=self.owner,
            text="Original pending claim text protected against admin edits.",
            status=ClaimStatus.PENDING,
        )
        payload = {
            "claim_text": "Admin attempting to alter user claim text improperly."
        }
        with self.assertNumQueries(2):
            resp = self.client.patch(
                f"/api/v1/claims/{claim.id}",
                data=json.dumps(payload),
                content_type="application/json",
                **self.admin_headers,
            )
        self.assertEqual(resp.status_code, 403)
        err_data = resp.json()
        ErrorResponse.model_validate(err_data)
        self.assertFalse(err_data["success"])
        self.assertEqual(err_data["error_code"], "PERMISSION_DENIED")

    def test_delete_claim_query_bound(self):
        claim = Claim.objects.create(
            user=self.owner,
            text="Pending claim created to verify soft-delete query bounds.",
            status=ClaimStatus.PENDING,
        )
        # 7 queries: 1 auth + 1 claim lookup + 1 SAVEPOINT + 1 atomic update + 1 status read + 1 audit insert + 1 RELEASE SAVEPOINT
        with self.assertNumQueries(7):
            resp = self.client.delete(
                f"/api/v1/claims/{claim.id}", **self.owner_headers
            )
        self.assertEqual(resp.status_code, 204)


class AuthenticationOperationsPerformanceTests(BasePerformanceTestCase):
    """
    Verifies query counts for all authentication operations:
    registration, login, profile (/me), token refresh, and logout.
    """

    test_ip = "198.51.100.205"

    def setUp(self):
        super().setUp()
        self.password = "StrongPass123!"
        self.user = User.objects.create_user(
            email="auth_perf@example.com",
            full_name="Auth Performance User",
            password=self.password,
        )

    def test_user_registration_query_bound(self):
        payload = {
            "full_name": "New Registration User",
            "email": "new_reg_perf@example.com",
            "password": self.password,
            "confirm_password": self.password,
        }
        # 4 queries: 1 email existence check + 1 SAVEPOINT + 1 user insert + 1 RELEASE SAVEPOINT
        with self.assertNumQueries(4):
            resp = self.client.post(
                "/api/v1/auth/register",
                data=json.dumps(payload),
                content_type="application/json",
            )
        self.assertEqual(resp.status_code, 201)

    def test_user_login_query_bound(self):
        payload = {
            "email": self.user.email,
            "password": self.password,
        }
        # 2 queries: 1 user lookup + 1 outstanding token insert
        with self.assertNumQueries(2):
            resp = self.client.post(
                "/api/v1/auth/login",
                data=json.dumps(payload),
                content_type="application/json",
            )
        self.assertEqual(resp.status_code, 200)

    def test_user_profile_me_query_bound(self):
        access_token, headers, _ = self.get_user_auth(self.user.email, self.password)
        with self.assertNumQueries(1):
            resp = self.client.get("/api/v1/auth/me", **headers)
        self.assertEqual(resp.status_code, 200)

    def test_token_refresh_query_bound(self):
        _, _, refresh_token = self.get_user_auth(self.user.email, self.password)
        payload = {"refresh_token": refresh_token}
        # 6 queries: check blacklist + get outstanding token + re-check blacklist + SAVEPOINT + insert blacklist + RELEASE SAVEPOINT
        with self.assertNumQueries(6):
            resp = self.client.post(
                "/api/v1/auth/refresh",
                data=json.dumps(payload),
                content_type="application/json",
            )
        self.assertEqual(resp.status_code, 200)

    def test_token_logout_query_bound(self):
        _, _, refresh_token = self.get_user_auth(self.user.email, self.password)
        payload = {"refresh_token": refresh_token}
        # 6 queries: check blacklist + get outstanding token + re-check blacklist + SAVEPOINT + insert blacklist + RELEASE SAVEPOINT
        with self.assertNumQueries(6):
            resp = self.client.post(
                "/api/v1/auth/logout",
                data=json.dumps(payload),
                content_type="application/json",
            )
        self.assertEqual(resp.status_code, 200)

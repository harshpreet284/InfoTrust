"""
Analysis REST API Test Suite (AI-013).
Verifies:
1. Authentication & token validation (401)
2. Role-based & ownership authorization (owner, admin, superuser, non-owner 403)
3. Resource handling (404 non-existent, 404 soft-deleted)
4. Path parameter validation (422 malformed UUID)
5. 6-state completed-analysis lifecycle matrix (409 conflict vs 200)
6. Data integrity & timestamp mapping
7. NULL vs genuine-zero preservation
8. Diagnostic isolation & forensic leak prevention
9. Database query count efficiency
"""

import json
import uuid
from datetime import datetime

from django.core.cache import cache
from django.test import Client, TestCase

from analysis.inference.adapter import ModelOutput
from analysis.models import Analysis, ModelPrediction, Verdict
from analysis.services.explainability import ExplainabilityService
from analysis.services.fact_check import FactCheckEvidenceItem, FactCheckResult
from analysis.services.hybrid import HybridCredibilityEngine
from analysis.services.rules import RuleValidationResult
from analysis.services.verdict import VerdictService
from authentication.models import User
from claims.models import Claim, ClaimStatus


class AnalysisApiTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = Client()

        # Users setup
        self.owner = User.objects.create_user(
            email="owner@example.com",
            password="password123",
            full_name="Claim Owner",
            role="USER",
        )
        self.other_user = User.objects.create_user(
            email="other@example.com",
            password="password123",
            full_name="Other User",
            role="USER",
        )
        self.app_admin = User.objects.create_user(
            email="admin@example.com",
            password="password123",
            full_name="App Admin",
            role="ADMIN",
        )
        # Superuser with role="USER" to prove superuser access is independent of ADMIN role string
        self.superuser = User.objects.create_user(
            email="superuser@example.com",
            password="password123",
            full_name="Superuser",
            role="USER",
            is_superuser=True,
        )

        # Obtain JWT tokens
        resp_owner = self.client.post(
            "/api/v1/auth/login",
            data=json.dumps({"email": "owner@example.com", "password": "password123"}),
            content_type="application/json",
        )
        self.owner_token = resp_owner.json()["data"]["access_token"]
        self.owner_headers = {"HTTP_AUTHORIZATION": f"Bearer {self.owner_token}"}

        resp_other = self.client.post(
            "/api/v1/auth/login",
            data=json.dumps({"email": "other@example.com", "password": "password123"}),
            content_type="application/json",
        )
        self.other_token = resp_other.json()["data"]["access_token"]
        self.other_headers = {"HTTP_AUTHORIZATION": f"Bearer {self.other_token}"}

        resp_admin = self.client.post(
            "/api/v1/auth/login",
            data=json.dumps({"email": "admin@example.com", "password": "password123"}),
            content_type="application/json",
        )
        self.admin_token = resp_admin.json()["data"]["access_token"]
        self.admin_headers = {"HTTP_AUTHORIZATION": f"Bearer {self.admin_token}"}

        resp_su = self.client.post(
            "/api/v1/auth/login",
            data=json.dumps(
                {"email": "superuser@example.com", "password": "password123"}
            ),
            content_type="application/json",
        )
        self.su_token = resp_su.json()["data"]["access_token"]
        self.su_headers = {"HTTP_AUTHORIZATION": f"Bearer {self.su_token}"}

        # Create nominal completed claim
        self.completed_claim = Claim.objects.create(
            user=self.owner,
            text="The global temperature increased by 1.1 degrees Celsius over the last century.",
            status=ClaimStatus.COMPLETED,
            is_deleted=False,
        )

        # Detailed forensic explainability dictionary (mimicking ExplainabilityResult.to_internal_dict())
        self.forensic_explainability_json = {
            "verdict": "CREDIBLE",
            "verdict_label": "Credible",
            "credibility_score": 85.5,
            "confidence_level": "HIGH",
            "overall_status": "FULL_SUCCESS",
            "is_definitive": True,
            "verdict_reason": "Strong converging evidence supports the claim.",
            "reasoning": [
                "Fine-tuned classification model predicted the claim is credible with 92.0% confidence.",
                "External fact-checking evidence confirmed 2 matching review(s).",
                "Historical narrative recurrence detected across 4 similar claims.",
                "Deterministic rule heuristics detected no sensationalism.",
            ],
            "score_breakdown": {
                "model": {
                    "component_score": 0.92,
                    "effective_weight": 0.45,
                    "weighted_contribution": 41.4,
                    "status": "AVAILABLE",
                },
                "fact_check": {
                    "component_score": 0.88,
                    "effective_weight": 0.35,
                    "weighted_contribution": 30.8,
                    "status": "AVAILABLE",
                },
                "narrative": {
                    "component_score": None,
                    "effective_weight": 0.0,
                    "weighted_contribution": 0.0,
                    "status": "UNSCORABLE",
                },
                "rule_engine": {
                    "component_score": 0.95,
                    "effective_weight": 0.20,
                    "weighted_contribution": 13.3,
                    "status": "AVAILABLE",
                },
            },
            "components": {
                "model": {
                    "detail_status": "FULL",
                    "prediction": "CREDIBLE",
                    "confidence": 0.92,
                    "summary": "Model predicted credible.",
                },
                "fact_check": {
                    "detail_status": "FULL",
                    "matches_count": 2,
                    "summary": "External fact-checking confirmed 2 reviews.",
                    "sources": [
                        {
                            "publisher": "PolitiFact",
                            "rating": "True",
                            "url": "https://politifact.example.com/climate",
                            "review_date": "2026-05-10",
                        },
                        {
                            "publisher": "Climate Feedback",
                            "rating": "Accurate",
                            "url": "https://climatefeedback.example.com/warming",
                            "review_date": "2026-05-12",
                        },
                    ],
                },
                "narrative": {
                    "detail_status": "FULL",
                    "similar_claims_count": 4,
                    "activity_level": "MEDIUM",
                    "first_seen": "2026-01-15T08:30:00Z",
                    "latest_occurrence": "2026-05-01T14:20:00Z",
                    "summary": "Historical recurrence detected across 4 claims.",
                },
                "similarity": {
                    "detail_status": "FULL",
                    "highest_similarity_score": 0.895,
                    "average_similarity_score": 0.74,
                    "related_claims_count": 4,
                },
            },
            # INTERNAL SENSITIVE DIAGNOSTICS THAT MUST NEVER LEAK:
            "diagnostics": {
                "failed_components": [],
                "error_details": {"secret_token": "super_secret_debug_api_key_123"},
                "thresholds": {"similarity_threshold": 0.75, "min_words": 10},
                "traceback": "Traceback (most recent call last):\n  File 'test.py', line 12",
            },
        }

        # Create nominal completed Analysis
        self.completed_analysis = Analysis.objects.create(
            claim=self.completed_claim,
            credibility_score=85.5,
            verdict=Verdict.CREDIBLE,
            explainability_json=self.forensic_explainability_json,
            model_prediction=ModelPrediction.CREDIBLE,
            model_confidence=0.92,
            fact_check_summary="External fact-checking confirmed 2 reviews.",
            fact_check_match_count=2,
            narrative_match_count=4,
            highest_similarity_score=0.895,
            rule_based_flags={"sensationalism": False},
            final_weighted_score=85.5,
        )

    # =========================================================================
    # 1. Authentication Tests (401 Unauthorized)
    # =========================================================================
    def test_unauthenticated_requests_return_401(self):
        cid = self.completed_claim.id
        endpoints = [
            f"/api/v1/analysis/{cid}/status",
            f"/api/v1/analysis/{cid}",
            f"/api/v1/analysis/{cid}/explanation",
            f"/api/v1/analysis/{cid}/narrative",
            f"/api/v1/analysis/{cid}/fact-check",
        ]
        for ep in endpoints:
            with self.subTest(endpoint=ep):
                resp = self.client.get(ep)
                self.assertEqual(resp.status_code, 401)
                data = resp.json()
                self.assertFalse(data["success"])
                self.assertEqual(data["error_code"], "AUTHENTICATION_ERROR")

    def test_invalid_bearer_token_returns_401(self):
        cid = self.completed_claim.id
        bad_headers = {"HTTP_AUTHORIZATION": "Bearer invalid.token.123"}
        resp = self.client.get(f"/api/v1/analysis/{cid}", **bad_headers)
        self.assertEqual(resp.status_code, 401)
        self.assertEqual(resp.json()["error_code"], "AUTHENTICATION_ERROR")

    # =========================================================================
    # 2. Authorization & Role Tests (200 vs 403)
    # =========================================================================
    def test_owner_access_granted(self):
        cid = self.completed_claim.id
        endpoints = [
            f"/api/v1/analysis/{cid}/status",
            f"/api/v1/analysis/{cid}",
            f"/api/v1/analysis/{cid}/explanation",
            f"/api/v1/analysis/{cid}/narrative",
            f"/api/v1/analysis/{cid}/fact-check",
        ]
        for ep in endpoints:
            with self.subTest(endpoint=ep):
                resp = self.client.get(ep, **self.owner_headers)
                self.assertEqual(resp.status_code, 200)
                self.assertTrue(resp.json()["success"])

    def test_app_admin_access_granted_to_another_users_claim(self):
        cid = self.completed_claim.id
        resp = self.client.get(f"/api/v1/analysis/{cid}", **self.admin_headers)
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["success"])

    def test_superuser_access_granted_with_user_role_string(self):
        """Proves Django superuser access is independent of user.role == 'ADMIN'."""
        self.assertEqual(self.superuser.role, "USER")
        self.assertTrue(self.superuser.is_superuser)

        cid = self.completed_claim.id
        resp = self.client.get(f"/api/v1/analysis/{cid}", **self.su_headers)
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["success"])
        self.assertEqual(resp.json()["data"]["claim_id"], str(cid))

    def test_non_owner_regular_user_rejected_with_403(self):
        cid = self.completed_claim.id
        endpoints = [
            f"/api/v1/analysis/{cid}/status",
            f"/api/v1/analysis/{cid}",
            f"/api/v1/analysis/{cid}/explanation",
            f"/api/v1/analysis/{cid}/narrative",
            f"/api/v1/analysis/{cid}/fact-check",
        ]
        for ep in endpoints:
            with self.subTest(endpoint=ep):
                resp = self.client.get(ep, **self.other_headers)
                self.assertEqual(resp.status_code, 403)
                data = resp.json()
                self.assertFalse(data["success"])
                self.assertEqual(data["error_code"], "PERMISSION_DENIED")

    # =========================================================================
    # 3. Resource Not Found & Soft Delete (404)
    # =========================================================================
    def test_nonexistent_claim_returns_404(self):
        random_id = uuid.uuid4()
        resp = self.client.get(f"/api/v1/analysis/{random_id}", **self.owner_headers)
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(resp.json()["error_code"], "NOT_FOUND")

    def test_soft_deleted_claim_returns_404(self):
        deleted_claim = Claim.objects.create(
            user=self.owner,
            text="A claim that has been soft deleted by the user.",
            status=ClaimStatus.COMPLETED,
            is_deleted=True,
        )
        Analysis.objects.create(
            claim=deleted_claim,
            credibility_score=75.0,
            verdict=Verdict.CREDIBLE,
        )
        resp = self.client.get(
            f"/api/v1/analysis/{deleted_claim.id}", **self.owner_headers
        )
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(resp.json()["error_code"], "NOT_FOUND")

    # =========================================================================
    # 4. Path Parameter Validation (422)
    # =========================================================================
    def test_malformed_uuid_returns_422(self):
        resp = self.client.get(
            "/api/v1/analysis/not-a-valid-uuid", **self.owner_headers
        )
        self.assertEqual(resp.status_code, 422)
        self.assertEqual(resp.json()["error_code"], "VALIDATION_ERROR")

    # =========================================================================
    # 5. Completed-Analysis 6-State Matrix Tests (409 vs 200)
    # =========================================================================
    def test_lifecycle_matrix_pending_without_analysis(self):
        c = Claim.objects.create(
            user=self.owner, text="Pending claim text.", status=ClaimStatus.PENDING
        )
        # Status endpoint succeeds with PENDING
        status_resp = self.client.get(
            f"/api/v1/analysis/{c.id}/status", **self.owner_headers
        )
        self.assertEqual(status_resp.status_code, 200)
        self.assertEqual(status_resp.json()["data"]["status"], "PENDING")

        # Result endpoints return 409 "Analysis still processing."
        endpoints = [
            f"/api/v1/analysis/{c.id}",
            f"/api/v1/analysis/{c.id}/explanation",
            f"/api/v1/analysis/{c.id}/narrative",
            f"/api/v1/analysis/{c.id}/fact-check",
        ]
        for ep in endpoints:
            with self.subTest(ep=ep):
                resp = self.client.get(ep, **self.owner_headers)
                self.assertEqual(resp.status_code, 409)
                self.assertIn("still processing", resp.json()["message"])

    def test_lifecycle_matrix_processing_without_analysis(self):
        c = Claim.objects.create(
            user=self.owner,
            text="Processing claim text.",
            status=ClaimStatus.PROCESSING,
        )
        status_resp = self.client.get(
            f"/api/v1/analysis/{c.id}/status", **self.owner_headers
        )
        self.assertEqual(status_resp.status_code, 200)
        self.assertEqual(status_resp.json()["data"]["status"], "PROCESSING")

        resp = self.client.get(f"/api/v1/analysis/{c.id}", **self.owner_headers)
        self.assertEqual(resp.status_code, 409)
        self.assertIn("still processing", resp.json()["message"])

    def test_lifecycle_matrix_failed_without_analysis(self):
        c = Claim.objects.create(
            user=self.owner, text="Failed claim text.", status=ClaimStatus.FAILED
        )
        status_resp = self.client.get(
            f"/api/v1/analysis/{c.id}/status", **self.owner_headers
        )
        self.assertEqual(status_resp.status_code, 200)
        self.assertEqual(status_resp.json()["data"]["status"], "FAILED")

        resp = self.client.get(f"/api/v1/analysis/{c.id}", **self.owner_headers)
        self.assertEqual(resp.status_code, 409)
        self.assertIn("could not be completed", resp.json()["message"])

    def test_lifecycle_matrix_failed_with_analysis_record_present(self):
        """FAILED claims must NEVER expose Analysis data, even if an Analysis record exists."""
        c = Claim.objects.create(
            user=self.owner,
            text="Failed claim with analysis row.",
            status=ClaimStatus.FAILED,
        )
        Analysis.objects.create(
            claim=c, credibility_score=50.0, verdict=Verdict.UNCERTAIN
        )

        resp = self.client.get(f"/api/v1/analysis/{c.id}", **self.owner_headers)
        self.assertEqual(resp.status_code, 409)
        self.assertIn("could not be completed", resp.json()["message"])

    def test_lifecycle_matrix_completed_without_analysis_record(self):
        """COMPLETED status without an Analysis row is an incomplete state, not in-flight."""
        c = Claim.objects.create(
            user=self.owner,
            text="Completed claim with missing row.",
            status=ClaimStatus.COMPLETED,
        )
        resp = self.client.get(f"/api/v1/analysis/{c.id}", **self.owner_headers)
        self.assertEqual(resp.status_code, 409)
        self.assertIn("incomplete", resp.json()["message"])

    def test_lifecycle_matrix_completed_with_analysis_record(self):
        """COMPLETED with Analysis row returns 200 OK."""
        cid = self.completed_claim.id
        resp = self.client.get(f"/api/v1/analysis/{cid}", **self.owner_headers)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["data"]["analysis_status"], "COMPLETED")

    # =========================================================================
    # 6. Data Integrity & Mappings
    # =========================================================================
    def test_summary_data_and_timestamp_mapping(self):
        cid = self.completed_claim.id
        resp = self.client.get(f"/api/v1/analysis/{cid}", **self.owner_headers)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["data"]

        self.assertEqual(data["claim_id"], str(cid))
        self.assertEqual(data["analysis_status"], "COMPLETED")
        self.assertEqual(data["verdict"], "CREDIBLE")
        self.assertEqual(data["credibility_score"], 85.5)

        # Confirm created_at matches analysis_timestamp
        self.assertIn("created_at", data)
        parsed_dt = datetime.fromisoformat(data["created_at"])
        self.assertAlmostEqual(
            parsed_dt.timestamp(),
            self.completed_analysis.analysis_timestamp.timestamp(),
            places=2,
        )

    def test_explanation_and_score_breakdown_mapping(self):
        cid = self.completed_claim.id
        resp = self.client.get(
            f"/api/v1/analysis/{cid}/explanation", **self.owner_headers
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["data"]

        self.assertEqual(data["verdict"], "CREDIBLE")
        self.assertEqual(data["credibility_score"], 85.5)

        sb = data["score_breakdown"]
        self.assertEqual(sb["classification_model"], 41.4)
        self.assertEqual(sb["fact_check"], 30.8)
        self.assertEqual(sb["narrative"], 0.0)
        self.assertEqual(sb["rule_engine"], 13.3)

        self.assertEqual(len(data["reasoning"]), 4)
        self.assertIn("Fine-tuned classification model", data["reasoning"][0])

    def test_narrative_activity_mapping(self):
        cid = self.completed_claim.id
        resp = self.client.get(
            f"/api/v1/analysis/{cid}/narrative", **self.owner_headers
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["data"]

        self.assertEqual(data["similar_claims"], 4)
        self.assertEqual(data["highest_similarity"], 89.5)  # 0.895 -> 89.5%
        self.assertEqual(data["first_seen"], "2026-01-15T08:30:00Z")
        self.assertEqual(data["latest_occurrence"], "2026-05-01T14:20:00Z")
        self.assertEqual(data["activity_level"], "MEDIUM")

    def test_fact_check_evidence_mapping(self):
        cid = self.completed_claim.id
        resp = self.client.get(
            f"/api/v1/analysis/{cid}/fact-check", **self.owner_headers
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["data"]

        self.assertEqual(data["matches_found"], 2)
        self.assertEqual(data["summary"], "External fact-checking confirmed 2 reviews.")
        self.assertEqual(len(data["sources"]), 2)

        s1 = data["sources"][0]
        self.assertEqual(s1["publisher"], "PolitiFact")
        self.assertEqual(s1["rating"], "True")
        self.assertEqual(s1["url"], "https://politifact.example.com/climate")
        self.assertEqual(s1["review_date"], "2026-05-10")

    # =========================================================================
    # 7. NULL vs. Genuine-Zero Preservation
    # =========================================================================
    def test_preserves_genuine_zero_counts_and_contributions(self):
        zero_claim = Claim.objects.create(
            user=self.owner,
            text="Zero matches claim text.",
            status=ClaimStatus.COMPLETED,
        )
        Analysis.objects.create(
            claim=zero_claim,
            credibility_score=50.0,
            verdict=Verdict.UNCERTAIN,
            narrative_match_count=0,
            fact_check_match_count=0,
            highest_similarity_score=0.0,
            explainability_json={
                "score_breakdown": {
                    "model": {"weighted_contribution": 0.0},
                    "fact_check": {"weighted_contribution": 0.0},
                    "narrative": {"weighted_contribution": 0.0},
                    "rule_engine": {"weighted_contribution": 0.0},
                },
                "components": {
                    "narrative": {
                        "detail_status": "FULL",
                        "similar_claims_count": 0,
                        "activity_level": "LOW",
                    },
                    "fact_check": {
                        "detail_status": "FULL",
                        "matches_count": 0,
                        "sources": [],
                    },
                },
            },
        )

        resp_narr = self.client.get(
            f"/api/v1/analysis/{zero_claim.id}/narrative", **self.owner_headers
        )
        self.assertEqual(resp_narr.json()["data"]["similar_claims"], 0)
        self.assertEqual(resp_narr.json()["data"]["highest_similarity"], 0.0)
        self.assertEqual(resp_narr.json()["data"]["activity_level"], "LOW")

        resp_fc = self.client.get(
            f"/api/v1/analysis/{zero_claim.id}/fact-check", **self.owner_headers
        )
        self.assertEqual(resp_fc.json()["data"]["matches_found"], 0)

        resp_exp = self.client.get(
            f"/api/v1/analysis/{zero_claim.id}/explanation", **self.owner_headers
        )
        sb = resp_exp.json()["data"]["score_breakdown"]
        self.assertEqual(sb["classification_model"], 0.0)
        self.assertEqual(sb["fact_check"], 0.0)
        self.assertEqual(sb["narrative"], 0.0)
        self.assertEqual(sb["rule_engine"], 0.0)

    def test_preserves_null_for_unperformed_or_missing_evaluations(self):
        unperformed_claim = Claim.objects.create(
            user=self.owner,
            text="Unperformed evaluation claim text.",
            status=ClaimStatus.COMPLETED,
        )
        Analysis.objects.create(
            claim=unperformed_claim,
            credibility_score=None,
            verdict=None,
            narrative_match_count=None,
            fact_check_match_count=None,
            highest_similarity_score=None,
            explainability_json={
                "score_breakdown": {},
                "components": {
                    "narrative": {
                        "detail_status": "NO_EVIDENCE",
                        "similar_claims_count": None,
                        "activity_level": "NONE",
                    },
                    "fact_check": {
                        "detail_status": "FAILED",
                        "matches_count": None,
                        "sources": [],
                    },
                },
            },
        )

        resp_narr = self.client.get(
            f"/api/v1/analysis/{unperformed_claim.id}/narrative", **self.owner_headers
        )
        narr_data = resp_narr.json()["data"]
        self.assertIsNone(narr_data["similar_claims"])
        self.assertIsNone(narr_data["highest_similarity"])
        self.assertIsNone(narr_data["activity_level"])

        resp_fc = self.client.get(
            f"/api/v1/analysis/{unperformed_claim.id}/fact-check", **self.owner_headers
        )
        fc_data = resp_fc.json()["data"]
        self.assertIsNone(fc_data["matches_found"])

        resp_exp = self.client.get(
            f"/api/v1/analysis/{unperformed_claim.id}/explanation", **self.owner_headers
        )
        sb = resp_exp.json()["data"]["score_breakdown"]
        self.assertIsNone(sb["classification_model"])
        self.assertIsNone(sb["fact_check"])
        self.assertIsNone(sb["narrative"])
        self.assertIsNone(sb["rule_engine"])

    # =========================================================================
    # 8. Diagnostic Isolation Across All Five Endpoints
    # =========================================================================
    def test_diagnostic_isolation_never_leaks_forensic_data(self):
        cid = self.completed_claim.id
        endpoints = [
            f"/api/v1/analysis/{cid}/status",
            f"/api/v1/analysis/{cid}",
            f"/api/v1/analysis/{cid}/explanation",
            f"/api/v1/analysis/{cid}/narrative",
            f"/api/v1/analysis/{cid}/fact-check",
        ]
        forbidden_substrings = [
            "super_secret_debug_api_key_123",
            "similarity_threshold",
            "Traceback",
            "traceback",
            "diagnostics",
            "failed_components",
        ]

        for ep in endpoints:
            with self.subTest(endpoint=ep):
                resp = self.client.get(ep, **self.owner_headers)
                self.assertEqual(resp.status_code, 200)
                raw_json = resp.content.decode("utf-8")
                for secret in forbidden_substrings:
                    self.assertNotIn(
                        secret, raw_json, f"Leaked sensitive secret '{secret}' in {ep}!"
                    )

    # =========================================================================
    # 9. Query Count Verification
    # =========================================================================
    def test_query_count_for_successful_authenticated_retrieval(self):
        """
        Target: 2 SQL queries on warm connection.
        Query 1: User lookup by JWT token.
        Query 2: Claim + Analysis joined lookup via select_related("analysis").
        """
        cid = self.completed_claim.id
        # Warm up JWT cache / connection
        self.client.get(f"/api/v1/analysis/{cid}/status", **self.owner_headers)

        with self.assertNumQueries(2):
            resp = self.client.get(f"/api/v1/analysis/{cid}", **self.owner_headers)
            self.assertEqual(resp.status_code, 200)

    def test_query_count_for_authenticated_malformed_uuid(self):
        """
        Target: 1 SQL query.
        Query 1: User lookup by JWT token during authentication.
        Path parameter validation fails in Pydantic before database query is issued.
        """
        with self.assertNumQueries(1):
            resp = self.client.get(
                "/api/v1/analysis/not-a-valid-uuid", **self.owner_headers
            )
            self.assertEqual(resp.status_code, 422)

    def test_query_count_for_unauthenticated_request(self):
        """
        Target: 0 SQL queries.
        Rejected at authentication gateway before user lookup or database queries.
        """
        cid = self.completed_claim.id
        with self.assertNumQueries(0):
            resp = self.client.get(f"/api/v1/analysis/{cid}")
            self.assertEqual(resp.status_code, 401)

    # =========================================================================
    # 10. Defect Regression Tests (Narrative Activity & Fact-Check Sources)
    # =========================================================================
    def test_narrative_activity_level_validation_matrix(self):
        """
        Activity level is returned ONLY when detail_status == 'FULL' AND
        activity_level in ('LOW', 'MEDIUM', 'HIGH'). All other combinations return None.
        """
        cases = [
            ("FAILED", "HIGH", None),
            ("NO_EVIDENCE", "LOW", None),
            ("CONTEXT_UNAVAILABLE", "MEDIUM", None),
            ("FULL", "INVALID", None),
            ("FULL", "", None),
            ("FULL", "LOW", "LOW"),
            ("FULL", "MEDIUM", "MEDIUM"),
            ("FULL", "HIGH", "HIGH"),
        ]

        for detail_status, raw_activity, expected in cases:
            with self.subTest(detail_status=detail_status, raw_activity=raw_activity):
                c = Claim.objects.create(
                    user=self.owner,
                    text=f"Narrative test claim {detail_status}_{raw_activity}",
                    status=ClaimStatus.COMPLETED,
                )
                Analysis.objects.create(
                    claim=c,
                    credibility_score=75.0,
                    verdict=Verdict.CREDIBLE,
                    explainability_json={
                        "components": {
                            "narrative": {
                                "detail_status": detail_status,
                                "activity_level": raw_activity,
                            }
                        }
                    },
                )
                resp = self.client.get(
                    f"/api/v1/analysis/{c.id}/narrative", **self.owner_headers
                )
                self.assertEqual(resp.status_code, 200)
                self.assertEqual(resp.json()["data"]["activity_level"], expected)

    def test_fact_check_source_validation_matrix(self):
        """
        Fact-check sources require non-empty publisher, rating, and url strings.
        Malformed or incomplete records are excluded, while valid sources are preserved.
        """
        c = Claim.objects.create(
            user=self.owner,
            text="Fact-check source validation claim",
            status=ClaimStatus.COMPLETED,
        )
        sources_payload = [
            # Missing publisher
            {"rating": "False", "url": "https://example.com/missing-publisher"},
            # Empty publisher
            {
                "publisher": "   ",
                "rating": "False",
                "url": "https://example.com/empty-publisher",
            },
            # Missing rating
            {
                "publisher": "Pub Missing Rating",
                "url": "https://example.com/missing-rating",
            },
            # Empty rating
            {
                "publisher": "Pub Empty Rating",
                "rating": "   ",
                "url": "https://example.com/empty-rating",
            },
            # Missing url
            {"publisher": "Pub Missing URL", "rating": "True"},
            # Empty url
            {"publisher": "Pub Empty URL", "rating": "True", "url": "  "},
            # Non-dict item (resilience check)
            "not-a-dict",
            # Valid source with review_date
            {
                "publisher": "Valid Publisher 1",
                "rating": "Verified False",
                "url": "https://example.com/valid-1",
                "review_date": "2026-06-01",
            },
            # Valid source without review_date
            {
                "publisher": "Valid Publisher 2",
                "rating": "Verified True",
                "url": "https://example.com/valid-2",
            },
            # Valid source with empty review_date string
            {
                "publisher": "Valid Publisher 3",
                "rating": "Misleading",
                "url": "https://example.com/valid-3",
                "review_date": "   ",
            },
        ]
        Analysis.objects.create(
            claim=c,
            credibility_score=80.0,
            verdict=Verdict.CREDIBLE,
            fact_check_match_count=3,
            explainability_json={
                "components": {
                    "fact_check": {
                        "detail_status": "FULL",
                        "matches_count": 3,
                        "sources": sources_payload,
                    }
                }
            },
        )

        resp = self.client.get(
            f"/api/v1/analysis/{c.id}/fact-check", **self.owner_headers
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["data"]
        sources = data["sources"]

        # Exactly 3 valid sources must be returned
        self.assertEqual(len(sources), 3)

        # 1. Valid source with review_date
        self.assertEqual(sources[0]["publisher"], "Valid Publisher 1")
        self.assertEqual(sources[0]["rating"], "Verified False")
        self.assertEqual(sources[0]["url"], "https://example.com/valid-1")
        self.assertEqual(sources[0]["review_date"], "2026-06-01")

        # 2. Valid source without review_date (None)
        self.assertEqual(sources[1]["publisher"], "Valid Publisher 2")
        self.assertEqual(sources[1]["rating"], "Verified True")
        self.assertEqual(sources[1]["url"], "https://example.com/valid-2")
        self.assertIsNone(sources[1]["review_date"])

        # 3. Valid source with empty review_date (cleaned to None)
        self.assertEqual(sources[2]["publisher"], "Valid Publisher 3")
        self.assertEqual(sources[2]["rating"], "Misleading")
        self.assertEqual(sources[2]["url"], "https://example.com/valid-3")
        self.assertIsNone(sources[2]["review_date"])

    def test_explainability_endpoint_misinformation_verdict(self):
        """
        Verifies GET /api/v1/analysis/{claim_id}/explanation serializes a MISINFORMATION verdict
        and corresponding score breakdown generated by the production services.
        """
        hybrid_engine = HybridCredibilityEngine()
        verdict_service = VerdictService()
        explain_service = ExplainabilityService()

        model_out = ModelOutput(
            prediction=ModelPrediction.MISINFORMATION, confidence=0.85
        )
        ev = FactCheckEvidenceItem(
            publisher="PolitiFact",
            rating="False",
            url="https://politifact.example.com/false-claim",
        )
        fc_res = FactCheckResult(
            matches=1,
            sources=(ev,),
            summary="Claim rated False by PolitiFact.",
            evidence_urls=("https://politifact.example.com/false-claim",),
        )
        rule_flags = {
            "clickbait_phrases": True,
            "duplicate_punctuation": False,
            "excessive_capitalization": False,
            "sensational_language": True,
            "short_or_vague_claim": False,
            "spam_patterns": False,
        }
        rule_res = RuleValidationResult(
            flags=rule_flags,
            triggered_count=2,
            credibility_penalty=0.30,
            rule_score=0.70,
            observations=("Clickbait detected.", "Sensational language detected."),
        )

        h_res = hybrid_engine.aggregate(
            model_output=model_out,
            fact_check_result=fc_res,
            rule_validation_result=rule_res,
        )
        v_res = verdict_service.generate_verdict(h_res)
        exp_res = explain_service.generate_explainability(
            h_res,
            v_res,
            model_output=model_out,
            fact_check_result=fc_res,
            rule_validation_result=rule_res,
        )

        claim = Claim.objects.create(
            user=self.owner,
            text="5G towers cause acute respiratory syndrome.",
            status=ClaimStatus.COMPLETED,
        )
        Analysis.objects.create(
            claim=claim,
            credibility_score=h_res.credibility_score,
            verdict=v_res.verdict,
            explainability_json=exp_res.to_internal_dict(),
            model_prediction=model_out.prediction,
            model_confidence=model_out.confidence,
            fact_check_summary=fc_res.summary,
            fact_check_match_count=fc_res.matches,
            final_weighted_score=h_res.credibility_score,
        )

        resp = self.client.get(
            f"/api/v1/analysis/{claim.id}/explanation", **self.owner_headers
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["data"]

        self.assertEqual(data["verdict"], "MISINFORMATION")
        self.assertEqual(data["credibility_score"], 14.4)
        sb = data["score_breakdown"]
        self.assertEqual(sb["classification_model"], 6.18)
        self.assertEqual(sb["fact_check"], 0.0)
        self.assertEqual(sb["rule_engine"], 8.24)
        self.assertEqual(sb["narrative"], 0.0)
        self.assertTrue(len(data["reasoning"]) >= 3)

    def test_explainability_endpoint_displays_model_confidence_in_reasoning(self):
        """
        Verifies GET /api/v1/analysis/{claim_id}/explanation preserves genuinely formatted
        numeric model confidence (0.884 -> 88.4%) in reasoning without manual string fabrication.
        """
        hybrid_engine = HybridCredibilityEngine()
        verdict_service = VerdictService()
        explain_service = ExplainabilityService()

        model_out = ModelOutput(prediction=ModelPrediction.CREDIBLE, confidence=0.884)
        h_res = hybrid_engine.aggregate(model_output=model_out)
        v_res = verdict_service.generate_verdict(h_res)
        exp_res = explain_service.generate_explainability(
            h_res, v_res, model_output=model_out
        )

        claim = Claim.objects.create(
            user=self.owner,
            text="Renewable energy accounted for 30% of global electricity in 2024.",
            status=ClaimStatus.COMPLETED,
        )
        Analysis.objects.create(
            claim=claim,
            credibility_score=h_res.credibility_score,
            verdict=v_res.verdict,
            explainability_json=exp_res.to_internal_dict(),
            model_prediction=model_out.prediction,
            model_confidence=model_out.confidence,
            final_weighted_score=h_res.credibility_score,
        )

        resp = self.client.get(
            f"/api/v1/analysis/{claim.id}/explanation", **self.owner_headers
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["data"]

        # Reasoning statement 0 comes directly from model explanation summary
        self.assertEqual(data["reasoning"][0], exp_res.reasoning[0])
        self.assertIn("88.4% confidence", data["reasoning"][0])
        self.assertIn("Fine-tuned classification model", data["reasoning"][0])

    def test_explainability_endpoint_partial_failure_breakdown(self):
        """
        Verifies GET /api/v1/analysis/{claim_id}/explanation gracefully handles partial component failure,
        returning renormalized contributions and the partial failure reasoning statement.
        """
        hybrid_engine = HybridCredibilityEngine()
        verdict_service = VerdictService()
        explain_service = ExplainabilityService()

        model_out = ModelOutput(prediction=ModelPrediction.CREDIBLE, confidence=0.80)
        rule_flags = {
            "clickbait_phrases": False,
            "duplicate_punctuation": False,
            "excessive_capitalization": False,
            "sensational_language": False,
            "short_or_vague_claim": False,
            "spam_patterns": False,
        }
        rule_res = RuleValidationResult(
            flags=rule_flags,
            triggered_count=0,
            credibility_penalty=0.0,
            rule_score=1.0,
            observations=(),
        )

        h_res = hybrid_engine.aggregate(
            model_output=model_out,
            fact_check_error="Fact-check API timeout",
            rule_validation_result=rule_res,
        )
        v_res = verdict_service.generate_verdict(h_res)
        exp_res = explain_service.generate_explainability(
            h_res, v_res, model_output=model_out, rule_validation_result=rule_res
        )

        claim = Claim.objects.create(
            user=self.owner,
            text="Scientific study confirms solar panels have 25-year operational lifespan.",
            status=ClaimStatus.COMPLETED,
        )
        Analysis.objects.create(
            claim=claim,
            credibility_score=h_res.credibility_score,
            verdict=v_res.verdict,
            explainability_json=exp_res.to_internal_dict(),
            model_prediction=model_out.prediction,
            model_confidence=model_out.confidence,
            final_weighted_score=h_res.credibility_score,
        )

        resp = self.client.get(
            f"/api/v1/analysis/{claim.id}/explanation", **self.owner_headers
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["data"]

        self.assertEqual(data["verdict"], "CREDIBLE")
        self.assertEqual(data["credibility_score"], 84.4)
        sb = data["score_breakdown"]
        self.assertEqual(sb["classification_model"], 62.22)
        self.assertEqual(sb["fact_check"], 0.0)
        self.assertEqual(sb["rule_engine"], 22.22)
        self.assertEqual(sb["narrative"], 0.0)

        # Confirm partial failure statement is serialized into public reasoning
        self.assertTrue(
            any(
                "evaluated under partial component failure: [fact_check]" in s
                for s in data["reasoning"]
            )
        )

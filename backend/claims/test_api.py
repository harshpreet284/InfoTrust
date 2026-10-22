from datetime import date, datetime, timedelta, timezone as dt_timezone
import json
from django.test import TestCase, Client

from authentication.models import User
from audit.models import AuditLog
from claims.models import Claim, ClaimStatus, ClaimFeedback, FeedbackType
from analysis.models import Analysis, Verdict

class ClaimApiTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(email="test@example.com", password="password123", full_name="Test User")
        self.other_user = User.objects.create_user(email="other@example.com", password="password123", full_name="Other User")
        self.admin = User.objects.create_superuser(email="admin@example.com", password="password123", full_name="Admin")
        self.app_admin = User.objects.create_user(email="appadmin@example.com", password="password123", full_name="App Admin", role="ADMIN")
        
        # Obtain a valid JWT token via the existing API
        resp = self.client.post("/api/v1/auth/login", data=json.dumps({"email": "test@example.com", "password": "password123"}), content_type="application/json")
        self.token = resp.json()["data"]["access_token"]
        self.headers = {"HTTP_AUTHORIZATION": f"Bearer {self.token}"}
        
        resp2 = self.client.post("/api/v1/auth/login", data=json.dumps({"email": "other@example.com", "password": "password123"}), content_type="application/json")
        self.other_headers = {"HTTP_AUTHORIZATION": f"Bearer {resp2.json()['data']['access_token']}"}
        
        resp3 = self.client.post("/api/v1/auth/login", data=json.dumps({"email": "admin@example.com", "password": "password123"}), content_type="application/json")
        self.admin_headers = {"HTTP_AUTHORIZATION": f"Bearer {resp3.json()['data']['access_token']}"}
        
        resp4 = self.client.post("/api/v1/auth/login", data=json.dumps({"email": "appadmin@example.com", "password": "password123"}), content_type="application/json")
        self.app_admin_headers = {"HTTP_AUTHORIZATION": f"Bearer {resp4.json()['data']['access_token']}"}

        self.claim = Claim.objects.create(
            user=self.user,
            text="Initial claim text that is long enough.",
        )
        
    def test_submit_claim_unauthenticated(self):
        resp = self.client.post("/api/v1/claims", data=json.dumps({"claim_text": "Vaccines are safe and thoroughly tested."}), content_type="application/json")
        self.assertEqual(resp.status_code, 401)
        data = resp.json()
        self.assertEqual(data["error_code"], "AUTHENTICATION_ERROR")
        
    def test_submit_claim_missing_text(self):
        resp = self.client.post("/api/v1/claims", data=json.dumps({}), content_type="application/json", **self.headers)
        self.assertEqual(resp.status_code, 422)
        data = resp.json()
        self.assertEqual(data["error_code"], "VALIDATION_ERROR")
        
    def test_submit_claim_too_short(self):
        resp = self.client.post("/api/v1/claims", data=json.dumps({"claim_text": "Short"}), content_type="application/json", **self.headers)
        self.assertEqual(resp.status_code, 422)
        
    def test_submit_claim_html_rejected(self):
        resp = self.client.post("/api/v1/claims", data=json.dumps({"claim_text": "<p>This is a claim that has HTML formatting</p>"}), content_type="application/json", **self.headers)
        self.assertEqual(resp.status_code, 422)

    def test_submit_claim_success(self):
        raw_text = "   This is a fully valid claim with enough characters to pass validation.   "
        resp = self.client.post("/api/v1/claims", data=json.dumps({"claim_text": raw_text}), content_type="application/json", **self.headers)
        
        self.assertEqual(resp.status_code, 201)
        data = resp.json()
        
        # 1. exact top-level key set
        self.assertSetEqual(set(data.keys()), {"success", "message", "data"})
        self.assertTrue(data["success"])
        self.assertEqual(data["message"], "Claim submitted successfully.")
        
        # 2. exact data key set
        claim_data = data["data"]
        self.assertSetEqual(set(claim_data.keys()), {"id", "claim_text", "status", "created_at"})
        self.assertEqual(claim_data["status"], "PENDING")
        self.assertEqual(claim_data["claim_text"], "This is a fully valid claim with enough characters to pass validation.")
        
        # 3. database checks
        claim = Claim.objects.get(id=claim_data["id"])
        self.assertEqual(claim.user, self.user)
        self.assertFalse(claim.is_deleted)
        self.assertEqual(claim.status, "PENDING")
        self.assertEqual(claim.text, "This is a fully valid claim with enough characters to pass validation.")

    def test_get_claim_unauthenticated(self):
        resp = self.client.get(f"/api/v1/claims/{self.claim.id}")
        self.assertEqual(resp.status_code, 401)

    def test_get_claim_owner_success(self):
        resp = self.client.get(f"/api/v1/claims/{self.claim.id}", **self.headers)
        self.assertEqual(resp.status_code, 200)
        
        data = resp.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["message"], "Claim retrieved successfully.")
        
        claim_data = data["data"]
        self.assertEqual(claim_data["id"], str(self.claim.id))
        self.assertEqual(claim_data["claim_text"], self.claim.text)
        self.assertEqual(claim_data["status"], self.claim.status)
        self.assertIn("created_at", claim_data)
        self.assertIn("updated_at", claim_data)
        self.assertFalse(claim_data["analysis_available"])

    def test_get_claim_admin_success(self):
        resp = self.client.get(f"/api/v1/claims/{self.claim.id}", **self.admin_headers)
        self.assertEqual(resp.status_code, 200)

    def test_get_claim_unauthorized_user(self):
        resp = self.client.get(f"/api/v1/claims/{self.claim.id}", **self.other_headers)
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.json()["error_code"], "PERMISSION_DENIED")

    def test_get_claim_not_found(self):
        import uuid
        random_id = uuid.uuid4()
        resp = self.client.get(f"/api/v1/claims/{random_id}", **self.headers)
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(resp.json()["error_code"], "NOT_FOUND")

    def test_get_claim_soft_deleted(self):
        self.claim.is_deleted = True
        self.claim.save()
        resp = self.client.get(f"/api/v1/claims/{self.claim.id}", **self.headers)
        self.assertEqual(resp.status_code, 404)

    def test_get_claim_malformed_uuid(self):
        resp = self.client.get("/api/v1/claims/not-a-uuid", **self.headers)
        self.assertEqual(resp.status_code, 422)

    # ==========================================
    # API-010: User Claim History API Tests
    # ==========================================

    def test_claim_history_unauthenticated(self):
        resp = self.client.get("/api/v1/claims/history")
        self.assertEqual(resp.status_code, 401)
        self.assertEqual(resp.json()["error_code"], "AUTHENTICATION_ERROR")

    def test_claim_history_invalid_token(self):
        resp = self.client.get("/api/v1/claims/history", HTTP_AUTHORIZATION="Bearer invalid_token_123")
        self.assertEqual(resp.status_code, 401)
        self.assertEqual(resp.json()["error_code"], "AUTHENTICATION_ERROR")

    def test_claim_history_own_claims_only(self):
        # Create claim for other_user
        Claim.objects.create(user=self.other_user, text="Other user's confidential claim text")
        
        resp = self.client.get("/api/v1/claims/history", **self.headers)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        
        self.assertEqual(data["count"], 1)
        self.assertEqual(len(data["results"]), 1)
        self.assertEqual(data["results"][0]["id"], str(self.claim.id))

    def test_claim_history_soft_deleted_excluded(self):
        # Create second claim for user and soft-delete it
        deleted_c = Claim.objects.create(user=self.user, text="Deleted claim that should be hidden", is_deleted=True)
        
        resp = self.client.get("/api/v1/claims/history", **self.headers)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        self.assertEqual(data["count"], 1)
        self.assertEqual(data["results"][0]["id"], str(self.claim.id))
        ids = [item["id"] for item in data["results"]]
        self.assertNotIn(str(deleted_c.id), ids)

    def test_claim_history_empty(self):
        # Create a fresh user with 0 claims
        new_user = User.objects.create_user(email="empty_claims@example.com", password="password123", full_name="Empty User")
        login_resp = self.client.post("/api/v1/auth/login", data=json.dumps({"email": "empty_claims@example.com", "password": "password123"}), content_type="application/json")
        headers = {"HTTP_AUTHORIZATION": f"Bearer {login_resp.json()['data']['access_token']}"}

        resp = self.client.get("/api/v1/claims/history", **headers)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["count"], 0)
        self.assertIsNone(data["next"])
        self.assertIsNone(data["previous"])
        self.assertEqual(data["results"], [])

    def test_claim_history_with_analysis_record(self):
        Analysis.objects.create(claim=self.claim, verdict="CREDIBLE", credibility_score=92.5)

        resp = self.client.get("/api/v1/claims/history", **self.headers)
        self.assertEqual(resp.status_code, 200)
        result = resp.json()["results"][0]

        self.assertEqual(result["id"], str(self.claim.id))
        self.assertEqual(result["verdict"], "CREDIBLE")
        self.assertEqual(result["credibility_score"], 92.5)

    def test_claim_history_without_analysis_record(self):
        resp = self.client.get("/api/v1/claims/history", **self.headers)
        self.assertEqual(resp.status_code, 200)
        result = resp.json()["results"][0]

        self.assertEqual(result["id"], str(self.claim.id))
        self.assertIsNone(result["verdict"])
        self.assertIsNone(result["credibility_score"])

    def test_claim_history_with_null_analysis_score(self):
        Analysis.objects.create(claim=self.claim, verdict=None, credibility_score=None)

        resp = self.client.get("/api/v1/claims/history", **self.headers)
        self.assertEqual(resp.status_code, 200)
        result = resp.json()["results"][0]

        self.assertEqual(result["id"], str(self.claim.id))
        self.assertIsNone(result["verdict"])
        self.assertIsNone(result["credibility_score"])

    def test_claim_history_pagination_standard_and_middle_and_last_page(self):
        # Create 4 additional claims for self.user (total 5)
        for i in range(4):
            Claim.objects.create(user=self.user, text=f"Pagination test claim number {i+2}")

        # Page 1 (page_size=2)
        resp1 = self.client.get("/api/v1/claims/history?page=1&page_size=2", **self.headers)
        self.assertEqual(resp1.status_code, 200)
        d1 = resp1.json()
        self.assertEqual(d1["count"], 5)
        self.assertEqual(len(d1["results"]), 2)
        self.assertIsNotNone(d1["next"])
        self.assertIsNone(d1["previous"])
        self.assertIn("page=2", d1["next"])

        # Page 2 (middle page)
        resp2 = self.client.get("/api/v1/claims/history?page=2&page_size=2", **self.headers)
        self.assertEqual(resp2.status_code, 200)
        d2 = resp2.json()
        self.assertEqual(d2["count"], 5)
        self.assertEqual(len(d2["results"]), 2)
        self.assertIsNotNone(d2["next"])
        self.assertIsNotNone(d2["previous"])
        self.assertIn("page=3", d2["next"])
        self.assertIn("page=1", d2["previous"])

        # Page 3 (last page)
        resp3 = self.client.get("/api/v1/claims/history?page=3&page_size=2", **self.headers)
        self.assertEqual(resp3.status_code, 200)
        d3 = resp3.json()
        self.assertEqual(d3["count"], 5)
        self.assertEqual(len(d3["results"]), 1)
        self.assertIsNone(d3["next"])
        self.assertIsNotNone(d3["previous"])
        self.assertIn("page=2", d3["previous"])

    def test_claim_history_pagination_out_of_range_page(self):
        resp = self.client.get("/api/v1/claims/history?page=10&page_size=2", **self.headers)
        self.assertEqual(resp.status_code, 200)
        d = resp.json()
        self.assertEqual(d["count"], 1)
        self.assertEqual(d["results"], [])
        self.assertIsNone(d["next"])
        self.assertIsNotNone(d["previous"])
        self.assertIn("page=9", d["previous"])

    def test_claim_history_pagination_invalid_page_zero_or_negative(self):
        resp = self.client.get("/api/v1/claims/history?page=0", **self.headers)
        self.assertEqual(resp.status_code, 422)
        self.assertEqual(resp.json()["error_code"], "VALIDATION_ERROR")

        resp_neg = self.client.get("/api/v1/claims/history?page=-1", **self.headers)
        self.assertEqual(resp_neg.status_code, 422)
        self.assertEqual(resp_neg.json()["error_code"], "VALIDATION_ERROR")

    def test_claim_history_pagination_invalid_page_size_zero_or_exceeds_max(self):
        resp_zero = self.client.get("/api/v1/claims/history?page_size=0", **self.headers)
        self.assertEqual(resp_zero.status_code, 422)
        self.assertEqual(resp_zero.json()["error_code"], "VALIDATION_ERROR")

        resp_max = self.client.get("/api/v1/claims/history?page_size=101", **self.headers)
        self.assertEqual(resp_max.status_code, 422)
        self.assertEqual(resp_max.json()["error_code"], "VALIDATION_ERROR")

    def test_claim_history_pagination_links_preserve_params(self):
        # Create 2 more claims (total 3)
        Claim.objects.create(user=self.user, text="Link test extra claim 1")
        Claim.objects.create(user=self.user, text="Link test extra claim 2")

        resp = self.client.get("/api/v1/claims/history?page=1&page_size=2&ordering=credibility_score", **self.headers)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        self.assertIsNotNone(data["next"])
        self.assertEqual(data["next"], "/api/v1/claims/history?page=2&page_size=2&ordering=credibility_score")

        resp2 = self.client.get(data["next"], **self.headers)
        self.assertEqual(resp2.status_code, 200)
        data2 = resp2.json()
        self.assertEqual(data2["previous"], "/api/v1/claims/history?page=1&page_size=2&ordering=credibility_score")

    def test_claim_history_sorting_created_at_desc_and_asc(self):
        from datetime import timedelta
        from django.utils import timezone
        
        now = timezone.now()
        c2 = Claim.objects.create(user=self.user, text="Newer claim text for sorting")
        Claim.objects.filter(id=self.claim.id).update(submitted_at=now - timedelta(seconds=10))
        Claim.objects.filter(id=c2.id).update(submitted_at=now)

        # Default / -created_at: newest first
        resp_desc = self.client.get("/api/v1/claims/history?ordering=-created_at", **self.headers)
        self.assertEqual(resp_desc.status_code, 200)
        results_desc = resp_desc.json()["results"]
        self.assertEqual(results_desc[0]["id"], str(c2.id))
        self.assertEqual(results_desc[1]["id"], str(self.claim.id))

        # created_at: oldest first
        resp_asc = self.client.get("/api/v1/claims/history?ordering=created_at", **self.headers)
        self.assertEqual(resp_asc.status_code, 200)
        results_asc = resp_asc.json()["results"]
        self.assertEqual(results_asc[0]["id"], str(self.claim.id))
        self.assertEqual(results_asc[1]["id"], str(c2.id))

    def test_claim_history_sorting_credibility_score_desc_and_asc_nulls_last(self):
        # Setup:
        # claim_high: score 90.0
        # claim_low: score 20.0
        # claim_null_score: analysis exists with credibility_score=None
        # claim_no_analysis: self.claim (no analysis record)
        claim_high = Claim.objects.create(user=self.user, text="High credibility claim text")
        Analysis.objects.create(claim=claim_high, credibility_score=90.0)

        claim_low = Claim.objects.create(user=self.user, text="Low credibility claim text")
        Analysis.objects.create(claim=claim_low, credibility_score=20.0)

        claim_null_score = Claim.objects.create(user=self.user, text="Claim with null analysis score")
        Analysis.objects.create(claim=claim_null_score, credibility_score=None)

        # DESC: 90.0 -> 20.0 -> nulls last (claim_null_score and self.claim)
        resp_desc = self.client.get("/api/v1/claims/history?ordering=-credibility_score", **self.headers)
        self.assertEqual(resp_desc.status_code, 200)
        results_desc = resp_desc.json()["results"]
        self.assertEqual(results_desc[0]["id"], str(claim_high.id))
        self.assertEqual(results_desc[1]["id"], str(claim_low.id))
        null_ids_desc = [r["id"] for r in results_desc[2:]]
        self.assertIn(str(claim_null_score.id), null_ids_desc)
        self.assertIn(str(self.claim.id), null_ids_desc)

        # ASC: 20.0 -> 90.0 -> nulls last (claim_null_score and self.claim)
        resp_asc = self.client.get("/api/v1/claims/history?ordering=credibility_score", **self.headers)
        self.assertEqual(resp_asc.status_code, 200)
        results_asc = resp_asc.json()["results"]
        self.assertEqual(results_asc[0]["id"], str(claim_low.id))
        self.assertEqual(results_asc[1]["id"], str(claim_high.id))
        null_ids_asc = [r["id"] for r in results_asc[2:]]
        self.assertIn(str(claim_null_score.id), null_ids_asc)
        self.assertIn(str(self.claim.id), null_ids_asc)

    def test_claim_history_sorting_status_asc_and_desc(self):
        c_completed = Claim.objects.create(user=self.user, text="Completed status claim", status=ClaimStatus.COMPLETED)

        resp_asc = self.client.get("/api/v1/claims/history?ordering=status", **self.headers)
        self.assertEqual(resp_asc.status_code, 200)
        self.assertEqual(resp_asc.json()["results"][0]["status"], ClaimStatus.COMPLETED)

        resp_desc = self.client.get("/api/v1/claims/history?ordering=-status", **self.headers)
        self.assertEqual(resp_desc.status_code, 200)
        self.assertEqual(resp_desc.json()["results"][0]["status"], ClaimStatus.PENDING)

    def test_claim_history_sorting_invalid_rejected_422(self):
        resp = self.client.get("/api/v1/claims/history?ordering=malicious_col", **self.headers)
        self.assertEqual(resp.status_code, 422)
        data = resp.json()
        self.assertEqual(data["error_code"], "VALIDATION_ERROR")
        self.assertIn("Invalid ordering 'malicious_col'", data["message"])

    def test_claim_history_deterministic_pagination_tied_values(self):
        # Create 3 more claims with identical status PENDING (total 4)
        for i in range(3):
            Claim.objects.create(user=self.user, text=f"Tied pending claim text {i+2}", status=ClaimStatus.PENDING)

        resp_p1 = self.client.get("/api/v1/claims/history?page=1&page_size=2&ordering=status", **self.headers)
        self.assertEqual(resp_p1.status_code, 200)
        ids_p1 = [r["id"] for r in resp_p1.json()["results"]]
        self.assertEqual(len(ids_p1), 2)

        resp_p2 = self.client.get("/api/v1/claims/history?page=2&page_size=2&ordering=status", **self.headers)
        self.assertEqual(resp_p2.status_code, 200)
        ids_p2 = [r["id"] for r in resp_p2.json()["results"]]
        self.assertEqual(len(ids_p2), 2)

        # Ensure no overlap between page 1 and page 2
        self.assertEqual(len(set(ids_p1).intersection(set(ids_p2))), 0)
        self.assertEqual(len(set(ids_p1).union(set(ids_p2))), 4)

    def test_claim_history_exact_response_structure(self):
        resp = self.client.get("/api/v1/claims/history", **self.headers)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        # Top-level keys
        self.assertSetEqual(set(data.keys()), {"count", "next", "previous", "results"})

        # Item keys
        item = data["results"][0]
        self.assertSetEqual(
            set(item.keys()),
            {"id", "claim_text", "status", "verdict", "credibility_score", "created_at"}
        )

        # Ensure internal model fields are not leaked
        self.assertNotIn("text", item)
        self.assertNotIn("submitted_at", item)
        self.assertNotIn("updated_at", item)
        self.assertNotIn("user", item)
        self.assertNotIn("user_id", item)
        self.assertNotIn("is_deleted", item)

    # ==========================================
    # API-011: Update Claim API Tests (CLAIM-004)
    # ==========================================

    def test_patch_claim_unauthenticated(self):
        resp = self.client.patch(
            f"/api/v1/claims/{self.claim.id}",
            data=json.dumps({"claim_text": "Updated text that is long enough."}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 401)
        self.assertEqual(resp.json()["error_code"], "AUTHENTICATION_ERROR")

    def test_patch_claim_invalid_token(self):
        resp = self.client.patch(
            f"/api/v1/claims/{self.claim.id}",
            data=json.dumps({"claim_text": "Updated text that is long enough."}),
            content_type="application/json",
            HTTP_AUTHORIZATION="Bearer invalid.token.value",
        )
        self.assertEqual(resp.status_code, 401)
        self.assertEqual(resp.json()["error_code"], "AUTHENTICATION_ERROR")

    def test_patch_claim_owner_success(self):
        new_text = "This is a freshly updated claim text that is sufficiently long."
        resp = self.client.patch(
            f"/api/v1/claims/{self.claim.id}",
            data=json.dumps({"claim_text": new_text}),
            content_type="application/json",
            **self.headers,
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        # Top-level keys
        self.assertSetEqual(set(data.keys()), {"success", "message", "data"})
        self.assertTrue(data["success"])
        self.assertEqual(data["message"], "Claim updated successfully.")

        # Data payload keys
        self.assertSetEqual(set(data["data"].keys()), {"id"})
        self.assertEqual(data["data"]["id"], str(self.claim.id))

        # Database state verification
        self.claim.refresh_from_db()
        self.assertEqual(self.claim.text, new_text)
        self.assertEqual(self.claim.status, ClaimStatus.PENDING)
        self.assertFalse(self.claim.is_deleted)
        self.assertIsNotNone(self.claim.updated_at)

    def test_patch_claim_non_owner_forbidden(self):
        resp = self.client.patch(
            f"/api/v1/claims/{self.claim.id}",
            data=json.dumps({"claim_text": "Attempted update by non-owner."}),
            content_type="application/json",
            **self.other_headers,
        )
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.json()["error_code"], "PERMISSION_DENIED")

    def test_patch_claim_admin_forbidden(self):
        resp = self.client.patch(
            f"/api/v1/claims/{self.claim.id}",
            data=json.dumps({"claim_text": "Attempted update by administrator."}),
            content_type="application/json",
            **self.admin_headers,
        )
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.json()["error_code"], "PERMISSION_DENIED")

    def test_patch_claim_not_found(self):
        import uuid
        random_id = uuid.uuid4()
        resp = self.client.patch(
            f"/api/v1/claims/{random_id}",
            data=json.dumps({"claim_text": "Valid text for missing claim."}),
            content_type="application/json",
            **self.headers,
        )
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(resp.json()["error_code"], "NOT_FOUND")

    def test_patch_claim_soft_deleted(self):
        self.claim.is_deleted = True
        self.claim.save(update_fields=["is_deleted"])

        resp = self.client.patch(
            f"/api/v1/claims/{self.claim.id}",
            data=json.dumps({"claim_text": "Valid text for soft-deleted claim."}),
            content_type="application/json",
            **self.headers,
        )
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(resp.json()["error_code"], "NOT_FOUND")

    def test_patch_claim_malformed_uuid(self):
        resp = self.client.patch(
            "/api/v1/claims/not-a-valid-uuid",
            data=json.dumps({"claim_text": "Valid text with bad UUID."}),
            content_type="application/json",
            **self.headers,
        )
        self.assertEqual(resp.status_code, 422)
        self.assertEqual(resp.json()["error_code"], "VALIDATION_ERROR")

    def test_patch_claim_status_processing_conflict(self):
        self.claim.status = ClaimStatus.PROCESSING
        self.claim.save(update_fields=["status"])

        resp = self.client.patch(
            f"/api/v1/claims/{self.claim.id}",
            data=json.dumps({"claim_text": "Valid text for processing claim."}),
            content_type="application/json",
            **self.headers,
        )
        self.assertEqual(resp.status_code, 409)
        data = resp.json()
        self.assertEqual(data["error_code"], "HTTP_409_ERROR")
        self.assertEqual(data["message"], "Analysis already started")

    def test_patch_claim_status_completed_conflict(self):
        self.claim.status = ClaimStatus.COMPLETED
        self.claim.save(update_fields=["status"])

        resp = self.client.patch(
            f"/api/v1/claims/{self.claim.id}",
            data=json.dumps({"claim_text": "Valid text for completed claim."}),
            content_type="application/json",
            **self.headers,
        )
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.json()["error_code"], "HTTP_409_ERROR")

    def test_patch_claim_status_failed_conflict(self):
        self.claim.status = ClaimStatus.FAILED
        self.claim.save(update_fields=["status"])

        resp = self.client.patch(
            f"/api/v1/claims/{self.claim.id}",
            data=json.dumps({"claim_text": "Valid text for failed claim."}),
            content_type="application/json",
            **self.headers,
        )
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.json()["error_code"], "HTTP_409_ERROR")

    def test_patch_claim_validation_missing_text(self):
        resp = self.client.patch(
            f"/api/v1/claims/{self.claim.id}",
            data=json.dumps({}),
            content_type="application/json",
            **self.headers,
        )
        self.assertEqual(resp.status_code, 422)
        self.assertEqual(resp.json()["error_code"], "VALIDATION_ERROR")

    def test_patch_claim_validation_too_short(self):
        resp = self.client.patch(
            f"/api/v1/claims/{self.claim.id}",
            data=json.dumps({"claim_text": "Short"}),
            content_type="application/json",
            **self.headers,
        )
        self.assertEqual(resp.status_code, 422)
        self.assertEqual(resp.json()["error_code"], "VALIDATION_ERROR")

    def test_patch_claim_validation_too_long(self):
        long_text = "A" * 2001
        resp = self.client.patch(
            f"/api/v1/claims/{self.claim.id}",
            data=json.dumps({"claim_text": long_text}),
            content_type="application/json",
            **self.headers,
        )
        self.assertEqual(resp.status_code, 422)
        self.assertEqual(resp.json()["error_code"], "VALIDATION_ERROR")

    def test_patch_claim_validation_whitespace_only(self):
        resp = self.client.patch(
            f"/api/v1/claims/{self.claim.id}",
            data=json.dumps({"claim_text": "          "}),
            content_type="application/json",
            **self.headers,
        )
        self.assertEqual(resp.status_code, 422)
        self.assertEqual(resp.json()["error_code"], "VALIDATION_ERROR")

    def test_patch_claim_validation_html_rejected(self):
        resp = self.client.patch(
            f"/api/v1/claims/{self.claim.id}",
            data=json.dumps({"claim_text": "<b>This has HTML tags</b> and is long enough."}),
            content_type="application/json",
            **self.headers,
        )
        self.assertEqual(resp.status_code, 422)
        self.assertEqual(resp.json()["error_code"], "VALIDATION_ERROR")

    def test_patch_claim_extra_fields_immunity(self):
        valid_text = "Valid updated text with lots of characters."
        resp = self.client.patch(
            f"/api/v1/claims/{self.claim.id}",
            data=json.dumps({
                "claim_text": valid_text,
                "status": "COMPLETED",
                "user_id": str(self.other_user.id),
                "is_deleted": True,
                "id": str(self.claim.id),
                "verdict": "VERIFIED",
                "credibility_score": 99.0,
            }),
            content_type="application/json",
            **self.headers,
        )
        self.assertEqual(resp.status_code, 200)

        self.claim.refresh_from_db()
        self.assertEqual(self.claim.text, valid_text)
        self.assertEqual(self.claim.status, ClaimStatus.PENDING)
        self.assertFalse(self.claim.is_deleted)
        self.assertEqual(self.claim.user, self.user)

    def _is_conditional_claim_update(self, qs, kwargs):
        if qs.model is not Claim or not {"text", "updated_at"}.issubset(kwargs.keys()):
            return False
        where_filters = {}
        for child in qs.query.where.children:
            target = getattr(getattr(child, "lhs", None), "target", None)
            if target and hasattr(target, "name"):
                where_filters[target.name] = getattr(child, "rhs", None)
        return (
            where_filters.get("id") == self.claim.id
            and where_filters.get("status") == ClaimStatus.PENDING
            and where_filters.get("is_deleted") is False
        )

    def test_patch_claim_zero_row_concurrent_status_change(self):
        from django.db.models import QuerySet
        from unittest.mock import patch

        original_update = QuerySet.update

        def side_effect(qs, *args, **kwargs):
            if self._is_conditional_claim_update(qs, kwargs):
                original_update(Claim.objects.filter(id=self.claim.id), status=ClaimStatus.PROCESSING)
                return original_update(qs, *args, **kwargs)
            return original_update(qs, *args, **kwargs)

        with patch.object(QuerySet, "update", autospec=True, side_effect=side_effect):
            resp = self.client.patch(
                f"/api/v1/claims/{self.claim.id}",
                data=json.dumps({"claim_text": "Updated text for status transition."}),
                content_type="application/json",
                **self.headers,
            )
            self.assertEqual(resp.status_code, 409)
            self.assertEqual(resp.json()["error_code"], "HTTP_409_ERROR")
            self.assertEqual(resp.json()["message"], "Analysis already started")

    def test_patch_claim_zero_row_concurrent_soft_delete(self):
        from django.db.models import QuerySet
        from unittest.mock import patch

        original_update = QuerySet.update

        def side_effect(qs, *args, **kwargs):
            if self._is_conditional_claim_update(qs, kwargs):
                original_update(Claim.objects.filter(id=self.claim.id), is_deleted=True)
                return original_update(qs, *args, **kwargs)
            return original_update(qs, *args, **kwargs)

        with patch.object(QuerySet, "update", autospec=True, side_effect=side_effect):
            resp = self.client.patch(
                f"/api/v1/claims/{self.claim.id}",
                data=json.dumps({"claim_text": "Updated text for soft deletion."}),
                content_type="application/json",
                **self.headers,
            )
            self.assertEqual(resp.status_code, 404)
            self.assertEqual(resp.json()["error_code"], "NOT_FOUND")

    def test_patch_claim_zero_row_defensive_fallback(self):
        from django.db.models import QuerySet
        from unittest.mock import patch

        original_update = QuerySet.update

        def side_effect(qs, *args, **kwargs):
            if self._is_conditional_claim_update(qs, kwargs):
                return 0
            return original_update(qs, *args, **kwargs)

        with patch.object(QuerySet, "update", autospec=True, side_effect=side_effect):
            resp = self.client.patch(
                f"/api/v1/claims/{self.claim.id}",
                data=json.dumps({"claim_text": "Updated text for fallback."}),
                content_type="application/json",
                **self.headers,
            )
            self.assertEqual(resp.status_code, 409)
            self.assertEqual(resp.json()["error_code"], "HTTP_409_ERROR")
            self.assertEqual(resp.json()["message"], "Claim update conflict. The claim could not be updated.")

    def test_patch_claim_app_admin_role_cannot_update_other_user_claim(self):
        initial_text = self.claim.text
        resp = self.client.patch(
            f"/api/v1/claims/{self.claim.id}",
            data=json.dumps({"claim_text": "Admin trying to edit claim text."}),
            content_type="application/json",
            **self.app_admin_headers,
        )
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.json()["error_code"], "PERMISSION_DENIED")

        self.claim.refresh_from_db()
        self.assertEqual(self.claim.text, initial_text)

    def test_delete_claim_unauthenticated(self):
        resp = self.client.delete(f"/api/v1/claims/{self.claim.id}")
        self.assertEqual(resp.status_code, 401)
        self.assertEqual(resp.json()["error_code"], "AUTHENTICATION_ERROR")

    def test_delete_claim_owner_success(self):
        resp = self.client.delete(f"/api/v1/claims/{self.claim.id}", **self.headers)
        self.assertEqual(resp.status_code, 204)
        self.assertEqual(resp.content, b"")

        self.claim.refresh_from_db()
        self.assertTrue(self.claim.is_deleted)
        self.assertTrue(Claim.objects.filter(id=self.claim.id).exists())

    def test_delete_claim_non_owner_forbidden(self):
        resp = self.client.delete(f"/api/v1/claims/{self.claim.id}", **self.other_headers)
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.json()["error_code"], "PERMISSION_DENIED")

        self.claim.refresh_from_db()
        self.assertFalse(self.claim.is_deleted)

    def test_delete_claim_admin_role_non_superuser_success(self):
        self.claim.status = ClaimStatus.COMPLETED
        self.claim.save(update_fields=["status"])

        resp = self.client.delete(f"/api/v1/claims/{self.claim.id}", **self.app_admin_headers)
        self.assertEqual(resp.status_code, 204)
        self.assertEqual(resp.content, b"")

        self.claim.refresh_from_db()
        self.assertTrue(self.claim.is_deleted)

    def test_delete_claim_superuser_success(self):
        self.claim.status = ClaimStatus.COMPLETED
        self.claim.save(update_fields=["status"])

        resp = self.client.delete(f"/api/v1/claims/{self.claim.id}", **self.admin_headers)
        self.assertEqual(resp.status_code, 204)
        self.assertEqual(resp.content, b"")

        self.claim.refresh_from_db()
        self.assertTrue(self.claim.is_deleted)

    def test_delete_claim_status_conflict_owner(self):
        self.claim.status = ClaimStatus.PROCESSING
        self.claim.save(update_fields=["status"])

        resp = self.client.delete(f"/api/v1/claims/{self.claim.id}", **self.headers)
        self.assertEqual(resp.status_code, 409)
        data = resp.json()
        self.assertEqual(data["error_code"], "HTTP_409_ERROR")
        self.assertEqual(data["message"], "Cannot delete analyzed claim")

        self.claim.refresh_from_db()
        self.assertFalse(self.claim.is_deleted)

    def test_delete_claim_not_found(self):
        import uuid
        random_id = uuid.uuid4()
        resp = self.client.delete(f"/api/v1/claims/{random_id}", **self.headers)
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(resp.json()["error_code"], "NOT_FOUND")

    def test_delete_claim_soft_deleted(self):
        self.claim.is_deleted = True
        self.claim.save(update_fields=["is_deleted"])

        resp = self.client.delete(f"/api/v1/claims/{self.claim.id}", **self.headers)
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(resp.json()["error_code"], "NOT_FOUND")

    def test_delete_claim_malformed_uuid(self):
        resp = self.client.delete("/api/v1/claims/not-a-valid-uuid", **self.headers)
        self.assertEqual(resp.status_code, 422)
        self.assertEqual(resp.json()["error_code"], "VALIDATION_ERROR")

    def test_delete_claim_retains_related_objects_and_excludes_from_endpoints(self):
        feedback = ClaimFeedback.objects.create(
            user=self.user,
            claim=self.claim,
            feedback_type=FeedbackType.HELPFUL,
        )

        resp = self.client.delete(f"/api/v1/claims/{self.claim.id}", **self.headers)
        self.assertEqual(resp.status_code, 204)

        # Database rows still exist
        self.assertTrue(Claim.objects.filter(id=self.claim.id).exists())
        self.assertTrue(ClaimFeedback.objects.filter(id=feedback.id).exists())

        # Excluded from GET /api/v1/claims/{id}
        get_resp = self.client.get(f"/api/v1/claims/{self.claim.id}", **self.headers)
        self.assertEqual(get_resp.status_code, 404)

        # Excluded from GET /api/v1/claims/history
        history_resp = self.client.get("/api/v1/claims/history", **self.headers)
        self.assertEqual(history_resp.status_code, 200)
        history_ids = [item["id"] for item in history_resp.json()["results"]]
        self.assertNotIn(str(self.claim.id), history_ids)

    def _is_conditional_claim_delete(self, qs, kwargs):
        if qs.model is not Claim or not {"is_deleted", "updated_at"}.issubset(kwargs.keys()):
            return False
        where_filters = {}
        for child in qs.query.where.children:
            target = getattr(getattr(child, "lhs", None), "target", None)
            if target and hasattr(target, "name"):
                where_filters[target.name] = getattr(child, "rhs", None)
        return (
            where_filters.get("id") == self.claim.id
            and where_filters.get("is_deleted") is False
        )

    def test_delete_claim_zero_row_concurrent_status_change(self):
        from django.db.models import QuerySet
        from unittest.mock import patch

        original_update = QuerySet.update

        def side_effect(qs, *args, **kwargs):
            if self._is_conditional_claim_delete(qs, kwargs):
                original_update(Claim.objects.filter(id=self.claim.id), status=ClaimStatus.PROCESSING)
                return original_update(qs, *args, **kwargs)
            return original_update(qs, *args, **kwargs)

        with patch.object(QuerySet, "update", autospec=True, side_effect=side_effect):
            resp = self.client.delete(
                f"/api/v1/claims/{self.claim.id}",
                **self.headers,
            )
            self.assertEqual(resp.status_code, 409)
            self.assertEqual(resp.json()["error_code"], "HTTP_409_ERROR")
            self.assertEqual(resp.json()["message"], "Cannot delete analyzed claim")

    def test_delete_claim_zero_row_concurrent_soft_delete(self):
        from django.db.models import QuerySet
        from unittest.mock import patch

        original_update = QuerySet.update

        def side_effect(qs, *args, **kwargs):
            if self._is_conditional_claim_delete(qs, kwargs):
                original_update(Claim.objects.filter(id=self.claim.id), is_deleted=True)
                return original_update(qs, *args, **kwargs)
            return original_update(qs, *args, **kwargs)

        with patch.object(QuerySet, "update", autospec=True, side_effect=side_effect):
            resp = self.client.delete(
                f"/api/v1/claims/{self.claim.id}",
                **self.headers,
            )
            self.assertEqual(resp.status_code, 404)
            self.assertEqual(resp.json()["error_code"], "NOT_FOUND")

    def test_delete_claim_zero_row_defensive_fallback(self):
        from django.db.models import QuerySet
        from unittest.mock import patch

        original_update = QuerySet.update

        def side_effect(qs, *args, **kwargs):
            if self._is_conditional_claim_delete(qs, kwargs):
                return 0
            return original_update(qs, *args, **kwargs)

        with patch.object(QuerySet, "update", autospec=True, side_effect=side_effect):
            resp = self.client.delete(
                f"/api/v1/claims/{self.claim.id}",
                **self.headers,
            )
            self.assertEqual(resp.status_code, 409)
            self.assertEqual(resp.json()["error_code"], "HTTP_409_ERROR")
            self.assertEqual(resp.json()["message"], "Claim delete conflict. The claim could not be updated.")

    # =========================================================================
    # API-013: Administrative Claims List Pagination & Authorization Tests
    # =========================================================================

    def test_admin_claims_list_default_pagination(self):
        resp = self.client.get("/api/v1/admin/claims", **self.admin_headers)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        self.assertSetEqual(set(data.keys()), {"count", "next", "previous", "results"})
        self.assertEqual(data["count"], 1)
        self.assertIsNone(data["next"])
        self.assertIsNone(data["previous"])
        self.assertEqual(len(data["results"]), 1)

        item = data["results"][0]
        self.assertSetEqual(
            set(item.keys()),
            {"claim_id", "claim_text", "submitted_by", "analysis_status", "verdict", "created_at"},
        )
        self.assertEqual(item["claim_id"], str(self.claim.id))
        self.assertEqual(item["claim_text"], self.claim.text)
        self.assertEqual(item["submitted_by"], self.user.full_name)
        self.assertEqual(item["analysis_status"], "PENDING")
        self.assertIsNone(item["verdict"])
        self.assertIn("T", item["created_at"])

    def test_admin_claims_list_custom_page_size_and_navigation(self):
        from datetime import timedelta
        from django.utils import timezone

        now = timezone.now()
        # Seed 4 additional claims to reach 5 total
        c2 = Claim.objects.create(user=self.user, text="Second test claim text.")
        c3 = Claim.objects.create(user=self.other_user, text="Third test claim text.")
        c4 = Claim.objects.create(user=self.other_user, text="Fourth test claim text.")
        c5 = Claim.objects.create(user=self.user, text="Fifth test claim text.")

        Claim.objects.filter(id=self.claim.id).update(submitted_at=now - timedelta(seconds=50))
        Claim.objects.filter(id=c2.id).update(submitted_at=now - timedelta(seconds=40))
        Claim.objects.filter(id=c3.id).update(submitted_at=now - timedelta(seconds=30))
        Claim.objects.filter(id=c4.id).update(submitted_at=now - timedelta(seconds=20))
        Claim.objects.filter(id=c5.id).update(submitted_at=now - timedelta(seconds=10))

        # Page 1: 2 items
        resp1 = self.client.get("/api/v1/admin/claims?page=1&page_size=2", **self.admin_headers)
        self.assertEqual(resp1.status_code, 200)
        d1 = resp1.json()
        self.assertEqual(d1["count"], 5)
        self.assertEqual(len(d1["results"]), 2)
        self.assertEqual(d1["next"], "/api/v1/admin/claims?page=2&page_size=2")
        self.assertIsNone(d1["previous"])
        self.assertEqual(d1["results"][0]["claim_id"], str(c5.id))
        self.assertEqual(d1["results"][1]["claim_id"], str(c4.id))

        # Page 2: 2 items
        resp2 = self.client.get("/api/v1/admin/claims?page=2&page_size=2", **self.admin_headers)
        self.assertEqual(resp2.status_code, 200)
        d2 = resp2.json()
        self.assertEqual(d2["count"], 5)
        self.assertEqual(len(d2["results"]), 2)
        self.assertEqual(d2["next"], "/api/v1/admin/claims?page=3&page_size=2")
        self.assertEqual(d2["previous"], "/api/v1/admin/claims?page=1&page_size=2")
        self.assertEqual(d2["results"][0]["claim_id"], str(c3.id))
        self.assertEqual(d2["results"][1]["claim_id"], str(c2.id))

        # Page 3: 1 item
        resp3 = self.client.get("/api/v1/admin/claims?page=3&page_size=2", **self.admin_headers)
        self.assertEqual(resp3.status_code, 200)
        d3 = resp3.json()
        self.assertEqual(d3["count"], 5)
        self.assertEqual(len(d3["results"]), 1)
        self.assertIsNone(d3["next"])
        self.assertEqual(d3["previous"], "/api/v1/admin/claims?page=2&page_size=2")
        self.assertEqual(d3["results"][0]["claim_id"], str(self.claim.id))

    def test_admin_claims_list_max_page_size(self):
        resp = self.client.get("/api/v1/admin/claims?page_size=100", **self.admin_headers)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["count"], 1)

    def test_admin_claims_list_validation_rejections(self):
        for invalid_url in [
            "/api/v1/admin/claims?page=0",
            "/api/v1/admin/claims?page=-1",
            "/api/v1/admin/claims?page_size=0",
            "/api/v1/admin/claims?page_size=101",
            "/api/v1/admin/claims?page=abc",
        ]:
            resp = self.client.get(invalid_url, **self.admin_headers)
            self.assertEqual(resp.status_code, 422, f"Expected 422 for {invalid_url}")
            self.assertEqual(resp.json()["error_code"], "VALIDATION_ERROR")

    def test_admin_claims_list_out_of_range_page(self):
        resp = self.client.get("/api/v1/admin/claims?page=50&page_size=10", **self.admin_headers)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["results"], [])
        self.assertIsNone(data["next"])
        self.assertEqual(data["previous"], "/api/v1/admin/claims?page=49&page_size=10")

    def test_admin_claims_list_soft_deleted_excluded(self):
        self.claim.is_deleted = True
        self.claim.save(update_fields=["is_deleted"])

        resp = self.client.get("/api/v1/admin/claims", **self.admin_headers)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["count"], 0)
        self.assertEqual(data["results"], [])

    def test_admin_claims_list_with_and_without_analysis(self):
        analyzed_claim = Claim.objects.create(
            user=self.user,
            text="Claim that has an analysis verdict.",
            status=ClaimStatus.COMPLETED,
        )
        Analysis.objects.create(
            claim=analyzed_claim,
            verdict="CREDIBLE",
            credibility_score=92.5,
        )

        resp = self.client.get("/api/v1/admin/claims", **self.admin_headers)
        self.assertEqual(resp.status_code, 200)
        results = resp.json()["results"]
        self.assertEqual(len(results), 2)

        verdicts = {item["claim_id"]: item["verdict"] for item in results}
        self.assertEqual(verdicts[str(analyzed_claim.id)], "CREDIBLE")
        self.assertIsNone(verdicts[str(self.claim.id)])

    def test_admin_claims_list_app_admin_role_success(self):
        resp = self.client.get("/api/v1/admin/claims", **self.app_admin_headers)
        self.assertEqual(resp.status_code, 200)

    def test_admin_claims_list_superuser_with_user_role_success(self):
        # Specifically tests Finding 1: superuser whose role is 'USER'
        su_user = User.objects.create_user(
            email="superuser_user_role@example.com",
            password="password123",
            full_name="Super User Role USER",
            role="USER",
            is_superuser=True,
        )
        login_resp = self.client.post(
            "/api/v1/auth/login",
            data=json.dumps({"email": "superuser_user_role@example.com", "password": "password123"}),
            content_type="application/json",
        )
        su_headers = {"HTTP_AUTHORIZATION": f"Bearer {login_resp.json()['data']['access_token']}"}

        resp = self.client.get("/api/v1/admin/claims", **su_headers)
        self.assertEqual(resp.status_code, 200)

    def test_admin_claims_list_superuser_with_admin_role_success(self):
        resp = self.client.get("/api/v1/admin/claims", **self.admin_headers)
        self.assertEqual(resp.status_code, 200)

    def test_admin_claims_list_normal_user_forbidden(self):
        resp = self.client.get("/api/v1/admin/claims", **self.headers)
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.json()["error_code"], "PERMISSION_DENIED")

    def test_admin_claims_list_unauthenticated(self):
        resp = self.client.get("/api/v1/admin/claims")
        self.assertEqual(resp.status_code, 401)
        self.assertEqual(resp.json()["error_code"], "AUTHENTICATION_ERROR")

    def test_admin_claims_list_invalid_token(self):
        resp = self.client.get("/api/v1/admin/claims", HTTP_AUTHORIZATION="Bearer invalid_token_xyz")
        self.assertEqual(resp.status_code, 401)
        self.assertEqual(resp.json()["error_code"], "AUTHENTICATION_ERROR")

    # 7. Search API tests (API-014)
    def test_user_claim_history_search_returns_filtered_results(self):
        c_vac = Claim.objects.create(
            user=self.user,
            text="mRNA vaccine demonstrates high efficacy in trial.",
            status=ClaimStatus.COMPLETED,
        )
        resp = self.client.get("/api/v1/claims/history?search=vaccine", **self.headers)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["count"], 1)
        self.assertEqual(len(data["results"]), 1)
        self.assertEqual(data["results"][0]["id"], str(c_vac.id))

    def test_user_claim_history_search_preserves_query_in_pagination_links(self):
        from datetime import timedelta
        from django.utils import timezone

        now = timezone.now()
        # Seed 3 claims matching 'booster' for user
        b1 = Claim.objects.create(user=self.user, text="Booster dose first study details.")
        b2 = Claim.objects.create(user=self.user, text="Booster dose second study details.")
        b3 = Claim.objects.create(user=self.user, text="Booster dose third study details.")
        Claim.objects.filter(id=b1.id).update(submitted_at=now - timedelta(seconds=30))
        Claim.objects.filter(id=b2.id).update(submitted_at=now - timedelta(seconds=20))
        Claim.objects.filter(id=b3.id).update(submitted_at=now - timedelta(seconds=10))

        # Page 1: 2 items
        resp1 = self.client.get("/api/v1/claims/history?page=1&page_size=2&search=booster", **self.headers)
        self.assertEqual(resp1.status_code, 200)
        d1 = resp1.json()
        self.assertEqual(d1["count"], 3)
        self.assertEqual(len(d1["results"]), 2)
        self.assertEqual(d1["next"], "/api/v1/claims/history?page=2&page_size=2&search=booster")
        self.assertIsNone(d1["previous"])

        # Page 2: 1 item
        resp2 = self.client.get("/api/v1/claims/history?page=2&page_size=2&search=booster", **self.headers)
        self.assertEqual(resp2.status_code, 200)
        d2 = resp2.json()
        self.assertEqual(d2["count"], 3)
        self.assertEqual(len(d2["results"]), 1)
        self.assertIsNone(d2["next"])
        self.assertEqual(d2["previous"], "/api/v1/claims/history?page=1&page_size=2&search=booster")

    def test_user_claim_history_search_preserves_ordering_and_search_in_links(self):
        from datetime import timedelta
        from django.utils import timezone

        now = timezone.now()
        b1 = Claim.objects.create(user=self.user, text="Antibody response booster first study.")
        b2 = Claim.objects.create(user=self.user, text="Antibody response booster second study.")
        b3 = Claim.objects.create(user=self.user, text="Antibody response booster third study.")
        Claim.objects.filter(id=b1.id).update(submitted_at=now - timedelta(seconds=30))
        Claim.objects.filter(id=b2.id).update(submitted_at=now - timedelta(seconds=20))
        Claim.objects.filter(id=b3.id).update(submitted_at=now - timedelta(seconds=10))

        resp = self.client.get(
            "/api/v1/claims/history?page=1&page_size=2&ordering=-created_at&search=booster",
            **self.headers,
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["count"], 3)
        self.assertIn("ordering=-created_at", data["next"])
        self.assertIn("search=booster", data["next"])
        self.assertIn("page=2", data["next"])
        self.assertIn("page_size=2", data["next"])

    def test_user_claim_history_empty_search_omits_search_from_pagination_links(self):
        # 2 claims exist (self.claim + 1 new)
        Claim.objects.create(user=self.user, text="Second generic test claim.")
        for url in [
            "/api/v1/claims/history?page=1&page_size=1&search=",
            "/api/v1/claims/history?page=1&page_size=1&search=%20%20%20",
        ]:
            resp = self.client.get(url, **self.headers)
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertEqual(data["count"], 2)
            self.assertIsNotNone(data["next"])
            self.assertNotIn("search", data["next"])

    def test_user_claim_history_search_iso_date_controlled_timestamp(self):
        dt_target = datetime(2026, 6, 15, 10, 0, 0, tzinfo=dt_timezone.utc)
        dt_other = datetime(2026, 8, 1, 12, 0, 0, tzinfo=dt_timezone.utc)
        dt_unrelated = datetime(2026, 9, 1, 14, 0, 0, tzinfo=dt_timezone.utc)

        # Claim A: submitted on 2026-06-15, no date text
        c_by_date = Claim.objects.create(
            user=self.user,
            text="Clinical study results released without mention of day.",
            status=ClaimStatus.PENDING,
        )
        Claim.objects.filter(id=c_by_date.id).update(submitted_at=dt_target)

        # Claim B: submitted on 2026-08-01, text contains 2026-06-15
        c_by_text = Claim.objects.create(
            user=self.user,
            text="The event occurred on 2026-06-15 according to reports.",
            status=ClaimStatus.PENDING,
        )
        Claim.objects.filter(id=c_by_text.id).update(submitted_at=dt_other)

        # Claim C: submitted on 2026-09-01, unrelated text
        c_unrelated = Claim.objects.create(
            user=self.user,
            text="Completely unrelated topic with no dates.",
            status=ClaimStatus.PENDING,
        )
        Claim.objects.filter(id=c_unrelated.id).update(submitted_at=dt_unrelated)

        resp = self.client.get("/api/v1/claims/history?search=2026-06-15", **self.headers)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        ids = {item["id"] for item in data["results"]}
        self.assertIn(str(c_by_date.id), ids)
        self.assertIn(str(c_by_text.id), ids)
        self.assertNotIn(str(c_unrelated.id), ids)

    def test_admin_claims_search_returns_filtered_results(self):
        c1 = Claim.objects.create(user=self.user, text="Arctic climate shift observed.")
        c2 = Claim.objects.create(user=self.other_user, text="Tropical climate anomalies reported.")
        Claim.objects.create(user=self.user, text="Completely unrelated tech topic.")

        resp = self.client.get("/api/v1/admin/claims?search=climate", **self.admin_headers)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["count"], 2)
        claim_ids = {item["claim_id"] for item in data["results"]}
        self.assertIn(str(c1.id), claim_ids)
        self.assertIn(str(c2.id), claim_ids)

    def test_admin_claims_search_preserves_query_in_pagination_links(self):
        from datetime import timedelta
        from django.utils import timezone

        now = timezone.now()
        c1 = Claim.objects.create(user=self.user, text="Deforestation impact on ecosystem first.")
        c2 = Claim.objects.create(user=self.other_user, text="Deforestation impact on ecosystem second.")
        c3 = Claim.objects.create(user=self.user, text="Deforestation impact on ecosystem third.")
        Claim.objects.filter(id=c1.id).update(submitted_at=now - timedelta(seconds=30))
        Claim.objects.filter(id=c2.id).update(submitted_at=now - timedelta(seconds=20))
        Claim.objects.filter(id=c3.id).update(submitted_at=now - timedelta(seconds=10))

        resp = self.client.get("/api/v1/admin/claims?page=1&page_size=2&search=deforestation", **self.admin_headers)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["count"], 3)
        self.assertEqual(data["next"], "/api/v1/admin/claims?page=2&page_size=2&search=deforestation")
        self.assertIsNone(data["previous"])

        resp2 = self.client.get("/api/v1/admin/claims?page=2&page_size=2&search=deforestation", **self.admin_headers)
        self.assertEqual(resp2.status_code, 200)
        d2 = resp2.json()
        self.assertIsNone(d2["next"])
        self.assertEqual(d2["previous"], "/api/v1/admin/claims?page=1&page_size=2&search=deforestation")

    def test_admin_claims_search_empty_omits_param(self):
        resp = self.client.get("/api/v1/admin/claims?page=1&page_size=1&search=", **self.admin_headers)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        if data["next"]:
            self.assertNotIn("search", data["next"])

    def test_admin_claims_search_authorization_enforced(self):
        # Normal user gets 403
        resp_user = self.client.get("/api/v1/admin/claims?search=climate", **self.headers)
        self.assertEqual(resp_user.status_code, 403)
        self.assertEqual(resp_user.json()["error_code"], "PERMISSION_DENIED")

        # Unauthenticated gets 401
        resp_unauth = self.client.get("/api/v1/admin/claims?search=climate")
        self.assertEqual(resp_unauth.status_code, 401)
        self.assertEqual(resp_unauth.json()["error_code"], "AUTHENTICATION_ERROR")

    # API-015: Filtering Integration Tests
    def test_user_history_filter_by_status(self):
        self.claim.status = ClaimStatus.COMPLETED
        self.claim.save()
        c2 = Claim.objects.create(
            user=self.user,
            text="Second pending claim text is valid.",
            status=ClaimStatus.PENDING,
        )

        # Exact case match
        resp = self.client.get("/api/v1/claims/history?status=COMPLETED", **self.headers)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["results"][0]["id"], str(self.claim.id))

        # Case normalization (lowercase)
        resp_lower = self.client.get("/api/v1/claims/history?status=completed", **self.headers)
        self.assertEqual(resp_lower.status_code, 200)
        data_lower = resp_lower.json()
        self.assertEqual(data_lower["count"], 1)
        self.assertEqual(data_lower["results"][0]["id"], str(self.claim.id))

        # Filter other status
        resp_pending = self.client.get("/api/v1/claims/history?status=PENDING", **self.headers)
        self.assertEqual(resp_pending.status_code, 200)
        self.assertEqual(resp_pending.json()["count"], 1)
        self.assertEqual(resp_pending.json()["results"][0]["id"], str(c2.id))

    def test_user_history_filter_by_status_invalid_422(self):
        resp = self.client.get("/api/v1/claims/history?status=INVALID_STATUS", **self.headers)
        self.assertEqual(resp.status_code, 422)
        data = resp.json()
        self.assertEqual(data["error_code"], "VALIDATION_ERROR")
        self.assertIn("Invalid status", data["message"])

    def test_user_history_filter_by_verdict(self):
        Analysis.objects.create(claim=self.claim, verdict=Verdict.CREDIBLE, credibility_score=92.0)
        c2 = Claim.objects.create(
            user=self.user,
            text="Second claim text for verdict test.",
            status=ClaimStatus.COMPLETED,
        )
        Analysis.objects.create(claim=c2, verdict=Verdict.MISINFORMATION, credibility_score=18.0)
        c3_unanalyzed = Claim.objects.create(
            user=self.user,
            text="Third claim with no analysis present.",
            status=ClaimStatus.PENDING,
        )

        # CREDIBLE
        resp = self.client.get("/api/v1/claims/history?verdict=CREDIBLE", **self.headers)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["results"][0]["id"], str(self.claim.id))
        self.assertEqual(data["results"][0]["verdict"], "CREDIBLE")

        # Case normalization (lowercase)
        resp_lower = self.client.get("/api/v1/claims/history?verdict=credible", **self.headers)
        self.assertEqual(resp_lower.status_code, 200)
        self.assertEqual(resp_lower.json()["count"], 1)

        # MISINFORMATION
        resp_misinfo = self.client.get("/api/v1/claims/history?verdict=MISINFORMATION", **self.headers)
        self.assertEqual(resp_misinfo.status_code, 200)
        self.assertEqual(resp_misinfo.json()["count"], 1)
        self.assertEqual(resp_misinfo.json()["results"][0]["id"], str(c2.id))

        # Unanalyzed claim never returned when verdict is queried
        resp_uncertain = self.client.get("/api/v1/claims/history?verdict=UNCERTAIN", **self.headers)
        self.assertEqual(resp_uncertain.status_code, 200)
        self.assertEqual(resp_uncertain.json()["count"], 0)

    def test_user_history_filter_by_verdict_invalid_422(self):
        resp = self.client.get("/api/v1/claims/history?verdict=NOT_A_VERDICT", **self.headers)
        self.assertEqual(resp.status_code, 422)
        data = resp.json()
        self.assertEqual(data["error_code"], "VALIDATION_ERROR")
        self.assertIn("Invalid verdict", data["message"])

    def test_user_history_filter_date_range_exact_boundaries(self):
        # Precise boundary timestamps:
        dt_start = datetime(2026, 7, 1, 0, 0, 0, 0, tzinfo=dt_timezone.utc)
        dt_end = datetime(2026, 7, 1, 23, 59, 59, 999999, tzinfo=dt_timezone.utc)
        dt_next = datetime(2026, 7, 2, 0, 0, 0, 0, tzinfo=dt_timezone.utc)
        dt_prev = datetime(2026, 6, 30, 23, 59, 59, 999999, tzinfo=dt_timezone.utc)

        c_start = Claim.objects.create(user=self.user, text="Claim at boundary start 00:00:00.")
        c_end = Claim.objects.create(user=self.user, text="Claim at boundary end 23:59:59.")
        c_next = Claim.objects.create(user=self.user, text="Claim next day 00:00:00.")
        c_prev = Claim.objects.create(user=self.user, text="Claim previous day 23:59:59.")

        Claim.objects.filter(id=c_start.id).update(submitted_at=dt_start)
        Claim.objects.filter(id=c_end.id).update(submitted_at=dt_end)
        Claim.objects.filter(id=c_next.id).update(submitted_at=dt_next)
        Claim.objects.filter(id=c_prev.id).update(submitted_at=dt_prev)

        # Single day range 2026-07-01 to 2026-07-01
        resp = self.client.get("/api/v1/claims/history?date_from=2026-07-01&date_to=2026-07-01", **self.headers)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        result_ids = {r["id"] for r in data["results"]}
        self.assertIn(str(c_start.id), result_ids)
        self.assertIn(str(c_end.id), result_ids)
        self.assertNotIn(str(c_next.id), result_ids)
        self.assertNotIn(str(c_prev.id), result_ids)

        # date_from only
        resp_from = self.client.get("/api/v1/claims/history?date_from=2026-07-01", **self.headers)
        self.assertEqual(resp_from.status_code, 200)
        from_ids = {r["id"] for r in resp_from.json()["results"]}
        self.assertIn(str(c_start.id), from_ids)
        self.assertIn(str(c_end.id), from_ids)
        self.assertIn(str(c_next.id), from_ids)
        self.assertNotIn(str(c_prev.id), from_ids)

        # date_to only
        resp_to = self.client.get("/api/v1/claims/history?date_to=2026-07-01", **self.headers)
        self.assertEqual(resp_to.status_code, 200)
        to_ids = {r["id"] for r in resp_to.json()["results"]}
        self.assertIn(str(c_start.id), to_ids)
        self.assertIn(str(c_end.id), to_ids)
        self.assertIn(str(c_prev.id), to_ids)
        self.assertNotIn(str(c_next.id), to_ids)

    def test_user_history_filter_inverted_date_range_422(self):
        resp = self.client.get("/api/v1/claims/history?date_from=2026-07-10&date_to=2026-07-01", **self.headers)
        self.assertEqual(resp.status_code, 422)
        data = resp.json()
        self.assertEqual(data["error_code"], "VALIDATION_ERROR")
        self.assertIn("cannot be after date_to", data["message"])

    def test_user_history_filter_invalid_date_format_422(self):
        resp1 = self.client.get("/api/v1/claims/history?date_from=2026-13-45", **self.headers)
        self.assertEqual(resp1.status_code, 422)
        self.assertEqual(resp1.json()["error_code"], "VALIDATION_ERROR")

        resp2 = self.client.get("/api/v1/claims/history?date_to=not-a-date", **self.headers)
        self.assertEqual(resp2.status_code, 422)
        self.assertEqual(resp2.json()["error_code"], "VALIDATION_ERROR")

    def test_user_history_pagination_preserves_all_filters(self):
        dt_fixed = datetime(2026, 7, 2, 10, 0, 0, tzinfo=dt_timezone.utc)
        claims = []
        for i in range(3):
            c = Claim.objects.create(
                user=self.user,
                text=f"Climate study index entry number {i} with enough length.",
                status=ClaimStatus.COMPLETED,
            )
            Claim.objects.filter(id=c.id).update(submitted_at=dt_fixed - timedelta(seconds=i * 10))
            Analysis.objects.create(claim=c, verdict=Verdict.CREDIBLE, credibility_score=90.0)
            claims.append(c)

        url = (
            "/api/v1/claims/history?"
            "page=1&page_size=2&"
            "status=COMPLETED&verdict=CREDIBLE&"
            "date_from=2026-07-01&date_to=2026-07-03&"
            "ordering=-created_at&search=Climate"
        )
        resp = self.client.get(url, **self.headers)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["count"], 3)
        self.assertEqual(len(data["results"]), 2)
        next_url = data["next"]
        self.assertIsNotNone(next_url)
        self.assertIn("page=2", next_url)
        self.assertIn("page_size=2", next_url)
        self.assertIn("status=COMPLETED", next_url)
        self.assertIn("verdict=CREDIBLE", next_url)
        self.assertIn("date_from=2026-07-01", next_url)
        self.assertIn("date_to=2026-07-03", next_url)
        self.assertIn("ordering=-created_at", next_url)
        self.assertIn("search=Climate", next_url)

        # Follow page 2
        resp2 = self.client.get(next_url, **self.headers)
        self.assertEqual(resp2.status_code, 200)
        d2 = resp2.json()
        self.assertEqual(len(d2["results"]), 1)
        prev_url = d2["previous"]
        self.assertIsNotNone(prev_url)
        self.assertIn("page=1", prev_url)
        self.assertIn("status=COMPLETED", prev_url)
        self.assertIn("verdict=CREDIBLE", prev_url)
        self.assertIn("date_from=2026-07-01", prev_url)
        self.assertIn("date_to=2026-07-03", prev_url)
        self.assertIn("ordering=-created_at", prev_url)
        self.assertIn("search=Climate", prev_url)

    def test_user_history_unsupplied_filters_omitted_from_links(self):
        Claim.objects.create(user=self.user, text="Second claim for omission verification.")
        resp = self.client.get("/api/v1/claims/history?page=1&page_size=1&status=PENDING", **self.headers)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIsNotNone(data["next"])
        self.assertIn("status=PENDING", data["next"])
        self.assertNotIn("verdict", data["next"])
        self.assertNotIn("date_from", data["next"])
        self.assertNotIn("date_to", data["next"])
        self.assertNotIn("search", data["next"])

    def test_admin_claims_filter_user_id(self):
        # self.claim belongs to self.user
        c_other = Claim.objects.create(user=self.other_user, text="Other user claim for admin filter.")

        # Filter by self.user.id
        resp_user = self.client.get(f"/api/v1/admin/claims?user_id={self.user.id}", **self.admin_headers)
        self.assertEqual(resp_user.status_code, 200)
        ids_user = {item["claim_id"] for item in resp_user.json()["results"]}
        self.assertIn(str(self.claim.id), ids_user)
        self.assertNotIn(str(c_other.id), ids_user)

        # Filter by self.other_user.id
        resp_other = self.client.get(f"/api/v1/admin/claims?user_id={self.other_user.id}", **self.admin_headers)
        self.assertEqual(resp_other.status_code, 200)
        ids_other = {item["claim_id"] for item in resp_other.json()["results"]}
        self.assertIn(str(c_other.id), ids_other)
        self.assertNotIn(str(self.claim.id), ids_other)

    def test_admin_claims_filter_user_id_invalid_uuid_422(self):
        resp = self.client.get("/api/v1/admin/claims?user_id=not-a-valid-uuid", **self.admin_headers)
        self.assertEqual(resp.status_code, 422)
        data = resp.json()
        self.assertEqual(data["error_code"], "VALIDATION_ERROR")

    def test_admin_claims_filter_all_params_preserved_in_pagination(self):
        dt_fixed = datetime(2026, 7, 2, 10, 0, 0, tzinfo=dt_timezone.utc)
        for i in range(3):
            c = Claim.objects.create(
                user=self.user,
                text=f"Renewable solar research report item {i} text.",
                status=ClaimStatus.COMPLETED,
            )
            Claim.objects.filter(id=c.id).update(submitted_at=dt_fixed - timedelta(seconds=i * 10))
            Analysis.objects.create(claim=c, verdict=Verdict.CREDIBLE, credibility_score=90.0)

        url = (
            "/api/v1/admin/claims?"
            f"page=1&page_size=2&"
            f"status=COMPLETED&verdict=CREDIBLE&"
            f"date_from=2026-07-01&date_to=2026-07-03&"
            f"search=Renewable&user_id={self.user.id}"
        )
        resp = self.client.get(url, **self.admin_headers)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["count"], 3)
        next_url = data["next"]
        self.assertIsNotNone(next_url)
        self.assertIn("page=2", next_url)
        self.assertIn("page_size=2", next_url)
        self.assertIn("status=COMPLETED", next_url)
        self.assertIn("verdict=CREDIBLE", next_url)
        self.assertIn("date_from=2026-07-01", next_url)
        self.assertIn("date_to=2026-07-03", next_url)
        self.assertIn("search=Renewable", next_url)
        self.assertIn(f"user_id={self.user.id}", next_url)
        # Ordering must NOT be present in admin pagination links
        self.assertNotIn("ordering", next_url)

    def test_admin_claims_filter_authorization(self):
        resp_user = self.client.get("/api/v1/admin/claims?status=COMPLETED", **self.headers)
        self.assertEqual(resp_user.status_code, 403)
        self.assertEqual(resp_user.json()["error_code"], "PERMISSION_DENIED")

        resp_unauth = self.client.get("/api/v1/admin/claims?status=COMPLETED")
        self.assertEqual(resp_unauth.status_code, 401)
        self.assertEqual(resp_unauth.json()["error_code"], "AUTHENTICATION_ERROR")

    def test_user_history_empty_and_whitespace_status_and_verdict_treated_as_absent(self):
        c2 = Claim.objects.create(
            user=self.user,
            text="Second claim text for whitespace filter testing.",
            status=ClaimStatus.COMPLETED,
        )
        Analysis.objects.create(claim=c2, verdict=Verdict.CREDIBLE, credibility_score=90.0)

        urls = [
            "/api/v1/claims/history?page=1&page_size=1&status=",
            "/api/v1/claims/history?page=1&page_size=1&status=%20%20%20",
            "/api/v1/claims/history?page=1&page_size=1&verdict=",
            "/api/v1/claims/history?page=1&page_size=1&verdict=%20%20%20",
            "/api/v1/claims/history?page=1&page_size=1&status=%20&verdict=%20%20",
        ]
        for url in urls:
            resp = self.client.get(url, **self.headers)
            self.assertEqual(resp.status_code, 200, f"Expected 200 for url: {url}")
            data = resp.json()
            self.assertEqual(data["count"], 2, f"Expected both claims returned for url: {url}")
            self.assertIsNotNone(data["next"], f"Expected next link for url: {url}")
            self.assertNotIn("status", data["next"], f"status should be omitted from next link for url: {url}")
            self.assertNotIn("verdict", data["next"], f"verdict should be omitted from next link for url: {url}")

    def test_admin_claims_empty_and_whitespace_status_and_verdict_treated_as_absent(self):
        c2 = Claim.objects.create(
            user=self.other_user,
            text="Other user claim text for whitespace filter testing.",
            status=ClaimStatus.COMPLETED,
        )
        Analysis.objects.create(claim=c2, verdict=Verdict.CREDIBLE, credibility_score=90.0)

        urls = [
            "/api/v1/admin/claims?page=1&page_size=1&status=",
            "/api/v1/admin/claims?page=1&page_size=1&status=%20%20%20",
            "/api/v1/admin/claims?page=1&page_size=1&verdict=",
            "/api/v1/admin/claims?page=1&page_size=1&verdict=%20%20%20",
            "/api/v1/admin/claims?page=1&page_size=1&status=%20&verdict=%20%20",
        ]
        for url in urls:
            resp = self.client.get(url, **self.admin_headers)
            self.assertEqual(resp.status_code, 200, f"Expected 200 for url: {url}")
            data = resp.json()
            self.assertGreaterEqual(data["count"], 2, f"Expected all claims returned for url: {url}")
            self.assertIsNotNone(data["next"], f"Expected next link for url: {url}")
            self.assertNotIn("status", data["next"], f"status should be omitted from next link for url: {url}")
            self.assertNotIn("verdict", data["next"], f"verdict should be omitted from next link for url: {url}")

    # API-016: Administrative Ordering Integration Tests
    def test_admin_claims_sorting_created_at_api(self):
        t_base = datetime(2026, 7, 1, 10, 0, 0, tzinfo=dt_timezone.utc)
        c1 = Claim.objects.create(user=self.user, text="Admin timestamp test alpha")
        c2 = Claim.objects.create(user=self.other_user, text="Admin timestamp test beta")
        Claim.objects.filter(id=c1.id).update(submitted_at=t_base)
        Claim.objects.filter(id=c2.id).update(submitted_at=t_base + timedelta(hours=2))

        # Descending (newest first)
        resp_desc = self.client.get("/api/v1/admin/claims?ordering=-created_at", **self.admin_headers)
        self.assertEqual(resp_desc.status_code, 200)
        results_desc = resp_desc.json()["results"]
        ids_desc = [r["claim_id"] for r in results_desc]
        self.assertLess(ids_desc.index(str(c2.id)), ids_desc.index(str(c1.id)))

        # Ascending (oldest first)
        resp_asc = self.client.get("/api/v1/admin/claims?ordering=created_at", **self.admin_headers)
        self.assertEqual(resp_asc.status_code, 200)
        results_asc = resp_asc.json()["results"]
        ids_asc = [r["claim_id"] for r in results_asc]
        self.assertLess(ids_asc.index(str(c1.id)), ids_asc.index(str(c2.id)))

    def test_admin_claims_sorting_credibility_score_nulls_last_api(self):
        t_base = datetime(2026, 7, 1, 10, 0, 0, tzinfo=dt_timezone.utc)
        c_low = Claim.objects.create(user=self.user, text="API explicit score test low 15.0", status=ClaimStatus.COMPLETED)
        Analysis.objects.create(claim=c_low, credibility_score=15.0, verdict=Verdict.MISINFORMATION)
        Claim.objects.filter(id=c_low.id).update(submitted_at=t_base)

        c_high = Claim.objects.create(user=self.other_user, text="API explicit score test high 85.0", status=ClaimStatus.COMPLETED)
        Analysis.objects.create(claim=c_high, credibility_score=85.0, verdict=Verdict.CREDIBLE)
        Claim.objects.filter(id=c_high.id).update(submitted_at=t_base + timedelta(minutes=1))

        c_null_score = Claim.objects.create(user=self.user, text="API explicit score test null score", status=ClaimStatus.PROCESSING)
        Analysis.objects.create(claim=c_null_score, credibility_score=None)
        Claim.objects.filter(id=c_null_score.id).update(submitted_at=t_base + timedelta(minutes=2))

        c_no_analysis = Claim.objects.create(user=self.other_user, text="API explicit score test no analysis", status=ClaimStatus.PENDING)
        Claim.objects.filter(id=c_no_analysis.id).update(submitted_at=t_base + timedelta(minutes=3))

        # Ascending: 15.0 -> 85.0 -> null scores last (ordered by secondary sort submitted_at asc)
        resp_asc = self.client.get("/api/v1/admin/claims?search=API explicit score test&ordering=credibility_score", **self.admin_headers)
        self.assertEqual(resp_asc.status_code, 200)
        items_asc = resp_asc.json()["results"]
        ids_asc = [r["claim_id"] for r in items_asc]
        self.assertEqual(ids_asc, [str(c_low.id), str(c_high.id), str(c_null_score.id), str(c_no_analysis.id)])

        # Descending: 85.0 -> 15.0 -> null scores last (ordered by secondary sort -submitted_at desc)
        resp_desc = self.client.get("/api/v1/admin/claims?search=API explicit score test&ordering=-credibility_score", **self.admin_headers)
        self.assertEqual(resp_desc.status_code, 200)
        items_desc = resp_desc.json()["results"]
        ids_desc = [r["claim_id"] for r in items_desc]
        self.assertEqual(ids_desc, [str(c_high.id), str(c_low.id), str(c_no_analysis.id), str(c_null_score.id)])

    def test_admin_claims_sorting_status_api(self):
        c_completed = Claim.objects.create(user=self.user, text="Admin completed claim status test", status=ClaimStatus.COMPLETED)
        c_pending = Claim.objects.create(user=self.other_user, text="Admin pending claim status test", status=ClaimStatus.PENDING)

        resp_asc = self.client.get("/api/v1/admin/claims?ordering=status", **self.admin_headers)
        self.assertEqual(resp_asc.status_code, 200)
        ids_asc = [r["claim_id"] for r in resp_asc.json()["results"]]
        self.assertLess(ids_asc.index(str(c_completed.id)), ids_asc.index(str(c_pending.id)))

        resp_desc = self.client.get("/api/v1/admin/claims?ordering=-status", **self.admin_headers)
        self.assertEqual(resp_desc.status_code, 200)
        ids_desc = [r["claim_id"] for r in resp_desc.json()["results"]]
        self.assertLess(ids_desc.index(str(c_pending.id)), ids_desc.index(str(c_completed.id)))

    def test_admin_claims_sorting_invalid_rejected_422(self):
        resp = self.client.get("/api/v1/admin/claims?ordering=disallowed_column", **self.admin_headers)
        self.assertEqual(resp.status_code, 422)
        data = resp.json()
        self.assertEqual(data["error_code"], "VALIDATION_ERROR")
        self.assertIn("Invalid ordering 'disallowed_column'", data["message"])

    def test_admin_claims_default_ordering_when_omitted(self):
        t_now = datetime.now(dt_timezone.utc)
        c_brand_new = Claim.objects.create(user=self.user, text="Admin default order brand new claim")
        Claim.objects.filter(id=c_brand_new.id).update(submitted_at=t_now + timedelta(hours=5))

        resp = self.client.get("/api/v1/admin/claims?page=1&page_size=1", **self.admin_headers)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["results"][0]["claim_id"], str(c_brand_new.id))
        self.assertIsNotNone(data["next"])
        self.assertNotIn("ordering", data["next"])

    def test_admin_claims_deterministic_pagination_tied_values(self):
        claims = []
        for i in range(4):
            c = Claim.objects.create(
                user=self.user,
                text=f"Admin tied pending item {i+1} unique pagination tag",
                status=ClaimStatus.PENDING,
            )
            claims.append(c)

        url_p1 = "/api/v1/admin/claims?search=unique pagination tag&page=1&page_size=2&ordering=status"
        resp_p1 = self.client.get(url_p1, **self.admin_headers)
        self.assertEqual(resp_p1.status_code, 200)
        ids_p1 = [r["claim_id"] for r in resp_p1.json()["results"]]
        self.assertEqual(len(ids_p1), 2)

        url_p2 = "/api/v1/admin/claims?search=unique pagination tag&page=2&page_size=2&ordering=status"
        resp_p2 = self.client.get(url_p2, **self.admin_headers)
        self.assertEqual(resp_p2.status_code, 200)
        ids_p2 = [r["claim_id"] for r in resp_p2.json()["results"]]
        self.assertEqual(len(ids_p2), 2)

        # 1. Page 1 and page 2 contain no duplicate IDs
        self.assertEqual(len(set(ids_p1).intersection(set(ids_p2))), 0)

        # 2. The union of IDs across both pages exactly equals the IDs of all four seeded claims
        expected_ids = {str(c.id) for c in claims}
        combined_ids = set(ids_p1).union(set(ids_p2))
        self.assertEqual(combined_ids, expected_ids)

        # 3. No seeded claim is omitted
        self.assertEqual(len(combined_ids), 4)
        for c in claims:
            self.assertIn(str(c.id), combined_ids)

    def test_admin_claims_pagination_preserves_ordering_search_and_all_filters(self):
        dt_fixed = datetime(2026, 7, 2, 12, 0, 0, tzinfo=dt_timezone.utc)
        created_claims = []
        for i in range(3):
            c = Claim.objects.create(
                user=self.user,
                text=f"Wind turbine energy efficiency study section {i+1} text",
                status=ClaimStatus.COMPLETED,
            )
            Claim.objects.filter(id=c.id).update(submitted_at=dt_fixed - timedelta(minutes=i * 10))
            Analysis.objects.create(claim=c, verdict=Verdict.CREDIBLE, credibility_score=90.0 - i * 5)
            created_claims.append(c)

        url = (
            "/api/v1/admin/claims?"
            f"page=1&page_size=2&"
            f"ordering=-credibility_score&"
            f"search=turbine&"
            f"status=COMPLETED&"
            f"verdict=CREDIBLE&"
            f"date_from=2026-07-01&"
            f"date_to=2026-07-03&"
            f"user_id={self.user.id}"
        )
        resp = self.client.get(url, **self.admin_headers)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["count"], 3)
        self.assertEqual(len(data["results"]), 2)

        next_url = data["next"]
        self.assertIsNotNone(next_url)
        self.assertIn("page=2", next_url)
        self.assertIn("page_size=2", next_url)
        self.assertIn("ordering=-credibility_score", next_url)
        self.assertIn("search=turbine", next_url)
        self.assertIn("status=COMPLETED", next_url)
        self.assertIn("verdict=CREDIBLE", next_url)
        self.assertIn("date_from=2026-07-01", next_url)
        self.assertIn("date_to=2026-07-03", next_url)
        self.assertIn(f"user_id={self.user.id}", next_url)

        # Follow page 2
        resp2 = self.client.get(next_url, **self.admin_headers)
        self.assertEqual(resp2.status_code, 200)
        data2 = resp2.json()
        self.assertEqual(len(data2["results"]), 1)

        prev_url = data2["previous"]
        self.assertIsNotNone(prev_url)
        self.assertIn("page=1", prev_url)
        self.assertIn("ordering=-credibility_score", prev_url)
        self.assertIn("search=turbine", prev_url)
        self.assertIn("status=COMPLETED", prev_url)
        self.assertIn("verdict=CREDIBLE", prev_url)
        self.assertIn("date_from=2026-07-01", prev_url)
        self.assertIn("date_to=2026-07-03", prev_url)
        self.assertIn(f"user_id={self.user.id}", prev_url)

    def test_admin_claims_ordering_authorization(self):
        resp_user = self.client.get("/api/v1/admin/claims?ordering=-created_at", **self.headers)
        self.assertEqual(resp_user.status_code, 403)
        self.assertEqual(resp_user.json()["error_code"], "PERMISSION_DENIED")

        resp_unauth = self.client.get("/api/v1/admin/claims?ordering=-created_at")
        self.assertEqual(resp_unauth.status_code, 401)
        self.assertEqual(resp_unauth.json()["error_code"], "AUTHENTICATION_ERROR")

    def test_admin_claims_ordering_soft_deleted_excluded(self):
        c_deleted = Claim.objects.create(
            user=self.user,
            text="Soft-deleted claim text for admin ordering check",
            status=ClaimStatus.COMPLETED,
            is_deleted=True,
        )
        Analysis.objects.create(claim=c_deleted, credibility_score=99.0, verdict=Verdict.CREDIBLE)

        resp = self.client.get("/api/v1/admin/claims?ordering=-credibility_score", **self.admin_headers)
        self.assertEqual(resp.status_code, 200)
        returned_ids = {r["claim_id"] for r in resp.json()["results"]}
        self.assertNotIn(str(c_deleted.id), returned_ids)

    # API-017: Permission Integration Tests
    def test_get_claim_app_admin_success(self):
        resp = self.client.get(f"/api/v1/claims/{self.claim.id}", **self.app_admin_headers)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["data"]["id"], str(self.claim.id))

    def test_protected_endpoints_invalid_token_rejected(self):
        bad_headers = {"HTTP_AUTHORIZATION": "Bearer invalid.jwt.token"}
        resp_history = self.client.get("/api/v1/claims/history", **bad_headers)
        self.assertEqual(resp_history.status_code, 401)
        self.assertEqual(resp_history.json()["error_code"], "AUTHENTICATION_ERROR")

        resp_detail = self.client.get(f"/api/v1/claims/{self.claim.id}", **bad_headers)
        self.assertEqual(resp_detail.status_code, 401)
        self.assertEqual(resp_detail.json()["error_code"], "AUTHENTICATION_ERROR")

    def test_app_admin_can_update_own_pending_claim(self):
        admin_claim = Claim.objects.create(
            user=self.app_admin,
            text="App admin original pending claim text that is long enough.",
            status=ClaimStatus.PENDING,
        )
        payload = json.dumps({"claim_text": "App admin updated pending claim text."})
        resp = self.client.patch(f"/api/v1/claims/{admin_claim.id}", data=payload, content_type="application/json", **self.app_admin_headers)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["success"])
        admin_claim.refresh_from_db()
        self.assertEqual(admin_claim.text, "App admin updated pending claim text.")

    def test_app_admin_can_list_admin_claims(self):
        resp = self.client.get("/api/v1/admin/claims", **self.app_admin_headers)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("results", data)
        self.assertIn("count", data)

    def test_submit_claim_endpoint_creates_audit_log(self):
        payload = json.dumps({"claim_text": "Valid submission text for testing audit logging via API."})
        resp = self.client.post("/api/v1/claims", data=payload, content_type="application/json", **self.headers)
        self.assertEqual(resp.status_code, 201)
        data = resp.json()
        claim_id = data["data"]["id"]

        log = AuditLog.objects.get(target=claim_id, action="CLAIM_SUBMITTED")
        self.assertEqual(log.user, self.user)
        self.assertEqual(log.metadata["claim_id"], claim_id)
        self.assertEqual(log.metadata["status"], ClaimStatus.PENDING)

    def test_patch_claim_endpoint_creates_audit_log(self):
        payload = json.dumps({"claim_text": "Valid updated claim text via endpoint."})
        resp = self.client.patch(f"/api/v1/claims/{self.claim.id}", data=payload, content_type="application/json", **self.headers)
        self.assertEqual(resp.status_code, 200)

        log = AuditLog.objects.get(target=str(self.claim.id), action="CLAIM_UPDATED")
        self.assertEqual(log.user, self.user)
        self.assertEqual(log.metadata["claim_id"], str(self.claim.id))
        self.assertEqual(log.metadata["status"], ClaimStatus.PENDING)

    def test_delete_claim_endpoint_creates_audit_log(self):
        claim_to_delete = Claim.objects.create(
            user=self.user,
            text="Claim created for testing delete endpoint audit.",
            status=ClaimStatus.PENDING,
            is_deleted=False,
        )
        resp = self.client.delete(f"/api/v1/claims/{claim_to_delete.id}", **self.headers)
        self.assertEqual(resp.status_code, 204)

        log = AuditLog.objects.get(target=str(claim_to_delete.id), action="CLAIM_DELETED")
        self.assertEqual(log.user, self.user)
        self.assertEqual(log.metadata["claim_id"], str(claim_to_delete.id))
        self.assertEqual(log.metadata["status"], ClaimStatus.PENDING)
        self.assertEqual(log.metadata["deleted_by_role"], "USER")
        self.assertFalse(log.metadata["is_admin_action"])
        self.assertTrue(log.metadata["soft_deleted"])

    def test_api_unauthenticated_requests_do_not_create_audit_logs(self):
        initial_count = AuditLog.objects.count()

        # POST unauthenticated -> 401
        resp_post = self.client.post("/api/v1/claims", data=json.dumps({"claim_text": "Valid text that is long enough."}), content_type="application/json")
        self.assertEqual(resp_post.status_code, 401)

        # PATCH unauthenticated -> 401
        resp_patch = self.client.patch(f"/api/v1/claims/{self.claim.id}", data=json.dumps({"claim_text": "Valid text that is long enough."}), content_type="application/json")
        self.assertEqual(resp_patch.status_code, 401)

        # DELETE unauthenticated -> 401
        resp_delete = self.client.delete(f"/api/v1/claims/{self.claim.id}")
        self.assertEqual(resp_delete.status_code, 401)

        self.assertEqual(AuditLog.objects.count(), initial_count)

    def test_api_forbidden_requests_do_not_create_audit_logs(self):
        initial_count = AuditLog.objects.count()

        # PATCH by non-owner -> 403
        resp_patch = self.client.patch(f"/api/v1/claims/{self.claim.id}", data=json.dumps({"claim_text": "Non-owner attempt text."}), content_type="application/json", **self.other_headers)
        self.assertEqual(resp_patch.status_code, 403)

        # DELETE by non-owner non-admin -> 403
        resp_delete = self.client.delete(f"/api/v1/claims/{self.claim.id}", **self.other_headers)
        self.assertEqual(resp_delete.status_code, 403)

        self.assertEqual(AuditLog.objects.count(), initial_count)

    def test_api_not_found_requests_do_not_create_audit_logs(self):
        import uuid
        initial_count = AuditLog.objects.count()
        random_id = uuid.uuid4()

        # PATCH non-existent -> 404
        resp_patch_missing = self.client.patch(f"/api/v1/claims/{random_id}", data=json.dumps({"claim_text": "Non-existent claim update text."}), content_type="application/json", **self.headers)
        self.assertEqual(resp_patch_missing.status_code, 404)

        # DELETE non-existent -> 404
        resp_delete_missing = self.client.delete(f"/api/v1/claims/{random_id}", **self.headers)
        self.assertEqual(resp_delete_missing.status_code, 404)

        # Soft-deleted claim
        soft_deleted_claim = Claim.objects.create(user=self.user, text="Already soft-deleted claim text.", is_deleted=True)
        resp_patch_deleted = self.client.patch(f"/api/v1/claims/{soft_deleted_claim.id}", data=json.dumps({"claim_text": "Soft-deleted claim update text."}), content_type="application/json", **self.headers)
        self.assertEqual(resp_patch_deleted.status_code, 404)

        resp_delete_deleted = self.client.delete(f"/api/v1/claims/{soft_deleted_claim.id}", **self.headers)
        self.assertEqual(resp_delete_deleted.status_code, 404)

        self.assertEqual(AuditLog.objects.count(), initial_count)

    def test_api_conflict_requests_do_not_create_audit_logs(self):
        initial_count = AuditLog.objects.count()

        analyzed_claim = Claim.objects.create(
            user=self.user,
            text="Analyzed claim text for testing conflict.",
            status=ClaimStatus.PROCESSING,
            is_deleted=False,
        )

        # PATCH analyzed -> 409
        resp_patch = self.client.patch(f"/api/v1/claims/{analyzed_claim.id}", data=json.dumps({"claim_text": "Attempt to update analyzed claim."}), content_type="application/json", **self.headers)
        self.assertEqual(resp_patch.status_code, 409)

        # DELETE analyzed by owner -> 409
        resp_delete = self.client.delete(f"/api/v1/claims/{analyzed_claim.id}", **self.headers)
        self.assertEqual(resp_delete.status_code, 409)

        self.assertEqual(AuditLog.objects.count(), initial_count)

    def test_api_validation_error_requests_do_not_create_audit_logs(self):
        initial_count = AuditLog.objects.count()

        # POST invalid (too short) -> 422
        resp_post = self.client.post("/api/v1/claims", data=json.dumps({"claim_text": "Short"}), content_type="application/json", **self.headers)
        self.assertEqual(resp_post.status_code, 422)

        # PATCH invalid (empty/whitespace) -> 422
        resp_patch = self.client.patch(f"/api/v1/claims/{self.claim.id}", data=json.dumps({"claim_text": "   "}), content_type="application/json", **self.headers)
        self.assertEqual(resp_patch.status_code, 422)

        self.assertEqual(AuditLog.objects.count(), initial_count)

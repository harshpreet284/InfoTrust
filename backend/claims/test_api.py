import json
from django.test import TestCase, Client

from authentication.models import User
from claims.models import Claim, ClaimStatus
from analysis.models import Analysis

class ClaimApiTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(email="test@example.com", password="password123", full_name="Test User")
        self.other_user = User.objects.create_user(email="other@example.com", password="password123", full_name="Other User")
        self.admin = User.objects.create_superuser(email="admin@example.com", password="password123", full_name="Admin")
        
        # Obtain a valid JWT token via the existing API
        resp = self.client.post("/api/v1/auth/login", data=json.dumps({"email": "test@example.com", "password": "password123"}), content_type="application/json")
        self.token = resp.json()["data"]["access_token"]
        self.headers = {"HTTP_AUTHORIZATION": f"Bearer {self.token}"}
        
        resp2 = self.client.post("/api/v1/auth/login", data=json.dumps({"email": "other@example.com", "password": "password123"}), content_type="application/json")
        self.other_headers = {"HTTP_AUTHORIZATION": f"Bearer {resp2.json()['data']['access_token']}"}
        
        resp3 = self.client.post("/api/v1/auth/login", data=json.dumps({"email": "admin@example.com", "password": "password123"}), content_type="application/json")
        self.admin_headers = {"HTTP_AUTHORIZATION": f"Bearer {resp3.json()['data']['access_token']}"}
        
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


import json
from django.test import TestCase, Client

from authentication.models import User
from claims.models import Claim

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

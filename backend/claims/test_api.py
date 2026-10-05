import json
from django.test import TestCase, Client

from authentication.models import User
from claims.models import Claim

class ClaimApiTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(email="test@example.com", password="password123", full_name="Test User")
        
        # Obtain a valid JWT token via the existing API
        resp = self.client.post("/api/v1/auth/login", data=json.dumps({"email": "test@example.com", "password": "password123"}), content_type="application/json")
        self.token = resp.json()["data"]["access_token"]
        self.headers = {"HTTP_AUTHORIZATION": f"Bearer {self.token}"}
        
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

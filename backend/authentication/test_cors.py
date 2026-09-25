from django.test import Client, TestCase


class CORSTests(TestCase):
    def setUp(self):
        self.client = Client()

    def test_cors_allowed_origin(self):
        """Test that requests from the allowed frontend origin receive CORS headers."""
        # We can use any endpoint. Let's try the JWT token obtain endpoint if it exists,
        # or just a non-existent path. CORS middleware adds headers even on 404s.
        response = self.client.options(
            "/auth/token/",
            HTTP_ORIGIN="http://localhost:5173",
            HTTP_ACCESS_CONTROL_REQUEST_METHOD="POST",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.headers.get("Access-Control-Allow-Origin"), "http://localhost:5173"
        )
        self.assertEqual(
            response.headers.get("Access-Control-Allow-Credentials"), "true"
        )

    def test_cors_disallowed_origin(self):
        """Test that unauthorized origins do not receive CORS headers."""
        response = self.client.options(
            "/auth/token/",
            HTTP_ORIGIN="http://evil.com",
            HTTP_ACCESS_CONTROL_REQUEST_METHOD="POST",
        )
        # Assuming the CORS package doesn't block the request entirely (it usually just doesn't add the headers)
        self.assertNotIn("Access-Control-Allow-Origin", response.headers)

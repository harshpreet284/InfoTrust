"""
Unit tests for FactCheckService (AI-005).
All tests execute deterministically with 100% mocked HTTP responses and zero live network access.
"""

import io
import json
import socket
import urllib.error
import urllib.request
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from analysis.services.fact_check import (
    FactCheckAPIError,
    FactCheckAuthError,
    FactCheckConfigError,
    FactCheckConnectionError,
    FactCheckEvidenceItem,
    FactCheckInputError,
    FactCheckRateLimitError,
    FactCheckResult,
    FactCheckService,
    FactCheckTimeoutError,
    _is_valid_evidence_url,
    _normalize_url,
)
from config.settings.base import _get_positive_float_env


class MockHTTPResponse:
    """Mock context manager for urllib.request.urlopen responses."""

    def __init__(self, body_bytes: bytes, status: int = 200):
        self.body_bytes = body_bytes
        self.status = status

    def read(self) -> bytes:
        return self.body_bytes

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass


class FactCheckServiceSuccessTests(SimpleTestCase):
    """Verifies successful evidence parsing, normalization, and summary generation."""

    def test_query_single_match_success(self):
        payload = {
            "claims": [
                {
                    "text": "The earth is flat.",
                    "claimant": "Flat Earth Society",
                    "claimDate": "2024-01-01T00:00:00Z",
                    "claimReview": [
                        {
                            "publisher": {
                                "name": "PolitiFact",
                                "site": "politifact.com",
                            },
                            "url": "https://www.politifact.com/factchecks/2024/jan/01/flat-earth/",
                            "title": "Earth is not flat",
                            "reviewDate": "2024-01-02T00:00:00Z",
                            "textualRating": "False",
                            "languageCode": "en",
                        }
                    ],
                }
            ]
        }
        mock_client = MagicMock(
            return_value=MockHTTPResponse(json.dumps(payload).encode("utf-8"))
        )

        service = FactCheckService(api_key="test-api-key", http_client=mock_client)
        result = service.query("The earth is flat.")

        self.assertIsInstance(result, FactCheckResult)
        self.assertEqual(result.matches, 1)
        self.assertEqual(len(result.sources), 1)
        self.assertEqual(len(result.evidence_urls), 1)
        self.assertEqual(
            result.evidence_urls[0],
            "https://www.politifact.com/factchecks/2024/jan/01/flat-earth/",
        )

        item = result.sources[0]
        self.assertIsInstance(item, FactCheckEvidenceItem)
        self.assertEqual(item.publisher, "PolitiFact")
        self.assertEqual(item.rating, "False")
        self.assertEqual(
            item.url,
            "https://www.politifact.com/factchecks/2024/jan/01/flat-earth/",
        )
        self.assertEqual(item.claim_text, "The earth is flat.")
        self.assertEqual(item.review_date, "2024-01-02T00:00:00Z")

        # Verify deterministic external attribution summary
        self.assertEqual(
            result.summary,
            "External fact-check review by PolitiFact reported rating: 'False'.",
        )

        # Verify serialization contract
        res_dict = result.to_dict()
        self.assertEqual(res_dict["matches"], 1)
        self.assertEqual(len(res_dict["sources"]), 1)
        self.assertEqual(res_dict["sources"][0]["publisher"], "PolitiFact")
        self.assertEqual(
            res_dict["evidence_urls"],
            ["https://www.politifact.com/factchecks/2024/jan/01/flat-earth/"],
        )

    def test_query_multiple_matches_multiple_claims(self):
        payload = {
            "claims": [
                {
                    "text": "Claim 1",
                    "claimReview": [
                        {
                            "publisher": {"name": "Source A"},
                            "url": "https://source-a.com/article1",
                            "textualRating": "False",
                        }
                    ],
                },
                {
                    "text": "Claim 2",
                    "claimReview": [
                        {
                            "publisher": {"name": "Source B"},
                            "url": "https://source-b.com/article2",
                            "textualRating": "Misleading",
                        }
                    ],
                },
            ]
        }
        mock_client = MagicMock(
            return_value=MockHTTPResponse(json.dumps(payload).encode("utf-8"))
        )

        service = FactCheckService(api_key="test-api-key", http_client=mock_client)
        result = service.query("Query claim")

        self.assertEqual(result.matches, 2)
        self.assertEqual(len(result.sources), 2)
        self.assertEqual(len(result.evidence_urls), 2)
        self.assertEqual(
            result.evidence_urls,
            (
                "https://source-a.com/article1",
                "https://source-b.com/article2",
            ),
        )
        self.assertIn("Source A reported 'False'", result.summary)
        self.assertIn("Source B reported 'Misleading'", result.summary)
        self.assertTrue(
            result.summary.startswith("External fact-check reviews (2 found):")
        )

    def test_query_duplicate_url_deduplication(self):
        payload = {
            "claims": [
                {
                    "text": "Claim 1",
                    "claimReview": [
                        {
                            "publisher": {"name": "Source A"},
                            "url": "https://source.com/factcheck/",
                            "textualRating": "False",
                        },
                        {
                            "publisher": {"name": "Source A Dup"},
                            "url": "https://source.com/factcheck",  # Normalized matches above
                            "textualRating": "False",
                        },
                    ],
                }
            ]
        }
        mock_client = MagicMock(
            return_value=MockHTTPResponse(json.dumps(payload).encode("utf-8"))
        )

        service = FactCheckService(api_key="test-api-key", http_client=mock_client)
        result = service.query("Duplicate claim")

        self.assertEqual(result.matches, 1)
        self.assertEqual(len(result.sources), 1)
        self.assertEqual(len(result.evidence_urls), 1)
        self.assertEqual(result.sources[0].publisher, "Source A")

    def test_query_distinct_reviews_same_publisher(self):
        payload = {
            "claims": [
                {
                    "text": "Claim",
                    "claimReview": [
                        {
                            "publisher": {"name": "FactCheckOrg"},
                            "url": "https://factcheck.org/2023/article1",
                            "textualRating": "False",
                        },
                        {
                            "publisher": {"name": "FactCheckOrg"},
                            "url": "https://factcheck.org/2024/article2",
                            "textualRating": "Mostly False",
                        },
                    ],
                }
            ]
        }
        mock_client = MagicMock(
            return_value=MockHTTPResponse(json.dumps(payload).encode("utf-8"))
        )

        service = FactCheckService(api_key="test-api-key", http_client=mock_client)
        result = service.query("Same publisher distinct articles")

        self.assertEqual(result.matches, 2)
        self.assertEqual(len(result.sources), 2)
        self.assertEqual(len(result.evidence_urls), 2)
        self.assertEqual(result.sources[0].rating, "False")
        self.assertEqual(result.sources[1].rating, "Mostly False")

    def test_query_skips_reviews_without_valid_url(self):
        payload = {
            "claims": [
                {
                    "text": "Claim with missing and invalid URLs",
                    "claimReview": [
                        {
                            "publisher": {"name": "NoURLPub"},
                            "url": "",  # Empty URL
                            "textualRating": "False",
                        },
                        {
                            "publisher": {"name": "NoneURLPub"},
                            "url": None,  # None URL
                            "textualRating": "False",
                        },
                        {
                            "publisher": {"name": "FTPPub"},
                            "url": "ftp://files.org/factcheck",  # Non-HTTP URL
                            "textualRating": "False",
                        },
                        {
                            "publisher": {"name": "ValidPub"},
                            "url": "https://valid.org/factcheck",
                            "textualRating": "Verified",
                        },
                    ],
                }
            ]
        }
        mock_client = MagicMock(
            return_value=MockHTTPResponse(json.dumps(payload).encode("utf-8"))
        )

        service = FactCheckService(api_key="test-api-key", http_client=mock_client)
        result = service.query("Test URL filtering")

        # Only the valid HTTP/HTTPS URL should be preserved
        self.assertEqual(result.matches, 1)
        self.assertEqual(len(result.sources), 1)
        self.assertEqual(result.sources[0].publisher, "ValidPub")
        self.assertEqual(result.evidence_urls, ("https://valid.org/factcheck",))


class FactCheckServiceNoMatchTests(SimpleTestCase):
    """Verifies no-match behavior (HTTP 200 with zero evidence)."""

    def test_query_zero_matches_empty_dict(self):
        # Google standard 0-match response is HTTP 200 with {}
        mock_client = MagicMock(return_value=MockHTTPResponse(b"{}"))

        service = FactCheckService(api_key="test-api-key", http_client=mock_client)
        result = service.query("Completely unreviewed claim")

        self.assertEqual(result.matches, 0)
        self.assertEqual(result.sources, ())
        self.assertEqual(result.evidence_urls, ())
        self.assertEqual(
            result.summary, "No external fact-check reviews found for this claim."
        )

    def test_query_zero_matches_empty_claims_list(self):
        mock_client = MagicMock(return_value=MockHTTPResponse(b'{"claims": []}'))

        service = FactCheckService(api_key="test-api-key", http_client=mock_client)
        result = service.query("Completely unreviewed claim")

        self.assertEqual(result.matches, 0)
        self.assertEqual(result.sources, ())
        self.assertEqual(result.evidence_urls, ())
        self.assertEqual(
            result.summary, "No external fact-check reviews found for this claim."
        )

    def test_query_zero_matches_when_all_reviews_skipped(self):
        payload = {
            "claims": [
                {
                    "text": "Claim",
                    "claimReview": [
                        {"publisher": {"name": "P1"}, "url": ""},  # No valid URL
                        {"publisher": {"name": "P2"}, "url": "not-a-url"},
                    ],
                }
            ]
        }
        mock_client = MagicMock(
            return_value=MockHTTPResponse(json.dumps(payload).encode("utf-8"))
        )

        service = FactCheckService(api_key="test-api-key", http_client=mock_client)
        result = service.query("Claim with only unusable reviews")

        self.assertEqual(result.matches, 0)
        self.assertEqual(result.sources, ())
        self.assertEqual(result.evidence_urls, ())


class FactCheckServiceMalformedPayloadTests(SimpleTestCase):
    """Verifies handling of wholly malformed and partially malformed responses."""

    def test_query_wholly_malformed_non_json(self):
        mock_client = MagicMock(
            return_value=MockHTTPResponse(b"<html>502 Bad Gateway</html>")
        )

        service = FactCheckService(api_key="test-api-key", http_client=mock_client)
        with self.assertRaises(FactCheckAPIError) as ctx:
            service.query("Query")

        self.assertIn("malformed non-JSON payload", str(ctx.exception))

    def test_query_wholly_malformed_non_dict_root(self):
        mock_client = MagicMock(return_value=MockHTTPResponse(b'["a", "list"]'))

        service = FactCheckService(api_key="test-api-key", http_client=mock_client)
        with self.assertRaises(FactCheckAPIError) as ctx:
            service.query("Query")

        self.assertIn("unexpected JSON root type", str(ctx.exception))

    def test_query_wholly_malformed_claims_not_list(self):
        mock_client = MagicMock(
            return_value=MockHTTPResponse(b'{"claims": "invalid-claims"}')
        )

        service = FactCheckService(api_key="test-api-key", http_client=mock_client)
        with self.assertRaises(FactCheckAPIError) as ctx:
            service.query("Query")

        self.assertIn("invalid 'claims' structure", str(ctx.exception))

    def test_query_provider_error_payload(self):
        payload = {
            "error": {
                "code": 403,
                "message": "API key not valid.",
                "status": "PERMISSION_DENIED",
            }
        }
        mock_client = MagicMock(
            return_value=MockHTTPResponse(json.dumps(payload).encode("utf-8"))
        )

        service = FactCheckService(api_key="test-api-key", http_client=mock_client)
        with self.assertRaises(FactCheckAPIError) as ctx:
            service.query("Query")

        self.assertEqual(ctx.exception.status_code, 403)
        self.assertIn("code 403", str(ctx.exception))


class FactCheckServiceInputAndConfigValidationTests(SimpleTestCase):
    """Verifies strict validation of input queries, timeout, and API keys."""

    def test_query_input_validation_empty_or_whitespace(self):
        service = FactCheckService(api_key="test-key")

        with self.assertRaises(FactCheckInputError):
            service.query("")

        with self.assertRaises(FactCheckInputError):
            service.query("   \t\n  ")

    def test_query_input_validation_non_string(self):
        service = FactCheckService(api_key="test-key")

        for invalid_input in [None, 123, ["claim"], {"claim": "text"}]:
            with self.subTest(invalid_input=invalid_input):
                with self.assertRaises(TypeError):
                    service.query(invalid_input)

    def test_timeout_validation_invalid_values(self):
        for invalid_timeout in [
            0,
            -1,
            -5.5,
            float("inf"),
            float("-inf"),
            float("nan"),
            True,
            False,
            "5.0",
        ]:
            with self.subTest(invalid_timeout=invalid_timeout):
                with self.assertRaises(FactCheckConfigError):
                    FactCheckService(api_key="test-key", timeout=invalid_timeout)

    def test_timeout_validation_valid_values(self):
        service1 = FactCheckService(api_key="test-key", timeout=10)
        self.assertEqual(service1.timeout, 10.0)

        service2 = FactCheckService(api_key="test-key", timeout=2.5)
        self.assertEqual(service2.timeout, 2.5)

    def test_max_results_validation(self):
        for invalid_max in [0, -1, True, False, 2.5, "10"]:
            with self.subTest(invalid_max=invalid_max):
                with self.assertRaises(FactCheckConfigError):
                    FactCheckService(api_key="test-key", max_results=invalid_max)

    def test_api_key_validation_missing_or_empty(self):
        with patch("analysis.services.fact_check.settings") as mock_settings:
            mock_settings.FACT_CHECK_API_KEY = ""
            mock_settings.FACT_CHECK_TIMEOUT_SECONDS = 5.0

            with patch.dict("os.environ", {"FACT_CHECK_API_KEY": ""}):
                service = FactCheckService()
                with self.assertRaises(FactCheckConfigError) as ctx:
                    service.query("Query claim")
                self.assertIn(
                    "FACT_CHECK_API_KEY is not configured", str(ctx.exception)
                )

    def test_settings_timeout_safe_fallback_helper(self):
        # Tests the _get_positive_float_env function used in config/settings/base.py
        with patch.dict("os.environ", {"TEST_VAR": "invalid"}):
            self.assertEqual(_get_positive_float_env("TEST_VAR", 5.0), 5.0)

        with patch.dict("os.environ", {"TEST_VAR": "-10.0"}):
            self.assertEqual(_get_positive_float_env("TEST_VAR", 5.0), 5.0)

        with patch.dict("os.environ", {"TEST_VAR": "0"}):
            self.assertEqual(_get_positive_float_env("TEST_VAR", 5.0), 5.0)

        with patch.dict("os.environ", {"TEST_VAR": "nan"}):
            self.assertEqual(_get_positive_float_env("TEST_VAR", 5.0), 5.0)

        with patch.dict("os.environ", {"TEST_VAR": "inf"}):
            self.assertEqual(_get_positive_float_env("TEST_VAR", 5.0), 5.0)

        with patch.dict("os.environ", {"TEST_VAR": "8.5"}):
            self.assertEqual(_get_positive_float_env("TEST_VAR", 5.0), 8.5)


class FactCheckServiceErrorHandlingAndSecurityTests(SimpleTestCase):
    """Verifies error classification, exception sanitization, and secret redaction."""

    def test_auth_error_401_and_403(self):
        for code in [401, 403]:
            with self.subTest(code=code):
                mock_client = MagicMock(
                    side_effect=urllib.error.HTTPError(
                        url="https://factchecktools.googleapis.com",
                        code=code,
                        msg="Forbidden",
                        hdrs={},
                        fp=io.BytesIO(b"{}"),
                    )
                )
                service = FactCheckService(
                    api_key="SUPER_SECRET_KEY_123", http_client=mock_client
                )

                with self.assertRaises(FactCheckAuthError) as ctx:
                    service.query("Claim")

                self.assertEqual(ctx.exception.status_code, code)
                self.assertIn(f"HTTP {code}", str(ctx.exception))
                self.assertNotIn("SUPER_SECRET_KEY_123", str(ctx.exception))
                self.assertNotIn("SUPER_SECRET_KEY_123", repr(ctx.exception))

    def test_rate_limited_429(self):
        mock_client = MagicMock(
            side_effect=urllib.error.HTTPError(
                url="https://factchecktools.googleapis.com",
                code=429,
                msg="Too Many Requests",
                hdrs={},
                fp=io.BytesIO(b"{}"),
            )
        )
        service = FactCheckService(api_key="test-key", http_client=mock_client)

        with self.assertRaises(FactCheckRateLimitError) as ctx:
            service.query("Claim")

        self.assertEqual(ctx.exception.status_code, 429)
        self.assertIn("rate limit exceeded", str(ctx.exception))

    def test_server_error_500_503(self):
        for code in [500, 502, 503, 504]:
            with self.subTest(code=code):
                mock_client = MagicMock(
                    side_effect=urllib.error.HTTPError(
                        url="https://factchecktools.googleapis.com",
                        code=code,
                        msg="Server Error",
                        hdrs={},
                        fp=io.BytesIO(b"{}"),
                    )
                )
                service = FactCheckService(api_key="test-key", http_client=mock_client)

                with self.assertRaises(FactCheckAPIError) as ctx:
                    service.query("Claim")

                self.assertEqual(ctx.exception.status_code, code)
                self.assertIn(f"HTTP {code}", str(ctx.exception))

    def test_timeout_error_handling(self):
        # Case 1: Direct TimeoutError
        mock_client1 = MagicMock(side_effect=TimeoutError("Connection timed out"))
        service1 = FactCheckService(api_key="test-key", http_client=mock_client1)

        with self.assertRaises(FactCheckTimeoutError) as ctx1:
            service1.query("Claim")
        self.assertEqual(str(ctx1.exception), "Fact-check provider request timed out.")

        # Case 2: URLError wrapping TimeoutError
        mock_client2 = MagicMock(
            side_effect=urllib.error.URLError(reason=socket.timeout("Socket timed out"))
        )
        service2 = FactCheckService(api_key="test-key", http_client=mock_client2)

        with self.assertRaises(FactCheckTimeoutError) as ctx2:
            service2.query("Claim")
        self.assertEqual(str(ctx2.exception), "Fact-check provider request timed out.")

    def test_network_connection_error_sanitized(self):
        # URLError wrapping gaierror (DNS resolution failure)
        raw_reason = socket.gaierror(11001, "getaddrinfo failed sensitive_host_info")
        mock_client = MagicMock(side_effect=urllib.error.URLError(reason=raw_reason))
        service = FactCheckService(api_key="SECRET_TOKEN_XYZ", http_client=mock_client)

        with self.assertRaises(FactCheckConnectionError) as ctx:
            service.query("Claim")

        # Stable, sanitized error message without raw reason interpolation
        self.assertEqual(
            str(ctx.exception),
            "Failed to establish network connection to fact-check provider.",
        )
        self.assertNotIn("sensitive_host_info", str(ctx.exception))
        self.assertNotIn("SECRET_TOKEN_XYZ", str(ctx.exception))

    def test_header_authentication_used(self):
        mock_client = MagicMock(return_value=MockHTTPResponse(b"{}"))
        service = FactCheckService(
            api_key="SECRET_API_KEY_456", http_client=mock_client
        )
        service.query("Test header claim")

        self.assertEqual(mock_client.call_count, 1)
        req_obj = mock_client.call_args[0][0]
        self.assertIsInstance(req_obj, urllib.request.Request)

        # Header contains the key
        self.assertEqual(req_obj.get_header("X-goog-api-key"), "SECRET_API_KEY_456")
        self.assertEqual(req_obj.get_header("User-agent"), "InfoTrust-FactCheck/1.0")

        # URL strictly does NOT contain key
        self.assertNotIn("key=", req_obj.full_url)
        self.assertNotIn("SECRET_API_KEY_456", req_obj.full_url)


class FactCheckHelpersTests(SimpleTestCase):
    """Verifies URL validation and normalization helper behaviors."""

    def test_is_valid_evidence_url(self):
        self.assertTrue(_is_valid_evidence_url("http://example.com/check"))
        self.assertTrue(_is_valid_evidence_url("https://example.com/check"))
        self.assertTrue(_is_valid_evidence_url("  https://example.com/check  "))

        self.assertFalse(_is_valid_evidence_url(""))
        self.assertFalse(_is_valid_evidence_url("   "))
        self.assertFalse(_is_valid_evidence_url(None))
        self.assertFalse(_is_valid_evidence_url("ftp://example.com/check"))
        self.assertFalse(_is_valid_evidence_url("file:///path/to/check"))
        self.assertFalse(_is_valid_evidence_url(12345))

    def test_normalize_url(self):
        url1 = "https://EXAMPLE.COM/factchecks/article/"
        url2 = "https://example.com/factchecks/article"
        self.assertEqual(_normalize_url(url1), _normalize_url(url2))

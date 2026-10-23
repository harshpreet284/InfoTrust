import json
import math
from unittest.mock import MagicMock, patch

from django.core.cache import cache
from django.test import RequestFactory, TestCase, override_settings
from ninja import NinjaAPI
from ninja.errors import Throttled
from ninja.testing import TestClient

from shared.exception_handlers import setup_exception_handlers
from shared.throttling import (
    AnalysisStatusRateThrottle,
    BaseInfoTrustThrottle,
    ClaimSubmitRateThrottle,
    LoginRateThrottle,
    RegisterRateThrottle,
    get_client_ip,
    is_trusted_proxy,
)


class TestProxyAndIPResolution(TestCase):
    def setUp(self):
        self.rf = RequestFactory()

    def test_is_trusted_proxy_single_ip(self):
        self.assertTrue(is_trusted_proxy("10.0.0.1", ["10.0.0.1"]))
        self.assertFalse(is_trusted_proxy("10.0.0.2", ["10.0.0.1"]))
        self.assertFalse(is_trusted_proxy("invalid_ip", ["10.0.0.1"]))
        self.assertFalse(is_trusted_proxy("10.0.0.1", []))

    def test_is_trusted_proxy_cidr_network(self):
        self.assertTrue(is_trusted_proxy("172.18.0.5", ["172.16.0.0/12"]))
        self.assertFalse(is_trusted_proxy("192.168.1.5", ["172.16.0.0/12"]))

    @override_settings(NINJA_NUM_PROXIES=0, TRUSTED_PROXIES=[])
    def test_default_untrusted_ignores_forwarded_headers(self):
        req = self.rf.get(
            "/",
            REMOTE_ADDR="198.51.100.10",
            HTTP_X_FORWARDED_FOR="1.1.1.1, 2.2.2.2",
            HTTP_X_REAL_IP="3.3.3.3",
        )
        self.assertEqual(get_client_ip(req), "198.51.100.10")

    @override_settings(NINJA_NUM_PROXIES=1, TRUSTED_PROXIES=["10.0.0.1"])
    def test_untrusted_direct_peer_ignores_forwarded_headers(self):
        # Peer is 198.51.100.5 (not in TRUSTED_PROXIES), so X-Forwarded-For must be ignored
        req = self.rf.get(
            "/",
            REMOTE_ADDR="198.51.100.5",
            HTTP_X_FORWARDED_FOR="1.1.1.1",
        )
        self.assertEqual(get_client_ip(req), "198.51.100.5")

    @override_settings(NINJA_NUM_PROXIES=1, TRUSTED_PROXIES=["10.0.0.1"])
    def test_trusted_peer_resolves_valid_ipv4(self):
        req = self.rf.get(
            "/",
            REMOTE_ADDR="10.0.0.1",
            HTTP_X_FORWARDED_FOR="203.0.113.195",
        )
        self.assertEqual(get_client_ip(req), "203.0.113.195")

    @override_settings(NINJA_NUM_PROXIES=1, TRUSTED_PROXIES=["10.0.0.1"])
    def test_trusted_peer_resolves_valid_ipv6(self):
        req = self.rf.get(
            "/",
            REMOTE_ADDR="10.0.0.1",
            HTTP_X_FORWARDED_FOR="2001:db8::8a2e:370:7334",
        )
        self.assertEqual(get_client_ip(req), "2001:db8::8a2e:370:7334")

    @override_settings(NINJA_NUM_PROXIES=1, TRUSTED_PROXIES=["10.0.0.1"])
    def test_trusted_peer_malformed_ip_falls_back_to_remote_addr(self):
        req = self.rf.get(
            "/",
            REMOTE_ADDR="10.0.0.1",
            HTTP_X_FORWARDED_FOR="not_a_valid_ip, 999.999.999.999",
        )
        self.assertEqual(get_client_ip(req), "10.0.0.1")

    @override_settings(NINJA_NUM_PROXIES=1, TRUSTED_PROXIES=["10.0.0.1"])
    def test_trusted_peer_empty_segments_falls_back_to_remote_addr(self):
        req = self.rf.get(
            "/",
            REMOTE_ADDR="10.0.0.1",
            HTTP_X_FORWARDED_FOR=", ,  ",
        )
        self.assertEqual(get_client_ip(req), "10.0.0.1")

    @override_settings(NINJA_NUM_PROXIES=1, TRUSTED_PROXIES=["10.0.0.1"])
    def test_trusted_peer_missing_header_falls_back_to_remote_addr(self):
        req = self.rf.get("/", REMOTE_ADDR="10.0.0.1")
        self.assertEqual(get_client_ip(req), "10.0.0.1")


class TestThrottleKeysAndSlidingWindow(TestCase):
    def setUp(self):
        cache.clear()
        self.rf = RequestFactory()

    def tearDown(self):
        cache.clear()

    def test_login_throttle_cache_key(self):
        throttle = LoginRateThrottle()
        req = self.rf.get("/", REMOTE_ADDR="198.51.100.1")
        key = throttle.get_cache_key(req)
        self.assertEqual(key, "throttle_login_198.51.100.1")

    def test_register_throttle_cache_key(self):
        throttle = RegisterRateThrottle()
        req = self.rf.get("/", REMOTE_ADDR="198.51.100.2")
        key = throttle.get_cache_key(req)
        self.assertEqual(key, "throttle_register_198.51.100.2")

    def test_claim_submit_throttle_cache_key_authenticated_user(self):
        throttle = ClaimSubmitRateThrottle()
        user = MagicMock()
        user.is_authenticated = True
        user.pk = "550e8400-e29b-41d4-a716-446655440000"

        req = self.rf.get("/", REMOTE_ADDR="198.51.100.3")
        req.user = user

        key = throttle.get_cache_key(req)
        self.assertEqual(key, "throttle_claim_submit_550e8400-e29b-41d4-a716-446655440000")

    def test_claim_submit_throttle_cache_key_unauthenticated_fallback(self):
        throttle = ClaimSubmitRateThrottle()
        req = self.rf.get("/", REMOTE_ADDR="198.51.100.4")
        req.user = None

        key = throttle.get_cache_key(req)
        self.assertEqual(key, "throttle_claim_submit_198.51.100.4")

    def test_analysis_status_throttle_cache_key(self):
        throttle = AnalysisStatusRateThrottle()
        user = MagicMock()
        user.is_authenticated = True
        user.pk = "user-123"

        req = self.rf.get("/", REMOTE_ADDR="198.51.100.5")
        req.user = user

        key = throttle.get_cache_key(req)
        self.assertEqual(key, "throttle_analysis_status_user-123")

    def test_sliding_window_expiration_deterministic(self):
        class DummyThrottle(BaseInfoTrustThrottle):
            scope = "dummy"
            default_rate = "2/min"

            def get_cache_key(self, request):
                return "throttle_dummy_key"

        throttle = DummyThrottle()
        req = self.rf.get("/")

        t0 = 1000.0
        with patch.object(throttle, "timer", return_value=t0):
            self.assertTrue(throttle.allow_request(req))
            self.assertTrue(throttle.allow_request(req))
            # Quota exhausted: 2 requests made
            self.assertFalse(throttle.allow_request(req))
            wait_seconds = throttle.wait()
            self.assertIsNotNone(wait_seconds)
            self.assertEqual(math.ceil(wait_seconds), 60)

        # Advance mock time past the 60s window duration
        with patch.object(throttle, "timer", return_value=t0 + 61.0):
            # Old timestamps expired from history; request should now succeed
            self.assertTrue(throttle.allow_request(req))


class TestCacheFailurePoliciesAndExceptionHandlers(TestCase):
    def setUp(self):
        cache.clear()
        self.rf = RequestFactory()

    def tearDown(self):
        cache.clear()

    @override_settings(RATE_LIMIT_FAIL_CLOSED=False)
    def test_cache_read_failure_fails_open_by_default(self):
        throttle = LoginRateThrottle()
        req = self.rf.get("/", REMOTE_ADDR="198.51.100.1")

        with patch.object(cache, "get", side_effect=Exception("Redis/DB cache connection failed")):
            with self.assertLogs("infotrust.security", level="WARNING") as cm:
                allowed = throttle.allow_request(req)
                self.assertTrue(allowed)
                self.assertIn("Rate limiting cache read failure", cm.output[0])
                self.assertIn("fail-open", cm.output[0])

    @override_settings(RATE_LIMIT_FAIL_CLOSED=False)
    def test_cache_write_failure_fails_open_by_default(self):
        throttle = LoginRateThrottle()
        req = self.rf.get("/", REMOTE_ADDR="198.51.100.1")

        with patch.object(cache, "set", side_effect=Exception("Cache write failure")):
            with self.assertLogs("infotrust.security", level="WARNING") as cm:
                allowed = throttle.allow_request(req)
                self.assertTrue(allowed)
                self.assertIn("Rate limiting cache write failure", cm.output[0])
                self.assertIn("fail-open", cm.output[0])

    @override_settings(RATE_LIMIT_FAIL_CLOSED=True)
    def test_cache_read_failure_fails_closed_when_configured(self):
        throttle = LoginRateThrottle()
        req = self.rf.get("/", REMOTE_ADDR="198.51.100.1")

        with patch.object(cache, "get", side_effect=Exception("Cache down")):
            with self.assertLogs("infotrust.security", level="WARNING") as cm:
                allowed = throttle.allow_request(req)
                self.assertFalse(allowed)
                self.assertTrue(getattr(req, "_rate_limit_backend_error", False))
                self.assertIn("fail-closed", cm.output[0])

    @override_settings(RATE_LIMIT_FAIL_CLOSED=True)
    def test_cache_write_failure_fails_closed_when_configured(self):
        throttle = LoginRateThrottle()
        req = self.rf.get("/", REMOTE_ADDR="198.51.100.1")

        with patch.object(cache, "set", side_effect=Exception("Cache write error")):
            with self.assertLogs("infotrust.security", level="WARNING") as cm:
                allowed = throttle.allow_request(req)
                self.assertFalse(allowed)
                self.assertTrue(getattr(req, "_rate_limit_backend_error", False))
                self.assertIn("fail-closed", cm.output[0])

    def test_throttled_handler_returns_429_with_exact_payload_and_retry_after(self):
        api = NinjaAPI(version="test_throttled")
        setup_exception_handlers(api)

        client = TestClient(api)
        req = self.rf.get("/test")
        handler = api._lookup_exception_handler(Throttled(wait=52.4))
        self.assertIsNotNone(handler)

        resp = handler(req, Throttled(wait=52.4))
        self.assertEqual(resp.status_code, 429)
        data = json.loads(resp.content)
        self.assertEqual(
            data,
            {
                "success": False,
                "message": "Rate limit exceeded. Please try again later.",
            },
        )
        self.assertEqual(resp["Retry-After"], "53")

    def test_throttled_handler_returns_503_under_backend_cache_failure(self):
        api = NinjaAPI(version="test_503")
        setup_exception_handlers(api)

        req = self.rf.get("/test")
        req._rate_limit_backend_error = True

        handler = api._lookup_exception_handler(Throttled(wait=None))
        self.assertIsNotNone(handler)

        resp = handler(req, Throttled(wait=None))
        self.assertEqual(resp.status_code, 503)
        data = json.loads(resp.content)
        self.assertEqual(
            data,
            {
                "success": False,
                "message": "Service temporarily unavailable. Please try again later.",
            },
        )
        self.assertFalse(resp.has_header("Retry-After"))

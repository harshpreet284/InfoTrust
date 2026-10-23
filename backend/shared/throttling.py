import ipaddress
import logging
import math
from typing import List, Optional

from django.conf import settings
from django.http import HttpRequest
from ninja.throttling import SimpleRateThrottle

logger = logging.getLogger("infotrust.security")


def is_trusted_proxy(peer_ip: str, trusted_list: List[str]) -> bool:
    """
    Validates if direct peer IP is in trusted proxy list or CIDR networks.
    """
    if not trusted_list:
        return False
    try:
        peer = ipaddress.ip_address(peer_ip)
    except ValueError:
        return False

    for trusted in trusted_list:
        try:
            if "/" in trusted:
                if peer in ipaddress.ip_network(trusted, strict=False):
                    return True
            else:
                if peer == ipaddress.ip_address(trusted):
                    return True
        except ValueError:
            continue
    return False


def get_client_ip(request: HttpRequest) -> str:
    """
    Safely resolves the client IP address from the request.

    - By default (NINJA_NUM_PROXIES <= 0 or direct peer not in TRUSTED_PROXIES),
      forwarded headers (X-Forwarded-For, X-Real-IP) are completely UNTRUSTED.
      The validated network socket IP in request.META['REMOTE_ADDR'] is strictly used.
    - If proxy forwarding is explicitly enabled and direct peer is a trusted proxy,
      the client IP is extracted from X-Forwarded-For at distance min(num_proxies, len(addrs))
      from the right-hand side and strictly validated using the standard ipaddress module.
    - Malformed or invalid forwarding chains safely fall back to REMOTE_ADDR.
    """
    remote_addr = (request.META.get("REMOTE_ADDR") or "127.0.0.1").strip()
    try:
        ipaddress.ip_address(remote_addr)
        safe_remote = remote_addr
    except ValueError:
        safe_remote = "127.0.0.1"

    num_proxies = getattr(settings, "NINJA_NUM_PROXIES", 0)
    trusted_proxies = getattr(settings, "TRUSTED_PROXIES", []) or []

    # Strict boundary: If proxy count is 0 OR direct peer is NOT a trusted proxy,
    # forwarded headers are completely UNTRUSTED.
    if num_proxies <= 0 or not is_trusted_proxy(safe_remote, trusted_proxies):
        return safe_remote

    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    if not xff:
        return safe_remote

    addrs = [addr.strip() for addr in xff.split(",") if addr.strip()]
    if not addrs:
        return safe_remote

    candidate_ip = addrs[-min(num_proxies, len(addrs))]
    try:
        parsed_ip = ipaddress.ip_address(candidate_ip)
        return str(parsed_ip)
    except ValueError:
        logger.warning(
            "Malformed IP in X-Forwarded-For: '%s'. Falling back to safe REMOTE_ADDR.",
            candidate_ip[:50],
        )
        return safe_remote


class BaseInfoTrustThrottle(SimpleRateThrottle):
    cache_format = "throttle_%(scope)s_%(ident)s"
    default_rate: Optional[str] = None

    def __init__(self, rate: Optional[str] = None):
        resolved_rate = rate or self.get_rate()
        self._backend_error = False
        super().__init__(rate=resolved_rate)

    def get_rate(self) -> Optional[str]:
        rates = getattr(settings, "NINJA_DEFAULT_THROTTLE_RATES", {}) or {}
        if self.scope and self.scope in rates and rates[self.scope] is not None:
            return rates[self.scope]
        if self.default_rate is not None:
            return self.default_rate
        return super().get_rate()

    def get_ident(self, request: HttpRequest) -> str:
        return get_client_ip(request)

    def wait(self) -> Optional[float]:
        if getattr(self, "_backend_error", False) or not hasattr(self, "history"):
            return None
        return super().wait()

    def allow_request(self, request: HttpRequest) -> bool:
        self.key = self.get_cache_key(request)
        if self.key is None:
            return True

        self._backend_error = False

        # Phase 1: Cache Read
        try:
            self.history = self.cache.get(self.key, [])
        except Exception as exc:
            self.history = []
            self._backend_error = True
            return self._handle_cache_failure(operation="read", exc=exc, request=request)

        self.now = self.timer()

        # Drop any requests from history that have passed throttle duration
        while self.history and self.history[-1] <= self.now - self.duration:
            self.history.pop()

        if len(self.history) >= self.num_requests:
            return self.throttle_failure()

        # Phase 2: Cache Write
        return self.throttle_success(request=request)

    def throttle_success(self, request: Optional[HttpRequest] = None) -> bool:
        self.history.insert(0, self.now)
        try:
            self.cache.set(self.key, self.history, self.duration)
        except Exception as exc:
            self._backend_error = True
            return self._handle_cache_failure(operation="write", exc=exc, request=request)
        return True

    def _handle_cache_failure(
        self, operation: str, exc: Exception, request: Optional[HttpRequest] = None
    ) -> bool:
        fail_closed = getattr(settings, "RATE_LIMIT_FAIL_CLOSED", False)
        logger.warning(
            "Rate limiting cache %s failure in %s for key '%s': %s. Policy: %s.",
            operation,
            self.__class__.__name__,
            getattr(self, "key", "unknown"),
            exc.__class__.__name__,
            "fail-closed" if fail_closed else "fail-open",
        )
        if fail_closed:
            if request is not None:
                request._rate_limit_backend_error = True
            return False
        return True


class LoginRateThrottle(BaseInfoTrustThrottle):
    scope = "login"
    default_rate = "10/min"

    def get_cache_key(self, request: HttpRequest) -> str:
        ident = self.get_ident(request)
        return self.cache_format % {"scope": self.scope, "ident": ident}


class RegisterRateThrottle(BaseInfoTrustThrottle):
    scope = "register"
    default_rate = "5/min"

    def get_cache_key(self, request: HttpRequest) -> str:
        ident = self.get_ident(request)
        return self.cache_format % {"scope": self.scope, "ident": ident}


class ClaimSubmitRateThrottle(BaseInfoTrustThrottle):
    scope = "claim_submit"
    default_rate = "30/hour"

    def get_cache_key(self, request: HttpRequest) -> str:
        if getattr(request, "user", None) and request.user.is_authenticated:
            ident = str(request.user.pk)
        else:
            ident = self.get_ident(request)
        return self.cache_format % {"scope": self.scope, "ident": ident}


class AnalysisStatusRateThrottle(BaseInfoTrustThrottle):
    """
    Deferred throttle class for future analysis milestone.
    Keyed by authenticated user ID.
    """
    scope = "analysis_status"
    default_rate = "120/hour"

    def get_cache_key(self, request: HttpRequest) -> str:
        if getattr(request, "user", None) and request.user.is_authenticated:
            ident = str(request.user.pk)
        else:
            ident = self.get_ident(request)
        return self.cache_format % {"scope": self.scope, "ident": ident}

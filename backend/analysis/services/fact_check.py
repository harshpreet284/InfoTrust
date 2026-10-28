"""
Fact-Check Service module for InfoTrust.
Coordinates external claim verification queries against Google Fact Check Tools API
and normalizes returned evidence for downstream analysis.
"""

import json
import logging
import math
import os
import socket
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Callable, Optional

from django.conf import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Domain Exceptions
# ---------------------------------------------------------------------------


class FactCheckServiceError(RuntimeError):
    """Base exception for all operational and domain failures in FactCheckService."""

    pass


class FactCheckConfigError(FactCheckServiceError, ValueError):
    """Raised when configuration (API key, timeout, max_results) is missing or invalid."""

    pass


class FactCheckInputError(FactCheckServiceError, ValueError):
    """Raised when input claim query fails validation (empty or whitespace-only)."""

    pass


class FactCheckAPIError(FactCheckServiceError):
    """Base exception for provider HTTP errors (4xx, 5xx) or malformed payloads."""

    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code


class FactCheckAuthError(FactCheckAPIError):
    """Raised when provider rejects credentials (HTTP 401 or 403)."""

    pass


class FactCheckRateLimitError(FactCheckAPIError):
    """Raised when provider rate limit is exceeded (HTTP 429)."""

    pass


class FactCheckTimeoutError(FactCheckServiceError):
    """Raised when a provider request times out."""

    pass


class FactCheckConnectionError(FactCheckServiceError):
    """Raised on socket connection drop, DNS resolution failure, or SSL error."""

    pass


# ---------------------------------------------------------------------------
# Data Contracts
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FactCheckEvidenceItem:
    """
    Represents an individual fact-check review from an external publisher.
    Must have a valid, non-empty HTTP/HTTPS evidence URL.
    """

    publisher: str
    rating: str
    url: str
    claim_text: Optional[str] = None
    review_date: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "publisher": self.publisher,
            "rating": self.rating,
            "url": self.url,
            "claim_text": self.claim_text,
            "review_date": self.review_date,
        }


@dataclass(frozen=True)
class FactCheckResult:
    """
    Normalized fact-check verification result.
    Invariant: matches == len(sources) == len(evidence_urls).
    """

    matches: int
    sources: tuple[FactCheckEvidenceItem, ...]
    summary: str
    evidence_urls: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "matches": self.matches,
            "sources": [item.to_dict() for item in self.sources],
            "summary": self.summary,
            "evidence_urls": list(self.evidence_urls),
        }

    @classmethod
    def empty(cls) -> "FactCheckResult":
        return cls(
            matches=0,
            sources=(),
            summary="No external fact-check reviews found for this claim.",
            evidence_urls=(),
        )


# ---------------------------------------------------------------------------
# Helper Functions
# ---------------------------------------------------------------------------


def _is_valid_evidence_url(url: Any) -> bool:
    """Verifies that url is a non-empty HTTP or HTTPS URL string."""
    if not isinstance(url, str):
        return False
    stripped = url.strip()
    return stripped.startswith("http://") or stripped.startswith("https://")


def _normalize_url(url: str) -> str:
    """Normalizes URL for deduplication while preserving identity."""
    parsed = urllib.parse.urlsplit(url.strip())
    # Scheme and netloc are case-insensitive
    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()
    path = parsed.path.rstrip("/") if parsed.path != "/" else "/"
    return urllib.parse.urlunsplit(
        (scheme, netloc, path, parsed.query, parsed.fragment)
    )


def _build_summary(sources: Sequence[FactCheckEvidenceItem]) -> str:
    """
    Constructs a deterministic, pure summary strictly grounded in returned evidence.
    Explicitly labels findings as reported by external reviewers, making no inference
    about claim truth or veracity.
    """
    if not sources:
        return "No external fact-check reviews found for this claim."

    if len(sources) == 1:
        return (
            f"External fact-check review by {sources[0].publisher} "
            f"reported rating: '{sources[0].rating}'."
        )

    # Multi-review summary: list up to first 3 reviews with explicit attribution
    top_sources = sources[:3]
    reviews_str = ", ".join(f"{s.publisher} reported '{s.rating}'" for s in top_sources)
    suffix = "..." if len(sources) > 3 else ""
    return (
        f"External fact-check reviews ({len(sources)} found): "
        f"{reviews_str}{suffix}."
    )


# ---------------------------------------------------------------------------
# Fact-Check Service
# ---------------------------------------------------------------------------


class FactCheckService:
    """
    Coordinates external fact-check queries against Google Fact Check Tools API.
    Normalizes returned claims and reviews into standardized dataclasses.
    """

    DEFAULT_ENDPOINT = "https://factchecktools.googleapis.com/v1alpha1/claims:search"

    def __init__(
        self,
        api_key: Optional[str] = None,
        timeout: Optional[float] = None,
        endpoint: str = DEFAULT_ENDPOINT,
        language_code: Optional[str] = None,
        max_results: int = 5,
        http_client: Optional[Callable[..., Any]] = None,
    ):
        """
        Initializes FactCheckService with optional configuration injection.

        Args:
            api_key: Optional API key. If omitted, resolved from settings/environment.
            timeout: Optional socket timeout in seconds. Must be positive finite float.
            endpoint: Base REST API endpoint for claims:search.
            language_code: Optional BCP-47 language tag (e.g. 'en-US'). None searches all.
            max_results: Maximum reviews to request (positive integer).
            http_client: Optional callable for making HTTP requests (defaults to urllib.request.urlopen).
        """
        self._injected_api_key = api_key

        if timeout is not None:
            if (
                isinstance(timeout, bool)
                or not isinstance(timeout, (int, float))
                or not math.isfinite(timeout)
                or timeout <= 0
            ):
                raise FactCheckConfigError(
                    f"timeout must be a positive finite number, got {timeout!r}."
                )
            self._timeout = float(timeout)
        else:
            self._timeout = getattr(settings, "FACT_CHECK_TIMEOUT_SECONDS", 5.0)

        if (
            isinstance(max_results, bool)
            or not isinstance(max_results, int)
            or max_results <= 0
        ):
            raise FactCheckConfigError(
                f"max_results must be a positive integer, got {max_results!r}."
            )
        self.max_results = max_results

        self.endpoint = endpoint
        self.language_code = language_code
        self._http_client = http_client or urllib.request.urlopen

    @property
    def timeout(self) -> float:
        return self._timeout

    @property
    def api_key(self) -> str:
        """Resolves API key from injected value, django settings, or environment."""
        if self._injected_api_key:
            return self._injected_api_key
        return getattr(
            settings, "FACT_CHECK_API_KEY", os.environ.get("FACT_CHECK_API_KEY", "")
        )

    def query(self, claim_text: str) -> FactCheckResult:
        """
        Queries external fact-check provider for reviews matching claim_text.

        Args:
            claim_text: Sanitized claim text string.

        Returns:
            FactCheckResult with matches, sources, summary, and evidence_urls.

        Raises:
            TypeError: If claim_text is not a string.
            FactCheckInputError: If claim_text is empty or whitespace-only.
            FactCheckConfigError: If FACT_CHECK_API_KEY is not configured or empty.
            FactCheckAuthError: On HTTP 401 or 403 provider responses.
            FactCheckRateLimitError: On HTTP 429 provider responses.
            FactCheckTimeoutError: On network or socket timeout.
            FactCheckConnectionError: On DNS resolution, SSL, or socket connection drops.
            FactCheckAPIError: On HTTP 5xx, HTTP 400, or wholly malformed payloads.
        """
        if not isinstance(claim_text, str):
            raise TypeError(
                f"claim_text must be a string, got {type(claim_text).__name__}."
            )

        cleaned_query = claim_text.strip()
        if not cleaned_query:
            raise FactCheckInputError("claim_text cannot be empty or whitespace-only.")

        resolved_key = self.api_key.strip() if self.api_key else ""
        if not resolved_key:
            raise FactCheckConfigError("FACT_CHECK_API_KEY is not configured or empty.")

        # Build request URL (API key is strictly omitted from query string)
        query_params = {"query": cleaned_query, "pageSize": self.max_results}
        if self.language_code:
            query_params["languageCode"] = self.language_code

        encoded_params = urllib.parse.urlencode(query_params)
        request_url = f"{self.endpoint}?{encoded_params}"

        # API key delivered via header to prevent exposure in logs or URL attributes
        headers = {
            "X-Goog-Api-Key": resolved_key,
            "User-Agent": "InfoTrust-FactCheck/1.0",
            "Accept": "application/json",
        }
        req = urllib.request.Request(request_url, headers=headers, method="GET")

        try:
            with self._http_client(req, timeout=self.timeout) as resp:
                raw_body = resp.read()
        except (TimeoutError, socket.timeout):
            raise FactCheckTimeoutError(
                "Fact-check provider request timed out."
            ) from None
        except urllib.error.HTTPError as err:
            if err.code in (401, 403):
                raise FactCheckAuthError(
                    f"Fact-check provider authentication failed (HTTP {err.code}).",
                    status_code=err.code,
                ) from None
            elif err.code == 429:
                raise FactCheckRateLimitError(
                    "Fact-check provider rate limit exceeded (HTTP 429).",
                    status_code=err.code,
                ) from None
            elif err.code == 400:
                raise FactCheckAPIError(
                    "Fact-check provider rejected request: Bad Request (HTTP 400).",
                    status_code=err.code,
                ) from None
            else:
                raise FactCheckAPIError(
                    f"Fact-check provider returned server error (HTTP {err.code}).",
                    status_code=err.code,
                ) from None
        except urllib.error.URLError as err:
            if isinstance(err.reason, (TimeoutError, socket.timeout)):
                raise FactCheckTimeoutError(
                    "Fact-check provider request timed out."
                ) from None
            raise FactCheckConnectionError(
                "Failed to establish network connection to fact-check provider."
            ) from None
        except OSError as err:
            if isinstance(err, (TimeoutError, socket.timeout)):
                raise FactCheckTimeoutError(
                    "Fact-check provider request timed out."
                ) from None
            raise FactCheckConnectionError(
                "Failed to establish network connection to fact-check provider."
            ) from None

        # Parse JSON response
        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise FactCheckAPIError(
                "Fact-check provider returned malformed non-JSON payload."
            ) from None

        if not isinstance(payload, dict):
            raise FactCheckAPIError(
                f"Fact-check provider returned unexpected JSON root type: expected dict, got {type(payload).__name__}."
            )

        # Check for provider-level error object returned with HTTP 200
        if "error" in payload and isinstance(payload["error"], dict):
            err_obj = payload["error"]
            err_code = err_obj.get("code")
            raise FactCheckAPIError(
                f"Fact-check provider returned error payload (code {err_code}).",
                status_code=int(err_code) if isinstance(err_code, int) else None,
            )

        # Valid zero-match response check (HTTP 200 with {} or {"claims": []})
        if "claims" not in payload:
            return FactCheckResult.empty()

        raw_claims = payload["claims"]
        if not isinstance(raw_claims, list):
            raise FactCheckAPIError(
                f"Fact-check provider returned invalid 'claims' structure: expected list, got {type(raw_claims).__name__}."
            )

        if not raw_claims:
            return FactCheckResult.empty()

        # Parse reviews and deduplicate by URL
        sources: list[FactCheckEvidenceItem] = []
        seen_urls: set[str] = set()

        for claim in raw_claims:
            if not isinstance(claim, dict):
                logger.warning("Skipping non-dict claim entry in fact-check payload.")
                continue

            claim_text_val = claim.get("text")
            reviewed_claim = str(claim_text_val).strip() if claim_text_val else None

            reviews = claim.get("claimReview")
            if not isinstance(reviews, list) or not reviews:
                continue

            for review in reviews:
                if not isinstance(review, dict):
                    logger.warning("Skipping non-dict review entry in claimReview.")
                    continue

                raw_url = review.get("url")
                if not _is_valid_evidence_url(raw_url):
                    # Reviews without a usable HTTP/HTTPS URL cannot serve as verifiable evidence
                    continue

                norm_url = _normalize_url(str(raw_url))
                if norm_url in seen_urls:
                    continue
                seen_urls.add(norm_url)

                # Publisher resolution
                pub_data = review.get("publisher")
                if isinstance(pub_data, dict):
                    pub_name = pub_data.get("name") or pub_data.get("site") or "Unknown"
                else:
                    pub_name = "Unknown"

                # Rating resolution
                rating_val = review.get("textualRating")
                rating_str = str(rating_val).strip() if rating_val else "Unrated"

                # Review date resolution
                date_val = review.get("reviewDate")
                review_date_str = str(date_val).strip() if date_val else None

                sources.append(
                    FactCheckEvidenceItem(
                        publisher=str(pub_name).strip(),
                        rating=rating_str,
                        url=str(raw_url).strip(),
                        claim_text=reviewed_claim,
                        review_date=review_date_str,
                    )
                )

        if not sources:
            return FactCheckResult.empty()

        sources_tuple = tuple(sources)
        evidence_urls_tuple = tuple(item.url for item in sources_tuple)
        summary_text = _build_summary(sources_tuple)

        return FactCheckResult(
            matches=len(sources_tuple),
            sources=sources_tuple,
            summary=summary_text,
            evidence_urls=evidence_urls_tuple,
        )

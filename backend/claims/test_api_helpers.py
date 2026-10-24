from types import SimpleNamespace

from django.test import TestCase

from claims.api import _build_history_page_link


class TestClaimApiHelpers(TestCase):
    def test_build_history_page_link_fallback_when_path_missing(self):
        """Verify _build_history_page_link falls back to /api/v1/claims/history when request lacks path."""
        link = _build_history_page_link(request=object(), page_num=2, page_size=15)
        self.assertTrue(link.startswith("/api/v1/claims/history?"))
        self.assertIn("page=2", link)
        self.assertIn("page_size=15", link)

    def test_build_history_page_link_with_search_and_ordering(self):
        """Verify _build_history_page_link properly encodes ordering and search query parameters."""
        req = SimpleNamespace(path="/api/v1/claims/history")
        link = _build_history_page_link(
            req,
            page_num=1,
            page_size=10,
            ordering="-created_at",
            search="covid vaccine",
        )
        self.assertIn("ordering=-created_at", link)
        self.assertIn("search=covid+vaccine", link)

    def test_build_history_page_link_omits_none_extra_params(self):
        """Verify _build_history_page_link includes valid extra_params and omits None values."""
        req = SimpleNamespace(path="/api/v1/claims/history")
        link = _build_history_page_link(
            req,
            page_num=1,
            page_size=10,
            extra_params={"status": "PENDING", "verdict": None},
        )
        self.assertIn("status=PENDING", link)
        self.assertNotIn("verdict", link)

import uuid
from django.test import TestCase
from django.core.exceptions import ObjectDoesNotExist

from datetime import date, datetime, timedelta, timezone as dt_timezone
from django.utils import timezone
from authentication.models import User
from claims.models import Claim, ClaimStatus
from analysis.models import Analysis, Verdict
from claims.selectors import (
    get_claim,
    list_all_claims_for_admin,
    get_user_claim_history,
    get_recent_claims,
)

class ClaimSelectorTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(email="owner@example.com", password="pwd", full_name="Owner")
        self.other_user = User.objects.create_user(email="other@example.com", password="pwd", full_name="Other")
        self.admin = User.objects.create_superuser(email="admin@example.com", password="pwd", full_name="Admin")
        
        self.claim1 = Claim.objects.create(
            user=self.owner,
            text="Owner's first claim",
            status=ClaimStatus.PENDING,
        )
        self.claim2 = Claim.objects.create(
            user=self.owner,
            text="Owner's second claim",
            status=ClaimStatus.PENDING,
        )
        self.other_claim = Claim.objects.create(
            user=self.other_user,
            text="Other user's claim",
            status=ClaimStatus.PENDING,
        )
        
        # Ensure explicit chronological differences since auto_now_add can tie in fast tests
        now = timezone.now()
        Claim.objects.filter(id=self.claim1.id).update(submitted_at=now - timedelta(seconds=10))
        Claim.objects.filter(id=self.claim2.id).update(submitted_at=now - timedelta(seconds=5))
        Claim.objects.filter(id=self.other_claim.id).update(submitted_at=now)
        
        # Soft-deleted claim
        self.deleted_claim = Claim.objects.create(
            user=self.owner,
            text="Deleted claim",
            status=ClaimStatus.PENDING,
            is_deleted=True,
        )
        Claim.objects.filter(id=self.deleted_claim.id).update(submitted_at=now - timedelta(seconds=15))

    # 1. get_claim tests
    def test_get_claim_owner_success(self):
        retrieved = get_claim(self.claim1.id, self.owner)
        self.assertEqual(retrieved.id, self.claim1.id)

    def test_get_claim_admin_success(self):
        retrieved = get_claim(self.claim1.id, self.admin)
        self.assertEqual(retrieved.id, self.claim1.id)

    def test_get_claim_non_owner_raises_authorization_error(self):
        from ninja.errors import AuthorizationError
        with self.assertRaises(AuthorizationError):
            get_claim(self.claim1.id, self.other_user)

    def test_get_claim_soft_deleted_excluded(self):
        with self.assertRaises(Claim.DoesNotExist):
            get_claim(self.deleted_claim.id, self.owner)

    def test_get_claim_admin_soft_deleted_excluded(self):
        with self.assertRaises(Claim.DoesNotExist):
            get_claim(self.deleted_claim.id, self.admin)

    # 2. list_all_claims_for_admin tests
    def test_admin_list_contains_claims_from_multiple_users(self):
        qs = list_all_claims_for_admin()
        self.assertEqual(qs.count(), 3)  # claim1, claim2, other_claim
        user_ids = {c.user_id for c in qs}
        self.assertIn(self.owner.id, user_ids)
        self.assertIn(self.other_user.id, user_ids)

    def test_admin_list_excludes_deleted_claims(self):
        qs = list_all_claims_for_admin()
        ids = {c.id for c in qs}
        self.assertNotIn(self.deleted_claim.id, ids)

    def test_admin_list_ordered_by_submitted_at(self):
        qs = list_all_claims_for_admin()
        self.assertEqual(qs.first().id, self.other_claim.id) # created last
        self.assertEqual(qs.last().id, self.claim1.id) # created first

    def test_admin_selector_user_relation_efficient(self):
        # We test that select_related("user", "analysis") exists and is efficient
        # for claims both with and without an Analysis record.
        Analysis.objects.create(claim=self.claim1, verdict="CREDIBLE", credibility_score=85.0)

        qs = list_all_claims_for_admin()
        with self.assertNumQueries(1):
            analyzed_count = 0
            unanalyzed_count = 0
            for claim in qs:
                # Accessing user.full_name should not trigger a new DB query because of select_related
                _ = claim.user.full_name
                if hasattr(claim, "analysis") and claim.analysis is not None:
                    _ = claim.analysis.verdict
                    analyzed_count += 1
                else:
                    _ = hasattr(claim, "analysis")
                    unanalyzed_count += 1
            self.assertEqual(analyzed_count, 1)
            self.assertEqual(unanalyzed_count, 2)

    # 3. get_user_claim_history tests
    def test_user_history_contains_only_owners_active_claims(self):
        qs = get_user_claim_history(self.owner)
        self.assertEqual(qs.count(), 2)
        ids = {c.id for c in qs}
        self.assertIn(self.claim1.id, ids)
        self.assertIn(self.claim2.id, ids)
        self.assertNotIn(self.other_claim.id, ids)
        self.assertNotIn(self.deleted_claim.id, ids)

    def test_user_history_ordered_by_submitted_at(self):
        qs = get_user_claim_history(self.owner)
        # claim2 was created after claim1
        self.assertEqual(qs.first().id, self.claim2.id)
        self.assertEqual(qs.last().id, self.claim1.id)

    def test_user_history_empty(self):
        new_user = User.objects.create_user(email="empty@example.com", password="pwd", full_name="Empty")
        qs = get_user_claim_history(new_user)
        self.assertEqual(qs.count(), 0)

    # 4. get_recent_claims tests
    def test_recent_claims_ordered_by_submitted_at(self):
        qs = get_recent_claims()
        self.assertEqual(qs.first().id, self.other_claim.id)
        self.assertEqual(qs.last().id, self.claim1.id)
        
    def test_recent_claims_no_hardcoded_limit_or_slicing(self):
        qs = get_recent_claims()
        # The queryset shouldn't be sliced (it has count() natively)
        self.assertEqual(qs.count(), 3)

    # 5. get_user_claim_history ordering & NULLS LAST tests
    def test_user_history_sorting_created_at_asc_and_desc(self):
        qs_desc = get_user_claim_history(self.owner, ordering="-created_at")
        self.assertEqual(qs_desc.first().id, self.claim2.id)
        self.assertEqual(qs_desc.last().id, self.claim1.id)

        qs_asc = get_user_claim_history(self.owner, ordering="created_at")
        self.assertEqual(qs_asc.first().id, self.claim1.id)
        self.assertEqual(qs_asc.last().id, self.claim2.id)

    def test_user_history_sorting_credibility_score_asc_nulls_last(self):
        # Create claims with: score 10.0, score 95.0, Analysis with None score, and no Analysis
        c_low = Claim.objects.create(user=self.owner, text="Claim with low credibility score", status=ClaimStatus.COMPLETED)
        Analysis.objects.create(claim=c_low, credibility_score=10.0)

        c_high = Claim.objects.create(user=self.owner, text="Claim with high credibility score", status=ClaimStatus.COMPLETED)
        Analysis.objects.create(claim=c_high, credibility_score=95.0)

        c_null_score = Claim.objects.create(user=self.owner, text="Claim with analysis but null score", status=ClaimStatus.PROCESSING)
        Analysis.objects.create(claim=c_null_score, credibility_score=None)

        # self.claim1 and self.claim2 have no Analysis
        qs = get_user_claim_history(self.owner, ordering="credibility_score")
        results = list(qs)
        
        # First two must be 10.0 then 95.0
        self.assertEqual(results[0].id, c_low.id)
        self.assertEqual(results[1].id, c_high.id)

        # Remaining items must be null credibility scores (c_null_score, claim1, claim2)
        remaining_ids = [c.id for c in results[2:]]
        self.assertIn(c_null_score.id, remaining_ids)
        self.assertIn(self.claim1.id, remaining_ids)
        self.assertIn(self.claim2.id, remaining_ids)

    def test_user_history_sorting_credibility_score_desc_nulls_last(self):
        c_low = Claim.objects.create(user=self.owner, text="Claim with low credibility score", status=ClaimStatus.COMPLETED)
        Analysis.objects.create(claim=c_low, credibility_score=10.0)

        c_high = Claim.objects.create(user=self.owner, text="Claim with high credibility score", status=ClaimStatus.COMPLETED)
        Analysis.objects.create(claim=c_high, credibility_score=95.0)

        c_null_score = Claim.objects.create(user=self.owner, text="Claim with analysis but null score", status=ClaimStatus.PROCESSING)
        Analysis.objects.create(claim=c_null_score, credibility_score=None)

        qs = get_user_claim_history(self.owner, ordering="-credibility_score")
        results = list(qs)

        # First two must be 95.0 then 10.0
        self.assertEqual(results[0].id, c_high.id)
        self.assertEqual(results[1].id, c_low.id)

        # Remaining items must be null credibility scores
        remaining_ids = [c.id for c in results[2:]]
        self.assertIn(c_null_score.id, remaining_ids)
        self.assertIn(self.claim1.id, remaining_ids)
        self.assertIn(self.claim2.id, remaining_ids)

    def test_user_history_sorting_status_asc_and_desc(self):
        c_completed = Claim.objects.create(user=self.owner, text="Completed claim text", status=ClaimStatus.COMPLETED)
        
        # COMPLETED starts with C, PENDING starts with P
        qs_asc = get_user_claim_history(self.owner, ordering="status")
        self.assertEqual(qs_asc.first().status, ClaimStatus.COMPLETED)

        qs_desc = get_user_claim_history(self.owner, ordering="-status")
        self.assertEqual(qs_desc.first().status, ClaimStatus.PENDING)

    def test_user_history_unsupported_ordering_raises_value_error(self):
        with self.assertRaises(ValueError) as ctx:
            get_user_claim_history(self.owner, ordering="unsupported_column")
        self.assertIn("Unsupported ordering 'unsupported_column'", str(ctx.exception))

    def test_user_history_select_related_analysis_efficiency(self):
        c = Claim.objects.create(user=self.owner, text="Claim with analysis test", status=ClaimStatus.COMPLETED)
        Analysis.objects.create(claim=c, credibility_score=80.0, verdict="CREDIBLE")

        qs = get_user_claim_history(self.owner)
        with self.assertNumQueries(1):
            for claim in qs:
                # Reading analysis shouldn't trigger additional SQL queries
                if hasattr(claim, "analysis") and claim.analysis is not None:
                    _ = claim.analysis.credibility_score
                    _ = claim.analysis.verdict

    # 6. Search selector tests (API-014)
    def test_user_history_search_partial_case_insensitive(self):
        c_vac = Claim.objects.create(
            user=self.owner,
            text="A breakthrough mRNA Vaccine trial has commenced.",
            status=ClaimStatus.PENDING,
        )
        qs = get_user_claim_history(self.owner, search="vAcCiNe")
        ids = {c.id for c in qs}
        self.assertIn(c_vac.id, ids)
        self.assertNotIn(self.claim1.id, ids)

    def test_user_history_search_leading_trailing_whitespace_trimmed(self):
        c_vac = Claim.objects.create(
            user=self.owner,
            text="A breakthrough mRNA Vaccine trial has commenced.",
            status=ClaimStatus.PENDING,
        )
        qs_trimmed = get_user_claim_history(self.owner, search="  vaccine  ")
        qs_exact = get_user_claim_history(self.owner, search="vaccine")
        self.assertEqual(list(qs_trimmed.values_list("id", flat=True)), list(qs_exact.values_list("id", flat=True)))
        self.assertIn(c_vac.id, {c.id for c in qs_trimmed})

    def test_user_history_search_empty_and_whitespace_only_unfiltered(self):
        qs_empty = get_user_claim_history(self.owner, search="")
        qs_whitespace = get_user_claim_history(self.owner, search="     ")
        qs_none = get_user_claim_history(self.owner, search=None)
        self.assertEqual(qs_empty.count(), 2)
        self.assertEqual(qs_whitespace.count(), 2)
        self.assertEqual(list(qs_empty), list(qs_none))

    def test_user_history_search_non_matching_query(self):
        qs = get_user_claim_history(self.owner, search="nonexistentphrase98765")
        self.assertEqual(qs.count(), 0)

    def test_user_history_search_soft_deleted_claims_excluded(self):
        deleted = Claim.objects.create(
            user=self.owner,
            text="Vaccine discussion that was soft deleted.",
            status=ClaimStatus.PENDING,
            is_deleted=True,
        )
        qs = get_user_claim_history(self.owner, search="vaccine")
        ids = {c.id for c in qs}
        self.assertNotIn(deleted.id, ids)

    def test_user_history_search_iso_date_matching_controlled_timestamp(self):
        dt_target = datetime(2026, 6, 15, 10, 0, 0, tzinfo=dt_timezone.utc)
        dt_other = datetime(2026, 8, 1, 12, 0, 0, tzinfo=dt_timezone.utc)
        dt_unrelated = datetime(2026, 9, 1, 14, 0, 0, tzinfo=dt_timezone.utc)

        # Claim A: submitted on 2026-06-15, no date text
        c_by_date = Claim.objects.create(
            user=self.owner,
            text="Clinical study results released without mention of day.",
            status=ClaimStatus.PENDING,
        )
        Claim.objects.filter(id=c_by_date.id).update(submitted_at=dt_target)

        # Claim B: submitted on 2026-08-01, but contains "2026-06-15" in text
        c_by_text = Claim.objects.create(
            user=self.owner,
            text="The event occurred on 2026-06-15 according to reports.",
            status=ClaimStatus.PENDING,
        )
        Claim.objects.filter(id=c_by_text.id).update(submitted_at=dt_other)

        # Claim C: submitted on 2026-09-01, unrelated text
        c_unrelated = Claim.objects.create(
            user=self.owner,
            text="Completely unrelated topic with no dates.",
            status=ClaimStatus.PENDING,
        )
        Claim.objects.filter(id=c_unrelated.id).update(submitted_at=dt_unrelated)

        qs = get_user_claim_history(self.owner, search="2026-06-15")
        ids = {c.id for c in qs}
        self.assertIn(c_by_date.id, ids)
        self.assertIn(c_by_text.id, ids)
        self.assertNotIn(c_unrelated.id, ids)

    def test_user_history_search_non_date_text_only(self):
        # Query that resembles a date pattern but is invalid date
        qs_invalid_date = get_user_claim_history(self.owner, search="2026-99-99")
        self.assertEqual(qs_invalid_date.count(), 0)

        # Query that is a word like 'October' only matches text
        c_month = Claim.objects.create(
            user=self.owner,
            text="Announcement made in October.",
            status=ClaimStatus.PENDING,
        )
        qs_month = get_user_claim_history(self.owner, search="October")
        self.assertEqual(qs_month.count(), 1)
        self.assertEqual(qs_month.first().id, c_month.id)

    def test_user_history_search_owner_isolation_preserved(self):
        # Other user has a matching claim
        Claim.objects.create(
            user=self.other_user,
            text="Other user's confidential vaccine post.",
            status=ClaimStatus.PENDING,
        )
        # Owner also has a matching claim
        owner_vac = Claim.objects.create(
            user=self.owner,
            text="Owner's personal vaccine post.",
            status=ClaimStatus.PENDING,
        )
        qs = get_user_claim_history(self.owner, search="vaccine")
        ids = {c.id for c in qs}
        self.assertIn(owner_vac.id, ids)
        self.assertEqual(qs.filter(user=self.other_user).count(), 0)

    def test_admin_selector_search_system_wide(self):
        c1 = Claim.objects.create(
            user=self.owner,
            text="System wide report on global warming.",
            status=ClaimStatus.PENDING,
        )
        c2 = Claim.objects.create(
            user=self.other_user,
            text="Another view on global warming trends.",
            status=ClaimStatus.PENDING,
        )
        qs = list_all_claims_for_admin(search="global warming")
        ids = {c.id for c in qs}
        self.assertIn(c1.id, ids)
        self.assertIn(c2.id, ids)
        # Verify both owners are present
        owners = {c.user_id for c in qs}
        self.assertIn(self.owner.id, owners)
        self.assertIn(self.other_user.id, owners)

    def test_admin_selector_search_soft_deleted_excluded(self):
        deleted = Claim.objects.create(
            user=self.other_user,
            text="System wide report on global warming deleted.",
            status=ClaimStatus.PENDING,
            is_deleted=True,
        )
        qs = list_all_claims_for_admin(search="global warming")
        ids = {c.id for c in qs}
        self.assertNotIn(deleted.id, ids)

    def test_admin_selector_search_efficiency(self):
        c1 = Claim.objects.create(
            user=self.owner,
            text="Efficiency search analyzed claim.",
            status=ClaimStatus.COMPLETED,
        )
        Analysis.objects.create(claim=c1, verdict="CREDIBLE", credibility_score=95.0)
        c2 = Claim.objects.create(
            user=self.other_user,
            text="Efficiency search unanalyzed claim.",
            status=ClaimStatus.PENDING,
        )

        qs = list_all_claims_for_admin(search="Efficiency search")
        with self.assertNumQueries(1):
            for claim in qs:
                _ = claim.user.full_name
                if hasattr(claim, "analysis") and claim.analysis is not None:
                    _ = claim.analysis.verdict
                else:
                    _ = hasattr(claim, "analysis")

    def test_search_special_characters_sql_escaped(self):
        special_claim = Claim.objects.create(
            user=self.owner,
            text="Special 100% discount with 'single' and \"double\" quotes & more_symbols.",
            status=ClaimStatus.PENDING,
        )
        for term in ["100%", "'single'", "\"double\"", "more_symbols", "&"]:
            qs = get_user_claim_history(self.owner, search=term)
            self.assertIn(special_claim.id, {c.id for c in qs}, f"Failed to match term: {term}")

    # 7. Filtering tests (API-015)
    def test_user_history_filter_by_status(self):
        self.claim1.status = ClaimStatus.COMPLETED
        self.claim1.save()
        self.claim2.status = ClaimStatus.FAILED
        self.claim2.save()

        qs_completed = get_user_claim_history(self.owner, status="COMPLETED")
        self.assertEqual(qs_completed.count(), 1)
        self.assertEqual(qs_completed.first().id, self.claim1.id)

        # Case-insensitive normalization in selector
        qs_completed_lower = get_user_claim_history(self.owner, status="completed")
        self.assertEqual(qs_completed_lower.count(), 1)
        self.assertEqual(qs_completed_lower.first().id, self.claim1.id)

        qs_failed = get_user_claim_history(self.owner, status="FAILED")
        self.assertEqual(qs_failed.count(), 1)
        self.assertEqual(qs_failed.first().id, self.claim2.id)

    def test_user_history_filter_by_verdict(self):
        Analysis.objects.create(claim=self.claim1, verdict=Verdict.CREDIBLE, credibility_score=90.0)
        Analysis.objects.create(claim=self.claim2, verdict=Verdict.MISINFORMATION, credibility_score=20.0)
        # claim without analysis
        claim_no_analysis = Claim.objects.create(
            user=self.owner,
            text="Unanalyzed claim by owner.",
            status=ClaimStatus.PENDING,
        )

        qs_cred = get_user_claim_history(self.owner, verdict="CREDIBLE")
        self.assertEqual(qs_cred.count(), 1)
        self.assertEqual(qs_cred.first().id, self.claim1.id)

        # Case-insensitive normalization
        qs_cred_lower = get_user_claim_history(self.owner, verdict="credible")
        self.assertEqual(qs_cred_lower.count(), 1)
        self.assertEqual(qs_cred_lower.first().id, self.claim1.id)

        qs_misinfo = get_user_claim_history(self.owner, verdict="MISINFORMATION")
        self.assertEqual(qs_misinfo.count(), 1)
        self.assertEqual(qs_misinfo.first().id, self.claim2.id)

        # Verdict that has no matches
        qs_uncertain = get_user_claim_history(self.owner, verdict="UNCERTAIN")
        self.assertEqual(qs_uncertain.count(), 0)

        # Unanalyzed claim is never included in verdict filter
        all_verdict_ids = {c.id for c in qs_cred} | {c.id for c in qs_misinfo} | {c.id for c in qs_uncertain}
        self.assertNotIn(claim_no_analysis.id, all_verdict_ids)

    def test_user_history_filter_date_boundaries_exact(self):
        # Precise UTC timestamps for boundary verification:
        # A: exactly at start of day 2026-06-15 00:00:00 UTC
        # B: middle of day 2026-06-15 12:00:00 UTC
        # C: last microsecond of day 2026-06-15 23:59:59.999999 UTC
        # D: start of next day 2026-06-16 00:00:00 UTC (exclusive bound)
        # E: previous day 2026-06-14 23:59:59.999999 UTC
        dt_a = datetime(2026, 6, 15, 0, 0, 0, 0, tzinfo=dt_timezone.utc)
        dt_b = datetime(2026, 6, 15, 12, 0, 0, 0, tzinfo=dt_timezone.utc)
        dt_c = datetime(2026, 6, 15, 23, 59, 59, 999999, tzinfo=dt_timezone.utc)
        dt_d = datetime(2026, 6, 16, 0, 0, 0, 0, tzinfo=dt_timezone.utc)
        dt_e = datetime(2026, 6, 14, 23, 59, 59, 999999, tzinfo=dt_timezone.utc)

        ca = Claim.objects.create(user=self.owner, text="Claim at 00:00:00 UTC")
        cb = Claim.objects.create(user=self.owner, text="Claim at 12:00:00 UTC")
        cc = Claim.objects.create(user=self.owner, text="Claim at 23:59:59.999999 UTC")
        cd = Claim.objects.create(user=self.owner, text="Claim next day 00:00:00 UTC")
        ce = Claim.objects.create(user=self.owner, text="Claim previous day 23:59:59 UTC")

        Claim.objects.filter(id=ca.id).update(submitted_at=dt_a)
        Claim.objects.filter(id=cb.id).update(submitted_at=dt_b)
        Claim.objects.filter(id=cc.id).update(submitted_at=dt_c)
        Claim.objects.filter(id=cd.id).update(submitted_at=dt_d)
        Claim.objects.filter(id=ce.id).update(submitted_at=dt_e)

        # Range exactly covering 2026-06-15: inclusive lower bound, exclusive next-day bound
        qs_single_day = get_user_claim_history(
            self.owner,
            date_from=date(2026, 6, 15),
            date_to=date(2026, 6, 15),
        )
        ids = {c.id for c in qs_single_day}
        self.assertIn(ca.id, ids)
        self.assertIn(cb.id, ids)
        self.assertIn(cc.id, ids)
        self.assertNotIn(cd.id, ids)
        self.assertNotIn(ce.id, ids)

        # String date inputs
        qs_str = get_user_claim_history(
            self.owner,
            date_from="2026-06-15",
            date_to="2026-06-15",
        )
        self.assertEqual({c.id for c in qs_str}, {ca.id, cb.id, cc.id})

        # Only date_from: includes ca, cb, cc, cd (and excluded ce)
        qs_from = get_user_claim_history(self.owner, date_from=date(2026, 6, 15))
        ids_from = {c.id for c in qs_from}
        self.assertIn(ca.id, ids_from)
        self.assertIn(cb.id, ids_from)
        self.assertIn(cc.id, ids_from)
        self.assertIn(cd.id, ids_from)
        self.assertNotIn(ce.id, ids_from)

        # Only date_to: includes ca, cb, cc, ce (and excludes cd)
        qs_to = get_user_claim_history(self.owner, date_to=date(2026, 6, 15))
        ids_to = {c.id for c in qs_to}
        self.assertIn(ca.id, ids_to)
        self.assertIn(cb.id, ids_to)
        self.assertIn(cc.id, ids_to)
        self.assertIn(ce.id, ids_to)
        self.assertNotIn(cd.id, ids_to)

    def test_user_history_filter_inverted_dates_raises_value_error(self):
        with self.assertRaises(ValueError):
            get_user_claim_history(
                self.owner,
                date_from=date(2026, 6, 16),
                date_to=date(2026, 6, 15),
            )
        with self.assertRaises(ValueError):
            get_user_claim_history(
                self.owner,
                date_from="2026-06-16",
                date_to="2026-06-15",
            )

    def test_user_history_filter_combined_with_search_and_ordering(self):
        c1 = Claim.objects.create(
            user=self.owner,
            text="Global economic outlook report positive trends.",
            status=ClaimStatus.COMPLETED,
        )
        Analysis.objects.create(claim=c1, verdict=Verdict.CREDIBLE, credibility_score=95.0)

        c2 = Claim.objects.create(
            user=self.owner,
            text="Global economic outlook report negative trends.",
            status=ClaimStatus.COMPLETED,
        )
        Analysis.objects.create(claim=c2, verdict=Verdict.MISINFORMATION, credibility_score=15.0)

        c3 = Claim.objects.create(
            user=self.owner,
            text="Global climate outlook unrelated to market matters.",
            status=ClaimStatus.COMPLETED,
        )
        Analysis.objects.create(claim=c3, verdict=Verdict.CREDIBLE, credibility_score=85.0)

        # Filter by search="economic", status="COMPLETED", verdict="CREDIBLE"
        qs = get_user_claim_history(
            self.owner,
            search="economic",
            status="COMPLETED",
            verdict="CREDIBLE",
            ordering="-credibility_score",
        )
        self.assertEqual(qs.count(), 1)
        self.assertEqual(qs.first().id, c1.id)

    def test_user_history_filter_owner_isolation_preserved(self):
        Claim.objects.create(
            user=self.other_user,
            text="Other user completed claim.",
            status=ClaimStatus.COMPLETED,
        )
        owner_c = Claim.objects.create(
            user=self.owner,
            text="Owner completed claim.",
            status=ClaimStatus.COMPLETED,
        )

        qs = get_user_claim_history(self.owner, status="COMPLETED")
        ids = {c.id for c in qs}
        self.assertIn(owner_c.id, ids)
        self.assertEqual(qs.filter(user=self.other_user).count(), 0)

    def test_admin_selector_filter_user_id(self):
        qs_owner = list_all_claims_for_admin(user_id=self.owner.id)
        self.assertGreater(qs_owner.count(), 0)
        for claim in qs_owner:
            self.assertEqual(claim.user_id, self.owner.id)

        qs_other = list_all_claims_for_admin(user_id=self.other_user.id)
        self.assertGreater(qs_other.count(), 0)
        for claim in qs_other:
            self.assertEqual(claim.user_id, self.other_user.id)

    def test_admin_selector_filter_status_and_verdict(self):
        self.claim1.status = ClaimStatus.COMPLETED
        self.claim1.save()
        Analysis.objects.create(claim=self.claim1, verdict=Verdict.CREDIBLE, credibility_score=88.0)

        self.other_claim.status = ClaimStatus.COMPLETED
        self.other_claim.save()
        Analysis.objects.create(claim=self.other_claim, verdict=Verdict.CREDIBLE, credibility_score=92.0)

        qs = list_all_claims_for_admin(status="COMPLETED", verdict="CREDIBLE")
        ids = {c.id for c in qs}
        self.assertIn(self.claim1.id, ids)
        self.assertIn(self.other_claim.id, ids)
        # Verify multiple owners present in admin view
        self.assertEqual({c.user_id for c in qs}, {self.owner.id, self.other_user.id})

    def test_admin_selector_filter_efficiency(self):
        self.claim1.status = ClaimStatus.COMPLETED
        self.claim1.save()
        Analysis.objects.create(claim=self.claim1, verdict=Verdict.CREDIBLE, credibility_score=88.0)

        qs = list_all_claims_for_admin(
            status="COMPLETED",
            verdict="CREDIBLE",
            user_id=self.owner.id,
        )
        with self.assertNumQueries(1):
            for claim in qs:
                _ = claim.user.full_name
                _ = claim.analysis.verdict

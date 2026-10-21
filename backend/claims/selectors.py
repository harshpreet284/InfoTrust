from datetime import date, datetime, time, timedelta, timezone as dt_timezone
import uuid
from typing import Optional, Union
from django.db.models import F, Q, QuerySet
from ninja.errors import AuthorizationError
from authentication.models import User
from claims.models import Claim
from claims.permissions import is_admin_user


ORDERING_MAP = {
    "-created_at": ("-submitted_at", "-id"),
    "created_at": ("submitted_at", "id"),
    "-credibility_score": (F("analysis__credibility_score").desc(nulls_last=True), "-submitted_at", "-id"),
    "credibility_score": (F("analysis__credibility_score").asc(nulls_last=True), "submitted_at", "id"),
    "-status": ("-status", "-submitted_at", "-id"),
    "status": ("status", "-submitted_at", "-id"),
}


def _build_claim_search_q(search: Optional[str]) -> Optional[Q]:
    """
    Constructs an ORM search filter for claims:
    - Trims leading/trailing whitespace.
    - If empty, returns None (no search filter applied).
    - Always performs case-insensitive partial match on claim text.
    - If the trimmed query is a valid ISO date (YYYY-MM-DD), also matches
      claims submitted on that calendar date via exact date equality.
    """
    if not search:
        return None
    cleaned = search.strip()
    if not cleaned:
        return None

    text_q = Q(text__icontains=cleaned)

    parsed_date = None
    try:
        parsed_date = datetime.strptime(cleaned, "%Y-%m-%d").date()
    except ValueError:
        pass

    if parsed_date:
        return text_q | Q(submitted_at__date=parsed_date)
    return text_q


def get_claim(claim_id: uuid.UUID, user: User) -> Claim:
    """
    Retrieves a single active claim.
    Admins can retrieve any active claim.
    Normal users can retrieve only their own active claims.
    """
    qs = Claim.objects.filter(id=claim_id, is_deleted=False)
    
    claim = qs.get()
    if not is_admin_user(user) and claim.user_id != user.id:
        raise AuthorizationError("You do not have permission to view this claim.")
        
    return claim


def _apply_claim_filters(
    qs: QuerySet[Claim],
    status: Optional[str] = None,
    verdict: Optional[str] = None,
    date_from: Optional[Union[date, str]] = None,
    date_to: Optional[Union[date, str]] = None,
    user_id: Optional[Union[uuid.UUID, str]] = None,
) -> QuerySet[Claim]:
    """
    Applies common claim filters:
    - status: Case-insensitive claim status filter.
    - verdict: Case-insensitive analysis verdict filter.
      Claims without an analysis or with a null verdict are excluded when verdict is filtered.
    - date_from: Inclusive UTC datetime lower bound (submitted_at >= YYYY-MM-DD 00:00:00 UTC).
    - date_to: Exclusive next-day UTC datetime upper bound (submitted_at < (YYYY-MM-DD + 1 day) 00:00:00 UTC).
    - user_id: Matches claim.user_id (used only in admin listings).
    """
    if status:
        cleaned_status = status.strip().upper() if isinstance(status, str) else str(status).upper()
        if cleaned_status:
            qs = qs.filter(status=cleaned_status)

    if verdict:
        cleaned_verdict = verdict.strip().upper() if isinstance(verdict, str) else str(verdict).upper()
        if cleaned_verdict:
            qs = qs.filter(analysis__verdict=cleaned_verdict)

    parsed_date_from = None
    if date_from:
        if isinstance(date_from, str):
            parsed_date_from = datetime.strptime(date_from.strip(), "%Y-%m-%d").date()
        elif isinstance(date_from, datetime):
            parsed_date_from = date_from.date()
        elif isinstance(date_from, date):
            parsed_date_from = date_from

    parsed_date_to = None
    if date_to:
        if isinstance(date_to, str):
            parsed_date_to = datetime.strptime(date_to.strip(), "%Y-%m-%d").date()
        elif isinstance(date_to, datetime):
            parsed_date_to = date_to.date()
        elif isinstance(date_to, date):
            parsed_date_to = date_to

    if parsed_date_from and parsed_date_to and parsed_date_from > parsed_date_to:
        raise ValueError(f"date_from ({parsed_date_from}) cannot be after date_to ({parsed_date_to}).")

    if parsed_date_from:
        start_dt = datetime.combine(parsed_date_from, time.min).replace(tzinfo=dt_timezone.utc)
        qs = qs.filter(submitted_at__gte=start_dt)

    if parsed_date_to:
        end_dt = datetime.combine(parsed_date_to + timedelta(days=1), time.min).replace(tzinfo=dt_timezone.utc)
        qs = qs.filter(submitted_at__lt=end_dt)

    if user_id:
        qs = qs.filter(user_id=user_id)

    return qs


def list_all_claims_for_admin(
    search: Optional[str] = None,
    status: Optional[str] = None,
    verdict: Optional[str] = None,
    date_from: Optional[Union[date, str]] = None,
    date_to: Optional[Union[date, str]] = None,
    user_id: Optional[Union[uuid.UUID, str]] = None,
    ordering: Optional[str] = None,
) -> QuerySet[Claim]:
    """
    Retrieves all active claims system-wide for the admin dashboard.
    Orders chronologically by submitted_at (newest first) with deterministic tie-breaker by default.
    Supports ordering by created_at, credibility_score, and status (asc and desc).
    Pre-fetches the user and analysis relations.
    Applies optional search filter across claim text and submission date.
    Applies optional filters by status, verdict, date range (UTC boundaries), and user_id.
    """
    if ordering is None:
        order_fields = ("-submitted_at", "-id")
    elif ordering in ORDERING_MAP:
        order_fields = ORDERING_MAP[ordering]
    else:
        allowed = ", ".join(sorted(ORDERING_MAP.keys()))
        raise ValueError(f"Unsupported ordering '{ordering}'. Allowed fields: {allowed}")

    qs = Claim.objects.filter(is_deleted=False).select_related("user", "analysis")
    search_q = _build_claim_search_q(search)
    if search_q:
        qs = qs.filter(search_q)

    qs = _apply_claim_filters(
        qs=qs,
        status=status,
        verdict=verdict,
        date_from=date_from,
        date_to=date_to,
        user_id=user_id,
    )
    return qs.order_by(*order_fields)


def get_user_claim_history(
    user: User,
    ordering: Optional[str] = None,
    search: Optional[str] = None,
    status: Optional[str] = None,
    verdict: Optional[str] = None,
    date_from: Optional[Union[date, str]] = None,
    date_to: Optional[Union[date, str]] = None,
) -> QuerySet[Claim]:
    """
    Retrieves all active claims owned by a specific user.
    Defaults to newest submissions first (-submitted_at, -id).
    Pre-fetches the analysis relation for efficient serialization.
    Applies optional search filter across claim text and submission date.
    Applies optional filters by status, verdict, and date range (UTC boundaries).
    Raises ValueError for any unsupported non-None ordering.
    """
    if ordering is None:
        order_fields = ("-submitted_at", "-id")
    elif ordering in ORDERING_MAP:
        order_fields = ORDERING_MAP[ordering]
    else:
        allowed = ", ".join(sorted(ORDERING_MAP.keys()))
        raise ValueError(f"Unsupported ordering '{ordering}'. Allowed fields: {allowed}")

    qs = Claim.objects.filter(user=user, is_deleted=False)
    search_q = _build_claim_search_q(search)
    if search_q:
        qs = qs.filter(search_q)

    qs = _apply_claim_filters(
        qs=qs,
        status=status,
        verdict=verdict,
        date_from=date_from,
        date_to=date_to,
    )

    return qs.select_related("analysis").order_by(*order_fields)


def get_recent_claims() -> QuerySet[Claim]:
    """
    Retrieves active claims chronologically.
    Returns an unevaluated QuerySet for the dashboard to slice/paginate.
    """
    return Claim.objects.filter(is_deleted=False).order_by("-submitted_at")

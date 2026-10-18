from datetime import datetime
import uuid
from typing import Optional
from django.db.models import F, Q, QuerySet
from ninja.errors import AuthorizationError
from authentication.models import User
from claims.models import Claim


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
    if not user.is_superuser and claim.user_id != user.id:
        raise AuthorizationError("You do not have permission to view this claim.")
        
    return claim


def list_all_claims_for_admin(search: Optional[str] = None) -> QuerySet[Claim]:
    """
    Retrieves all active claims system-wide for the admin dashboard.
    Orders chronologically by submitted_at (newest first) with deterministic tie-breaker.
    Pre-fetches the user and analysis relations.
    Applies optional search filter across claim text and submission date.
    """
    qs = Claim.objects.filter(is_deleted=False).select_related("user", "analysis")
    search_q = _build_claim_search_q(search)
    if search_q:
        qs = qs.filter(search_q)
    return qs.order_by("-submitted_at", "-id")


def get_user_claim_history(
    user: User,
    ordering: Optional[str] = None,
    search: Optional[str] = None,
) -> QuerySet[Claim]:
    """
    Retrieves all active claims owned by a specific user.
    Defaults to newest submissions first (-submitted_at, -id).
    Pre-fetches the analysis relation for efficient serialization.
    Applies optional search filter across claim text and submission date.
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

    return qs.select_related("analysis").order_by(*order_fields)


def get_recent_claims() -> QuerySet[Claim]:
    """
    Retrieves active claims chronologically.
    Returns an unevaluated QuerySet for the dashboard to slice/paginate.
    """
    return Claim.objects.filter(is_deleted=False).order_by("-submitted_at")

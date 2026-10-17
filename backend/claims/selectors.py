import uuid
from typing import Optional
from django.db.models import F, QuerySet
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


def list_all_claims_for_admin() -> QuerySet[Claim]:
    """
    Retrieves all active claims system-wide for the admin dashboard.
    Orders chronologically by submitted_at (newest first) with deterministic tie-breaker.
    Pre-fetches the user and analysis relations.
    """
    return (
        Claim.objects.filter(is_deleted=False)
        .select_related("user", "analysis")
        .order_by("-submitted_at", "-id")
    )


def get_user_claim_history(user: User, ordering: Optional[str] = None) -> QuerySet[Claim]:
    """
    Retrieves all active claims owned by a specific user.
    Defaults to newest submissions first (-submitted_at, -id).
    Pre-fetches the analysis relation for efficient serialization.
    Raises ValueError for any unsupported non-None ordering.
    """
    if ordering is None:
        order_fields = ("-submitted_at", "-id")
    elif ordering in ORDERING_MAP:
        order_fields = ORDERING_MAP[ordering]
    else:
        allowed = ", ".join(sorted(ORDERING_MAP.keys()))
        raise ValueError(f"Unsupported ordering '{ordering}'. Allowed fields: {allowed}")

    return (
        Claim.objects.filter(user=user, is_deleted=False)
        .select_related("analysis")
        .order_by(*order_fields)
    )


def get_recent_claims() -> QuerySet[Claim]:
    """
    Retrieves active claims chronologically.
    Returns an unevaluated QuerySet for the dashboard to slice/paginate.
    """
    return Claim.objects.filter(is_deleted=False).order_by("-submitted_at")

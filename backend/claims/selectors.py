import uuid
from django.db.models import QuerySet
from ninja.errors import AuthorizationError
from authentication.models import User
from claims.models import Claim


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
    Orders chronologically by submitted_at (newest first).
    Pre-fetches the user relation.
    """
    return Claim.objects.filter(is_deleted=False).select_related("user").order_by("-submitted_at")


def get_user_claim_history(user: User) -> QuerySet[Claim]:
    """
    Retrieves all active claims owned by a specific user.
    Orders chronologically by submitted_at (newest first).
    """
    return Claim.objects.filter(user=user, is_deleted=False).order_by("-submitted_at")


def get_recent_claims() -> QuerySet[Claim]:
    """
    Retrieves active claims chronologically.
    Returns an unevaluated QuerySet for the dashboard to slice/paginate.
    """
    return Claim.objects.filter(is_deleted=False).order_by("-submitted_at")

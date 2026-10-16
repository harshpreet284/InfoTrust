import uuid
from django.core.exceptions import ObjectDoesNotExist
from django.http import Http404
from django.utils import timezone
from ninja.errors import AuthorizationError, HttpError

from authentication.models import User
from claims.models import Claim, ClaimStatus
from claims.schemas import ClaimCreateSchema, ClaimUpdateSchema


def _get_claim_for_mutation(claim_id: uuid.UUID, user: User) -> Claim:
    """
    Internal helper to securely fetch a claim for mutation operations.
    Excludes soft-deleted claims entirely (treated as Not Found).
    Ensures the user has base mutation-level access (owner or admin).
    """
    try:
        claim = Claim.objects.get(id=claim_id, is_deleted=False)
    except ObjectDoesNotExist:
        raise Http404("Claim not found.")

    if claim.user != user and not user.is_superuser:
        raise AuthorizationError(message="You do not have permission to access this claim.")

    return claim


def submit_claim(user: User, payload: ClaimCreateSchema) -> Claim:
    """
    Creates a new pending claim for the user.
    """
    claim = Claim.objects.create(
        user=user,
        text=payload.claim_text,
        status=ClaimStatus.PENDING,
        is_deleted=False,
    )
    return claim


def update_claim(claim_id: uuid.UUID, user: User, payload: ClaimUpdateSchema) -> Claim:
    """
    Updates the text of a PENDING claim. Only the owner may update.
    Protects against concurrent transitions or soft-deletes via conditional update.
    """
    claim = _get_claim_for_mutation(claim_id, user)

    # Admins cannot update claims, only the actual owner
    if claim.user != user:
        raise AuthorizationError(message="You do not have permission to access this claim.")

    if claim.status != ClaimStatus.PENDING:
        raise HttpError(409, "Analysis already started")

    # Atomic conditional update requiring PENDING and active state
    updated_count = Claim.objects.filter(
        id=claim.id,
        status=ClaimStatus.PENDING,
        is_deleted=False,
    ).update(
        text=payload.claim_text,
        updated_at=timezone.now(),
    )

    if updated_count == 0:
        # Re-read state to distinguish soft-delete/missing (404) from status conflict (409)
        try:
            current_claim = Claim.objects.get(id=claim.id)
        except Claim.DoesNotExist:
            raise Claim.DoesNotExist("Claim matching query does not exist.")

        if current_claim.is_deleted:
            raise Claim.DoesNotExist("Claim matching query does not exist.")

        if current_claim.status != ClaimStatus.PENDING:
            raise HttpError(409, "Analysis already started")

        # Defensive fallback: record exists, is active, and is PENDING,
        # but conditional update affected 0 rows (unexpected update conflict).
        raise HttpError(409, "Claim update conflict. The claim could not be updated.")

    claim.refresh_from_db()
    return claim


def _is_admin_user(user: User) -> bool:
    """
    Checks if a user has administrator privileges.
    Recognizes application admins (role == 'ADMIN') and Django superusers (is_superuser == True).
    """
    return getattr(user, "role", None) == "ADMIN" or getattr(user, "is_superuser", False)


def _get_claim_for_deletion(claim_id: uuid.UUID, user: User) -> Claim:
    """
    Internal helper to securely fetch a claim for deletion operations.
    Excludes soft-deleted claims entirely (treated as Not Found via Http404).
    Ensures the user is either the claim owner or an administrator.
    Normal non-owners are rejected with AuthorizationError (HTTP 403).
    """
    try:
        claim = Claim.objects.get(id=claim_id, is_deleted=False)
    except ObjectDoesNotExist:
        raise Http404("Claim not found.")

    if claim.user != user and not _is_admin_user(user):
        raise AuthorizationError(message="You do not have permission to access this claim.")

    return claim


def delete_claim(claim_id: uuid.UUID, user: User) -> None:
    """
    Soft-deletes a claim.
    Owners may only delete active PENDING claims.
    Admins (role=='ADMIN' or is_superuser) may delete ANY active claim regardless of status.
    Executes an atomic conditional update and distinguishes:
      - 404 Not Found (missing record or already soft-deleted)
      - 409 Conflict (normal owner status conflict)
      - 409 Conflict (defensive unexpected update conflict)
    """
    claim = _get_claim_for_deletion(claim_id, user)
    is_admin = _is_admin_user(user)

    # Normal owners cannot delete claims once analysis has started/completed/failed
    if not is_admin and claim.status != ClaimStatus.PENDING:
        raise HttpError(409, "Cannot delete analyzed claim")

    now = timezone.now()
    if is_admin:
        updated_count = Claim.objects.filter(
            id=claim.id,
            is_deleted=False,
        ).update(is_deleted=True, updated_at=now)
    else:
        updated_count = Claim.objects.filter(
            id=claim.id,
            user=user,
            status=ClaimStatus.PENDING,
            is_deleted=False,
        ).update(is_deleted=True, updated_at=now)

    if updated_count == 0:
        # Re-read state to distinguish missing/soft-deleted from status conflict
        try:
            current_claim = Claim.objects.get(id=claim.id)
        except ObjectDoesNotExist:
            raise Http404("Claim not found.")

        if current_claim.is_deleted:
            raise Http404("Claim not found.")

        if not is_admin and current_claim.status != ClaimStatus.PENDING:
            raise HttpError(409, "Cannot delete analyzed claim")

        # Defensive fallback: record exists, is active, and passed status check,
        # but conditional update affected 0 rows (unexpected update conflict).
        raise HttpError(409, "Claim delete conflict. The claim could not be updated.")

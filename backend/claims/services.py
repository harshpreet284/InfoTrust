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


def delete_claim(claim_id: uuid.UUID, user: User) -> None:
    """
    Soft-deletes a claim.
    Owners may only delete PENDING claims.
    Admins may delete ANY claim regardless of status.
    """
    claim = _get_claim_for_mutation(claim_id, user)

    # Normal owners must have PENDING status
    if not user.is_superuser and claim.status != ClaimStatus.PENDING:
        raise HttpError(409, "Cannot delete analyzed claim")

    claim.is_deleted = True
    claim.save(update_fields=['is_deleted', 'updated_at'])

import uuid
from django.core.exceptions import ObjectDoesNotExist
from django.http import Http404
from ninja.errors import AuthorizationError, HttpError

from authentication.models import User
from claims.models import Claim, ClaimStatus
from claims.schemas import ClaimCreateSchema


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


def update_claim(claim_id: uuid.UUID, user: User, payload: ClaimCreateSchema) -> Claim:
    """
    Updates the text of a PENDING claim. Only the owner may update.
    """
    claim = _get_claim_for_mutation(claim_id, user)

    # Admins cannot update claims, only the actual owner
    if claim.user != user:
        raise AuthorizationError(message="You do not have permission to access this claim.")

    if claim.status != ClaimStatus.PENDING:
        raise HttpError(409, "Analysis already started")

    claim.text = payload.claim_text
    claim.save(update_fields=['text', 'updated_at'])
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

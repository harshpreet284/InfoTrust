import uuid
from ninja import Router

from authentication.permissions import RoleAuth
from claims.schemas import ClaimCreateSchema, ClaimSubmitSuccessOut, ClaimDetailSuccessOut
from claims.services import submit_claim
from claims.selectors import get_claim

router = Router(tags=["Claims"])


@router.post("", response={201: ClaimSubmitSuccessOut}, auth=RoleAuth(["USER", "ADMIN"]))
def submit_new_claim(request, payload: ClaimCreateSchema):
    claim = submit_claim(user=request.user, payload=payload)
    return 201, {
        "success": True,
        "message": "Claim submitted successfully.",
        "data": claim,
    }


@router.get("/{claim_id}", response={200: ClaimDetailSuccessOut}, auth=RoleAuth(["USER", "ADMIN"]))
def get_claim_detail(request, claim_id: uuid.UUID):
    claim = get_claim(claim_id=claim_id, user=request.user)
    return 200, {
        "success": True,
        "message": "Claim retrieved successfully.",
        "data": claim,
    }

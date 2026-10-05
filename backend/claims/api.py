from ninja import Router

from authentication.permissions import RoleAuth
from claims.schemas import ClaimCreateSchema, ClaimSubmitSuccessOut
from claims.services import submit_claim

router = Router(tags=["Claims"])


@router.post("", response={201: ClaimSubmitSuccessOut}, auth=RoleAuth(["USER", "ADMIN"]))
def submit_new_claim(request, payload: ClaimCreateSchema):
    claim = submit_claim(user=request.user, payload=payload)
    return 201, {
        "success": True,
        "message": "Claim submitted successfully.",
        "data": claim,
    }

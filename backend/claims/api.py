from typing import Optional
from urllib.parse import urlencode
import uuid
from ninja import Query, Router

from authentication.permissions import RoleAuth
from claims.schemas import (
    ClaimCreateSchema,
    ClaimSubmitSuccessOut,
    ClaimDetailSuccessOut,
    ClaimHistoryFilterSchema,
    ClaimHistoryPaginationOut,
    ClaimUpdateSchema,
    ClaimUpdateSuccessOut,
)
from claims.services import delete_claim, submit_claim, update_claim
from claims.selectors import get_claim, get_user_claim_history

router = Router(tags=["Claims"])


def _build_history_page_link(request, page_num: int, page_size: int, ordering: Optional[str]) -> str:
    path = request.path if hasattr(request, "path") else "/api/v1/claims/history"
    params = {"page": page_num, "page_size": page_size}
    if ordering:
        params["ordering"] = ordering
    return f"{path}?{urlencode(params)}"


@router.post("", response={201: ClaimSubmitSuccessOut}, auth=RoleAuth(["USER", "ADMIN"]))
def submit_new_claim(request, payload: ClaimCreateSchema):
    claim = submit_claim(user=request.user, payload=payload)
    return 201, {
        "success": True,
        "message": "Claim submitted successfully.",
        "data": claim,
    }


@router.get("/history", response={200: ClaimHistoryPaginationOut}, auth=RoleAuth(["USER", "ADMIN"]))
def get_user_claim_history_endpoint(request, filters: Query[ClaimHistoryFilterSchema]):
    qs = get_user_claim_history(user=request.user, ordering=filters.ordering)
    total_count = qs.count()

    offset = (filters.page - 1) * filters.page_size
    claims_page = list(qs[offset : offset + filters.page_size])

    next_link = None
    if (filters.page * filters.page_size) < total_count:
        next_link = _build_history_page_link(request, filters.page + 1, filters.page_size, filters.ordering)

    prev_link = None
    if filters.page > 1:
        prev_link = _build_history_page_link(request, filters.page - 1, filters.page_size, filters.ordering)

    return 200, {
        "count": total_count,
        "next": next_link,
        "previous": prev_link,
        "results": claims_page,
    }


@router.get("/{claim_id}", response={200: ClaimDetailSuccessOut}, auth=RoleAuth(["USER", "ADMIN"]))
def get_claim_detail(request, claim_id: uuid.UUID):
    claim = get_claim(claim_id=claim_id, user=request.user)
    return 200, {
        "success": True,
        "message": "Claim retrieved successfully.",
        "data": claim,
    }


@router.patch("/{claim_id}", response={200: ClaimUpdateSuccessOut}, auth=RoleAuth(["USER", "ADMIN"]))
def update_existing_claim(request, claim_id: uuid.UUID, payload: ClaimUpdateSchema):
    claim = update_claim(claim_id=claim_id, user=request.user, payload=payload)
    return 200, {
        "success": True,
        "message": "Claim updated successfully.",
        "data": {"id": claim.id},
    }


@router.delete("/{claim_id}", response={204: None}, auth=RoleAuth(["USER", "ADMIN"]))
def delete_existing_claim(request, claim_id: uuid.UUID):
    delete_claim(claim_id=claim_id, user=request.user)
    return 204, None

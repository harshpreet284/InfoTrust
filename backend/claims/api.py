from typing import Optional
from urllib.parse import urlencode
import uuid
from django.http import HttpRequest
from ninja import Query, Router
from ninja.errors import HttpError
from ninja_jwt.authentication import JWTAuth

from authentication.permissions import RoleAuth
from shared.pagination import PaginationParamsSchema, paginate_queryset
from claims.schemas import (
    AdminClaimFilterSchema,
    AdminClaimPaginationOut,
    ClaimCreateSchema,
    ClaimSubmitSuccessOut,
    ClaimDetailSuccessOut,
    ClaimHistoryFilterSchema,
    ClaimHistoryPaginationOut,
    ClaimUpdateSchema,
    ClaimUpdateSuccessOut,
)
from claims.services import delete_claim, submit_claim, update_claim
from claims.selectors import get_claim, get_user_claim_history, list_all_claims_for_admin

router = Router(tags=["Claims"])


def _build_history_page_link(
    request,
    page_num: int,
    page_size: int,
    ordering: Optional[str] = None,
    search: Optional[str] = None,
) -> str:
    path = request.path if hasattr(request, "path") else "/api/v1/claims/history"
    params = {"page": page_num, "page_size": page_size}
    if ordering:
        params["ordering"] = ordering
    if search:
        params["search"] = search
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
    qs = get_user_claim_history(user=request.user, ordering=filters.ordering, search=filters.search)
    total_count = qs.count()

    offset = (filters.page - 1) * filters.page_size
    claims_page = list(qs[offset : offset + filters.page_size])

    normalized_search = filters.search.strip() if filters.search and filters.search.strip() else None

    next_link = None
    if (filters.page * filters.page_size) < total_count:
        next_link = _build_history_page_link(
            request, filters.page + 1, filters.page_size, filters.ordering, normalized_search
        )

    prev_link = None
    if filters.page > 1:
        prev_link = _build_history_page_link(
            request, filters.page - 1, filters.page_size, filters.ordering, normalized_search
        )

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


class AdminEndpointAuth(JWTAuth):
    """
    Endpoint-specific authorization for administrative endpoints.
    Allows application admins (role == 'ADMIN') and Django superusers (is_superuser == True).
    Rejects normal users with HTTP 403 PERMISSION_DENIED.
    """
    def authenticate(self, request: HttpRequest, token: str):
        user = super().authenticate(request, token)
        is_admin = getattr(user, "role", None) == "ADMIN" or getattr(user, "is_superuser", False)
        if user and not is_admin:
            raise HttpError(403, "You do not have permission to perform this action.")
        return user


admin_router = Router(tags=["Admin"])


@admin_router.get("/claims", response={200: AdminClaimPaginationOut}, auth=AdminEndpointAuth())
def list_admin_claims_endpoint(request, filters: Query[AdminClaimFilterSchema]):
    qs = list_all_claims_for_admin(search=filters.search)
    normalized_search = filters.search.strip() if filters.search and filters.search.strip() else None
    extra_params = {"search": normalized_search} if normalized_search else None
    total_count, next_link, prev_link, claims_page = paginate_queryset(
        qs=qs,
        page=filters.page,
        page_size=filters.page_size,
        base_path="/api/v1/admin/claims",
        extra_params=extra_params,
    )
    return 200, {
        "count": total_count,
        "next": next_link,
        "previous": prev_link,
        "results": claims_page,
    }

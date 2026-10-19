from typing import Any, Dict, Optional
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
    extra_params: Optional[Dict[str, Any]] = None,
) -> str:
    path = request.path if hasattr(request, "path") else "/api/v1/claims/history"
    params: Dict[str, Any] = {"page": page_num, "page_size": page_size}
    if ordering:
        params["ordering"] = ordering
    if search:
        params["search"] = search
    if extra_params:
        for k, v in extra_params.items():
            if v is not None:
                params[k] = v
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
    qs = get_user_claim_history(
        user=request.user,
        ordering=filters.ordering,
        search=filters.search,
        status=filters.status,
        verdict=filters.verdict,
        date_from=filters.date_from,
        date_to=filters.date_to,
    )
    total_count = qs.count()

    offset = (filters.page - 1) * filters.page_size
    claims_page = list(qs[offset : offset + filters.page_size])

    normalized_search = filters.search.strip() if filters.search and filters.search.strip() else None

    extra_params: Dict[str, Any] = {}
    if filters.status:
        extra_params["status"] = filters.status
    if filters.verdict:
        extra_params["verdict"] = filters.verdict
    if filters.date_from:
        extra_params["date_from"] = filters.date_from.isoformat()
    if filters.date_to:
        extra_params["date_to"] = filters.date_to.isoformat()

    next_link = None
    if (filters.page * filters.page_size) < total_count:
        next_link = _build_history_page_link(
            request,
            filters.page + 1,
            filters.page_size,
            filters.ordering,
            normalized_search,
            extra_params=extra_params if extra_params else None,
        )

    prev_link = None
    if filters.page > 1:
        prev_link = _build_history_page_link(
            request,
            filters.page - 1,
            filters.page_size,
            filters.ordering,
            normalized_search,
            extra_params=extra_params if extra_params else None,
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
    qs = list_all_claims_for_admin(
        search=filters.search,
        status=filters.status,
        verdict=filters.verdict,
        date_from=filters.date_from,
        date_to=filters.date_to,
        user_id=filters.user_id,
    )
    normalized_search = filters.search.strip() if filters.search and filters.search.strip() else None

    extra_params: Dict[str, Any] = {}
    if normalized_search:
        extra_params["search"] = normalized_search
    if filters.status:
        extra_params["status"] = filters.status
    if filters.verdict:
        extra_params["verdict"] = filters.verdict
    if filters.date_from:
        extra_params["date_from"] = filters.date_from.isoformat()
    if filters.date_to:
        extra_params["date_to"] = filters.date_to.isoformat()
    if filters.user_id:
        extra_params["user_id"] = str(filters.user_id)

    total_count, next_link, prev_link, claims_page = paginate_queryset(
        qs=qs,
        page=filters.page,
        page_size=filters.page_size,
        base_path="/api/v1/admin/claims",
        extra_params=extra_params if extra_params else None,
    )
    return 200, {
        "count": total_count,
        "next": next_link,
        "previous": prev_link,
        "results": claims_page,
    }

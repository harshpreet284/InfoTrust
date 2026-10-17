from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlencode

from django.db.models import QuerySet
from ninja import Schema
from pydantic import Field


class PaginationParamsSchema(Schema):
    page: int = Field(1, ge=1, description="Page number (1-based)")
    page_size: int = Field(10, ge=1, le=100, description="Page size (1-100)")


def paginate_queryset(
    qs: QuerySet,
    page: int,
    page_size: int,
    base_path: str,
    extra_params: Optional[Dict[str, Any]] = None,
) -> Tuple[int, Optional[str], Optional[str], List[Any]]:
    """
    Paginates a Django QuerySet using standard 1-based page and page_size.
    Constructs canonical next and previous links preserving any extra query parameters.
    Returns: (total_count, next_link, prev_link, page_items)
    """
    total_count = qs.count()
    offset = (page - 1) * page_size
    page_items = list(qs[offset : offset + page_size])

    next_link = None
    if (page * page_size) < total_count:
        params: Dict[str, Any] = {"page": page + 1, "page_size": page_size}
        if extra_params:
            params.update({k: v for k, v in extra_params.items() if v is not None})
        next_link = f"{base_path}?{urlencode(params)}"

    prev_link = None
    if page > 1:
        params = {"page": page - 1, "page_size": page_size}
        if extra_params:
            params.update({k: v for k, v in extra_params.items() if v is not None})
        prev_link = f"{base_path}?{urlencode(params)}"

    return total_count, next_link, prev_link, page_items

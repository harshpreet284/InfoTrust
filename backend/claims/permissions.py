from typing import Any, Optional
from django.http import HttpRequest
from ninja.errors import HttpError
from ninja_jwt.authentication import JWTAuth


def is_admin_user(user: Optional[Any]) -> bool:
    """
    Canonical helper to check administrator privileges.
    Recognizes application admins (role == 'ADMIN') and Django superusers (is_superuser is True).
    """
    if not user:
        return False
    return getattr(user, "role", None) == "ADMIN" or bool(getattr(user, "is_superuser", False))


class AdminEndpointAuth(JWTAuth):
    """
    Endpoint-specific authorization for administrative endpoints.
    Allows application admins (role == 'ADMIN') and Django superusers (is_superuser == True).
    Rejects normal users with HTTP 403 PERMISSION_DENIED.
    """
    def authenticate(self, request: HttpRequest, token: str):
        user = super().authenticate(request, token)
        if user and not is_admin_user(user):
            raise HttpError(403, "You do not have permission to perform this action.")
        return user

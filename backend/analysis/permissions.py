"""
Analysis API Authentication & Authorization Permissions (AI-013).
Provides JWT Bearer authentication and role-based access control for Analysis endpoints.
"""

from django.http import HttpRequest
from ninja.errors import HttpError
from ninja_jwt.authentication import JWTAuth


class AnalysisEndpointAuth(JWTAuth):
    """
    JWT Bearer authentication for Analysis endpoints.
    Allows authenticated users with role 'USER' or 'ADMIN', as well as Django superusers.
    Rejects unauthenticated requests with HTTP 401 (handled natively by JWTAuth).
    Rejects unauthorized roles with HTTP 403.
    """

    openapi_description = "JWT Bearer authentication. Send token in the 'Authorization: Bearer <token>' header."
    openapi_bearerFormat = "JWT"

    def authenticate(self, request: HttpRequest, token: str):
        # 1. Native JWT validation (InvalidToken/AuthenticationFailed raised for 401)
        user = super().authenticate(request, token)

        # 2. RBAC check: allow USER, ADMIN, or any Django superuser (regardless of role string)
        if user and not (
            getattr(user, "role", None) in ("USER", "ADMIN")
            or bool(getattr(user, "is_superuser", False))
        ):
            raise HttpError(403, "You do not have permission to perform this action.")

        return user

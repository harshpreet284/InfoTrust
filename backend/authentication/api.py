from ninja import Router

from authentication.exceptions import (
    AccountDisabledError,
    DuplicateEmailError,
    InvalidCredentialsError,
    InvalidTokenError,
)
from authentication.permissions import RoleAuth
from authentication.schemas import (
    AuthErrorOut,
    CurrentUserSuccessOut,
    LoginIn,
    LoginSuccessOut,
    LogoutSuccessOut,
    RefreshSuccessOut,
    RefreshTokenIn,
    RegistrationConflictOut,
    RegistrationIn,
    RegistrationSuccessOut,
)
from authentication.services import (
    authenticate_user,
    logout_user,
    refresh_access_token,
    register_user,
)
from shared.schemas import ErrorResponse, RateLimitErrorOut, ServiceUnavailableErrorOut
from shared.throttling import LoginRateThrottle, RegisterRateThrottle

router = Router(tags=["Authentication"])


@router.post(
    "/register",
    response={
        201: RegistrationSuccessOut,
        409: RegistrationConflictOut,
        422: ErrorResponse,
        429: RateLimitErrorOut,
        503: ServiceUnavailableErrorOut,
    },
    throttle=RegisterRateThrottle(),
    summary="Register a new user account",
    description="Registers a new standard user account. Enforces unique email, strong password, and password confirmation.",
    openapi_extra={
        "responses": {
            429: {
                "headers": {
                    "Retry-After": {
                        "description": "Seconds to wait before retrying.",
                        "schema": {"type": "integer"},
                    }
                }
            }
        }
    },
)
def register(request, payload: RegistrationIn):
    try:
        user = register_user(payload)
        return 201, {
            "success": True,
            "message": "Registration successful.",
            "data": user,
        }
    except DuplicateEmailError as e:
        return 409, {
            "success": False,
            "message": "Email already exists.",
            "errors": {"email": [str(e)]},
        }


@router.post(
    "/login",
    response={
        200: LoginSuccessOut,
        401: AuthErrorOut,
        403: AuthErrorOut,
        422: ErrorResponse,
        429: RateLimitErrorOut,
        503: ServiceUnavailableErrorOut,
    },
    throttle=LoginRateThrottle(),
    summary="Authenticate user and obtain JWT tokens",
    description="Authenticates with email and password. Returns an access token, refresh token, and user profile.",
    openapi_extra={
        "responses": {
            429: {
                "headers": {
                    "Retry-After": {
                        "description": "Seconds to wait before retrying.",
                        "schema": {"type": "integer"},
                    }
                }
            }
        }
    },
)
def login(request, payload: LoginIn):
    try:
        result = authenticate_user(payload)
        return 200, {"success": True, "message": "Login successful.", "data": result}
    except InvalidCredentialsError as e:
        return 401, {"success": False, "message": str(e)}
    except AccountDisabledError as e:
        return 403, {"success": False, "message": str(e)}


@router.post(
    "/refresh",
    response={
        200: RefreshSuccessOut,
        401: AuthErrorOut,
        422: ErrorResponse,
    },
    summary="Refresh access token",
    description="Exchanges a valid refresh token for a new access token and rotated refresh token.",
)
def refresh(request, payload: RefreshTokenIn):
    try:
        result = refresh_access_token(payload)
        return 200, {
            "success": True,
            "message": "Token refreshed successfully.",
            "data": result,
        }
    except InvalidTokenError as e:
        return 401, {"success": False, "message": str(e)}


@router.post(
    "/logout",
    response={
        200: LogoutSuccessOut,
        401: AuthErrorOut,
        422: ErrorResponse,
    },
    summary="Logout user",
    description="Blacklists the provided refresh token and terminates the session.",
)
def logout(request, payload: RefreshTokenIn):
    try:
        logout_user(payload)
        return 200, {"success": True, "message": "Logged out successfully.", "data": {}}
    except InvalidTokenError as e:
        return 401, {"success": False, "message": str(e)}


@router.get(
    "/me",
    response={
        200: CurrentUserSuccessOut,
        401: ErrorResponse,
        403: ErrorResponse,
    },
    auth=RoleAuth(["USER", "ADMIN"]),
    summary="Retrieve current user profile",
    description="Returns the profile information of the currently authenticated user.",
)
def get_current_user(request):
    return 200, {
        "success": True,
        "message": "User profile retrieved successfully.",
        "data": request.user,
    }

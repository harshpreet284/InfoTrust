from ninja import Router

from authentication.exceptions import (
    AccountDisabledError,
    DuplicateEmailError,
    InvalidCredentialsError,
    InvalidTokenError,
)
from authentication.permissions import RoleAuth
from authentication.schemas import (
    CurrentUserSuccessOut,
    LoginIn,
    LoginSuccessOut,
    LogoutSuccessOut,
    RefreshSuccessOut,
    RefreshTokenIn,
    RegistrationIn,
    RegistrationSuccessOut,
)
from authentication.services import (
    authenticate_user,
    logout_user,
    refresh_access_token,
    register_user,
)

# Minimal router for the authentication app
router = Router()


@router.post("/register", response={201: RegistrationSuccessOut, 409: dict})
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


@router.post("/login", response={200: LoginSuccessOut, 401: dict, 403: dict})
def login(request, payload: LoginIn):
    try:
        result = authenticate_user(payload)
        return 200, {"success": True, "message": "Login successful.", "data": result}
    except InvalidCredentialsError as e:
        return 401, {"success": False, "message": str(e)}
    except AccountDisabledError as e:
        return 403, {"success": False, "message": str(e)}


@router.post("/refresh", response={200: RefreshSuccessOut, 401: dict})
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


@router.post("/logout", response={200: LogoutSuccessOut, 401: dict})
def logout(request, payload: RefreshTokenIn):
    try:
        logout_user(payload)
        return 200, {"success": True, "message": "Logged out successfully.", "data": {}}
    except InvalidTokenError as e:
        return 401, {"success": False, "message": str(e)}


@router.get(
    "/me", response={200: CurrentUserSuccessOut}, auth=RoleAuth(["USER", "ADMIN"])
)
def get_current_user(request):
    return 200, {
        "success": True,
        "message": "User profile retrieved successfully.",
        "data": request.user,
    }

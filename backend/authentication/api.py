from ninja import Router
from authentication.schemas import RegistrationIn, RegistrationSuccessOut, LoginIn, LoginSuccessOut, RefreshTokenIn, RefreshSuccessOut
from authentication.services import register_user, authenticate_user, refresh_access_token
from authentication.exceptions import DuplicateEmailError, InvalidCredentialsError, AccountDisabledError, InvalidTokenError

# Minimal router for the authentication app
router = Router()

@router.post("/register", response={201: RegistrationSuccessOut, 409: dict})
def register(request, payload: RegistrationIn):
    try:
        user = register_user(payload)
        return 201, {"success": True, "message": "Registration successful.", "data": user}
    except DuplicateEmailError as e:
        return 409, {
            "success": False,
            "message": "Email already exists.",
            "errors": {"email": [str(e)]}
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
        return 200, {"success": True, "message": "Token refreshed successfully.", "data": result}
    except InvalidTokenError as e:
        return 401, {"success": False, "message": str(e)}

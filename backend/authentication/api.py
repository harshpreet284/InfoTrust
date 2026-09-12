from ninja import Router
from authentication.schemas import RegistrationIn, RegistrationSuccessOut, LoginIn, LoginSuccessOut
from authentication.services import register_user, authenticate_user
from authentication.exceptions import DuplicateEmailError, InvalidCredentialsError, AccountDisabledError

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

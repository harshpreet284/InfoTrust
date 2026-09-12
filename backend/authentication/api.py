from ninja import Router
from authentication.schemas import RegistrationIn, RegistrationSuccessOut
from authentication.services import register_user
from authentication.exceptions import DuplicateEmailError

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

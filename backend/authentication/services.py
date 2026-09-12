from django.db import transaction, IntegrityError
from authentication.models import User
from authentication.schemas import RegistrationIn, LoginIn
from authentication.exceptions import DuplicateEmailError, InvalidCredentialsError, AccountDisabledError
from ninja_jwt.tokens import RefreshToken

def register_user(payload: RegistrationIn) -> User:
    """
    Registers a new user given a validated RegistrationIn payload.
    Enforces email uniqueness and defaults role to USER.
    """
    # 1. Pre-check for clean failure without transaction rollback overhead
    if User.objects.filter(email=payload.email).exists():
        raise DuplicateEmailError("This email is already registered.")

    # 2. Concurrency-safe creation
    try:
        with transaction.atomic():
            user = User.objects.create_user(
                email=payload.email,
                full_name=payload.full_name,
                password=payload.password
            )
            return user
    except IntegrityError as e:
        error_msg = str(e).lower()
        # Differentiate uniqueness violation from other DB constraints portably
        if 'unique' in error_msg and 'email' in error_msg:
            raise DuplicateEmailError("This email is already registered.")
        
        # If the IntegrityError was caused by something else, escalate it normally
        raise

def authenticate_user(payload: LoginIn) -> dict:
    """
    Authenticates a user from a validated LoginIn payload.
    Returns a dictionary containing access_token, refresh_token, and user.
    Raises InvalidCredentialsError for wrong email/password.
    Raises AccountDisabledError for correct credentials but inactive account.
    """
    user = User.objects.filter(email=payload.email).first()
    
    if user is None:
        # Dummy hash calculation to mitigate timing attacks on missing emails
        User().set_password(payload.password)
        raise InvalidCredentialsError("Invalid email or password.")
        
    if not user.check_password(payload.password):
        raise InvalidCredentialsError("Invalid email or password.")
        
    if not user.is_active:
        raise AccountDisabledError("This account has been disabled.")
        
    refresh = RefreshToken.for_user(user)
    
    return {
        "access_token": str(refresh.access_token),
        "refresh_token": str(refresh),
        "user": user
    }

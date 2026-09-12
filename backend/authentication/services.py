from django.db import transaction, IntegrityError
from authentication.models import User
from authentication.schemas import RegistrationIn, LoginIn, RefreshTokenIn
from authentication.exceptions import DuplicateEmailError, InvalidCredentialsError, AccountDisabledError, InvalidTokenError
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

def refresh_access_token(payload: RefreshTokenIn) -> dict:
    """
    Validates a refresh token and returns a new access token and rotated refresh token
    using the native django-ninja-jwt validation mechanism.
    """
    from ninja_jwt.schema import TokenRefreshInputSchema
    from ninja_jwt.exceptions import InvalidToken

    try:
        ninja_payload = TokenRefreshInputSchema(refresh=payload.refresh_token)
        output_schema = ninja_payload.to_response_schema()
    except InvalidToken:
        raise InvalidTokenError("Invalid or expired refresh token.")
        
    return {
        "access_token": output_schema.access,
        "refresh_token": output_schema.refresh
    }

def logout_user(payload: RefreshTokenIn) -> None:
    """
    Validates a refresh token and blacklists it, invalidating future refresh attempts.
    """
    from ninja_jwt.schema import TokenBlacklistInputSchema
    from ninja_jwt.exceptions import InvalidToken

    try:
        TokenBlacklistInputSchema(refresh=payload.refresh_token)
    except InvalidToken:
        raise InvalidTokenError("Invalid or expired refresh token.")

from django.db import transaction, IntegrityError
from authentication.models import User
from authentication.schemas import RegistrationIn
from authentication.exceptions import DuplicateEmailError

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

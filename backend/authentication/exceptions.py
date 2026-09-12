class DuplicateEmailError(Exception):
    """Raised when a user attempts to register with an email that already exists."""
    pass

class InvalidCredentialsError(Exception):
    """Raised when authentication fails due to invalid email or password."""
    pass

class AccountDisabledError(Exception):
    """Raised when a user authenticates successfully but their account is inactive."""
    pass

class InvalidTokenError(Exception):
    """Raised when a refresh token is invalid, expired, or blacklisted."""
    pass

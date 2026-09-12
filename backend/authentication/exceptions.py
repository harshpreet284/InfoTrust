class DuplicateEmailError(Exception):
    """Raised when a user attempts to register with an email that already exists."""
    pass

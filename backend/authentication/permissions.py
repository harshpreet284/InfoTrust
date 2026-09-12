from typing import List
from ninja_jwt.authentication import JWTAuth
from ninja.errors import HttpError
from django.http import HttpRequest

class RoleAuth(JWTAuth):
    def __init__(self, allowed_roles: List[str]):
        super().__init__()
        self.allowed_roles = allowed_roles

    def authenticate(self, request: HttpRequest, token: str):
        # 1. Native validation (InvalidToken/AuthenticationFailed raised automatically for 401)
        user = super().authenticate(request, token)
        
        # 2. RBAC check
        if user and user.role not in self.allowed_roles:
            raise HttpError(403, "You do not have permission to perform this action.")
            
        return user

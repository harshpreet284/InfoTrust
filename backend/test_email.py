from pydantic import BaseModel, EmailStr
class A(BaseModel):
    email: EmailStr
A(email='test@example.com')

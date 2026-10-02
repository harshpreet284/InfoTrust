from analysis.models import Analysis
from claims.models import Claim
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

User = get_user_model()
u = User.objects.first()
if not u:
    u = User.objects.create_user(email="scratch2@test.com", password="pwd", full_name="Scratch")
c = Claim.objects.first()
if not c:
    c = Claim.objects.create(user=u, text="1234567890")

a = Analysis(claim=c, model_confidence=1.1)
try:
    a.full_clean()
    print("SUCCESS: full_clean() passed, no validation error raised for model_confidence!")
except ValidationError as e:
    print(f"VALIDATION_ERROR: {e.message_dict}")

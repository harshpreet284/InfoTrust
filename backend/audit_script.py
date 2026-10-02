import sys
from claims.models import Claim
from analysis.models import Analysis, Verdict

# 1. Claims with text length < 10
from django.db.models.functions import Length
invalid_claims = Claim.objects.annotate(text_len=Length('text')).filter(text_len__lt=10)
if invalid_claims.exists():
    print(f"AUDIT FAILED: Found {invalid_claims.count()} claims with text length < 10.")
    for c in invalid_claims:
        print(f" - Claim ID: {c.id}, Text: '{c.text}'")
    sys.exit(1)

# 2. Analyses with verdict outside allowed values
allowed_verdicts = [v[0] for v in Verdict.choices]
invalid_verdicts = Analysis.objects.exclude(verdict__in=allowed_verdicts).exclude(verdict__isnull=True)
if invalid_verdicts.exists():
    print(f"AUDIT FAILED: Found {invalid_verdicts.count()} analyses with invalid verdict.")
    sys.exit(1)

# 3. Analyses with credibility_score < 0 or > 100
invalid_cred = Analysis.objects.filter(credibility_score__lt=0) | Analysis.objects.filter(credibility_score__gt=100)
if invalid_cred.exists():
    print(f"AUDIT FAILED: Found {invalid_cred.count()} analyses with invalid credibility_score.")
    sys.exit(1)

# 4. Analyses with final_weighted_score < 0 or > 100
invalid_weighted = Analysis.objects.filter(final_weighted_score__lt=0) | Analysis.objects.filter(final_weighted_score__gt=100)
if invalid_weighted.exists():
    print(f"AUDIT FAILED: Found {invalid_weighted.count()} analyses with invalid final_weighted_score.")
    sys.exit(1)

# 5. Analyses with model_confidence < 0 or > 1
invalid_conf = Analysis.objects.filter(model_confidence__lt=0) | Analysis.objects.filter(model_confidence__gt=1)
if invalid_conf.exists():
    print(f"AUDIT FAILED: Found {invalid_conf.count()} analyses with invalid model_confidence.")
    sys.exit(1)

print("AUDIT SUCCESS: No violating records found.")

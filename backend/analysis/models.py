from django.db import models
from claims.models import Claim

class Verdict(models.TextChoices):
    CREDIBLE = 'CREDIBLE', 'Credible'
    UNCERTAIN = 'UNCERTAIN', 'Uncertain'
    MISINFORMATION = 'MISINFORMATION', 'Misinformation'

class ModelPrediction(models.TextChoices):
    CREDIBLE = 'CREDIBLE', 'Credible'
    MISINFORMATION = 'MISINFORMATION', 'Misinformation'

class Analysis(models.Model):
    # Using the OneToOneField as the primary key to share the Claim's UUID.
    # This is a standard Django best practice for 1-to-1 extension models.
    claim = models.OneToOneField(
        Claim,
        on_delete=models.CASCADE,
        primary_key=True,
        related_name='analysis'
    )
    
    # Nullable because analysis might fail or be created before processing is fully complete.
    credibility_score = models.FloatField(null=True, blank=True)
    verdict = models.CharField(max_length=20, choices=Verdict.choices, null=True, blank=True)
    
    # Store explainability details as JSON
    explainability_json = models.JSONField(default=dict, blank=True)
    
    # Raw ML model outputs
    model_prediction = models.CharField(max_length=20, choices=ModelPrediction.choices, null=True, blank=True)
    model_confidence = models.FloatField(null=True, blank=True)
    
    # Hybrid Credibility Engine Fields
    fact_check_summary = models.TextField(null=True, blank=True)
    fact_check_match_count = models.IntegerField(null=True, blank=True)
    narrative_match_count = models.IntegerField(null=True, blank=True)
    highest_similarity_score = models.FloatField(null=True, blank=True)
    rule_based_flags = models.JSONField(default=dict, blank=True)
    final_weighted_score = models.FloatField(null=True, blank=True)

    analysis_timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Analysis for Claim {self.claim_id}"

import uuid
from django.db import models
from django.conf import settings

class ClaimStatus(models.TextChoices):
    PENDING = 'PENDING', 'Pending'
    PROCESSING = 'PROCESSING', 'Processing'
    COMPLETED = 'COMPLETED', 'Completed'
    FAILED = 'FAILED', 'Failed'

class Claim(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='claims'
    )
    text = models.TextField()
    status = models.CharField(
        max_length=20,
        choices=ClaimStatus.choices,
        default=ClaimStatus.PENDING
    )
    submitted_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['submitted_at'], name='claim_submitted_at_idx'),
        ]

    def __str__(self):
        return f"{self.id} - {self.status}"

class FeedbackType(models.TextChoices):
    HELPFUL = 'HELPFUL', 'Helpful'
    NOT_HELPFUL = 'NOT_HELPFUL', 'Not Helpful'

class ClaimFeedback(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='claim_feedback'
    )
    claim = models.ForeignKey(
        Claim,
        on_delete=models.CASCADE,
        related_name='feedback'
    )
    feedback_type = models.CharField(
        max_length=20,
        choices=FeedbackType.choices
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'claim'],
                name='unique_user_claim_feedback'
            )
        ]

    def __str__(self):
        return f"Feedback by {self.user_id} on Claim {self.claim_id}: {self.feedback_type}"

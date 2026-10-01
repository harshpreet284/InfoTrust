from django.contrib import admin
from .models import Claim, ClaimFeedback

@admin.register(Claim)
class ClaimAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'status', 'submitted_at')
    list_filter = ('status', 'submitted_at')
    search_fields = ('id', 'text', 'user__email')
    readonly_fields = ('id', 'submitted_at', 'updated_at')

@admin.register(ClaimFeedback)
class ClaimFeedbackAdmin(admin.ModelAdmin):
    list_display = ('user', 'claim', 'feedback_type')
    list_filter = ('feedback_type',)
    search_fields = ('user__email', 'claim__id')
    readonly_fields = ('user', 'claim')

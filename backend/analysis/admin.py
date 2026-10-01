from django.contrib import admin
from .models import Analysis

@admin.register(Analysis)
class AnalysisAdmin(admin.ModelAdmin):
    list_display = ('claim', 'verdict', 'credibility_score', 'final_weighted_score', 'analysis_timestamp')
    list_filter = ('verdict', 'model_prediction', 'analysis_timestamp')
    search_fields = ('claim__id', 'fact_check_summary')
    readonly_fields = ('claim', 'analysis_timestamp')

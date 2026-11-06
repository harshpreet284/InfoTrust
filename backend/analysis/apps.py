from django.apps import AppConfig


class AnalysisConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "analysis"

    def ready(self) -> None:
        # Register system checks with Django's check framework
        import analysis.checks  # noqa: F401

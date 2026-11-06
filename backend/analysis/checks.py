"""
Django system checks for model artifact availability and integrity (AI-017).
Registered under the dedicated 'model_artifacts' tag.
"""

from typing import Any, List, Optional

from django.conf import settings
from django.core.checks import Error, Warning, register

from analysis.model_loader.loader import (
    ModelArtifactCorruptedError,
    ModelArtifactNotFoundError,
    ModelLoadingError,
    validate_model_availability,
)


@register("model_artifacts")
def check_model_artifacts(
    app_configs: Optional[Any] = None,
    **kwargs: Any,
) -> List[Any]:
    """
    Validates model artifact availability without loading model weights into memory.
    Bypassed during database management commands (e.g. migrate) via kwargs['databases'].
    """
    # 1. Skip check during migration management commands
    if kwargs.get("databases") is not None:
        return []
    import sys

    if any(
        cmd in sys.argv
        for cmd in ("makemigrations", "migrate", "showmigrations", "sqlmigrate")
    ):
        return []

    # 2. Check startup validation configuration
    check_enabled = getattr(settings, "MODEL_STARTUP_CHECK_ENABLED", True)
    env = getattr(settings, "INFOTRUST_ENV", "production").strip().lower()

    if not check_enabled:
        if env in ("development", "test", "local"):
            return [
                Warning(
                    "Model artifact validation is disabled via MODEL_STARTUP_CHECK_ENABLED=False.",
                    hint="Model availability will only be validated lazily on first inference.",
                    id="analysis.W001",
                )
            ]
        # In production/staging, settings/base.py prevents this, but fail-closed check here as safeguard
        return [
            Error(
                "MODEL_STARTUP_CHECK_ENABLED cannot be disabled in production/staging environments.",
                id="analysis.E002",
            )
        ]

    # 3. Perform weight-free availability validation
    try:
        validate_model_availability()
    except (
        ModelArtifactNotFoundError,
        ModelArtifactCorruptedError,
        ModelLoadingError,
    ) as exc:
        return [
            Error(
                f"Model artifact preflight validation failed: {exc}",
                hint="Verify that MODEL_ARTIFACT_PATH points to a valid artifact directory with required files.",
                id="analysis.E001",
            )
        ]
    except Exception as exc:
        return [
            Error(
                f"Unexpected error during model artifact preflight validation: {exc}",
                id="analysis.E001",
            )
        ]

    return []

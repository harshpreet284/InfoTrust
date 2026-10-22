from typing import Any, Dict, Optional
from django.contrib.auth import get_user_model
from audit.models import AuditLog

User = get_user_model()


def log_audit_event(
    *,
    action: str,
    user: Optional[Any] = None,
    target: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> AuditLog:
    """
    Creates and persists an AuditLog entry.
    Ensures safe defaults and consistent structure.
    """
    return AuditLog.objects.create(
        user=user,
        action=action,
        target=target,
        metadata=metadata if metadata is not None else {},
    )

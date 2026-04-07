"""Audit logging service."""

import logging
from sqlalchemy.ext.asyncio import AsyncSession
from app.domain.models.network import AuditLog

logger = logging.getLogger(__name__)


async def log_action(
    session: AsyncSession,
    action: str,
    entity_type: str,
    entity_id: str | None = None,
    entity_name: str | None = None,
    details: str | None = None,
    user_id: str | None = None,
):
    """Record an action in the audit log."""
    entry = AuditLog(
        user_id=user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        entity_name=entity_name,
        details=details,
    )
    session.add(entry)
    logger.info(f"AUDIT: {action} {entity_type} {entity_name or entity_id} by {user_id}")

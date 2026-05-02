import json

from sqlalchemy.ext.asyncio import AsyncSession

from cli_any_app.models.audit_event import AuditEvent


async def record_audit_event(
    db: AsyncSession,
    event_type: str,
    *,
    session_id: str | None = None,
    actor: str = "local-admin",
    reason: str | None = None,
    metadata: dict | None = None,
) -> None:
    db.add(
        AuditEvent(
            event_type=event_type,
            actor=actor,
            session_id=session_id,
            reason=reason,
            metadata_json=json.dumps(metadata or {}, sort_keys=True),
        )
    )

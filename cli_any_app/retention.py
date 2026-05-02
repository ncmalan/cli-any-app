from __future__ import annotations

from datetime import datetime, timezone, timedelta

from sqlalchemy import select

from cli_any_app.audit import record_audit_event
from cli_any_app.models.database import get_session
from cli_any_app.models.session import Session


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


async def purge_expired_sessions(now: datetime | None = None, *, limit: int | None = None) -> dict:
    """Hard-delete sessions older than each session's retention period."""
    now = now or datetime.now(timezone.utc)
    purged: list[str] = []
    async with get_session() as db:
        query = (
            select(Session)
            .where(Session.created_at <= now)
            .order_by(Session.created_at)
        )
        result = await db.execute(query)
        for session in result.scalars():
            retention_days = max(session.retention_days or 0, 0)
            expires_at = _as_utc(session.created_at) + timedelta(days=retention_days)
            if expires_at > now:
                continue
            await record_audit_event(
                db,
                "session.purged",
                session_id=session.id,
                reason="retention_expired",
                metadata={
                    "retention_days": retention_days,
                    "created_at": session.created_at.isoformat(),
                    "expires_at": expires_at.isoformat(),
                },
            )
            purged.append(session.id)
            await db.delete(session)
            if limit is not None and len(purged) >= limit:
                break
        await db.commit()
    return {"purged": len(purged), "session_ids": purged}

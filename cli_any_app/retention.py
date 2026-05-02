from __future__ import annotations

from datetime import datetime, timezone, timedelta

from sqlalchemy import and_, or_, select

from cli_any_app.audit import record_audit_event
from cli_any_app.models.database import get_session
from cli_any_app.models.session import Session


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _normalized_retention_days(value: int | None) -> int:
    return max(value or 0, 0)


async def _expired_session_predicate(db, now: datetime):
    result = await db.execute(select(Session.retention_days).distinct())
    retention_values = sorted({_normalized_retention_days(value) for value in result.scalars()})
    predicates = []
    for retention_days in retention_values:
        cutoff = now - timedelta(days=retention_days)
        if retention_days == 0:
            retention_predicate = or_(Session.retention_days <= 0, Session.retention_days.is_(None))
        else:
            retention_predicate = Session.retention_days == retention_days
        predicates.append(and_(retention_predicate, Session.created_at <= cutoff))
    return or_(*predicates) if predicates else None


async def purge_expired_sessions(now: datetime | None = None, *, limit: int | None = None) -> dict:
    """Hard-delete sessions older than each session's retention period."""
    now = now or datetime.now(timezone.utc)
    if limit is not None and limit <= 0:
        return {"purged": 0, "session_ids": []}

    purged: list[str] = []
    async with get_session() as db:
        expired_predicate = await _expired_session_predicate(db, now)
        if expired_predicate is None:
            return {"purged": 0, "session_ids": []}
        query = (
            select(Session)
            .where(expired_predicate)
            .order_by(Session.created_at)
        )
        if limit is not None:
            query = query.limit(limit)
        result = await db.execute(query)
        for session in result.scalars():
            retention_days = _normalized_retention_days(session.retention_days)
            expires_at = _as_utc(session.created_at) + timedelta(days=retention_days)
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
        await db.commit()
    return {"purged": len(purged), "session_ids": purged}

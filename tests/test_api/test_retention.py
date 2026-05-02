from datetime import datetime, timezone, timedelta

import pytest
from sqlalchemy import select


@pytest.fixture(autouse=True)
async def setup_db(tmp_path):
    from cli_any_app.models.database import init_db

    await init_db(f"sqlite+aiosqlite:///{tmp_path}/test.db")
    yield


async def test_purge_expired_sessions_removes_old_data_and_audits():
    from cli_any_app.models.audit_event import AuditEvent
    from cli_any_app.models.database import get_session
    from cli_any_app.models.flow import Flow
    from cli_any_app.models.request import CapturedRequest
    from cli_any_app.models.session import Session
    from cli_any_app.retention import purge_expired_sessions

    now = datetime.now(timezone.utc)
    async with get_session() as db:
        old = Session(
            name="Old",
            app_name="app",
            retention_days=1,
            created_at=now - timedelta(days=3),
            updated_at=now - timedelta(days=3),
        )
        new = Session(
            name="New",
            app_name="app",
            retention_days=30,
            created_at=now,
            updated_at=now,
        )
        old_not_expired = Session(
            name="Old but retained",
            app_name="app",
            retention_days=30,
            created_at=now - timedelta(days=3),
            updated_at=now - timedelta(days=3),
        )
        db.add_all([old, new, old_not_expired])
        await db.flush()
        flow = Flow(session_id=old.id, label="old-flow", order=1)
        db.add(flow)
        await db.flush()
        db.add(CapturedRequest(flow_id=flow.id, method="GET", url="https://api.example.com", status_code=200))
        await db.commit()
        old_id = old.id
        new_id = new.id
        old_not_expired_id = old_not_expired.id

    result = await purge_expired_sessions(now=now)
    assert result["purged"] == 1
    assert result["session_ids"] == [old_id]

    async with get_session() as db:
        assert await db.get(Session, old_id) is None
        assert await db.get(Session, new_id) is not None
        assert await db.get(Session, old_not_expired_id) is not None
        events = await db.execute(select(AuditEvent).where(AuditEvent.event_type == "session.purged"))
        audit = events.scalar_one()
        assert audit.session_id == old_id


async def test_purge_expired_sessions_limits_expired_query():
    from cli_any_app.models.database import get_session
    from cli_any_app.models.session import Session
    from cli_any_app.retention import purge_expired_sessions

    now = datetime.now(timezone.utc)
    async with get_session() as db:
        expired_first = Session(
            name="Expired first",
            app_name="app",
            retention_days=1,
            created_at=now - timedelta(days=5),
            updated_at=now - timedelta(days=5),
        )
        expired_second = Session(
            name="Expired second",
            app_name="app",
            retention_days=1,
            created_at=now - timedelta(days=4),
            updated_at=now - timedelta(days=4),
        )
        old_not_expired = Session(
            name="Old but retained",
            app_name="app",
            retention_days=30,
            created_at=now - timedelta(days=3),
            updated_at=now - timedelta(days=3),
        )
        db.add_all([expired_first, expired_second, old_not_expired])
        await db.commit()
        expired_first_id = expired_first.id
        expired_second_id = expired_second.id
        old_not_expired_id = old_not_expired.id

    result = await purge_expired_sessions(now=now, limit=1)
    assert result == {"purged": 1, "session_ids": [expired_first_id]}

    async with get_session() as db:
        assert await db.get(Session, expired_first_id) is None
        assert await db.get(Session, expired_second_id) is not None
        assert await db.get(Session, old_not_expired_id) is not None


async def test_purge_expired_sessions_zero_limit_skips_delete():
    from cli_any_app.models.database import get_session
    from cli_any_app.models.session import Session
    from cli_any_app.retention import purge_expired_sessions

    now = datetime.now(timezone.utc)
    async with get_session() as db:
        expired = Session(
            name="Expired",
            app_name="app",
            retention_days=1,
            created_at=now - timedelta(days=5),
            updated_at=now - timedelta(days=5),
        )
        db.add(expired)
        await db.commit()
        expired_id = expired.id

    result = await purge_expired_sessions(now=now, limit=0)
    assert result == {"purged": 0, "session_ids": []}

    async with get_session() as db:
        assert await db.get(Session, expired_id) is not None

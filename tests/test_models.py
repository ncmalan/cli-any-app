import json
from datetime import datetime, timezone, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from cli_any_app.models.database import get_session, init_db
from cli_any_app.models.session import Session
from cli_any_app.models.flow import Flow
from cli_any_app.models.request import CapturedRequest


@pytest.fixture(autouse=True)
async def setup_db(tmp_path):
    await init_db(f"sqlite+aiosqlite:///{tmp_path}/test.db")
    yield


@pytest.mark.asyncio
async def test_create_session_with_flows_and_requests(setup_db):
    async with get_session() as db:
        session = Session(name="Test Session", app_name="test-app")
        db.add(session)
        await db.flush()

        flow = Flow(session_id=session.id, label="login", order=0)
        db.add(flow)
        await db.flush()

        req = CapturedRequest(
            flow_id=flow.id,
            method="POST",
            url="https://api.example.com/auth/login",
            request_headers=json.dumps({"Content-Type": "application/json"}),
            request_body='{"email":"test@test.com"}',
            status_code=200,
            response_headers=json.dumps({"Content-Type": "application/json"}),
            response_body='{"token":"abc123"}',
            content_type="application/json",
            is_api=True,
        )
        db.add(req)
        await db.commit()

    async with get_session() as db:
        result = await db.execute(select(Session))
        s = result.scalar_one()
        assert s.name == "Test Session"
        assert s.app_name == "test-app"
        assert s.status == "created"


@pytest.mark.asyncio
async def test_flow_request_relationship_orders_without_string_eval(setup_db):
    async with get_session() as db:
        session = Session(name="Ordered", app_name="test-app")
        db.add(session)
        await db.flush()
        flow = Flow(session_id=session.id, label="lookup", order=1)
        db.add(flow)
        await db.flush()
        later = datetime.now(timezone.utc)
        earlier = later - timedelta(seconds=1)
        db.add_all([
            CapturedRequest(
                id="req-b",
                flow_id=flow.id,
                method="GET",
                url="https://api.example.com/later",
                status_code=200,
                timestamp=later,
            ),
            CapturedRequest(
                id="req-a",
                flow_id=flow.id,
                method="GET",
                url="https://api.example.com/earlier",
                status_code=200,
                timestamp=earlier,
            ),
        ])
        await db.commit()
        flow_id = flow.id

    async with get_session() as db:
        result = await db.execute(
            select(Flow).options(selectinload(Flow.requests)).where(Flow.id == flow_id)
        )
        loaded = result.scalar_one()
        assert [request.url for request in loaded.requests] == [
            "https://api.example.com/earlier",
            "https://api.example.com/later",
        ]

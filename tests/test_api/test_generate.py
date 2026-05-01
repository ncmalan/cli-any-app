from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from cli_any_app.api.generate import _run_generation
from cli_any_app.models.audit_event import AuditEvent
from cli_any_app.models.generated_cli import GeneratedCLI
from cli_any_app.models.generation_attempt import GenerationAttempt
from cli_any_app.models.session import Session


@pytest.fixture(autouse=True)
async def setup_db(tmp_path):
    from cli_any_app.models.database import init_db
    from cli_any_app.api.domains import _domain_filters

    await init_db(f"sqlite+aiosqlite:///{tmp_path}/test.db")
    _domain_filters.clear()
    yield


@pytest.fixture
async def client():
    from cli_any_app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_start_generation_respects_disabled_domains(client):
    from cli_any_app.models.database import get_session
    from cli_any_app.models.request import CapturedRequest

    resp = await client.post("/api/sessions", json={"name": "Test", "app_name": "test-app"})
    session_id = resp.json()["id"]

    resp = await client.post(f"/api/sessions/{session_id}/flows", json={"label": "Flow 1"})
    flow_id = resp.json()["id"]

    async with get_session() as db:
        db.add_all([
            CapturedRequest(
                flow_id=flow_id,
                method="GET",
                url="https://api.good.com/users",
                status_code=200,
                request_headers="{}",
                response_headers="{}",
                content_type="application/json",
                is_api=True,
            ),
            CapturedRequest(
                flow_id=flow_id,
                method="GET",
                url="https://api.bad.com/users",
                status_code=200,
                request_headers="{}",
                response_headers="{}",
                content_type="application/json",
                is_api=True,
            ),
        ])
        await db.commit()

    resp = await client.put(f"/api/sessions/{session_id}/domains/api.bad.com", json={"enabled": False})
    assert resp.status_code == 200

    mock_run_pipeline = AsyncMock(return_value={
        "status": "success",
        "api_spec": {"app_name": "test-app"},
        "package_path": "",
        "validation": {"valid": True, "errors": [], "warnings": []},
    })

    with patch("cli_any_app.api.generate.run_pipeline", mock_run_pipeline):
        resp = await client.post(f"/api/sessions/{session_id}/generate")

    assert resp.status_code == 200
    assert mock_run_pipeline.await_count == 1

    session_data = mock_run_pipeline.await_args.args[0]
    assert len(session_data["flows"]) == 1
    assert [request["url"] for request in session_data["flows"][0]["requests"]] == [
        "https://api.good.com/users"
    ]


async def test_run_generation_upserts_generated_cli(tmp_path):
    from cli_any_app.models.database import get_session

    async with get_session() as db:
        session = Session(name="Test", app_name="test-app")
        db.add(session)
        await db.commit()
        await db.refresh(session)
        session_id = session.id

    first_package = tmp_path / "pkg-1"
    second_package = tmp_path / "pkg-2"
    first_package.mkdir()
    second_package.mkdir()
    (first_package / "SKILL.md").write_text("first")
    (second_package / "SKILL.md").write_text("second")

    mock_run_pipeline = AsyncMock(side_effect=[
        {
            "status": "success",
            "api_spec": {"app_name": "test-app", "version": 1},
            "package_path": str(first_package),
            "validation": {"valid": True, "errors": [], "warnings": []},
        },
        {
            "status": "success",
            "api_spec": {"app_name": "test-app", "version": 2},
            "package_path": str(second_package),
            "validation": {"valid": True, "errors": [], "warnings": []},
        },
    ])

    with patch("cli_any_app.api.generate.run_pipeline", mock_run_pipeline):
        await _run_generation(session_id, {"app_name": "test-app", "flows": []})
        await _run_generation(session_id, {"app_name": "test-app", "flows": []})

    async with get_session() as db:
        result = await db.execute(select(GeneratedCLI).where(GeneratedCLI.session_id == session_id))
        generated = result.scalars().all()
        assert len(generated) == 1
        assert generated[0].package_path == str(second_package)
        assert generated[0].skill_md == "second"

        session = await db.get(Session, session_id)
        assert session is not None
        assert session.status == "complete"
        assert session.error_message is None


async def test_approve_generation_attempt_requires_validated_success(client):
    from cli_any_app.models.database import get_session

    async with get_session() as db:
        session = Session(name="Test", app_name="test-app")
        db.add(session)
        await db.flush()
        attempt = GenerationAttempt(
            session_id=session.id,
            status="complete",
            validation_report_json='{"valid": true, "errors": [], "warnings": []}',
            package_path="/tmp/generated/test",
            approval_status="pending",
        )
        db.add(attempt)
        await db.commit()
        session_id = session.id
        attempt_id = attempt.id

    resp = await client.post(
        f"/api/sessions/{session_id}/generation-attempts/{attempt_id}/approve",
        json={"reason": "Reviewed generated files and validation report"},
    )
    assert resp.status_code == 200
    assert resp.json()["approval_status"] == "approved"

    async with get_session() as db:
        approved = await db.get(GenerationAttempt, attempt_id)
        assert approved.approval_status == "approved"
        events = await db.execute(select(AuditEvent).where(AuditEvent.event_type == "generation.approved"))
        assert len(events.scalars().all()) == 1


async def test_approve_generation_attempt_rejects_failed_validation(client):
    from cli_any_app.models.database import get_session

    async with get_session() as db:
        session = Session(name="Test", app_name="test-app")
        db.add(session)
        await db.flush()
        attempt = GenerationAttempt(
            session_id=session.id,
            status="validation_failed",
            validation_report_json='{"valid": false, "errors": ["bad"], "warnings": []}',
            approval_status="pending",
        )
        db.add(attempt)
        await db.commit()
        session_id = session.id
        attempt_id = attempt.id

    resp = await client.post(
        f"/api/sessions/{session_id}/generation-attempts/{attempt_id}/approve",
        json={"reason": "Trying to approve failed output"},
    )
    assert resp.status_code == 409

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture(autouse=True)
async def secure_db(tmp_path):
    from cli_any_app.config import settings
    from cli_any_app.models.database import init_db

    settings.test_auto_auth = False
    settings.data_dir = tmp_path / "data"
    settings.admin_password = "test-password"
    await init_db(f"sqlite+aiosqlite:///{tmp_path}/secure.db")
    yield
    settings.test_auto_auth = True


@pytest.fixture
async def client():
    from cli_any_app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c


async def _login(client: AsyncClient) -> str:
    resp = await client.post("/api/auth/login", json={"password": "test-password"})
    assert resp.status_code == 200
    return resp.json()["csrf_token"]


async def test_rest_requires_authentication(client):
    resp = await client.get("/api/sessions")
    assert resp.status_code == 401


async def test_state_change_requires_csrf(client):
    csrf = await _login(client)

    missing = await client.post("/api/sessions", json={"name": "S1", "app_name": "app"})
    assert missing.status_code == 403

    ok = await client.post(
        "/api/sessions",
        json={"name": "S1", "app_name": "app"},
        headers={"X-CSRF-Token": csrf},
    )
    assert ok.status_code == 201


async def test_ws_token_requires_authentication(client):
    resp = await client.get("/api/auth/ws-token")
    assert resp.status_code == 401

    await _login(client)
    authed = await client.get("/api/auth/ws-token")
    assert authed.status_code == 200
    assert authed.json()["token"]


async def test_capture_requires_valid_recording_token(client, monkeypatch):
    from cli_any_app.capture.proxy_manager import proxy_manager
    from cli_any_app.models.database import get_session
    from cli_any_app.models.flow import Flow
    from cli_any_app.models.session import Session
    from cli_any_app.security import token_hash

    session = Session(
        name="Capture",
        app_name="app",
        status="recording",
        capture_token_hash=token_hash("good-token"),
    )
    async with get_session() as db:
        db.add(session)
        await db.flush()
        db.add(Flow(session_id=session.id, label="login", order=1))
        await db.commit()
        session_id = session.id

    monkeypatch.setattr(proxy_manager, "owns_session", lambda sid: sid == session_id)
    payload = {
        "session_id": session_id,
        "method": "GET",
        "url": "https://api.example.com/users?token=secret",
        "request_headers": {"Authorization": "Bearer secret"},
        "request_body": None,
        "status_code": 200,
        "response_headers": {"Content-Type": "application/json"},
        "response_body": '{"email":"patient@example.com"}',
        "content_type": "application/json",
    }

    missing = await client.post("/api/internal/capture", json=payload)
    assert missing.status_code == 403

    bad = await client.post(
        "/api/internal/capture",
        json=payload,
        headers={"X-Capture-Token": "bad-token"},
    )
    assert bad.status_code == 403

    ok = await client.post(
        "/api/internal/capture",
        json=payload,
        headers={"X-Capture-Token": "good-token"},
    )
    assert ok.status_code == 202
    assert ok.json()["status"] == "captured"

    from cli_any_app.models.request import CapturedRequest
    from sqlalchemy import select

    async with get_session() as db:
        result = await db.execute(select(CapturedRequest))
        captured = result.scalar_one()
        assert "secret" not in captured.url
        assert "secret" not in captured.request_headers
        assert captured.request_body is None
        assert captured.response_body is None
        assert captured.response_body_hash is not None

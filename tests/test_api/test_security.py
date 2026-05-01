import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture(autouse=True)
async def secure_db(tmp_path):
    from cli_any_app.config import settings
    from cli_any_app.models.database import init_db

    old_values = {
        "test_auto_auth": settings.test_auto_auth,
        "data_dir": settings.data_dir,
        "admin_password": settings.admin_password,
        "max_session_capture_bytes": settings.max_session_capture_bytes,
        "host": settings.host,
        "port": settings.port,
        "ws_allowed_origins": settings.ws_allowed_origins,
    }
    settings.test_auto_auth = False
    settings.data_dir = tmp_path / "data"
    settings.admin_password = "test-password"
    await init_db(f"sqlite+aiosqlite:///{tmp_path}/secure.db")
    yield
    for key, value in old_values.items():
        setattr(settings, key, value)


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


def test_ws_origin_validation_uses_configured_allowlist():
    from cli_any_app.config import settings
    from cli_any_app.security import validate_ws_origin

    class FakeWebSocket:
        def __init__(self, origin: str, host: str = "attacker.example:8000"):
            self.headers = {"origin": origin, "host": host}

    settings.test_auto_auth = False
    settings.host = "127.0.0.1"
    settings.port = 8000
    settings.ws_allowed_origins = []

    assert validate_ws_origin(FakeWebSocket("http://localhost:8000"))
    assert validate_ws_origin(FakeWebSocket("http://127.0.0.1:8000"))
    assert not validate_ws_origin(FakeWebSocket("http://attacker.example:8000"))
    assert not validate_ws_origin(FakeWebSocket("http://localhost:8000.attacker.example"))
    assert not validate_ws_origin(FakeWebSocket("not a url"))

    settings.ws_allowed_origins = ["http://dev.local:5173"]
    assert validate_ws_origin(FakeWebSocket("http://dev.local:5173"))


def test_redact_url_redacts_phi_like_path_segments():
    from cli_any_app.capture.privacy import redact_url

    _, redacted_path, redacted_full = redact_url(
        "https://api.example.test/patients/jane.doe@example.com/MRN-12345"
        "?token=secret&phone=555-123-4567"
    )

    assert "jane.doe@example.com" not in redacted_path
    assert "jane.doe@example.com" not in redacted_full
    assert "MRN-12345" not in redacted_path
    assert "MRN-12345" not in redacted_full
    assert "secret" not in redacted_full
    assert "555-123-4567" not in redacted_full


async def test_capture_enforces_cumulative_session_size_limit(client, monkeypatch):
    from cli_any_app.capture.proxy_manager import proxy_manager
    from cli_any_app.config import settings
    from cli_any_app.models.database import get_session
    from cli_any_app.models.flow import Flow
    from cli_any_app.models.session import Session
    from cli_any_app.security import token_hash

    settings.max_session_capture_bytes = 200
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
        "method": "POST",
        "url": "https://api.example.com/patients",
        "request_headers": {},
        "request_body": "x" * 64,
        "status_code": 200,
        "response_headers": {},
        "response_body": "y" * 64,
        "content_type": "application/json",
    }

    ok = await client.post(
        "/api/internal/capture",
        json=payload,
        headers={"X-Capture-Token": "good-token"},
    )
    assert ok.status_code == 202

    oversized = await client.post(
        "/api/internal/capture",
        json=payload,
        headers={"X-Capture-Token": "good-token"},
    )
    assert oversized.status_code == 413
    assert oversized.json()["detail"] == "Session capture size limit exceeded"

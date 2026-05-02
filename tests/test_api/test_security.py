import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture(autouse=True)
async def secure_db(tmp_path, regulated_test_settings):
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
        "cookie_secure": settings.cookie_secure,
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
    csp = resp.headers["content-security-policy"]
    assert "connect-src 'self' ws://testserver wss://testserver" in csp
    assert " ws: " not in csp
    assert " wss: " not in csp


async def test_auth_middleware_does_not_swallow_unexpected_errors(client, monkeypatch):
    import cli_any_app.main as main

    def broken_auth(_request):
        raise RuntimeError("unexpected auth bug")

    monkeypatch.setattr(main, "require_http_auth", broken_auth)

    with pytest.raises(RuntimeError, match="unexpected auth bug"):
        await client.get("/api/sessions")


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


def test_session_cookie_secure_attribute_is_configurable():
    from fastapi import Response

    from cli_any_app.config import settings
    from cli_any_app.security import clear_session_cookie, create_session_cookie

    settings.cookie_secure = True
    response = Response()
    create_session_cookie(response)

    set_cookie_headers = [
        value.decode()
        for name, value in response.raw_headers
        if name.decode().lower() == "set-cookie"
    ]
    assert len(set_cookie_headers) == 2
    assert all("Secure" in header for header in set_cookie_headers)

    logout_response = Response()
    clear_session_cookie(logout_response)
    delete_cookie_headers = [
        value.decode()
        for name, value in logout_response.raw_headers
        if name.decode().lower() == "set-cookie"
    ]
    assert len(delete_cookie_headers) == 2
    assert all("Secure" in header for header in delete_cookie_headers)


def test_unsign_payload_rejects_malformed_expiry_values():
    import hashlib
    import hmac
    import json

    from cli_any_app.security import SESSION_PURPOSE, _b64e, get_app_secret, unsign_payload

    def signed(payload):
        raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
        encoded = _b64e(raw)
        sig = hmac.new(get_app_secret(), encoded.encode(), hashlib.sha256).digest()
        return f"{encoded}.{_b64e(sig)}"

    null_exp = signed({"purpose": SESSION_PURPOSE, "exp": None})
    non_numeric_exp = signed({"purpose": SESSION_PURPOSE, "exp": "not-a-number"})

    assert unsign_payload(null_exp, SESSION_PURPOSE) is None
    assert unsign_payload(non_numeric_exp, SESSION_PURPOSE) is None


def test_private_secret_writes_reject_symlink_targets(tmp_path):
    from cli_any_app.config import settings
    from cli_any_app.security import _write_private

    settings.secrets_dir.mkdir(parents=True, exist_ok=True)
    outside = tmp_path / "outside-secret.txt"
    outside.write_text("safe")
    link = settings.secrets_dir / "admin-password.hash"
    link.symlink_to(outside)

    with pytest.raises(RuntimeError, match="symlink"):
        _write_private(link, "overwritten")

    assert outside.read_text() == "safe"


def test_payload_key_write_rejects_symlink_targets(tmp_path):
    from cli_any_app.capture.privacy import _private_write
    from cli_any_app.config import settings

    settings.secrets_dir.mkdir(parents=True, exist_ok=True)
    outside = tmp_path / "payload-target.key"
    outside.write_bytes(b"safe")
    link = settings.secrets_dir / "payload-data.key"
    link.symlink_to(outside)

    with pytest.raises(RuntimeError, match="symlink"):
        _private_write(link, b"overwritten")

    assert outside.read_bytes() == b"safe"


def test_private_secret_writes_reject_paths_outside_secrets_dir(tmp_path):
    from cli_any_app.private_files import write_private_bytes

    outside_dir = tmp_path / "outside"

    with pytest.raises(RuntimeError, match="outside secrets directory"):
        write_private_bytes(outside_dir / "app-secret.key", b"secret")

    assert not outside_dir.exists()


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
        "https://user:password@api.example.test:8443/patients/jane.doe@example.com/MRN-12345"
        "?token=secret&phone=555-123-4567"
    )

    assert "user:password" not in redacted_full
    assert "jane.doe@example.com" not in redacted_path
    assert "jane.doe@example.com" not in redacted_full
    assert "MRN-12345" not in redacted_path
    assert "MRN-12345" not in redacted_full
    assert "secret" not in redacted_full
    assert "555-123-4567" not in redacted_full
    assert redacted_full.startswith("https://api.example.test:8443/")


async def test_capture_enforces_cumulative_session_size_limit(client, monkeypatch):
    from cli_any_app.capture.proxy_manager import proxy_manager
    from cli_any_app.config import settings
    from cli_any_app.models.database import get_session
    from cli_any_app.models.flow import Flow
    from cli_any_app.models.session import Session
    from cli_any_app.security import token_hash

    settings.max_session_capture_bytes = 6
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


async def test_capture_session_size_limit_counts_encrypted_raw_payloads(client, monkeypatch):
    from cli_any_app.capture.proxy_manager import proxy_manager
    from cli_any_app.config import settings
    from cli_any_app.models.database import get_session
    from cli_any_app.models.flow import Flow
    from cli_any_app.models.session import Session
    from cli_any_app.security import token_hash

    settings.raw_body_capture_enabled = True
    settings.max_session_capture_bytes = 150
    monkeypatch.setattr(
        "cli_any_app.api.capture.encrypt_payload",
        lambda value: ("c" * 50) if value is not None else None,
    )
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
        "request_body": "x",
        "status_code": 200,
        "response_headers": {},
        "response_body": "y",
        "content_type": "text/plain",
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

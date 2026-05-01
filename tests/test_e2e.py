import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture(autouse=True)
async def setup_db(tmp_path):
    from cli_any_app.models.database import init_db
    await init_db(f"sqlite+aiosqlite:///{tmp_path}/test.db")
    # Reset the in-memory domain filter state between tests
    from cli_any_app.api.domains import _domain_filters
    _domain_filters.clear()
    yield


@pytest.fixture
async def client():
    from cli_any_app.main import app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_full_capture_flow(client):
    # 1. Create a session
    resp = await client.post("/api/sessions", json={"name": "Test E2E", "app_name": "test-app"})
    assert resp.status_code == 201
    session = resp.json()
    session_id = session["id"]
    assert session["status"] == "created"

    # 2. Create a flow
    resp = await client.post(f"/api/sessions/{session_id}/flows", json={"label": "login"})
    assert resp.status_code == 201
    flow = resp.json()
    flow_id = flow["id"]
    assert flow["label"] == "login"

    # 3. Post mock captured requests
    # API request (should be captured)
    resp = await client.post("/api/internal/capture", json={
        "session_id": session_id,
        "method": "POST",
        "url": "https://api.example.com/v1/auth/login",
        "request_headers": {"Content-Type": "application/json", "User-Agent": "TestApp/1.0"},
        "request_body": '{"email":"test@test.com","password":"secret"}',
        "status_code": 200,
        "response_headers": {"Content-Type": "application/json"},
        "response_body": '{"token":"abc123","user":{"id":1,"name":"Test"}}',
        "content_type": "application/json",
    })
    assert resp.status_code == 202
    assert resp.json()["status"] == "captured"
    assert resp.json()["is_api"] is True

    # Non-API request (image -- should still be captured but flagged)
    resp = await client.post("/api/internal/capture", json={
        "session_id": session_id,
        "method": "GET",
        "url": "https://cdn.example.com/images/logo.png",
        "request_headers": {},
        "request_body": None,
        "status_code": 200,
        "response_headers": {"Content-Type": "image/png"},
        "response_body": None,
        "content_type": "image/png",
    })
    assert resp.status_code == 202
    assert resp.json()["is_api"] is False

    # Noise domain request (stored as metadata and disabled by default)
    resp = await client.post("/api/internal/capture", json={
        "session_id": session_id,
        "method": "POST",
        "url": "https://firebaselogging.googleapis.com/v1/log",
        "request_headers": {},
        "request_body": "{}",
        "status_code": 200,
        "response_headers": {},
        "response_body": "{}",
        "content_type": "application/json",
    })
    assert resp.status_code == 202
    assert resp.json()["status"] == "captured"

    # 4. List domains
    resp = await client.get(f"/api/sessions/{session_id}/domains")
    assert resp.status_code == 200
    domains = resp.json()
    domain_names = [d["domain"] for d in domains]
    assert "api.example.com" in domain_names
    assert "cdn.example.com" in domain_names
    assert "firebaselogging.googleapis.com" in domain_names

    # Verify domain enabled state
    api_domain = next(d for d in domains if d["domain"] == "api.example.com")
    assert api_domain["enabled"] is True
    assert api_domain["is_noise"] is False

    # 5. Toggle a domain
    resp = await client.put(
        f"/api/sessions/{session_id}/domains/cdn.example.com",
        json={"enabled": False}
    )
    assert resp.status_code == 200
    assert resp.json()["enabled"] is False

    # 6. Stop the flow
    resp = await client.post(f"/api/sessions/{session_id}/flows/{flow_id}/stop")
    assert resp.status_code == 200
    assert resp.json()["ended_at"] is not None

    # 7. Verify flows list
    resp = await client.get(f"/api/sessions/{session_id}/flows")
    assert resp.status_code == 200
    flows = resp.json()
    assert len(flows) == 1
    assert flows[0]["label"] == "login"

    # 8. Verify session can be retrieved
    resp = await client.get(f"/api/sessions/{session_id}")
    assert resp.status_code == 200
    assert resp.json()["name"] == "Test E2E"


async def test_capture_with_no_active_flow(client):
    # Create session but no flow
    resp = await client.post("/api/sessions", json={"name": "No Flow", "app_name": "test"})
    session_id = resp.json()["id"]

    resp = await client.post("/api/internal/capture", json={
        "session_id": session_id,
        "method": "GET",
        "url": "https://api.example.com/test",
        "request_headers": {},
        "request_body": None,
        "status_code": 200,
        "response_headers": {},
        "response_body": "{}",
        "content_type": "application/json",
    })
    assert resp.status_code == 202
    assert resp.json()["status"] == "no_active_flow"


async def test_multiple_flows_capture_isolation(client):
    """Requests are captured to the currently active (open) flow only."""
    resp = await client.post("/api/sessions", json={"name": "Multi Flow", "app_name": "test"})
    session_id = resp.json()["id"]

    # Create and stop flow 1
    resp = await client.post(f"/api/sessions/{session_id}/flows", json={"label": "flow-1"})
    flow1_id = resp.json()["id"]

    resp = await client.post("/api/internal/capture", json={
        "session_id": session_id,
        "method": "GET",
        "url": "https://api.example.com/flow1",
        "request_headers": {},
        "request_body": None,
        "status_code": 200,
        "response_headers": {},
        "response_body": "{}",
        "content_type": "application/json",
    })
    assert resp.json()["status"] == "captured"

    resp = await client.post(f"/api/sessions/{session_id}/flows/{flow1_id}/stop")
    assert resp.status_code == 200

    # Create flow 2 and capture to it
    resp = await client.post(f"/api/sessions/{session_id}/flows", json={"label": "flow-2"})
    flow2_id = resp.json()["id"]

    resp = await client.post("/api/internal/capture", json={
        "session_id": session_id,
        "method": "POST",
        "url": "https://api.example.com/flow2",
        "request_headers": {},
        "request_body": "{}",
        "status_code": 201,
        "response_headers": {},
        "response_body": "{}",
        "content_type": "application/json",
    })
    assert resp.json()["status"] == "captured"

    # Stop flow 2 and verify no active flow
    resp = await client.post(f"/api/sessions/{session_id}/flows/{flow2_id}/stop")
    assert resp.status_code == 200

    resp = await client.post("/api/internal/capture", json={
        "session_id": session_id,
        "method": "GET",
        "url": "https://api.example.com/orphan",
        "request_headers": {},
        "request_body": None,
        "status_code": 200,
        "response_headers": {},
        "response_body": "{}",
        "content_type": "application/json",
    })
    assert resp.json()["status"] == "no_active_flow"

    # Verify we have 2 flows
    resp = await client.get(f"/api/sessions/{session_id}/flows")
    assert len(resp.json()) == 2

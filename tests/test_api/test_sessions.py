import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture(autouse=True)
async def setup_db(tmp_path):
    from cli_any_app.models.database import init_db
    await init_db(f"sqlite+aiosqlite:///{tmp_path}/test.db")
    yield


@pytest.fixture
async def client():
    from cli_any_app.main import app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_create_session(client):
    resp = await client.post("/api/sessions", json={"name": "Test", "app_name": "test-app"})
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Test"
    assert data["app_name"] == "test-app"
    assert data["status"] == "created"
    assert "id" in data


async def test_create_session_strips_names_and_rejects_blank_or_oversized(client):
    blank_name = await client.post("/api/sessions", json={"name": "   ", "app_name": "test-app"})
    assert blank_name.status_code == 422

    blank_app = await client.post("/api/sessions", json={"name": "Test", "app_name": "   "})
    assert blank_app.status_code == 422

    oversized = await client.post("/api/sessions", json={"name": "x" * 121, "app_name": "test-app"})
    assert oversized.status_code == 422

    resp = await client.post("/api/sessions", json={"name": "  Test  ", "app_name": "  test-app  "})
    assert resp.status_code == 201
    assert resp.json()["name"] == "Test"
    assert resp.json()["app_name"] == "test-app"


async def test_list_sessions(client):
    await client.post("/api/sessions", json={"name": "S1", "app_name": "app1"})
    await client.post("/api/sessions", json={"name": "S2", "app_name": "app2"})
    resp = await client.get("/api/sessions")
    assert resp.status_code == 200
    assert len(resp.json()) == 2


async def test_get_session(client):
    create = await client.post("/api/sessions", json={"name": "S1", "app_name": "app1"})
    sid = create.json()["id"]
    resp = await client.get(f"/api/sessions/{sid}")
    assert resp.status_code == 200
    assert resp.json()["name"] == "S1"


async def test_get_session_not_found(client):
    resp = await client.get("/api/sessions/nonexistent")
    assert resp.status_code == 404


async def test_delete_session(client):
    create = await client.post("/api/sessions", json={"name": "S1", "app_name": "app1"})
    sid = create.json()["id"]
    resp = await client.delete(f"/api/sessions/{sid}")
    assert resp.status_code == 204


async def test_delete_session_not_found(client):
    resp = await client.delete("/api/sessions/nonexistent")
    assert resp.status_code == 404


async def test_start_recording_conflict_returns_409(client, monkeypatch):
    from cli_any_app.capture.proxy_manager import proxy_manager

    state = {"running": False, "owner": None}

    def fake_start(session_id, port=None, capture_token=None):
        if state["running"] and state["owner"] != session_id:
            raise RuntimeError(f"Proxy already running for session {state['owner']}")
        state["running"] = True
        state["owner"] = session_id
        return port or 8080

    monkeypatch.setattr(proxy_manager, "start", fake_start)

    s1 = (await client.post("/api/sessions", json={"name": "S1", "app_name": "app1"})).json()["id"]
    s2 = (await client.post("/api/sessions", json={"name": "S2", "app_name": "app2"})).json()["id"]

    resp = await client.post(f"/api/sessions/{s1}/start-recording")
    assert resp.status_code == 200

    resp = await client.post(f"/api/sessions/{s2}/start-recording")
    assert resp.status_code == 409
    assert "Proxy already running" in resp.text


async def test_stop_recording_other_session_returns_409(client, monkeypatch):
    from cli_any_app.capture.proxy_manager import proxy_manager

    state = {"running": False, "owner": None}

    def fake_start(session_id, port=None, capture_token=None):
        state["running"] = True
        state["owner"] = session_id
        return port or 8080

    def fake_stop(session_id=None):
        if state["running"] and session_id and state["owner"] != session_id:
            raise RuntimeError(f"Proxy is running for session {state['owner']}")
        state["running"] = False
        state["owner"] = None

    monkeypatch.setattr(proxy_manager, "start", fake_start)
    monkeypatch.setattr(proxy_manager, "stop", fake_stop)

    s1 = (await client.post("/api/sessions", json={"name": "S1", "app_name": "app1"})).json()["id"]
    s2 = (await client.post("/api/sessions", json={"name": "S2", "app_name": "app2"})).json()["id"]

    resp = await client.post(f"/api/sessions/{s1}/start-recording")
    assert resp.status_code == 200

    resp = await client.post(f"/api/sessions/{s2}/stop-recording")
    assert resp.status_code == 409
    assert "Proxy is running" in resp.text

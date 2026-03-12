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
    assert data["status"] == "stopped"
    assert "id" in data


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

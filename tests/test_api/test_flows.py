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


@pytest.fixture
async def session_id(client):
    resp = await client.post("/api/sessions", json={"name": "Test", "app_name": "test-app"})
    return resp.json()["id"]


async def test_create_flow(client, session_id):
    resp = await client.post(f"/api/sessions/{session_id}/flows", json={"label": "Login flow"})
    assert resp.status_code == 201
    data = resp.json()
    assert data["label"] == "Login flow"
    assert data["session_id"] == session_id
    assert data["order"] == 1
    assert data["ended_at"] is None
    assert "id" in data


async def test_create_flow_auto_order(client, session_id):
    await client.post(f"/api/sessions/{session_id}/flows", json={"label": "Flow 1"})
    resp = await client.post(f"/api/sessions/{session_id}/flows", json={"label": "Flow 2"})
    assert resp.json()["order"] == 2


async def test_list_flows(client, session_id):
    await client.post(f"/api/sessions/{session_id}/flows", json={"label": "Flow 1"})
    await client.post(f"/api/sessions/{session_id}/flows", json={"label": "Flow 2"})
    resp = await client.get(f"/api/sessions/{session_id}/flows")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    assert data[0]["order"] < data[1]["order"]


async def test_stop_flow(client, session_id):
    create = await client.post(f"/api/sessions/{session_id}/flows", json={"label": "Flow 1"})
    flow_id = create.json()["id"]
    resp = await client.post(f"/api/sessions/{session_id}/flows/{flow_id}/stop")
    assert resp.status_code == 200
    assert resp.json()["ended_at"] is not None


async def test_stop_flow_not_found(client, session_id):
    resp = await client.post(f"/api/sessions/{session_id}/flows/nonexistent/stop")
    assert resp.status_code == 404


async def test_delete_flow(client, session_id):
    create = await client.post(f"/api/sessions/{session_id}/flows", json={"label": "Flow 1"})
    flow_id = create.json()["id"]
    resp = await client.delete(f"/api/sessions/{session_id}/flows/{flow_id}")
    assert resp.status_code == 204


async def test_delete_flow_not_found(client, session_id):
    resp = await client.delete(f"/api/sessions/{session_id}/flows/nonexistent")
    assert resp.status_code == 404


async def test_list_flow_requests(client, session_id):
    create = await client.post(f"/api/sessions/{session_id}/flows", json={"label": "Flow 1"})
    flow_id = create.json()["id"]

    from cli_any_app.models.database import get_session
    from cli_any_app.models.request import CapturedRequest

    async with get_session() as db:
        db.add(
            CapturedRequest(
                flow_id=flow_id,
                method="GET",
                url="https://api.example.com/items",
                status_code=200,
                request_headers="{}",
                response_headers="{}",
                content_type="application/json",
            )
        )
        await db.commit()

    resp = await client.get(f"/api/sessions/{session_id}/flows/{flow_id}/requests")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["flow_id"] == flow_id
    assert data[0]["url"] == "https://api.example.com/items"

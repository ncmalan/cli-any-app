import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select


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


async def _create_session_with_requests(client):
    """Helper: create a session, flow, and some captured requests."""
    resp = await client.post("/api/sessions", json={"name": "Test", "app_name": "test-app"})
    session_id = resp.json()["id"]

    resp = await client.post(f"/api/sessions/{session_id}/flows", json={"label": "Flow 1"})
    flow_id = resp.json()["id"]

    # Insert requests directly into the DB
    from cli_any_app.models.database import get_session
    from cli_any_app.models.request import CapturedRequest

    async with get_session() as db:
        for url in [
            "https://api.example.com/users",
            "https://api.example.com/posts",
            "https://api.example.com/users/1",
            "https://tracking.facebook.com/event",
            "https://analytics.google-analytics.com/collect",
        ]:
            req = CapturedRequest(
                flow_id=flow_id,
                method="GET",
                url=url,
                status_code=200,
            )
            db.add(req)
        await db.commit()

    return session_id


async def test_list_domains(client):
    session_id = await _create_session_with_requests(client)
    resp = await client.get(f"/api/sessions/{session_id}/domains")
    assert resp.status_code == 200
    domains = resp.json()
    assert len(domains) == 3  # example.com, facebook.com, google-analytics.com

    # example.com should have highest count (3 requests)
    assert domains[0]["domain"] == "api.example.com"
    assert domains[0]["request_count"] == 3
    assert domains[0]["is_noise"] is False
    assert domains[0]["enabled"] is True

    # noise domains should be disabled by default
    noise_domains = [d for d in domains if d["is_noise"]]
    assert len(noise_domains) == 2
    for d in noise_domains:
        assert d["enabled"] is False


async def test_list_domains_empty_session(client):
    resp = await client.post("/api/sessions", json={"name": "Empty", "app_name": "app"})
    session_id = resp.json()["id"]
    resp = await client.get(f"/api/sessions/{session_id}/domains")
    assert resp.status_code == 200
    assert resp.json() == []


async def test_toggle_domain(client):
    session_id = await _create_session_with_requests(client)

    # Enable a noise domain
    resp = await client.put(
        f"/api/sessions/{session_id}/domains/tracking.facebook.com",
        json={"enabled": True},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["domain"] == "tracking.facebook.com"
    assert data["request_count"] == 1
    assert data["enabled"] is True
    assert data["is_noise"] is True

    # Verify it persists in the list
    resp = await client.get(f"/api/sessions/{session_id}/domains")
    fb_domain = [d for d in resp.json() if d["domain"] == "tracking.facebook.com"][0]
    assert fb_domain["enabled"] is True


async def test_toggle_domain_disable(client):
    session_id = await _create_session_with_requests(client)

    # Disable a non-noise domain
    resp = await client.put(
        f"/api/sessions/{session_id}/domains/api.example.com",
        json={"enabled": False},
    )
    assert resp.status_code == 200
    assert resp.json()["enabled"] is False

    # Verify it persists in the list
    resp = await client.get(f"/api/sessions/{session_id}/domains")
    example = [d for d in resp.json() if d["domain"] == "api.example.com"][0]
    assert example["enabled"] is False


async def test_toggle_domain_rejects_empty_normalized_domain(client):
    session_id = await _create_session_with_requests(client)

    resp = await client.put(
        f"/api/sessions/{session_id}/domains/%20%20%20",
        json={"enabled": True},
    )

    assert resp.status_code == 400
    assert resp.json()["detail"] == "Domain is required"


async def test_domain_listing_normalizes_host_before_noise_detection(client):
    from cli_any_app.models.database import get_session
    from cli_any_app.models.flow import Flow
    from cli_any_app.models.request import CapturedRequest
    from cli_any_app.models.session import Session

    session = Session(name="Ports", app_name="app")
    async with get_session() as db:
        db.add(session)
        await db.flush()
        flow = Flow(session_id=session.id, label="Flow", order=1)
        db.add(flow)
        await db.flush()
        db.add_all(
            [
                CapturedRequest(
                    flow_id=flow.id,
                    method="GET",
                    url="https://firebaselogging.googleapis.com:443/log",
                    host="firebaselogging.googleapis.com:443",
                    status_code=200,
                ),
                CapturedRequest(
                    flow_id=flow.id,
                    method="GET",
                    url="https://analytics.google-analytics.com:8443/collect",
                    host="analytics.google-analytics.com:8443",
                    status_code=200,
                ),
            ]
        )
        await db.commit()
        session_id = session.id

    resp = await client.get(f"/api/sessions/{session_id}/domains")
    assert resp.status_code == 200
    domains = {item["domain"]: item for item in resp.json()}
    assert set(domains) == {
        "firebaselogging.googleapis.com",
        "analytics.google-analytics.com",
    }
    assert all(item["is_noise"] is True for item in domains.values())
    assert all(item["enabled"] is False for item in domains.values())

    toggle = await client.put(
        f"/api/sessions/{session_id}/domains/firebaselogging.googleapis.com:443",
        json={"enabled": True},
    )
    assert toggle.status_code == 200
    assert toggle.json()["domain"] == "firebaselogging.googleapis.com"
    assert toggle.json()["request_count"] == 1

    resp = await client.get(f"/api/sessions/{session_id}/domains")
    domains = {item["domain"]: item for item in resp.json()}
    assert domains["firebaselogging.googleapis.com"]["enabled"] is True


async def test_toggle_domain_bounds_and_trims_reason(client):
    from cli_any_app.models.audit_event import AuditEvent
    from cli_any_app.models.database import get_session
    from cli_any_app.models.domain_filter import DomainFilter

    session_id = await _create_session_with_requests(client)

    resp = await client.put(
        f"/api/sessions/{session_id}/domains/api.example.com",
        json={"enabled": False, "reason": "  reviewer disabled domain  "},
    )
    assert resp.status_code == 200

    async with get_session() as db:
        filters = await db.execute(select(DomainFilter).where(DomainFilter.session_id == session_id))
        domain_filter = filters.scalar_one()
        assert domain_filter.reason == "reviewer disabled domain"
        events = await db.execute(select(AuditEvent).where(AuditEvent.event_type == "domain_filter.changed"))
        audit_event = events.scalar_one()
        assert audit_event.reason == "reviewer disabled domain"

    blank = await client.put(
        f"/api/sessions/{session_id}/domains/api.example.com",
        json={"enabled": True, "reason": "   "},
    )
    assert blank.status_code == 400
    assert blank.json()["detail"] == "Domain filter reason cannot be blank"

    too_long = await client.put(
        f"/api/sessions/{session_id}/domains/api.example.com",
        json={"enabled": True, "reason": "x" * 501},
    )
    assert too_long.status_code == 422

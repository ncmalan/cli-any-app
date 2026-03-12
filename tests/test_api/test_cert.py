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


async def test_cert_endpoint_returns_pem(client, tmp_path):
    from cli_any_app import config
    cert_path = tmp_path / "mitmproxy-ca-cert.pem"
    cert_path.write_text("-----BEGIN CERTIFICATE-----\nFAKE\n-----END CERTIFICATE-----")
    config.settings.mitmproxy_ca_dir = tmp_path
    resp = await client.get("/api/cert")
    assert resp.status_code == 200
    assert "BEGIN CERTIFICATE" in resp.text


async def test_cert_endpoint_404_when_missing(client, tmp_path):
    from cli_any_app import config
    config.settings.mitmproxy_ca_dir = tmp_path  # no cert file here
    resp = await client.get("/api/cert")
    assert resp.status_code == 404


async def test_cert_qr_endpoint_returns_png(client):
    resp = await client.get("/api/cert/qr")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/png"
    # PNG magic bytes
    assert resp.content[:4] == b"\x89PNG"

import pytest
from httpx import ASGITransport, AsyncClient

from cli_any_app.main import app


@pytest.fixture(autouse=True)
def regulated_test_settings(tmp_path):
    from cli_any_app.config import settings

    old_values = {
        "test_auto_auth": settings.test_auto_auth,
        "data_dir": settings.data_dir,
        "admin_password": settings.admin_password,
        "raw_body_capture_enabled": settings.raw_body_capture_enabled,
    }
    settings.test_auto_auth = True
    settings.data_dir = tmp_path / "data"
    settings.admin_password = "test-password"
    settings.raw_body_capture_enabled = False
    yield
    for key, value in old_values.items():
        setattr(settings, key, value)


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c

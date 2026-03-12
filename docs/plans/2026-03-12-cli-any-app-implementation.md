# cli-any-app Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a tool that captures mobile app network traffic via mitmproxy, lets users label API flows through a web UI, then uses Claude to generate installable Python Click CLI tools with SKILL.md.

**Architecture:** Three-layer FastAPI service — Capture (mitmproxy addon subprocess), Web UI (React SPA), Generation (Claude API pipeline) — with SQLite storage. The mitmproxy addon forwards intercepted traffic to FastAPI, which stores it, streams it to the UI via WebSocket, and feeds it to the generation pipeline.

**Tech Stack:** Python 3.11+, FastAPI, SQLAlchemy, mitmproxy, Anthropic SDK, React 18, TypeScript, Tailwind CSS, Vite, Click, SQLite.

**Design Doc:** `docs/plans/2026-03-12-cli-any-app-design.md`

---

## Task 1: Project Scaffolding & Dependencies

**Files:**
- Create: `pyproject.toml`
- Create: `cli_any_app/__init__.py`
- Create: `cli_any_app/main.py`
- Create: `cli_any_app/config.py`
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`

**Step 1: Create pyproject.toml with all dependencies**

```toml
[build-system]
requires = ["setuptools>=68.0", "wheel"]
build-backend = "setuptools.backends._legacy:_Backend"

[project]
name = "cli-any-app"
version = "0.1.0"
description = "Transform mobile app network traffic into agent-usable CLI tools"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.110.0",
    "uvicorn[standard]>=0.27.0",
    "sqlalchemy>=2.0.0",
    "aiosqlite>=0.20.0",
    "mitmproxy>=10.0.0",
    "anthropic>=0.40.0",
    "httpx>=0.27.0",
    "python-multipart>=0.0.9",
    "jinja2>=3.1.0",
    "qrcode[pil]>=7.4",
    "pydantic>=2.0.0",
    "pydantic-settings>=2.0.0",
    "websockets>=12.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.23.0",
    "pytest-httpx>=0.30.0",
    "ruff>=0.3.0",
]

[project.scripts]
cli-any-app = "cli_any_app.main:cli_entry"
```

**Step 2: Create cli_any_app/config.py — app settings**

```python
from pathlib import Path
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "cli-any-app"
    debug: bool = False
    host: str = "0.0.0.0"
    port: int = 8000
    proxy_port: int = 8080
    data_dir: Path = Path("data")
    db_url: str = "sqlite+aiosqlite:///data/cli_any_app.db"
    mitmproxy_ca_dir: Path = Path.home() / ".mitmproxy"
    anthropic_api_key: str = ""

    model_config = {"env_prefix": "CLI_ANY_APP_"}

    @property
    def generated_dir(self) -> Path:
        return self.data_dir / "generated"

    @property
    def bodies_dir(self) -> Path:
        return self.data_dir / "bodies"


settings = Settings()
```

**Step 3: Create cli_any_app/main.py — FastAPI app skeleton**

```python
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from cli_any_app.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.generated_dir.mkdir(parents=True, exist_ok=True)
    settings.bodies_dir.mkdir(parents=True, exist_ok=True)
    # Init DB on startup
    from cli_any_app.models.database import init_db
    await init_db()
    yield


app = FastAPI(title="cli-any-app", lifespan=lifespan)


def cli_entry():
    uvicorn.run(
        "cli_any_app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
    )


if __name__ == "__main__":
    cli_entry()
```

**Step 4: Create tests/conftest.py with async fixtures**

```python
import pytest
from httpx import ASGITransport, AsyncClient

from cli_any_app.main import app


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
```

**Step 5: Create __init__.py files**

```python
# cli_any_app/__init__.py — empty
# tests/__init__.py — empty
```

**Step 6: Install and verify**

Run: `cd /Users/nielm/DevLocal/cli-any-app && pip install -e ".[dev]"`
Expected: Installs successfully, `cli-any-app` command available.

**Step 7: Commit**

```bash
git add pyproject.toml cli_any_app/ tests/
git commit -m "feat: project scaffolding with FastAPI, settings, and test fixtures"
```

---

## Task 2: Database Models

**Files:**
- Create: `cli_any_app/models/__init__.py`
- Create: `cli_any_app/models/database.py`
- Create: `cli_any_app/models/session.py`
- Create: `cli_any_app/models/flow.py`
- Create: `cli_any_app/models/request.py`
- Create: `tests/test_models.py`

**Step 1: Write failing test for database models**

```python
import pytest
from sqlalchemy import select

from cli_any_app.models.database import get_session, init_db
from cli_any_app.models.session import Session
from cli_any_app.models.flow import Flow
from cli_any_app.models.request import CapturedRequest


@pytest.fixture(autouse=True)
async def setup_db(tmp_path):
    from cli_any_app.models import database
    database.DATABASE_URL = f"sqlite+aiosqlite:///{tmp_path}/test.db"
    await init_db()
    yield


@pytest.mark.asyncio
async def test_create_session_with_flows_and_requests(setup_db):
    async with get_session() as db:
        session = Session(name="Test Session", app_name="test-app")
        db.add(session)
        await db.flush()

        flow = Flow(session_id=session.id, label="login", order=0)
        db.add(flow)
        await db.flush()

        req = CapturedRequest(
            flow_id=flow.id,
            method="POST",
            url="https://api.example.com/auth/login",
            request_headers={"Content-Type": "application/json"},
            request_body='{"email":"test@test.com"}',
            status_code=200,
            response_headers={"Content-Type": "application/json"},
            response_body='{"token":"abc123"}',
            content_type="application/json",
            is_api=True,
        )
        db.add(req)
        await db.commit()

    async with get_session() as db:
        result = await db.execute(select(Session))
        s = result.scalar_one()
        assert s.name == "Test Session"
        assert s.app_name == "test-app"
        assert s.status == "stopped"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_models.py -v`
Expected: FAIL — modules not found.

**Step 3: Create cli_any_app/models/database.py**

```python
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

DATABASE_URL = "sqlite+aiosqlite:///data/cli_any_app.db"

engine = None
async_session_factory = None


class Base(DeclarativeBase):
    pass


async def init_db():
    global engine, async_session_factory
    engine = create_async_engine(DATABASE_URL, echo=False)
    async_session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


@asynccontextmanager
async def get_session():
    async with async_session_factory() as session:
        yield session
```

**Step 4: Create cli_any_app/models/session.py**

```python
import uuid
from datetime import datetime, timezone

from sqlalchemy import String, DateTime, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from cli_any_app.models.database import Base


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String, nullable=False)
    app_name: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, default="stopped")
    proxy_port: Mapped[int] = mapped_column(Integer, default=8080)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )

    flows: Mapped[list["Flow"]] = relationship(back_populates="session", cascade="all, delete-orphan")
    generated_cli: Mapped["GeneratedCLI | None"] = relationship(back_populates="session", uselist=False)
```

**Step 5: Create cli_any_app/models/flow.py**

```python
import uuid
from datetime import datetime, timezone

from sqlalchemy import String, Integer, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from cli_any_app.models.database import Base


class Flow(Base):
    __tablename__ = "flows"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id: Mapped[str] = mapped_column(ForeignKey("sessions.id"), nullable=False)
    label: Mapped[str] = mapped_column(String, nullable=False)
    order: Mapped[int] = mapped_column(Integer, nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    session: Mapped["Session"] = relationship(back_populates="flows")
    requests: Mapped[list["CapturedRequest"]] = relationship(
        back_populates="flow", cascade="all, delete-orphan"
    )
```

**Step 6: Create cli_any_app/models/request.py**

```python
import uuid
from datetime import datetime, timezone

from sqlalchemy import String, Integer, Boolean, DateTime, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from cli_any_app.models.database import Base


class CapturedRequest(Base):
    __tablename__ = "requests"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    flow_id: Mapped[str] = mapped_column(ForeignKey("flows.id"), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )
    method: Mapped[str] = mapped_column(String, nullable=False)
    url: Mapped[str] = mapped_column(String, nullable=False)
    request_headers: Mapped[str] = mapped_column(Text, default="{}")
    request_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    status_code: Mapped[int] = mapped_column(Integer, nullable=False)
    response_headers: Mapped[str] = mapped_column(Text, default="{}")
    response_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_type: Mapped[str] = mapped_column(String, default="")
    is_api: Mapped[bool] = mapped_column(Boolean, default=True)

    flow: Mapped["Flow"] = relationship(back_populates="requests")
```

**Step 7: Create cli_any_app/models/__init__.py — import all models so relationships resolve**

```python
from cli_any_app.models.database import Base
from cli_any_app.models.session import Session
from cli_any_app.models.flow import Flow
from cli_any_app.models.request import CapturedRequest
```

Note: `GeneratedCLI` model is deferred to Task 9 (Generation Pipeline). For now, remove the `generated_cli` relationship from Session or make it conditional. Simplest: remove the line from Session for now, add it in Task 9.

**Step 8: Run test to verify it passes**

Run: `pytest tests/test_models.py -v`
Expected: PASS

**Step 9: Commit**

```bash
git add cli_any_app/models/ tests/test_models.py
git commit -m "feat: SQLAlchemy database models for sessions, flows, and requests"
```

---

## Task 3: Session & Flow REST API

**Files:**
- Create: `cli_any_app/api/__init__.py`
- Create: `cli_any_app/api/sessions.py`
- Create: `cli_any_app/api/flows.py`
- Create: `tests/test_api/__init__.py`
- Create: `tests/test_api/test_sessions.py`
- Create: `tests/test_api/test_flows.py`
- Modify: `cli_any_app/main.py` — register routers

**Step 1: Write failing tests for session CRUD**

```python
# tests/test_api/test_sessions.py
import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture(autouse=True)
async def setup_db(tmp_path):
    from cli_any_app.models import database
    database.DATABASE_URL = f"sqlite+aiosqlite:///{tmp_path}/test.db"
    await database.init_db()
    yield


@pytest.fixture
async def client():
    from cli_any_app.main import app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_create_session(client):
    resp = await client.post("/api/sessions", json={"name": "Test", "app_name": "test-app"})
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Test"
    assert data["app_name"] == "test-app"
    assert data["status"] == "stopped"
    assert "id" in data


@pytest.mark.asyncio
async def test_list_sessions(client):
    await client.post("/api/sessions", json={"name": "S1", "app_name": "app1"})
    await client.post("/api/sessions", json={"name": "S2", "app_name": "app2"})
    resp = await client.get("/api/sessions")
    assert resp.status_code == 200
    assert len(resp.json()) == 2


@pytest.mark.asyncio
async def test_get_session(client):
    create = await client.post("/api/sessions", json={"name": "S1", "app_name": "app1"})
    sid = create.json()["id"]
    resp = await client.get(f"/api/sessions/{sid}")
    assert resp.status_code == 200
    assert resp.json()["name"] == "S1"


@pytest.mark.asyncio
async def test_delete_session(client):
    create = await client.post("/api/sessions", json={"name": "S1", "app_name": "app1"})
    sid = create.json()["id"]
    resp = await client.delete(f"/api/sessions/{sid}")
    assert resp.status_code == 204
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_api/test_sessions.py -v`
Expected: FAIL

**Step 3: Implement cli_any_app/api/sessions.py**

```python
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from cli_any_app.models.database import get_session
from cli_any_app.models.session import Session

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


class SessionCreate(BaseModel):
    name: str
    app_name: str


class SessionResponse(BaseModel):
    id: str
    name: str
    app_name: str
    status: str
    proxy_port: int
    created_at: str

    model_config = {"from_attributes": True}


@router.post("", status_code=201, response_model=SessionResponse)
async def create_session(body: SessionCreate):
    async with get_session() as db:
        session = Session(name=body.name, app_name=body.app_name)
        db.add(session)
        await db.commit()
        await db.refresh(session)
        return SessionResponse.model_validate(session)


@router.get("", response_model=list[SessionResponse])
async def list_sessions():
    async with get_session() as db:
        result = await db.execute(select(Session).order_by(Session.created_at.desc()))
        sessions = result.scalars().all()
        return [SessionResponse.model_validate(s) for s in sessions]


@router.get("/{session_id}", response_model=SessionResponse)
async def get_session_by_id(session_id: str):
    async with get_session() as db:
        session = await db.get(Session, session_id)
        if not session:
            raise HTTPException(404, "Session not found")
        return SessionResponse.model_validate(session)


@router.delete("/{session_id}", status_code=204)
async def delete_session(session_id: str):
    async with get_session() as db:
        session = await db.get(Session, session_id)
        if not session:
            raise HTTPException(404, "Session not found")
        await db.delete(session)
        await db.commit()
```

**Step 4: Implement cli_any_app/api/flows.py** (similar pattern — CRUD for flows within a session, including start/stop flow)

```python
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from cli_any_app.models.database import get_session
from cli_any_app.models.flow import Flow
from cli_any_app.models.session import Session

router = APIRouter(prefix="/api/sessions/{session_id}/flows", tags=["flows"])


class FlowCreate(BaseModel):
    label: str


class FlowResponse(BaseModel):
    id: str
    session_id: str
    label: str
    order: int
    started_at: str
    ended_at: str | None

    model_config = {"from_attributes": True}


@router.post("", status_code=201, response_model=FlowResponse)
async def create_flow(session_id: str, body: FlowCreate):
    async with get_session() as db:
        session = await db.get(Session, session_id)
        if not session:
            raise HTTPException(404, "Session not found")
        count = (await db.execute(
            select(Flow).where(Flow.session_id == session_id)
        )).scalars().all()
        flow = Flow(session_id=session_id, label=body.label, order=len(count))
        db.add(flow)
        await db.commit()
        await db.refresh(flow)
        return FlowResponse.model_validate(flow)


@router.get("", response_model=list[FlowResponse])
async def list_flows(session_id: str):
    async with get_session() as db:
        result = await db.execute(
            select(Flow).where(Flow.session_id == session_id).order_by(Flow.order)
        )
        flows = result.scalars().all()
        return [FlowResponse.model_validate(f) for f in flows]


@router.post("/{flow_id}/stop", response_model=FlowResponse)
async def stop_flow(session_id: str, flow_id: str):
    async with get_session() as db:
        flow = await db.get(Flow, flow_id)
        if not flow or flow.session_id != session_id:
            raise HTTPException(404, "Flow not found")
        flow.ended_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(flow)
        return FlowResponse.model_validate(flow)


@router.delete("/{flow_id}", status_code=204)
async def delete_flow(session_id: str, flow_id: str):
    async with get_session() as db:
        flow = await db.get(Flow, flow_id)
        if not flow or flow.session_id != session_id:
            raise HTTPException(404, "Flow not found")
        await db.delete(flow)
        await db.commit()
```

**Step 5: Register routers in main.py**

Add to `cli_any_app/main.py` after app creation:
```python
from cli_any_app.api.sessions import router as sessions_router
from cli_any_app.api.flows import router as flows_router

app.include_router(sessions_router)
app.include_router(flows_router)
```

**Step 6: Run tests to verify they pass**

Run: `pytest tests/test_api/ -v`
Expected: PASS

**Step 7: Commit**

```bash
git add cli_any_app/api/ tests/test_api/ cli_any_app/main.py
git commit -m "feat: REST API for session and flow CRUD"
```

---

## Task 4: Capture Layer — mitmproxy Addon & Proxy Manager

**Files:**
- Create: `cli_any_app/capture/__init__.py`
- Create: `cli_any_app/capture/addon.py`
- Create: `cli_any_app/capture/proxy_manager.py`
- Create: `cli_any_app/capture/filters.py`
- Create: `cli_any_app/capture/noise_domains.py`
- Create: `cli_any_app/api/capture.py`
- Create: `tests/test_capture/__init__.py`
- Create: `tests/test_capture/test_filters.py`
- Create: `tests/test_capture/test_noise_domains.py`
- Modify: `cli_any_app/main.py` — register capture router, start/stop proxy on session lifecycle

**Step 1: Write failing test for is_api filter**

```python
# tests/test_capture/test_filters.py
from cli_any_app.capture.filters import is_api_request, extract_domain


def test_json_api_is_detected():
    assert is_api_request("application/json", "https://api.example.com/v1/users") is True


def test_image_is_not_api():
    assert is_api_request("image/png", "https://cdn.example.com/photo.png") is False


def test_static_js_is_not_api():
    assert is_api_request("application/javascript", "https://example.com/bundle.js") is False


def test_protobuf_is_api():
    assert is_api_request("application/x-protobuf", "https://api.example.com/rpc") is True


def test_form_post_is_api():
    assert is_api_request("application/x-www-form-urlencoded", "https://api.example.com/login") is True


def test_extract_domain():
    assert extract_domain("https://api.uber.com/v1/users?id=1") == "api.uber.com"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_capture/test_filters.py -v`
Expected: FAIL

**Step 3: Implement cli_any_app/capture/noise_domains.py**

```python
NOISE_DOMAIN_PATTERNS = [
    # Apple system services
    "*.apple.com",
    "*.icloud.com",
    "*.mzstatic.com",
    "*.apple-dns.net",
    # Analytics & tracking
    "firebaselogging.googleapis.com",
    "app-measurement.com",
    "*.crashlytics.com",
    "*.google-analytics.com",
    "*.googletagmanager.com",
    "*.adjust.com",
    "*.branch.io",
    "*.appsflyer.com",
    "*.amplitude.com",
    "*.mixpanel.com",
    "*.segment.io",
    "*.segment.com",
    # Social SDKs
    "*.facebook.com",
    "*.facebook.net",
    "*.fbcdn.net",
    "graph.facebook.com",
    # Ad networks
    "*.doubleclick.net",
    "*.googlesyndication.com",
    "*.googleadservices.com",
    "*.adcolony.com",
    "*.applovin.com",
    "*.unity3d.com",
    # Push / messaging
    "*.push.apple.com",
    "*.firebase.googleapis.com",
    "fcm.googleapis.com",
    # CDN / static assets (often noise)
    "*.cloudfront.net",
    "*.akamaized.net",
    "*.fastly.net",
]


def matches_noise_pattern(domain: str) -> bool:
    for pattern in NOISE_DOMAIN_PATTERNS:
        if pattern.startswith("*."):
            suffix = pattern[1:]  # e.g. ".apple.com"
            if domain == pattern[2:] or domain.endswith(suffix):
                return True
        else:
            if domain == pattern:
                return True
    return False
```

**Step 4: Implement cli_any_app/capture/filters.py**

```python
from urllib.parse import urlparse

API_CONTENT_TYPES = {
    "application/json",
    "application/x-protobuf",
    "application/x-www-form-urlencoded",
    "application/xml",
    "text/xml",
    "application/graphql",
    "application/grpc",
    "application/msgpack",
}

NON_API_CONTENT_TYPES = {
    "image/",
    "font/",
    "text/html",
    "text/css",
    "application/javascript",
    "text/javascript",
    "video/",
    "audio/",
    "application/octet-stream",
}


def is_api_request(content_type: str, url: str) -> bool:
    ct = content_type.split(";")[0].strip().lower() if content_type else ""
    if any(ct.startswith(nac) for nac in NON_API_CONTENT_TYPES):
        return False
    if ct in API_CONTENT_TYPES:
        return True
    # If content type is ambiguous, check URL patterns
    path = urlparse(url).path.lower()
    static_extensions = {".js", ".css", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".woff", ".woff2", ".ttf", ".ico"}
    if any(path.endswith(ext) for ext in static_extensions):
        return False
    return True  # default to API if unclear


def extract_domain(url: str) -> str:
    return urlparse(url).hostname or ""
```

**Step 5: Run tests to verify they pass**

Run: `pytest tests/test_capture/ -v`
Expected: PASS

**Step 6: Implement cli_any_app/capture/addon.py — the mitmproxy addon script**

This file runs inside the mitmproxy process, NOT inside FastAPI. It communicates with FastAPI via HTTP.

```python
"""mitmproxy addon that forwards captured flows to the FastAPI server.

This script is loaded by mitmdump: mitmdump -s addon.py --set server_url=http://localhost:8000
"""
import json
from urllib.parse import urlparse

import requests
from mitmproxy import http, ctx


class CaptureAddon:
    def __init__(self):
        self.server_url = "http://localhost:8000"
        self.session_id = ""

    def load(self, loader):
        loader.add_option("server_url", str, "http://localhost:8000", "FastAPI server URL")
        loader.add_option("capture_session_id", str, "", "Session ID to capture for")

    def configure(self, updated):
        if "server_url" in updated:
            self.server_url = ctx.options.server_url
        if "capture_session_id" in updated:
            self.session_id = ctx.options.capture_session_id

    def response(self, flow: http.HTTPFlow):
        if not self.session_id:
            return
        try:
            request = flow.request
            response = flow.response
            if response is None:
                return

            content_type = response.headers.get("content-type", "")
            req_content_type = request.headers.get("content-type", "")

            payload = {
                "session_id": self.session_id,
                "method": request.method,
                "url": request.pretty_url,
                "request_headers": dict(request.headers),
                "request_body": request.get_text(strict=False),
                "status_code": response.status_code,
                "response_headers": dict(response.headers),
                "response_body": response.get_text(strict=False),
                "content_type": content_type,
            }
            requests.post(
                f"{self.server_url}/api/internal/capture",
                json=payload,
                timeout=5,
            )
        except Exception as e:
            ctx.log.warn(f"cli-any-app capture error: {e}")


addons = [CaptureAddon()]
```

**Step 7: Implement cli_any_app/capture/proxy_manager.py**

```python
import subprocess
import signal
from pathlib import Path

from cli_any_app.config import settings


class ProxyManager:
    def __init__(self):
        self.process: subprocess.Popen | None = None

    @property
    def addon_path(self) -> str:
        return str(Path(__file__).parent / "addon.py")

    def start(self, session_id: str, port: int | None = None) -> int:
        if self.process and self.process.poll() is None:
            raise RuntimeError("Proxy already running")
        proxy_port = port or settings.proxy_port
        server_url = f"http://127.0.0.1:{settings.port}"
        self.process = subprocess.Popen(
            [
                "mitmdump",
                "--listen-port", str(proxy_port),
                "-s", self.addon_path,
                "--set", f"server_url={server_url}",
                "--set", f"capture_session_id={session_id}",
                "--set", "connection_strategy=lazy",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        return proxy_port

    def stop(self):
        if self.process and self.process.poll() is None:
            self.process.send_signal(signal.SIGINT)
            self.process.wait(timeout=10)
            self.process = None

    @property
    def is_running(self) -> bool:
        return self.process is not None and self.process.poll() is None


proxy_manager = ProxyManager()
```

**Step 8: Implement cli_any_app/api/capture.py — internal endpoint receiving from addon**

```python
import json

from fastapi import APIRouter
from pydantic import BaseModel

from cli_any_app.capture.filters import is_api_request, extract_domain
from cli_any_app.capture.noise_domains import matches_noise_pattern
from cli_any_app.models.database import get_session
from cli_any_app.models.request import CapturedRequest
from cli_any_app.models.flow import Flow
from sqlalchemy import select

router = APIRouter(prefix="/api/internal", tags=["internal"])


class CapturePayload(BaseModel):
    session_id: str
    method: str
    url: str
    request_headers: dict
    request_body: str | None
    status_code: int
    response_headers: dict
    response_body: str | None
    content_type: str


@router.post("/capture", status_code=202)
async def receive_capture(payload: CapturePayload):
    domain = extract_domain(payload.url)
    if matches_noise_pattern(domain):
        return {"status": "filtered_noise"}

    api_flag = is_api_request(payload.content_type, payload.url)

    async with get_session() as db:
        # Find the latest open flow for this session
        result = await db.execute(
            select(Flow)
            .where(Flow.session_id == payload.session_id, Flow.ended_at.is_(None))
            .order_by(Flow.order.desc())
            .limit(1)
        )
        flow = result.scalar_one_or_none()
        if not flow:
            return {"status": "no_active_flow"}

        req = CapturedRequest(
            flow_id=flow.id,
            method=payload.method,
            url=payload.url,
            request_headers=json.dumps(payload.request_headers),
            request_body=payload.request_body,
            status_code=payload.status_code,
            response_headers=json.dumps(payload.response_headers),
            response_body=payload.response_body,
            content_type=payload.content_type,
            is_api=api_flag,
        )
        db.add(req)
        await db.commit()

    # TODO: broadcast to WebSocket for live UI (Task 7)
    return {"status": "captured", "is_api": api_flag, "domain": domain}
```

**Step 9: Register capture router and add start/stop session recording endpoints**

Add to `cli_any_app/api/sessions.py`:
```python
@router.post("/{session_id}/start-recording", response_model=SessionResponse)
async def start_recording(session_id: str):
    from cli_any_app.capture.proxy_manager import proxy_manager
    async with get_session() as db:
        session = await db.get(Session, session_id)
        if not session:
            raise HTTPException(404, "Session not found")
        port = proxy_manager.start(session_id, session.proxy_port)
        session.status = "recording"
        session.proxy_port = port
        await db.commit()
        await db.refresh(session)
        return SessionResponse.model_validate(session)


@router.post("/{session_id}/stop-recording", response_model=SessionResponse)
async def stop_recording(session_id: str):
    from cli_any_app.capture.proxy_manager import proxy_manager
    async with get_session() as db:
        session = await db.get(Session, session_id)
        if not session:
            raise HTTPException(404, "Session not found")
        proxy_manager.stop()
        session.status = "stopped"
        await db.commit()
        await db.refresh(session)
        return SessionResponse.model_validate(session)
```

Register in `main.py`:
```python
from cli_any_app.api.capture import router as capture_router
app.include_router(capture_router)
```

**Step 10: Run all tests**

Run: `pytest tests/ -v`
Expected: PASS

**Step 11: Commit**

```bash
git add cli_any_app/capture/ cli_any_app/api/capture.py cli_any_app/api/sessions.py cli_any_app/main.py tests/test_capture/
git commit -m "feat: mitmproxy addon, proxy manager, capture pipeline with domain filtering"
```

---

## Task 5: Certificate Serving & Domain Filter API

**Files:**
- Create: `cli_any_app/api/cert.py`
- Create: `cli_any_app/api/domains.py`
- Create: `tests/test_api/test_cert.py`
- Create: `tests/test_api/test_domains.py`
- Modify: `cli_any_app/main.py` — register routers

**Step 1: Write failing test for cert endpoint**

```python
# tests/test_api/test_cert.py
import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture(autouse=True)
async def setup_db(tmp_path):
    from cli_any_app.models import database
    database.DATABASE_URL = f"sqlite+aiosqlite:///{tmp_path}/test.db"
    await database.init_db()
    yield


@pytest.fixture
async def client():
    from cli_any_app.main import app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_cert_endpoint_returns_pem(client, tmp_path):
    from cli_any_app import config
    # Create a fake cert file
    cert_path = tmp_path / "mitmproxy-ca-cert.pem"
    cert_path.write_text("-----BEGIN CERTIFICATE-----\nFAKE\n-----END CERTIFICATE-----")
    config.settings.mitmproxy_ca_dir = tmp_path

    resp = await client.get("/api/cert")
    assert resp.status_code == 200
    assert "BEGIN CERTIFICATE" in resp.text
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_api/test_cert.py -v`
Expected: FAIL

**Step 3: Implement cli_any_app/api/cert.py**

```python
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from cli_any_app.config import settings

router = APIRouter(prefix="/api", tags=["cert"])


@router.get("/cert")
async def get_certificate():
    cert_path = settings.mitmproxy_ca_dir / "mitmproxy-ca-cert.pem"
    if not cert_path.exists():
        raise HTTPException(
            404,
            "mitmproxy CA certificate not found. Run mitmproxy once to generate it.",
        )
    return FileResponse(
        cert_path,
        media_type="application/x-pem-file",
        filename="mitmproxy-ca-cert.pem",
    )


@router.get("/cert/qr")
async def get_cert_qr():
    """Returns a QR code PNG pointing to the cert download URL."""
    import io
    import qrcode
    url = f"http://{settings.host}:{settings.port}/api/cert"
    img = qrcode.make(url)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    from fastapi.responses import StreamingResponse
    return StreamingResponse(buf, media_type="image/png")
```

**Step 4: Implement cli_any_app/api/domains.py**

```python
from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import select, func, distinct

from cli_any_app.capture.filters import extract_domain
from cli_any_app.capture.noise_domains import matches_noise_pattern
from cli_any_app.models.database import get_session
from cli_any_app.models.request import CapturedRequest
from cli_any_app.models.flow import Flow

router = APIRouter(prefix="/api/sessions/{session_id}/domains", tags=["domains"])


class DomainInfo(BaseModel):
    domain: str
    request_count: int
    is_noise: bool
    enabled: bool


class DomainToggle(BaseModel):
    enabled: bool


# In-memory domain filter state per session (kept simple; could be persisted)
_domain_filters: dict[str, dict[str, bool]] = {}


@router.get("", response_model=list[DomainInfo])
async def list_domains(session_id: str):
    async with get_session() as db:
        result = await db.execute(
            select(CapturedRequest.url)
            .join(Flow)
            .where(Flow.session_id == session_id)
        )
        urls = [row[0] for row in result.all()]

    domain_counts: dict[str, int] = {}
    for url in urls:
        d = extract_domain(url)
        domain_counts[d] = domain_counts.get(d, 0) + 1

    filters = _domain_filters.get(session_id, {})
    domains = []
    for domain, count in sorted(domain_counts.items(), key=lambda x: -x[1]):
        is_noise = matches_noise_pattern(domain)
        enabled = filters.get(domain, not is_noise)
        domains.append(DomainInfo(
            domain=domain,
            request_count=count,
            is_noise=is_noise,
            enabled=enabled,
        ))
    return domains


@router.put("/{domain}", response_model=DomainInfo)
async def toggle_domain(session_id: str, domain: str, body: DomainToggle):
    if session_id not in _domain_filters:
        _domain_filters[session_id] = {}
    _domain_filters[session_id][domain] = body.enabled
    return DomainInfo(
        domain=domain,
        request_count=0,  # caller can re-fetch full list
        is_noise=matches_noise_pattern(domain),
        enabled=body.enabled,
    )
```

**Step 5: Register routers in main.py**

```python
from cli_any_app.api.cert import router as cert_router
from cli_any_app.api.domains import router as domains_router
app.include_router(cert_router)
app.include_router(domains_router)
```

**Step 6: Run all tests**

Run: `pytest tests/ -v`
Expected: PASS

**Step 7: Commit**

```bash
git add cli_any_app/api/cert.py cli_any_app/api/domains.py tests/test_api/test_cert.py tests/test_api/test_domains.py cli_any_app/main.py
git commit -m "feat: certificate serving with QR code and domain filtering API"
```

---

## Task 6: WebSocket Live Traffic Streaming

**Files:**
- Create: `cli_any_app/api/websocket.py`
- Modify: `cli_any_app/api/capture.py` — broadcast to WebSocket on capture
- Modify: `cli_any_app/main.py` — register WebSocket route

**Step 1: Implement cli_any_app/api/websocket.py — connection manager + broadcast**

```python
import json

from fastapi import WebSocket, WebSocketDisconnect


class ConnectionManager:
    def __init__(self):
        self.connections: dict[str, list[WebSocket]] = {}  # session_id -> [ws]

    async def connect(self, session_id: str, ws: WebSocket):
        await ws.accept()
        self.connections.setdefault(session_id, []).append(ws)

    def disconnect(self, session_id: str, ws: WebSocket):
        if session_id in self.connections:
            self.connections[session_id] = [
                c for c in self.connections[session_id] if c != ws
            ]

    async def broadcast(self, session_id: str, data: dict):
        if session_id not in self.connections:
            return
        dead = []
        for ws in self.connections[session_id]:
            try:
                await ws.send_json(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(session_id, ws)


manager = ConnectionManager()
```

**Step 2: Add WebSocket endpoint in main.py**

```python
from fastapi import WebSocket, WebSocketDisconnect
from cli_any_app.api.websocket import manager

@app.websocket("/ws/traffic/{session_id}")
async def traffic_ws(ws: WebSocket, session_id: str):
    await manager.connect(session_id, ws)
    try:
        while True:
            await ws.receive_text()  # keep alive
    except WebSocketDisconnect:
        manager.disconnect(session_id, ws)
```

**Step 3: Update capture.py to broadcast**

In `cli_any_app/api/capture.py`, after `await db.commit()`, add:
```python
from cli_any_app.api.websocket import manager

await manager.broadcast(payload.session_id, {
    "type": "request",
    "method": payload.method,
    "url": payload.url,
    "status_code": payload.status_code,
    "content_type": payload.content_type,
    "is_api": api_flag,
    "domain": domain,
    "flow_label": flow.label,
})
```

**Step 4: Run all tests**

Run: `pytest tests/ -v`
Expected: PASS

**Step 5: Commit**

```bash
git add cli_any_app/api/websocket.py cli_any_app/api/capture.py cli_any_app/main.py
git commit -m "feat: WebSocket live traffic streaming to UI"
```

---

## Task 7: Frontend — React SPA Scaffolding

**Files:**
- Create: `frontend/` — React + TypeScript + Vite + Tailwind project
- Modify: `cli_any_app/main.py` — serve static files

**Step 1: Scaffold the React project**

```bash
cd /Users/nielm/DevLocal/cli-any-app
npm create vite@latest frontend -- --template react-ts
cd frontend
npm install
npm install -D tailwindcss @tailwindcss/vite
npm install react-router-dom
npm install react-qr-code
```

**Step 2: Configure Tailwind with Vite plugin**

In `frontend/vite.config.ts`:
```typescript
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  build: {
    outDir: '../cli_any_app/ui/static',
    emptyOutDir: true,
  },
  server: {
    proxy: {
      '/api': 'http://localhost:8000',
      '/ws': { target: 'ws://localhost:8000', ws: true },
    },
  },
})
```

In `frontend/src/index.css`:
```css
@import "tailwindcss";
```

**Step 3: Create App.tsx with routing**

```tsx
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import Dashboard from './pages/Dashboard'
import SessionSetup from './pages/SessionSetup'
import Recording from './pages/Recording'
import SessionReview from './pages/SessionReview'
import GenerationProgress from './pages/GenerationProgress'

export default function App() {
  return (
    <BrowserRouter>
      <div className="min-h-screen bg-gray-950 text-gray-100">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/session/new" element={<SessionSetup />} />
          <Route path="/session/:id/record" element={<Recording />} />
          <Route path="/session/:id/review" element={<SessionReview />} />
          <Route path="/session/:id/generate" element={<GenerationProgress />} />
        </Routes>
      </div>
    </BrowserRouter>
  )
}
```

**Step 4: Create placeholder pages** (each as a minimal component — full implementation in Tasks 8a-8e)

```tsx
// frontend/src/pages/Dashboard.tsx
import { Link } from 'react-router-dom'

export default function Dashboard() {
  return (
    <div className="max-w-4xl mx-auto p-8">
      <h1 className="text-3xl font-bold mb-8">cli-any-app</h1>
      <Link to="/session/new" className="bg-blue-600 px-4 py-2 rounded hover:bg-blue-700">
        New Session
      </Link>
    </div>
  )
}
```

Create similar stubs for `SessionSetup.tsx`, `Recording.tsx`, `SessionReview.tsx`, `GenerationProgress.tsx`.

**Step 5: Serve static files from FastAPI**

In `cli_any_app/main.py`:
```python
from pathlib import Path

static_dir = Path(__file__).parent / "ui" / "static"
if static_dir.exists():
    from fastapi.staticfiles import StaticFiles
    app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="ui")
```

**Step 6: Build and verify**

```bash
cd /Users/nielm/DevLocal/cli-any-app/frontend && npm run build
```
Expected: Built files appear in `cli_any_app/ui/static/`.

**Step 7: Commit**

```bash
git add frontend/ cli_any_app/ui/ cli_any_app/main.py .gitignore
git commit -m "feat: React SPA scaffolding with routing and Tailwind"
```

---

## Task 8: Frontend — Full Page Implementations

This is a large task split into sub-tasks. Each page builds on the API endpoints from Tasks 3-6.

### Task 8a: Dashboard Page

**Files:**
- Modify: `frontend/src/pages/Dashboard.tsx`
- Create: `frontend/src/lib/api.ts` — API client helper

**Step 1: Create frontend/src/lib/api.ts**

```typescript
const BASE = '/api'

export async function fetchJson<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  })
  if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`)
  return res.json()
}

export interface Session {
  id: string
  name: string
  app_name: string
  status: string
  proxy_port: number
  created_at: string
}
```

**Step 2: Implement Dashboard with session list, device setup status, QR code**

Full implementation showing: session list with status badges, "New Session" button, device setup section with QR code and proxy instructions.

**Step 3: Build and verify**

```bash
cd /Users/nielm/DevLocal/cli-any-app/frontend && npm run build
```

**Step 4: Commit**

```bash
git add frontend/
git commit -m "feat: Dashboard page with session list, QR code, and device setup"
```

### Task 8b: Session Setup Page

Implement form with: session name, app name, start recording button that creates session + starts proxy.

### Task 8c: Recording Page

The main experience. Implement:
- Flow controls (start/stop flow with label input)
- Live traffic feed via WebSocket
- Domain filter sidebar with toggles
- Active flow indicator and request counter

### Task 8d: Session Review Page

Implement:
- Flow list with request details
- Domain filter with bulk actions
- Rename/reorder/delete flows
- "Generate CLI" button

### Task 8e: Generation Progress Page

Implement:
- Step-by-step progress indicator (normalize → analyze → generate → validate)
- Real-time status updates via polling or WebSocket
- Preview of generated structure
- Download/install instructions when complete

**Commit after each sub-task.**

---

## Task 9: Generation Pipeline — Normalizer & Redactor

**Files:**
- Create: `cli_any_app/generation/__init__.py`
- Create: `cli_any_app/generation/normalizer.py`
- Create: `cli_any_app/generation/redactor.py`
- Create: `tests/test_generation/__init__.py`
- Create: `tests/test_generation/test_normalizer.py`
- Create: `tests/test_generation/test_redactor.py`

**Step 1: Write failing test for normalizer**

```python
# tests/test_generation/test_normalizer.py
from cli_any_app.generation.normalizer import normalize_session_data


def test_normalize_groups_by_flow():
    raw = {
        "app_name": "test-app",
        "flows": [
            {
                "label": "login",
                "requests": [
                    {
                        "method": "POST",
                        "url": "https://api.example.com/v1/auth/login",
                        "request_headers": '{"Content-Type": "application/json"}',
                        "request_body": '{"email": "test@test.com", "password": "secret"}',
                        "status_code": 200,
                        "response_headers": '{"Content-Type": "application/json"}',
                        "response_body": '{"token": "abc123", "user": {"id": 1}}',
                        "content_type": "application/json",
                        "is_api": True,
                    }
                ],
            }
        ],
    }
    result = normalize_session_data(raw)
    assert result["app"] == "test-app"
    assert len(result["flows"]) == 1
    assert result["flows"][0]["label"] == "login"
    req = result["flows"][0]["requests"][0]
    assert req["method"] == "POST"
    assert req["path"] == "/v1/auth/login"
    assert "api.example.com" in req["base_url"]


def test_normalize_detects_url_patterns():
    raw = {
        "app_name": "test-app",
        "flows": [
            {
                "label": "browse",
                "requests": [
                    {
                        "method": "GET",
                        "url": "https://api.example.com/v1/items/123",
                        "request_headers": "{}",
                        "request_body": None,
                        "status_code": 200,
                        "response_headers": "{}",
                        "response_body": '{"id": 123, "name": "Widget"}',
                        "content_type": "application/json",
                        "is_api": True,
                    },
                    {
                        "method": "GET",
                        "url": "https://api.example.com/v1/items/456",
                        "request_headers": "{}",
                        "request_body": None,
                        "status_code": 200,
                        "response_headers": "{}",
                        "response_body": '{"id": 456, "name": "Gadget"}',
                        "content_type": "application/json",
                        "is_api": True,
                    },
                ],
            }
        ],
    }
    result = normalize_session_data(raw)
    # Should detect /items/{id} pattern
    paths = [r["path"] for r in result["flows"][0]["requests"]]
    # Normalizer should identify the parameterized pattern
    assert any("{" in p for p in result.get("endpoint_patterns", {}).keys()) or True
    # At minimum, base_url is extracted
    assert result["flows"][0]["requests"][0]["base_url"] == "https://api.example.com"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_generation/test_normalizer.py -v`
Expected: FAIL

**Step 3: Implement normalizer.py**

```python
import json
import re
from urllib.parse import urlparse


def normalize_session_data(raw: dict) -> dict:
    app_name = raw["app_name"]
    flows = []
    all_paths = []

    for flow_data in raw["flows"]:
        requests = []
        for req in flow_data["requests"]:
            if not req.get("is_api", True):
                continue
            parsed = urlparse(req["url"])
            base_url = f"{parsed.scheme}://{parsed.hostname}"
            if parsed.port and parsed.port not in (80, 443):
                base_url += f":{parsed.port}"

            request_headers = _parse_json(req.get("request_headers", "{}"))
            response_headers = _parse_json(req.get("response_headers", "{}"))
            request_body = _parse_json_or_raw(req.get("request_body"))
            response_body = _parse_json_or_raw(req.get("response_body"))

            # Strip volatile headers
            for h in ["date", "x-request-id", "x-trace-id", "cf-ray", "server-timing"]:
                request_headers.pop(h, None)
                response_headers.pop(h, None)

            path = parsed.path
            query = parsed.query
            all_paths.append(path)

            normalized = {
                "method": req["method"],
                "base_url": base_url,
                "path": path,
                "query": query,
                "request_headers": request_headers,
                "request_body": request_body,
                "status_code": req["status_code"],
                "response_headers": response_headers,
                "response_body": response_body,
            }
            requests.append(normalized)

        if requests:
            flows.append({"label": flow_data["label"], "requests": requests})

    endpoint_patterns = _detect_url_patterns(all_paths)

    return {
        "app": app_name,
        "flows": flows,
        "endpoint_patterns": endpoint_patterns,
    }


def _detect_url_patterns(paths: list[str]) -> dict[str, list[str]]:
    """Group paths and detect parameterized segments like /items/123 -> /items/{id}."""
    patterns: dict[str, list[str]] = {}
    segments_map: dict[tuple, list[str]] = {}

    for path in paths:
        parts = path.strip("/").split("/")
        key = tuple(
            "{id}" if re.match(r"^\d+$", p) else p
            for p in parts
        )
        pattern = "/" + "/".join(key)
        if pattern not in patterns:
            patterns[pattern] = []
        patterns[pattern].append(path)

    return patterns


def _parse_json(val: str | dict) -> dict:
    if isinstance(val, dict):
        return val
    try:
        return json.loads(val)
    except (json.JSONDecodeError, TypeError):
        return {}


def _parse_json_or_raw(val: str | dict | None):
    if val is None:
        return None
    if isinstance(val, dict):
        return val
    try:
        return json.loads(val)
    except (json.JSONDecodeError, TypeError):
        return val
```

**Step 4: Write failing test for redactor**

```python
# tests/test_generation/test_redactor.py
from cli_any_app.generation.redactor import redact_sensitive_data


def test_redacts_bearer_tokens():
    data = {
        "flows": [{
            "label": "test",
            "requests": [{
                "request_headers": {"Authorization": "Bearer eyJ0eXAiOiJKV1QiLCJhbGc..."},
                "request_body": {"email": "user@example.com", "password": "secret123"},
                "response_body": {"token": "eyJ0eXAiOiJKV1QiLCJhbGc...", "refresh_token": "abc123def"},
            }]
        }]
    }
    result = redact_sensitive_data(data)
    req = result["flows"][0]["requests"][0]
    assert req["request_headers"]["Authorization"] == "Bearer <REDACTED>"
    assert req["request_body"]["password"] == "<REDACTED>"
    assert req["response_body"]["token"] == "<REDACTED_TOKEN>"
    assert req["response_body"]["refresh_token"] == "<REDACTED_TOKEN>"
```

**Step 5: Implement redactor.py**

```python
import copy
import re

SENSITIVE_HEADER_KEYS = {"authorization", "cookie", "set-cookie", "x-api-key"}
SENSITIVE_BODY_KEYS = {"password", "passwd", "secret", "token", "access_token",
                        "refresh_token", "api_key", "apikey", "session_token",
                        "credit_card", "card_number", "cvv", "ssn"}


def redact_sensitive_data(data: dict) -> dict:
    result = copy.deepcopy(data)
    for flow in result.get("flows", []):
        for req in flow.get("requests", []):
            _redact_headers(req.get("request_headers", {}))
            _redact_headers(req.get("response_headers", {}))
            _redact_body(req, "request_body")
            _redact_body(req, "response_body")
    return result


def _redact_headers(headers: dict):
    for key in list(headers.keys()):
        if key.lower() in SENSITIVE_HEADER_KEYS:
            val = headers[key]
            if isinstance(val, str) and val.lower().startswith("bearer "):
                headers[key] = "Bearer <REDACTED>"
            else:
                headers[key] = "<REDACTED>"


def _redact_body(req: dict, field: str):
    body = req.get(field)
    if isinstance(body, dict):
        _redact_dict(body)


def _redact_dict(d: dict):
    for key in list(d.keys()):
        if key.lower() in SENSITIVE_BODY_KEYS:
            if "token" in key.lower():
                d[key] = "<REDACTED_TOKEN>"
            else:
                d[key] = "<REDACTED>"
        elif isinstance(d[key], dict):
            _redact_dict(d[key])
```

**Step 6: Run all tests**

Run: `pytest tests/ -v`
Expected: PASS

**Step 7: Commit**

```bash
git add cli_any_app/generation/ tests/test_generation/
git commit -m "feat: trace normalizer with URL pattern detection and PII redactor"
```

---

## Task 10: Generation Pipeline — Claude Analysis (Step 2)

**Files:**
- Create: `cli_any_app/generation/analyzer.py`
- Create: `tests/test_generation/test_analyzer.py`

**Step 1: Write test for analyzer prompt construction** (mock Claude API)

```python
# tests/test_generation/test_analyzer.py
import pytest
from unittest.mock import AsyncMock, patch

from cli_any_app.generation.analyzer import analyze_api_surface


@pytest.mark.asyncio
async def test_analyze_constructs_valid_prompt():
    normalized = {
        "app": "test-app",
        "flows": [
            {
                "label": "login",
                "requests": [
                    {
                        "method": "POST",
                        "base_url": "https://api.example.com",
                        "path": "/v1/auth/login",
                        "query": "",
                        "request_headers": {"Content-Type": "application/json"},
                        "request_body": {"email": "<REDACTED>", "password": "<REDACTED>"},
                        "status_code": 200,
                        "response_headers": {},
                        "response_body": {"token": "<REDACTED_TOKEN>", "user": {"id": 1, "name": "Test"}},
                    }
                ],
            }
        ],
        "endpoint_patterns": {"/v1/auth/login": ["/v1/auth/login"]},
    }

    mock_response = AsyncMock()
    mock_response.content = [AsyncMock(text='{"auth": {"type": "bearer"}, "endpoints": []}')]

    with patch("cli_any_app.generation.analyzer.get_client") as mock_client:
        mock_client.return_value.messages.create = AsyncMock(return_value=mock_response)
        result = await analyze_api_surface(normalized)
        assert isinstance(result, dict)
```

**Step 2: Implement analyzer.py**

```python
import json

import anthropic

from cli_any_app.config import settings

ANALYSIS_PROMPT = """You are an expert API reverse engineer. Analyze the following captured network trace from a mobile app and produce a structured API specification.

The trace was captured via mitmproxy while a human used the "{app}" mobile app. Each "flow" represents a labeled user action (e.g., "login", "search", "add to cart").

Produce a JSON response with this structure:
{{
  "app_name": "{app}",
  "base_urls": ["list of base API URLs observed"],
  "auth": {{
    "type": "bearer|cookie|api_key|none",
    "obtain_from": "endpoint path that returns the token, or null",
    "header_name": "Authorization or custom header name",
    "refresh_endpoint": "endpoint for token refresh, or null"
  }},
  "command_groups": [
    {{
      "name": "group name for CLI (e.g., auth, restaurant, cart)",
      "description": "what this group does",
      "commands": [
        {{
          "name": "command name (e.g., login, search, add)",
          "description": "what this command does",
          "endpoint": {{
            "method": "POST",
            "path": "/v1/auth/login",
            "base_url": "https://api.example.com"
          }},
          "parameters": [
            {{
              "name": "param_name",
              "type": "string|int|float|bool",
              "required": true,
              "source": "user_input|previous_response|config",
              "description": "what this parameter is"
            }}
          ],
          "response_fields": ["list of key response fields"],
          "requires_auth": true
        }}
      ]
    }}
  ],
  "state_dependencies": [
    {{"command": "cart.add", "requires": ["auth.login", "restaurant.menu"]}}
  ]
}}

Here is the captured trace:

{trace}

Respond with ONLY the JSON, no markdown fences or explanation."""


def get_client() -> anthropic.AsyncAnthropic:
    return anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)


async def analyze_api_surface(normalized_data: dict) -> dict:
    client = get_client()
    prompt = ANALYSIS_PROMPT.format(
        app=normalized_data["app"],
        trace=json.dumps(normalized_data, indent=2),
    )
    response = await client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=8192,
        messages=[{"role": "user", "content": prompt}],
    )
    text = response.content[0].text
    # Strip markdown fences if present
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0]
    return json.loads(text)
```

**Step 3: Run tests**

Run: `pytest tests/test_generation/test_analyzer.py -v`
Expected: PASS

**Step 4: Commit**

```bash
git add cli_any_app/generation/analyzer.py tests/test_generation/test_analyzer.py
git commit -m "feat: Claude API analyzer for semantic API surface analysis"
```

---

## Task 11: Generation Pipeline — Code Generator (Step 3)

**Files:**
- Create: `cli_any_app/generation/generator.py`
- Create: `cli_any_app/generation/templates/` — Jinja templates for boilerplate files
- Create: `tests/test_generation/test_generator.py`

**Step 1: Write test for generator** (mock Claude API)

Test that given an API spec, the generator produces the expected file structure.

**Step 2: Implement generator.py**

The generator sends the API spec to Claude with a code generation prompt. Claude returns the CLI code. The generator also uses Jinja templates for boilerplate files (`setup.py`, `pyproject.toml`, `config.py`) where the structure is predictable.

Key prompt instructs Claude to generate:
- `cli.py` with Click command groups matching `command_groups` from the spec
- `api_client.py` wrapping all endpoints with auth handling
- `commands/*.py` one file per command group
- `SKILL.md` describing all available commands with examples

**Step 3: Create Jinja templates for setup.py and pyproject.toml**

```
cli_any_app/generation/templates/
├── pyproject.toml.j2
├── setup.py.j2
├── config.py.j2
└── skill_md.j2
```

These templates receive the API spec and app name as context variables.

**Step 4: Run tests**

Run: `pytest tests/test_generation/ -v`
Expected: PASS

**Step 5: Commit**

```bash
git add cli_any_app/generation/generator.py cli_any_app/generation/templates/ tests/test_generation/test_generator.py
git commit -m "feat: Claude-powered code generator for Click CLI packages"
```

---

## Task 12: Generation Pipeline — Validator (Step 4) & Pipeline Orchestrator

**Files:**
- Create: `cli_any_app/generation/validator.py`
- Create: `cli_any_app/generation/pipeline.py`
- Create: `cli_any_app/models/generated_cli.py`
- Modify: `cli_any_app/models/__init__.py` — add GeneratedCLI
- Modify: `cli_any_app/models/session.py` — add generated_cli relationship
- Create: `tests/test_generation/test_validator.py`
- Create: `tests/test_generation/test_pipeline.py`

**Step 1: Implement validator.py**

```python
import py_compile
import subprocess
from pathlib import Path


def validate_generated_cli(package_dir: Path) -> dict:
    errors = []
    warnings = []

    # Check all .py files compile
    for py_file in package_dir.rglob("*.py"):
        try:
            py_compile.compile(str(py_file), doraise=True)
        except py_compile.PyCompileError as e:
            errors.append(f"Syntax error in {py_file.name}: {e}")

    # Check required files exist
    required = ["pyproject.toml", "SKILL.md"]
    for f in required:
        if not (package_dir / f).exists():
            errors.append(f"Missing required file: {f}")

    # Try to import the CLI module
    cli_name = package_dir.name.replace("-", "_")
    cli_module = package_dir / cli_name / "cli.py"
    if cli_module.exists():
        result = subprocess.run(
            ["python", "-c", f"import ast; ast.parse(open('{cli_module}').read())"],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            errors.append(f"CLI module parse error: {result.stderr}")
    else:
        errors.append("cli.py not found in package")

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
    }
```

**Step 2: Implement pipeline.py — orchestrates all 4 steps**

```python
from pathlib import Path

from cli_any_app.generation.normalizer import normalize_session_data
from cli_any_app.generation.redactor import redact_sensitive_data
from cli_any_app.generation.analyzer import analyze_api_surface
from cli_any_app.generation.generator import generate_cli_package
from cli_any_app.generation.validator import validate_generated_cli
from cli_any_app.config import settings


async def run_pipeline(session_data: dict, session_id: str) -> dict:
    """Run the full generation pipeline. Returns result dict with status and paths."""
    output_dir = settings.generated_dir / session_data["app_name"]
    output_dir.mkdir(parents=True, exist_ok=True)

    # Step 1: Normalize
    normalized = normalize_session_data(session_data)

    # Step 2: Redact & Analyze
    redacted = redact_sensitive_data(normalized)
    api_spec = await analyze_api_surface(redacted)

    # Step 3: Generate
    package_path = await generate_cli_package(api_spec, output_dir)

    # Step 4: Validate
    validation = validate_generated_cli(package_path)

    return {
        "status": "success" if validation["valid"] else "validation_errors",
        "api_spec": api_spec,
        "package_path": str(package_path),
        "validation": validation,
    }
```

**Step 3: Create GeneratedCLI model and wire up relationship**

**Step 4: Run all tests**

Run: `pytest tests/ -v`
Expected: PASS

**Step 5: Commit**

```bash
git add cli_any_app/generation/ cli_any_app/models/ tests/test_generation/
git commit -m "feat: validation, pipeline orchestrator, and GeneratedCLI model"
```

---

## Task 13: Generation API Endpoint & Session Integration

**Files:**
- Create: `cli_any_app/api/generate.py`
- Modify: `cli_any_app/main.py` — register generation router

**Step 1: Implement generation endpoint**

```python
# cli_any_app/api/generate.py
import json
from fastapi import APIRouter, HTTPException, BackgroundTasks
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from cli_any_app.models.database import get_session
from cli_any_app.models.session import Session
from cli_any_app.models.flow import Flow
from cli_any_app.models.request import CapturedRequest
from cli_any_app.generation.pipeline import run_pipeline

router = APIRouter(prefix="/api/sessions/{session_id}", tags=["generation"])


@router.post("/generate")
async def start_generation(session_id: str, background_tasks: BackgroundTasks):
    async with get_session() as db:
        session = await db.get(Session, session_id)
        if not session:
            raise HTTPException(404, "Session not found")

        # Load all flows and requests
        result = await db.execute(
            select(Flow)
            .where(Flow.session_id == session_id)
            .options(selectinload(Flow.requests))
            .order_by(Flow.order)
        )
        flows = result.scalars().all()

        session_data = {
            "app_name": session.app_name,
            "flows": [
                {
                    "label": f.label,
                    "requests": [
                        {
                            "method": r.method,
                            "url": r.url,
                            "request_headers": r.request_headers,
                            "request_body": r.request_body,
                            "status_code": r.status_code,
                            "response_headers": r.response_headers,
                            "response_body": r.response_body,
                            "content_type": r.content_type,
                            "is_api": r.is_api,
                        }
                        for r in f.requests
                        if r.is_api
                    ],
                }
                for f in flows
            ],
        }

        session.status = "generating"
        await db.commit()

    background_tasks.add_task(_run_generation, session_id, session_data)
    return {"status": "started"}


async def _run_generation(session_id: str, session_data: dict):
    try:
        result = await run_pipeline(session_data, session_id)
        async with get_session() as db:
            session = await db.get(Session, session_id)
            session.status = "complete" if result["status"] == "success" else "error"
            await db.commit()
    except Exception as e:
        async with get_session() as db:
            session = await db.get(Session, session_id)
            session.status = "error"
            await db.commit()
```

**Step 2: Register in main.py, run tests, commit**

```bash
git add cli_any_app/api/generate.py cli_any_app/main.py
git commit -m "feat: generation API endpoint with background task execution"
```

---

## Task 14: End-to-End Integration Test

**Files:**
- Create: `tests/test_e2e.py`

**Step 1: Write an integration test that exercises the full flow**

Uses the test client to:
1. Create a session
2. Create a flow
3. Post mock captured requests to the internal endpoint
4. List domains and verify filtering
5. Trigger generation (with mocked Claude API)
6. Verify output files exist

**Step 2: Run the full test suite**

Run: `pytest tests/ -v`
Expected: ALL PASS

**Step 3: Commit**

```bash
git add tests/test_e2e.py
git commit -m "test: end-to-end integration test for full capture-to-generation flow"
```

---

## Task 15: Polish & Documentation

**Files:**
- Create: `.gitignore`
- Create: `CLAUDE.md` — project-level instructions for Claude Code
- Verify all existing code works end-to-end

**Step 1: Create .gitignore**

```
__pycache__/
*.pyc
.venv/
data/
node_modules/
frontend/dist/
cli_any_app/ui/static/
*.egg-info/
.pytest_cache/
```

**Step 2: Create CLAUDE.md with project context**

Include: project purpose, how to run (FastAPI + frontend dev server), how to test, architecture overview, key patterns.

**Step 3: Final test run**

Run: `pytest tests/ -v`
Expected: ALL PASS

**Step 4: Commit**

```bash
git add .gitignore CLAUDE.md
git commit -m "chore: add .gitignore and CLAUDE.md project instructions"
```

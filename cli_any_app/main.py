from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

from cli_any_app.api.auth import router as auth_router
from cli_any_app.api.capture import router as capture_router
from cli_any_app.api.cert import router as cert_router
from cli_any_app.api.domains import router as domains_router
from cli_any_app.api.flows import router as flows_router
from cli_any_app.api.generate import router as generate_router
from cli_any_app.api.retention import router as retention_router
from cli_any_app.api.sessions import router as sessions_router
from cli_any_app.api.settings import router as settings_router
from cli_any_app.api.websocket import generation_manager, manager
from cli_any_app.config import settings
from cli_any_app.security import (
    ensure_admin_password,
    require_csrf,
    require_http_auth,
    validate_ws_origin,
    validate_ws_token,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.generated_dir.mkdir(parents=True, exist_ok=True)
    settings.bodies_dir.mkdir(parents=True, exist_ok=True)
    settings.secrets_dir.mkdir(parents=True, exist_ok=True)
    bootstrap_password = ensure_admin_password()
    if bootstrap_password:
        import logging

        logging.getLogger(__name__).warning(
            "BOOTSTRAP ADMIN PASSWORD written to %s",
            settings.secrets_dir / "bootstrap-admin-password.txt",
        )
    from cli_any_app.models.database import init_db

    await init_db(settings.db_url, create_schema=settings.db_create_all)
    if settings.retention_purge_on_startup:
        from cli_any_app.retention import purge_expired_sessions

        await purge_expired_sessions()
    try:
        yield
    finally:
        from cli_any_app.capture.proxy_manager import proxy_manager

        proxy_manager.stop()


app = FastAPI(title="cli-any-app", lifespan=lifespan)


def _host_with_optional_port(host: str, port: int | None) -> str:
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    return f"{host}:{port}" if port is not None else host


def _websocket_csp_sources(request: Request | None) -> str:
    if request is not None:
        host = request.url.hostname or settings.host
        port = request.url.port
    else:
        host = settings.host
        port = settings.port
    host_port = _host_with_optional_port(host, port)
    return f"ws://{host_port} wss://{host_port}"


def _apply_security_headers(response, request: Request | None = None):
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "same-origin")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; "
        f"connect-src 'self' {_websocket_csp_sources(request)}; "
        "img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self'",
    )
    return response


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    path = request.url.path
    auth_exempt = path == "/api/auth/login" or path == "/api/internal/capture"
    if path.startswith("/api/") and not auth_exempt:
        try:
            session = require_http_auth(request)
            if request.method not in {"GET", "HEAD", "OPTIONS"}:
                require_csrf(request, session)
        except HTTPException as exc:
            response = JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
            response.headers.setdefault("Cache-Control", "no-store")
            return _apply_security_headers(
                response,
                request,
            )
    response = await call_next(request)
    if path.startswith("/api/"):
        response.headers.setdefault("Cache-Control", "no-store")
    return _apply_security_headers(response, request)


app.include_router(auth_router)
app.include_router(sessions_router)
app.include_router(flows_router)
app.include_router(capture_router)
app.include_router(cert_router)
app.include_router(domains_router)
app.include_router(generate_router)
app.include_router(retention_router)
app.include_router(settings_router)


@app.websocket("/ws/traffic/{session_id}")
async def traffic_ws(ws: WebSocket, session_id: str):
    if not validate_ws_origin(ws) or not validate_ws_token(ws.query_params.get("token")):
        await ws.close(code=1008)
        return
    await manager.connect(session_id, ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(session_id, ws)


@app.websocket("/ws/generation/{session_id}")
async def generation_ws(ws: WebSocket, session_id: str):
    if not validate_ws_origin(ws) or not validate_ws_token(ws.query_params.get("token")):
        await ws.close(code=1008)
        return
    await generation_manager.connect(session_id, ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        generation_manager.disconnect(session_id, ws)


static_dir = Path(__file__).parent / "ui" / "static"
if static_dir.exists():
    from fastapi.staticfiles import StaticFiles

    app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="ui")


def cli_entry():
    host_is_lan = settings.host not in {"127.0.0.1", "localhost", "::1"}
    if host_is_lan and not settings.allow_lan:
        raise RuntimeError("Refusing to bind non-local host without CLI_ANY_APP_ALLOW_LAN=true")
    uvicorn.run(
        "cli_any_app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
    )


if __name__ == "__main__":
    cli_entry()

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from fastapi import HTTPException, Request, Response, WebSocket

from cli_any_app.config import settings
from cli_any_app.private_files import private_file_exists, read_private_bytes, write_private_bytes, write_private_text

SESSION_PURPOSE = "session"
WS_PURPOSE = "ws"


def _b64e(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _b64d(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


def _secret_path() -> Path:
    return settings.secrets_dir / "app-secret.key"


def _admin_hash_path() -> Path:
    return settings.secrets_dir / "admin-password.hash"


def _bootstrap_password_path() -> Path:
    return settings.secrets_dir / "bootstrap-admin-password.txt"


def _write_private(path: Path, content: str) -> None:
    write_private_text(path, content)


def get_app_secret() -> bytes:
    path = _secret_path()
    existing = read_private_bytes(path)
    if existing is not None:
        return existing
    secret = secrets.token_bytes(32)
    write_private_bytes(path, secret)
    return secret


def hash_secret(value: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", value.encode(), salt, 390_000)
    return f"pbkdf2_sha256${_b64e(salt)}${_b64e(digest)}"


def verify_secret(value: str, encoded: str) -> bool:
    try:
        scheme, salt_b64, digest_b64 = encoded.split("$", 2)
    except ValueError:
        return False
    if scheme != "pbkdf2_sha256":
        return False
    expected = hash_secret(value, _b64d(salt_b64)).split("$", 2)[2]
    return hmac.compare_digest(expected, digest_b64)


def ensure_admin_password() -> str | None:
    """Create the single local operator password hash.

    Returns a bootstrap password only when one was generated for first use.
    """
    path = _admin_hash_path()
    if settings.admin_password:
        _write_private(path, hash_secret(settings.admin_password))
        return None
    if private_file_exists(path):
        return None
    bootstrap = secrets.token_urlsafe(18)
    _write_private(path, hash_secret(bootstrap))
    _write_private(_bootstrap_password_path(), bootstrap + "\n")
    return bootstrap


def verify_admin_password(password: str) -> bool:
    ensure_admin_password()
    path = _admin_hash_path()
    encoded = read_private_bytes(path)
    if encoded is None:
        return False
    return verify_secret(password, encoded.decode().strip())


def sign_payload(payload: dict[str, Any], purpose: str, ttl_seconds: int) -> str:
    now = int(time.time())
    body = {**payload, "purpose": purpose, "iat": now, "exp": now + ttl_seconds}
    raw = json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
    encoded = _b64e(raw)
    sig = hmac.new(get_app_secret(), encoded.encode(), hashlib.sha256).digest()
    return f"{encoded}.{_b64e(sig)}"


def unsign_payload(token: str, purpose: str) -> dict[str, Any] | None:
    try:
        encoded, sig = token.split(".", 1)
    except ValueError:
        return None
    expected = hmac.new(get_app_secret(), encoded.encode(), hashlib.sha256).digest()
    if not hmac.compare_digest(_b64e(expected), sig):
        return None
    try:
        payload = json.loads(_b64d(encoded))
    except (json.JSONDecodeError, ValueError):
        return None
    if payload.get("purpose") != purpose:
        return None
    try:
        expires_at = int(payload.get("exp", 0))
    except (TypeError, ValueError):
        return None
    if expires_at < int(time.time()):
        return None
    return payload


def create_session_cookie(response: Response) -> str:
    csrf = secrets.token_urlsafe(24)
    session_token = sign_payload({"sub": "local-admin", "csrf": csrf}, SESSION_PURPOSE, settings.session_ttl_seconds)
    response.set_cookie(
        settings.auth_cookie_name,
        session_token,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        max_age=settings.session_ttl_seconds,
    )
    response.set_cookie(
        settings.csrf_cookie_name,
        csrf,
        httponly=False,
        samesite="lax",
        secure=settings.cookie_secure,
        max_age=settings.session_ttl_seconds,
    )
    return csrf


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(settings.auth_cookie_name, secure=settings.cookie_secure)
    response.delete_cookie(settings.csrf_cookie_name, secure=settings.cookie_secure)


def session_from_request(request: Request) -> dict[str, Any] | None:
    token = request.cookies.get(settings.auth_cookie_name)
    if not token:
        return None
    return unsign_payload(token, SESSION_PURPOSE)


def require_http_auth(request: Request) -> dict[str, Any]:
    if settings.test_auto_auth:
        return {"sub": "test-admin", "csrf": "test-csrf"}
    payload = session_from_request(request)
    if payload is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    return payload


def require_csrf(request: Request, session: dict[str, Any]) -> None:
    if settings.test_auto_auth:
        return
    expected = session.get("csrf")
    provided = request.headers.get("x-csrf-token")
    if not expected or not provided or not hmac.compare_digest(str(expected), provided):
        raise HTTPException(status_code=403, detail="CSRF token missing or invalid")


def create_ws_token() -> str:
    return sign_payload({"sub": "local-admin"}, WS_PURPOSE, settings.ws_token_ttl_seconds)


def validate_ws_token(token: str | None) -> bool:
    if settings.test_auto_auth:
        return True
    if not token:
        return False
    return unsign_payload(token, WS_PURPOSE) is not None


def validate_ws_origin(ws: WebSocket) -> bool:
    if settings.test_auto_auth:
        return True
    origin = ws.headers.get("origin")
    if not origin:
        return False
    try:
        parsed = urlsplit(origin)
        origin_port = parsed.port
    except ValueError:
        return False
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return False
    if origin_port is None:
        origin_port = 443 if parsed.scheme == "https" else 80

    origin_host = parsed.hostname.lower()
    allowed = _allowed_ws_origins()
    return (origin_host, origin_port) in allowed


def _allowed_ws_origins() -> set[tuple[str, int]]:
    hosts = {"127.0.0.1", "localhost", "::1"}
    configured_host = settings.host.strip().lower().strip("[]")
    if configured_host and configured_host not in {"0.0.0.0", "::", "*"}:
        hosts.add(configured_host)

    allowed = {(host, settings.port) for host in hosts}
    for configured_origin in settings.ws_allowed_origins:
        try:
            parsed = urlsplit(configured_origin)
            port = parsed.port
        except ValueError:
            continue
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            continue
        if port is None:
            port = 443 if parsed.scheme == "https" else 80
        allowed.add((parsed.hostname.lower(), port))
    return allowed


def token_hash(token: str) -> str:
    return hmac.new(get_app_secret(), token.encode(), hashlib.sha256).hexdigest()


def verify_token_hash(token: str, digest: str | None) -> bool:
    if not token or not digest:
        return False
    return hmac.compare_digest(token_hash(token), digest)

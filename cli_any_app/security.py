from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import stat
import time
from pathlib import Path
from typing import Any

from fastapi import HTTPException, Request, Response, WebSocket

from cli_any_app.config import settings

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
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, stat.S_IRUSR | stat.S_IWUSR)
    with os.fdopen(fd, "w") as f:
        f.write(content)


def get_app_secret() -> bytes:
    path = _secret_path()
    if path.exists():
        return path.read_bytes()
    secret = secrets.token_bytes(32)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, stat.S_IRUSR | stat.S_IWUSR)
    with os.fdopen(fd, "wb") as f:
        f.write(secret)
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
    if path.exists():
        return None
    bootstrap = secrets.token_urlsafe(18)
    _write_private(path, hash_secret(bootstrap))
    _write_private(_bootstrap_password_path(), bootstrap + "\n")
    return bootstrap


def verify_admin_password(password: str) -> bool:
    ensure_admin_password()
    path = _admin_hash_path()
    if not path.exists():
        return False
    return verify_secret(password, path.read_text().strip())


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
    if int(payload.get("exp", 0)) < int(time.time()):
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
        secure=False,
        max_age=settings.session_ttl_seconds,
    )
    response.set_cookie(
        settings.csrf_cookie_name,
        csrf,
        httponly=False,
        samesite="lax",
        secure=False,
        max_age=settings.session_ttl_seconds,
    )
    return csrf


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(settings.auth_cookie_name)
    response.delete_cookie(settings.csrf_cookie_name)


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
    allowed_hosts = {ws.headers.get("host", ""), f"127.0.0.1:{settings.port}", f"localhost:{settings.port}"}
    return any(origin.endswith(host) for host in allowed_hosts if host)


def token_hash(token: str) -> str:
    return hmac.new(get_app_secret(), token.encode(), hashlib.sha256).hexdigest()


def verify_token_hash(token: str, digest: str | None) -> bool:
    if not token or not digest:
        return False
    return hmac.compare_digest(token_hash(token), digest)

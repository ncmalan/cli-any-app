from pydantic import BaseModel
from fastapi import APIRouter, HTTPException, Request, Response

from cli_any_app.security import (
    clear_session_cookie,
    create_session_cookie,
    create_ws_token,
    require_http_auth,
    verify_admin_password,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    password: str


class AuthStatus(BaseModel):
    authenticated: bool
    username: str | None = None
    csrf_token: str | None = None


class WsTokenResponse(BaseModel):
    token: str


@router.post("/login", response_model=AuthStatus)
async def login(body: LoginRequest, response: Response):
    if not verify_admin_password(body.password):
        raise HTTPException(status_code=401, detail="Invalid password")
    csrf = create_session_cookie(response)
    return AuthStatus(authenticated=True, username="local-admin", csrf_token=csrf)


@router.post("/logout", response_model=AuthStatus)
async def logout(response: Response):
    clear_session_cookie(response)
    return AuthStatus(authenticated=False)


@router.get("/me", response_model=AuthStatus)
async def me(request: Request):
    session = require_http_auth(request)
    return AuthStatus(
        authenticated=True,
        username=str(session.get("sub", "local-admin")),
        csrf_token=str(session.get("csrf", "")),
    )


@router.get("/ws-token", response_model=WsTokenResponse)
async def ws_token(request: Request):
    require_http_auth(request)
    return WsTokenResponse(token=create_ws_token())

import json

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy import LargeBinary, cast, func, select

from cli_any_app.capture.filters import is_api_request, extract_domain
from cli_any_app.capture.privacy import (
    body_hash,
    body_size,
    encrypt_payload,
    headers_size,
    is_binary_content,
    redact_body_text,
    redact_headers,
    redact_url,
)
from cli_any_app.config import settings
from cli_any_app.models.database import get_session
from cli_any_app.models.encrypted_payload import EncryptedPayload
from cli_any_app.models.flow import Flow
from cli_any_app.models.request import CapturedRequest
from cli_any_app.models.session import Session
from cli_any_app.security import verify_token_hash

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
async def receive_capture(payload: CapturePayload, x_capture_token: str | None = Header(None)):
    domain = extract_domain(payload.url)

    request_header_bytes = headers_size(payload.request_headers)
    response_header_bytes = headers_size(payload.response_headers)
    request_body_size = body_size(payload.request_body)
    response_body_size = body_size(payload.response_body)

    if request_header_bytes > settings.max_header_bytes:
        raise HTTPException(status_code=413, detail="Request headers exceed capture limit")
    if response_header_bytes > settings.max_header_bytes:
        raise HTTPException(status_code=413, detail="Response headers exceed capture limit")
    if request_body_size > settings.max_body_bytes:
        raise HTTPException(status_code=413, detail="Request body exceeds capture limit")
    if response_body_size > settings.max_body_bytes:
        raise HTTPException(status_code=413, detail="Response body exceeds capture limit")

    api_flag = is_api_request(payload.content_type, payload.url)
    host, redacted_path, redacted_url = redact_url(payload.url)
    request_headers = redact_headers(payload.request_headers)
    response_headers = redact_headers(payload.response_headers)
    request_body_hash = body_hash(payload.request_body)
    response_body_hash = body_hash(payload.response_body)
    binary_body = is_binary_content(payload.content_type)
    request_body = None
    response_body = None
    encrypted_request_body = None
    encrypted_response_body = None
    redaction_status = "metadata_only"

    if settings.raw_body_capture_enabled and not binary_body:
        request_body = redact_body_text(payload.request_body, payload.content_type)
        response_body = redact_body_text(payload.response_body, payload.content_type)
        encrypted_request_body = encrypt_payload(payload.request_body)
        encrypted_response_body = encrypt_payload(payload.response_body)
        redaction_status = "redacted"
    elif binary_body:
        redaction_status = "skipped_binary"
    stored_request_headers = json.dumps(request_headers, sort_keys=True)
    stored_response_headers = json.dumps(response_headers, sort_keys=True)
    incoming_capture_bytes = (
        body_size(stored_request_headers)
        + body_size(stored_response_headers)
        + body_size(request_body)
        + body_size(response_body)
        + body_size(encrypted_request_body)
        + body_size(encrypted_response_body)
    )

    async with get_session() as db:
        session = await db.get(Session, payload.session_id)
        if not session or session.status == "deleted":
            raise HTTPException(status_code=404, detail="Session not found")
        if not settings.test_auto_auth:
            if session.status != "recording":
                raise HTTPException(status_code=409, detail="Session is not recording")
            if not verify_token_hash(x_capture_token or "", session.capture_token_hash):
                raise HTTPException(status_code=403, detail="Invalid capture token")
            from cli_any_app.capture.proxy_manager import proxy_manager

            if not proxy_manager.owns_session(payload.session_id):
                raise HTTPException(status_code=403, detail="Active proxy does not own session")
        if settings.max_session_capture_bytes > 0:
            existing_bytes = await _session_capture_bytes(db, payload.session_id)
            if existing_bytes + incoming_capture_bytes > settings.max_session_capture_bytes:
                raise HTTPException(status_code=413, detail="Session capture size limit exceeded")
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
            url=redacted_url,
            host=host,
            redacted_path=redacted_path,
            request_headers=stored_request_headers,
            request_body=request_body,
            request_body_size=request_body_size,
            request_body_hash=request_body_hash,
            status_code=payload.status_code,
            response_headers=stored_response_headers,
            response_body=response_body,
            response_body_size=response_body_size,
            response_body_hash=response_body_hash,
            content_type=payload.content_type,
            is_api=api_flag,
            redaction_status=redaction_status,
        )
        db.add(req)
        await db.flush()
        if settings.raw_body_capture_enabled and not binary_body:
            db.add(
                EncryptedPayload(
                    request_id=req.id,
                    request_body_ciphertext=encrypted_request_body,
                    response_body_ciphertext=encrypted_response_body,
                )
            )
        await db.commit()
    from cli_any_app.api.websocket import manager

    await manager.broadcast(payload.session_id, {
        "type": "request",
        "method": payload.method,
        "url": redacted_url,
        "status_code": payload.status_code,
        "content_type": payload.content_type,
        "is_api": api_flag,
        "domain": domain,
        "flow_label": flow.label,
    })
    return {"status": "captured", "is_api": api_flag, "domain": domain}


async def _session_capture_bytes(db, session_id: str) -> int:
    def stored_text_bytes(column):
        return func.coalesce(func.length(cast(column, LargeBinary)), 0)

    request_bytes = (
        stored_text_bytes(CapturedRequest.request_body)
        + stored_text_bytes(CapturedRequest.response_body)
        + stored_text_bytes(CapturedRequest.request_headers)
        + stored_text_bytes(CapturedRequest.response_headers)
        + stored_text_bytes(EncryptedPayload.request_body_ciphertext)
        + stored_text_bytes(EncryptedPayload.response_body_ciphertext)
    )
    result = await db.execute(
        select(func.coalesce(func.sum(request_bytes), 0))
        .select_from(CapturedRequest)
        .join(Flow, CapturedRequest.flow_id == Flow.id)
        .outerjoin(EncryptedPayload, EncryptedPayload.request_id == CapturedRequest.id)
        .where(Flow.session_id == session_id)
    )
    return int(result.scalar_one() or 0)

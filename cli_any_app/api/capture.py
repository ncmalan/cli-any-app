import json

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import select

from cli_any_app.capture.filters import is_api_request, extract_domain
from cli_any_app.capture.noise_domains import matches_noise_pattern
from cli_any_app.models.database import get_session
from cli_any_app.models.request import CapturedRequest
from cli_any_app.models.flow import Flow

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
    return {"status": "captured", "is_api": api_flag, "domain": domain}

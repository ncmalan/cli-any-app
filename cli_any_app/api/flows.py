from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_serializer
from sqlalchemy import select, func

from cli_any_app.audit import record_audit_event
from cli_any_app.capture.privacy import decrypt_payload
from cli_any_app.config import settings
from cli_any_app.models.database import get_session
from cli_any_app.models.encrypted_payload import EncryptedPayload
from cli_any_app.models.flow import Flow
from cli_any_app.models.request import CapturedRequest
from cli_any_app.models.session import Session

router = APIRouter(prefix="/api/sessions/{session_id}/flows", tags=["flows"])


class FlowCreate(BaseModel):
    label: str


class FlowResponse(BaseModel):
    id: str
    session_id: str
    label: str
    order: int
    started_at: datetime
    ended_at: datetime | None

    model_config = {"from_attributes": True}

    @field_serializer("started_at")
    def serialize_started_at(self, v: datetime) -> str:
        return v.isoformat()

    @field_serializer("ended_at")
    def serialize_ended_at(self, v: datetime | None) -> str | None:
        return v.isoformat() if v else None


class RequestResponse(BaseModel):
    id: str
    flow_id: str
    timestamp: datetime
    method: str
    url: str
    request_headers: str
    request_body: str | None
    status_code: int
    response_headers: str
    response_body: str | None
    request_body_size: int = 0
    request_body_hash: str | None = None
    response_body_size: int = 0
    response_body_hash: str | None = None
    redaction_status: str = "metadata_only"
    content_type: str
    is_api: bool

    model_config = {"from_attributes": True}

    @field_serializer("timestamp")
    def serialize_timestamp(self, v: datetime) -> str:
        return v.isoformat()


class RevealRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


class RawPayloadResponse(BaseModel):
    request_body: str | None
    response_body: str | None


async def _get_active_session(db, session_id: str) -> Session:
    session = await db.get(Session, session_id)
    if not session or session.status == "deleted":
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@router.post("", status_code=201, response_model=FlowResponse)
async def create_flow(session_id: str, body: FlowCreate):
    async with get_session() as db:
        session = await _get_active_session(db, session_id)
        if session.status != "recording" and not settings.test_auto_auth:
            raise HTTPException(status_code=409, detail="Session is not recording")
        active_result = await db.execute(
            select(Flow).where(Flow.session_id == session_id, Flow.ended_at.is_(None))
        )
        if active_result.scalar_one_or_none():
            raise HTTPException(status_code=409, detail="Session already has an active flow")
        result = await db.execute(
            select(func.coalesce(func.max(Flow.order), 0)).where(Flow.session_id == session_id)
        )
        next_order = result.scalar() + 1

        flow = Flow(session_id=session_id, label=body.label, order=next_order)
        db.add(flow)
        await db.flush()
        await record_audit_event(
            db,
            "flow.created",
            session_id=session_id,
            metadata={"flow_id": flow.id, "label": body.label},
        )
        await db.commit()
        await db.refresh(flow)
        return flow


@router.get("", response_model=list[FlowResponse])
async def list_flows(session_id: str):
    async with get_session() as db:
        await _get_active_session(db, session_id)
        result = await db.execute(
            select(Flow).where(Flow.session_id == session_id).order_by(Flow.order)
        )
        return result.scalars().all()


@router.get("/{flow_id}/requests", response_model=list[RequestResponse])
async def list_flow_requests(session_id: str, flow_id: str):
    async with get_session() as db:
        await _get_active_session(db, session_id)
        flow = await db.get(Flow, flow_id)
        if not flow or flow.session_id != session_id:
            raise HTTPException(status_code=404, detail="Flow not found")

        result = await db.execute(
            select(CapturedRequest)
            .where(CapturedRequest.flow_id == flow_id)
            .order_by(CapturedRequest.timestamp)
        )
        return result.scalars().all()


@router.post("/{flow_id}/stop", response_model=FlowResponse)
async def stop_flow(session_id: str, flow_id: str):
    async with get_session() as db:
        await _get_active_session(db, session_id)
        flow = await db.get(Flow, flow_id)
        if not flow or flow.session_id != session_id:
            raise HTTPException(status_code=404, detail="Flow not found")
        if flow.ended_at is not None:
            return flow
        flow.ended_at = datetime.now(timezone.utc)
        await record_audit_event(
            db,
            "flow.stopped",
            session_id=session_id,
            metadata={"flow_id": flow_id},
        )
        await db.commit()
        await db.refresh(flow)
        return flow


@router.delete("/{flow_id}", status_code=204)
async def delete_flow(session_id: str, flow_id: str):
    async with get_session() as db:
        await _get_active_session(db, session_id)
        flow = await db.get(Flow, flow_id)
        if not flow or flow.session_id != session_id:
            raise HTTPException(status_code=404, detail="Flow not found")
        await record_audit_event(
            db,
            "flow.deleted",
            session_id=session_id,
            metadata={"flow_id": flow_id},
        )
        await db.delete(flow)
        await db.commit()


@router.post("/requests/{request_id}/reveal", response_model=RawPayloadResponse)
async def reveal_raw_payload(session_id: str, request_id: str, body: RevealRequest):
    reason = body.reason.strip()
    if not reason:
        raise HTTPException(status_code=400, detail="Reveal reason is required")
    async with get_session() as db:
        await _get_active_session(db, session_id)
        result = await db.execute(
            select(CapturedRequest, EncryptedPayload)
            .join(Flow, CapturedRequest.flow_id == Flow.id)
            .join(EncryptedPayload, EncryptedPayload.request_id == CapturedRequest.id)
            .where(Flow.session_id == session_id, CapturedRequest.id == request_id)
        )
        row = result.one_or_none()
        if not row:
            raise HTTPException(status_code=404, detail="Raw payload not found")
        _request, payload = row
        await record_audit_event(
            db,
            "payload.revealed",
            session_id=session_id,
            reason=reason,
            metadata={"request_id": request_id},
        )
        await db.commit()
        return RawPayloadResponse(
            request_body=decrypt_payload(payload.request_body_ciphertext),
            response_body=decrypt_payload(payload.response_body_ciphertext),
        )

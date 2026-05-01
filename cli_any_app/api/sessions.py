import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_serializer
from sqlalchemy import select

from cli_any_app.audit import record_audit_event
from cli_any_app.config import settings
from cli_any_app.models.database import get_session
from cli_any_app.models.flow import Flow
from cli_any_app.models.session import Session
from cli_any_app.security import token_hash

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


class SessionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    app_name: str = Field(min_length=1, max_length=120)


class SessionResponse(BaseModel):
    id: str
    name: str
    app_name: str
    status: str
    proxy_port: int
    error_message: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}

    @field_serializer("created_at")
    def serialize_created_at(self, v: datetime) -> str:
        return v.isoformat()


@router.post("", status_code=201, response_model=SessionResponse)
async def create_session(body: SessionCreate):
    async with get_session() as db:
        session = Session(
            name=body.name.strip(),
            app_name=body.app_name.strip(),
            retention_days=settings.default_retention_days,
        )
        db.add(session)
        await db.flush()
        await record_audit_event(
            db,
            "session.created",
            session_id=session.id,
            metadata={"name": session.name, "app_name": session.app_name},
        )
        await db.commit()
        await db.refresh(session)
        return session


@router.get("", response_model=list[SessionResponse])
async def list_sessions():
    async with get_session() as db:
        result = await db.execute(
            select(Session)
            .where(Session.status != "deleted")
            .order_by(Session.created_at.desc())
        )
        return result.scalars().all()


@router.get("/{session_id}", response_model=SessionResponse)
async def get_session_by_id(session_id: str):
    async with get_session() as db:
        session = await db.get(Session, session_id)
        if not session or session.status == "deleted":
            raise HTTPException(status_code=404, detail="Session not found")
        return session


@router.delete("/{session_id}", status_code=204)
async def delete_session(session_id: str):
    from cli_any_app.capture.proxy_manager import proxy_manager

    async with get_session() as db:
        session = await db.get(Session, session_id)
        if not session or session.status == "deleted":
            raise HTTPException(status_code=404, detail="Session not found")
        if proxy_manager.owns_session(session_id):
            proxy_manager.stop(session_id)
        session.status = "deleted"
        session.deleted_at = datetime.now(timezone.utc)
        session.capture_token_hash = None
        await record_audit_event(db, "session.deleted", session_id=session_id)
        await db.commit()


@router.post("/{session_id}/start-recording", response_model=SessionResponse)
async def start_recording(session_id: str):
    from cli_any_app.capture.proxy_manager import proxy_manager
    async with get_session() as db:
        session = await db.get(Session, session_id)
        if not session or session.status == "deleted":
            raise HTTPException(status_code=404, detail="Session not found")
        if session.status not in {"created", "stopped", "error", "validation_failed", "needs_review"}:
            if session.status == "recording":
                return session
            raise HTTPException(status_code=409, detail=f"Cannot start recording from {session.status}")
        capture_token = secrets.token_urlsafe(32)
        try:
            port = proxy_manager.start(
                session_id,
                session.proxy_port,
                capture_token=capture_token,
            )
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        session.status = "recording"
        session.proxy_port = port
        session.capture_token_hash = token_hash(capture_token)
        await record_audit_event(
            db,
            "recording.started",
            session_id=session_id,
            metadata={"proxy_port": port},
        )
        await db.commit()
        await db.refresh(session)
        return session


@router.post("/{session_id}/stop-recording", response_model=SessionResponse)
async def stop_recording(session_id: str):
    from cli_any_app.capture.proxy_manager import proxy_manager
    async with get_session() as db:
        session = await db.get(Session, session_id)
        if not session or session.status == "deleted":
            raise HTTPException(status_code=404, detail="Session not found")
        try:
            proxy_manager.stop(session_id)
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        result = await db.execute(
            select(Flow).where(Flow.session_id == session_id, Flow.ended_at.is_(None))
        )
        for flow in result.scalars().all():
            flow.ended_at = datetime.now(timezone.utc)
        session.status = "stopped"
        session.capture_token_hash = None
        await record_audit_event(db, "recording.stopped", session_id=session_id)
        await db.commit()
        await db.refresh(session)
        return session

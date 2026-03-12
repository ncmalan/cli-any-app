from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, field_serializer
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
    created_at: datetime

    model_config = {"from_attributes": True}

    @field_serializer("created_at")
    def serialize_created_at(self, v: datetime) -> str:
        return v.isoformat()


@router.post("", status_code=201, response_model=SessionResponse)
async def create_session(body: SessionCreate):
    async with get_session() as db:
        session = Session(name=body.name, app_name=body.app_name)
        db.add(session)
        await db.commit()
        await db.refresh(session)
        return session


@router.get("", response_model=list[SessionResponse])
async def list_sessions():
    async with get_session() as db:
        result = await db.execute(select(Session).order_by(Session.created_at.desc()))
        return result.scalars().all()


@router.get("/{session_id}", response_model=SessionResponse)
async def get_session_by_id(session_id: str):
    async with get_session() as db:
        session = await db.get(Session, session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        return session


@router.delete("/{session_id}", status_code=204)
async def delete_session(session_id: str):
    async with get_session() as db:
        session = await db.get(Session, session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        await db.delete(session)
        await db.commit()


@router.post("/{session_id}/start-recording", response_model=SessionResponse)
async def start_recording(session_id: str):
    from cli_any_app.capture.proxy_manager import proxy_manager
    async with get_session() as db:
        session = await db.get(Session, session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        port = proxy_manager.start(session_id, session.proxy_port)
        session.status = "recording"
        session.proxy_port = port
        await db.commit()
        await db.refresh(session)
        return session


@router.post("/{session_id}/stop-recording", response_model=SessionResponse)
async def stop_recording(session_id: str):
    from cli_any_app.capture.proxy_manager import proxy_manager
    async with get_session() as db:
        session = await db.get(Session, session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        proxy_manager.stop()
        session.status = "stopped"
        await db.commit()
        await db.refresh(session)
        return session

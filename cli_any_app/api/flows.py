from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, field_serializer
from sqlalchemy import select, func

from cli_any_app.models.database import get_session
from cli_any_app.models.flow import Flow

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


@router.post("", status_code=201, response_model=FlowResponse)
async def create_flow(session_id: str, body: FlowCreate):
    async with get_session() as db:
        result = await db.execute(
            select(func.coalesce(func.max(Flow.order), 0)).where(Flow.session_id == session_id)
        )
        next_order = result.scalar() + 1

        flow = Flow(session_id=session_id, label=body.label, order=next_order)
        db.add(flow)
        await db.commit()
        await db.refresh(flow)
        return flow


@router.get("", response_model=list[FlowResponse])
async def list_flows(session_id: str):
    async with get_session() as db:
        result = await db.execute(
            select(Flow).where(Flow.session_id == session_id).order_by(Flow.order)
        )
        return result.scalars().all()


@router.post("/{flow_id}/stop", response_model=FlowResponse)
async def stop_flow(session_id: str, flow_id: str):
    async with get_session() as db:
        flow = await db.get(Flow, flow_id)
        if not flow or flow.session_id != session_id:
            raise HTTPException(status_code=404, detail="Flow not found")
        flow.ended_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(flow)
        return flow


@router.delete("/{flow_id}", status_code=204)
async def delete_flow(session_id: str, flow_id: str):
    async with get_session() as db:
        flow = await db.get(Flow, flow_id)
        if not flow or flow.session_id != session_id:
            raise HTTPException(status_code=404, detail="Flow not found")
        await db.delete(flow)
        await db.commit()

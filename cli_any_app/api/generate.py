import json
import logging
from fastapi import APIRouter, HTTPException, BackgroundTasks

logger = logging.getLogger(__name__)
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from cli_any_app.models.database import get_session
from cli_any_app.models.session import Session
from cli_any_app.models.flow import Flow
from cli_any_app.models.request import CapturedRequest
from cli_any_app.models.generated_cli import GeneratedCLI
from cli_any_app.generation.pipeline import run_pipeline

router = APIRouter(prefix="/api/sessions/{session_id}", tags=["generation"])


@router.post("/generate")
async def start_generation(session_id: str, background_tasks: BackgroundTasks):
    async with get_session() as db:
        session = await db.get(Session, session_id)
        if not session:
            raise HTTPException(404, "Session not found")

        # Load all flows and requests
        result = await db.execute(
            select(Flow)
            .where(Flow.session_id == session_id)
            .options(selectinload(Flow.requests))
            .order_by(Flow.order)
        )
        flows = result.scalars().all()

        session_data = {
            "app_name": session.app_name,
            "flows": [
                {
                    "label": f.label,
                    "requests": [
                        {
                            "method": r.method,
                            "url": r.url,
                            "request_headers": r.request_headers,
                            "request_body": r.request_body,
                            "status_code": r.status_code,
                            "response_headers": r.response_headers,
                            "response_body": r.response_body,
                            "content_type": r.content_type,
                            "is_api": r.is_api,
                        }
                        for r in f.requests
                        if r.is_api
                    ],
                }
                for f in flows
            ],
        }

        session.status = "generating"
        session.error_message = None
        await db.commit()

    background_tasks.add_task(_run_generation, session_id, session_data)
    return {"status": "started"}


async def _broadcast_progress(session_id: str, step: str, message: str, detail: str | None = None):
    from cli_any_app.api.websocket import generation_manager
    await generation_manager.broadcast(session_id, {
        "step": step,
        "message": message,
        "detail": detail,
    })


async def _run_generation(session_id: str, session_data: dict):
    async def on_progress(step: str, message: str, detail: str | None = None):
        await _broadcast_progress(session_id, step, message, detail)

    try:
        await on_progress("starting", "Generation pipeline started")
        result = await run_pipeline(session_data, session_id, on_progress=on_progress)
        await on_progress("complete", "Generation complete!")

        async with get_session() as db:
            session = await db.get(Session, session_id)
            session.status = "complete" if result["status"] in ("success", "validation_errors") else "error"

            # Store the generated CLI metadata
            generated = GeneratedCLI(
                session_id=session_id,
                api_spec=json.dumps(result.get("api_spec", {})),
                package_path=result.get("package_path", ""),
                skill_md="",
            )
            db.add(generated)
            await db.commit()
    except Exception as e:
        logger.exception(f"Generation failed for session {session_id}: {e}")
        await on_progress("error", str(e))
        async with get_session() as db:
            session = await db.get(Session, session_id)
            if session:
                session.status = "error"
                session.error_message = str(e)
                await db.commit()


@router.get("/status")
async def get_generation_status(session_id: str):
    async with get_session() as db:
        session = await db.get(Session, session_id)
        if not session:
            raise HTTPException(404, "Session not found")
        return {"session_id": session_id, "status": session.status}

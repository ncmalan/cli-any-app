import json
import logging
from pathlib import Path
from fastapi import APIRouter, HTTPException, BackgroundTasks

logger = logging.getLogger(__name__)
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from cli_any_app.api.domains import is_domain_enabled
from cli_any_app.capture.filters import extract_domain
from cli_any_app.models.database import get_session
from cli_any_app.models.session import Session
from cli_any_app.models.flow import Flow
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

        serialized_flows = []
        for flow in flows:
            requests = [
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
                for r in flow.requests
                if r.is_api and is_domain_enabled(session_id, extract_domain(r.url))
            ]
            if requests:
                serialized_flows.append({"label": flow.label, "requests": requests})

        session_data = {
            "app_name": session.app_name,
            "session_name": session.name,
            "flows": serialized_flows,
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
            if not session:
                return
            session.status = "complete" if result["status"] in ("success", "validation_errors") else "error"

            generated_result = await db.execute(
                select(GeneratedCLI).where(GeneratedCLI.session_id == session_id)
            )
            generated = generated_result.scalar_one_or_none()
            if not generated:
                generated = GeneratedCLI(session_id=session_id)
                db.add(generated)

            package_path = result.get("package_path", "")
            generated.api_spec = json.dumps(result.get("api_spec", {}))
            generated.package_path = package_path
            generated.skill_md = _load_skill_md(package_path)
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


def _load_skill_md(package_path: str) -> str:
    if not package_path:
        return ""

    skill_path = Path(package_path) / "SKILL.md"
    try:
        return skill_path.read_text()
    except OSError:
        return ""


@router.get("/status")
async def get_generation_status(session_id: str):
    async with get_session() as db:
        session = await db.get(Session, session_id)
        if not session:
            raise HTTPException(404, "Session not found")
        return {"session_id": session_id, "status": session.status}

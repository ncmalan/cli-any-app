import json
import logging
from datetime import datetime, timezone
import hashlib
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from cli_any_app.audit import record_audit_event
from cli_any_app.api.domains import domain_enabled_from_map, load_domain_enabled_map
from cli_any_app.capture.filters import extract_domain
from cli_any_app.config import settings
from cli_any_app.generation.pipeline import run_pipeline
from cli_any_app.generation.redactor import has_unredacted_sensitive_data
from cli_any_app.models.database import get_session
from cli_any_app.models.flow import Flow
from cli_any_app.models.generated_cli import GeneratedCLI
from cli_any_app.models.generation_attempt import GenerationAttempt
from cli_any_app.models.session import Session

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/sessions/{session_id}", tags=["generation"])


class GenerationStartRequest(BaseModel):
    reviewer_acknowledged: bool = False


class GenerationApprovalRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


def _attempt_payload(attempt: GenerationAttempt | None) -> dict | None:
    if attempt is None:
        return None
    return {
        "id": attempt.id,
        "status": attempt.status,
        "approval_status": attempt.approval_status,
        "package_path": attempt.package_path,
        "validation": json.loads(attempt.validation_report_json or "{}"),
        "created_at": attempt.created_at.isoformat(),
        "completed_at": attempt.completed_at.isoformat() if attempt.completed_at else None,
    }


@router.post("/generate")
async def start_generation(
    session_id: str,
    background_tasks: BackgroundTasks,
    body: GenerationStartRequest | None = None,
):
    async with get_session() as db:
        session = await db.get(Session, session_id)
        if not session or session.status == "deleted":
            raise HTTPException(404, "Session not found")
        if session.status == "recording":
            raise HTTPException(409, "Stop recording before generation")
        if not settings.test_auto_auth and not (body and body.reviewer_acknowledged):
            raise HTTPException(400, "Reviewer acknowledgement is required")

        # Load all flows and requests
        result = await db.execute(
            select(Flow)
            .where(Flow.session_id == session_id)
            .options(selectinload(Flow.requests))
            .order_by(Flow.order)
        )
        flows = result.scalars().all()
        domain_filters = await load_domain_enabled_map(db, session_id)

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
                    "redaction_status": r.redaction_status,
                }
                for r in flow.requests
                if r.is_api
                and domain_enabled_from_map(domain_filters, r.host or extract_domain(r.url))
            ]
            if requests:
                serialized_flows.append({"label": flow.label, "requests": requests})

        request_count = sum(len(flow["requests"]) for flow in serialized_flows)
        if request_count == 0:
            raise HTTPException(400, "Generation requires at least one enabled API request")
        unsafe_statuses = {
            r.get("redaction_status")
            for flow in serialized_flows
            for r in flow["requests"]
            if r.get("redaction_status") not in {"metadata_only", "redacted", "skipped_binary"}
        }
        if unsafe_statuses:
            raise HTTPException(400, "Generation blocked by redaction preflight")

        session_data = {
            "app_name": session.app_name,
            "session_name": session.name,
            "flows": serialized_flows,
        }
        if has_unredacted_sensitive_data(session_data):
            raise HTTPException(400, "Generation blocked by redaction preflight")
        redacted_input = json.dumps(session_data, sort_keys=True)

        attempt = GenerationAttempt(
            session_id=session_id,
            status="started",
            redacted_input_hash=hashlib.sha256(redacted_input.encode()).hexdigest(),
            prompt_hash=hashlib.sha256(b"cli-any-app-pipeline-v1").hexdigest(),
            model=settings.llm_model,
            approval_status="pending",
        )
        db.add(attempt)
        await db.flush()

        session.status = "generating"
        session.error_message = None
        await record_audit_event(
            db,
            "generation.started",
            session_id=session_id,
            metadata={"attempt_id": attempt.id, "request_count": request_count},
        )
        await db.commit()

    background_tasks.add_task(_run_generation, session_id, session_data, attempt.id)
    return {"status": "started", "attempt_id": attempt.id}


async def _broadcast_progress(session_id: str, step: str, message: str, detail: str | None = None):
    from cli_any_app.api.websocket import generation_manager
    await generation_manager.broadcast(session_id, {
        "step": step,
        "message": message,
        "detail": detail,
    })


async def _run_generation(session_id: str, session_data: dict, attempt_id: str | None = None):
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
            session.status = "complete" if result["status"] == "success" else "validation_failed"

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
            if attempt_id:
                attempt = await db.get(GenerationAttempt, attempt_id)
                if attempt:
                    attempt.status = session.status
                    attempt.package_path = package_path
                    attempt.validation_report_json = json.dumps(
                        result.get("validation", {}),
                        sort_keys=True,
                    )
                    attempt.file_hashes_json = json.dumps(
                        _hash_generated_files(package_path),
                        sort_keys=True,
                    )
                    attempt.completed_at = datetime.now(timezone.utc)
            await db.commit()
    except Exception as e:
        logger.exception(f"Generation failed for session {session_id}: {e}")
        await on_progress("error", str(e))
        async with get_session() as db:
            session = await db.get(Session, session_id)
            if session:
                session.status = "error"
                session.error_message = str(e)
                if attempt_id:
                    attempt = await db.get(GenerationAttempt, attempt_id)
                    if attempt:
                        attempt.status = "error"
                        attempt.validation_report_json = json.dumps({"error": str(e)})
                        attempt.completed_at = datetime.now(timezone.utc)
                await db.commit()


def _load_skill_md(package_path: str) -> str:
    if not package_path:
        return ""

    skill_path = Path(package_path) / "SKILL.md"
    try:
        return skill_path.read_text()
    except OSError:
        return ""


def _hash_generated_files(package_path: str) -> dict[str, str]:
    if not package_path:
        return {}
    root = Path(package_path)
    if not root.exists():
        return {}
    hashes: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            hashes[str(path.relative_to(root))] = hashlib.sha256(path.read_bytes()).hexdigest()
    return hashes


@router.get("/status")
async def get_generation_status(session_id: str):
    async with get_session() as db:
        session = await db.get(Session, session_id)
        if not session:
            raise HTTPException(404, "Session not found")
        latest = await db.execute(
            select(GenerationAttempt)
            .where(GenerationAttempt.session_id == session_id)
            .order_by(GenerationAttempt.created_at.desc())
            .limit(1)
        )
        attempt = latest.scalar_one_or_none()
        return {
            "session_id": session_id,
            "status": session.status,
            "latest_attempt": _attempt_payload(attempt),
        }


@router.get("/generation-attempts")
async def list_generation_attempts(session_id: str):
    async with get_session() as db:
        session = await db.get(Session, session_id)
        if not session or session.status == "deleted":
            raise HTTPException(404, "Session not found")
        result = await db.execute(
            select(GenerationAttempt)
            .where(GenerationAttempt.session_id == session_id)
            .order_by(GenerationAttempt.created_at.desc())
        )
        return [_attempt_payload(attempt) for attempt in result.scalars().all()]


@router.post("/generation-attempts/{attempt_id}/approve")
async def approve_generation_attempt(
    session_id: str,
    attempt_id: str,
    body: GenerationApprovalRequest,
):
    async with get_session() as db:
        session = await db.get(Session, session_id)
        attempt = await db.get(GenerationAttempt, attempt_id)
        if not session or session.status == "deleted" or not attempt or attempt.session_id != session_id:
            raise HTTPException(404, "Generation attempt not found")
        validation = json.loads(attempt.validation_report_json or "{}")
        if attempt.status != "complete" or validation.get("valid") is not True:
            raise HTTPException(409, "Only successfully validated attempts can be approved")
        attempt.approval_status = "approved"
        await record_audit_event(
            db,
            "generation.approved",
            session_id=session_id,
            reason=body.reason,
            metadata={"attempt_id": attempt_id, "package_path": attempt.package_path},
        )
        await db.commit()
        return _attempt_payload(attempt)


@router.post("/generation-attempts/{attempt_id}/reject")
async def reject_generation_attempt(
    session_id: str,
    attempt_id: str,
    body: GenerationApprovalRequest,
):
    async with get_session() as db:
        session = await db.get(Session, session_id)
        attempt = await db.get(GenerationAttempt, attempt_id)
        if not session or session.status == "deleted" or not attempt or attempt.session_id != session_id:
            raise HTTPException(404, "Generation attempt not found")
        attempt.approval_status = "rejected"
        await record_audit_event(
            db,
            "generation.rejected",
            session_id=session_id,
            reason=body.reason,
            metadata={"attempt_id": attempt_id},
        )
        await db.commit()
        return _attempt_payload(attempt)

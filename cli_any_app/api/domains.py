from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

from cli_any_app.audit import record_audit_event
from cli_any_app.capture.filters import extract_domain
from cli_any_app.capture.noise_domains import matches_noise_pattern
from cli_any_app.models.database import get_session
from cli_any_app.models.domain_filter import DomainFilter
from cli_any_app.models.flow import Flow
from cli_any_app.models.request import CapturedRequest
from cli_any_app.models.session import Session

router = APIRouter(prefix="/api/sessions/{session_id}/domains", tags=["domains"])


class DomainInfo(BaseModel):
    domain: str
    request_count: int
    is_noise: bool
    enabled: bool


class DomainToggle(BaseModel):
    enabled: bool
    reason: str | None = Field(default=None, max_length=500)


_domain_filters: dict[str, dict[str, bool]] = {}


def is_domain_enabled(session_id: str, domain: str) -> bool:
    """Compatibility fallback for legacy tests; generation uses persisted filters."""
    filters = _domain_filters.get(session_id, {})
    return filters.get(domain, not matches_noise_pattern(domain))


async def load_domain_enabled_map(db, session_id: str) -> dict[str, bool]:
    result = await db.execute(select(DomainFilter).where(DomainFilter.session_id == session_id))
    return {row.domain: row.enabled for row in result.scalars().all()}


def domain_enabled_from_map(filters: dict[str, bool], domain: str) -> bool:
    return filters.get(domain, not matches_noise_pattern(domain))


@router.get("", response_model=list[DomainInfo])
async def list_domains(session_id: str):
    async with get_session() as db:
        session = await db.get(Session, session_id)
        if not session or session.status == "deleted":
            raise HTTPException(status_code=404, detail="Session not found")
        result = await db.execute(
            select(CapturedRequest.url, CapturedRequest.host)
            .join(Flow)
            .where(Flow.session_id == session_id)
        )
        rows = result.all()
        filters = await load_domain_enabled_map(db, session_id)

    domain_counts: dict[str, int] = {}
    for url, host in rows:
        d = host or extract_domain(url)
        domain_counts[d] = domain_counts.get(d, 0) + 1

    domains = []
    for domain, count in sorted(domain_counts.items(), key=lambda x: -x[1]):
        is_noise = matches_noise_pattern(domain)
        enabled = domain_enabled_from_map(filters, domain)
        domains.append(DomainInfo(domain=domain, request_count=count, is_noise=is_noise, enabled=enabled))
    return domains


@router.put("/{domain}", response_model=DomainInfo)
async def toggle_domain(session_id: str, domain: str, body: DomainToggle):
    reason = body.reason.strip() if body.reason is not None else None
    if body.reason is not None and not reason:
        raise HTTPException(status_code=400, detail="Domain filter reason cannot be blank")

    async with get_session() as db:
        session = await db.get(Session, session_id)
        if not session or session.status == "deleted":
            raise HTTPException(status_code=404, detail="Session not found")
        result = await db.execute(
            select(DomainFilter).where(
                DomainFilter.session_id == session_id,
                DomainFilter.domain == domain,
            )
        )
        existing = result.scalar_one_or_none()
        if existing:
            existing.enabled = body.enabled
            existing.reason = reason
            existing.source = "user"
        else:
            existing = DomainFilter(
                session_id=session_id,
                domain=domain,
                enabled=body.enabled,
                reason=reason,
                source="user",
            )
            db.add(existing)
        _domain_filters.setdefault(session_id, {})[domain] = body.enabled
        await record_audit_event(
            db,
            "domain_filter.changed",
            session_id=session_id,
            reason=reason,
            metadata={"domain": domain, "enabled": body.enabled, "source": "user"},
        )
        await db.commit()
    return DomainInfo(
        domain=domain,
        request_count=0,
        is_noise=matches_noise_pattern(domain),
        enabled=body.enabled,
    )

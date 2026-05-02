from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import case, func, or_, select

from cli_any_app.audit import record_audit_event
from cli_any_app.capture.filters import normalize_domain
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
    api_request_count: int
    is_noise: bool
    enabled: bool


class DomainToggle(BaseModel):
    enabled: bool
    reason: str | None = Field(default=None, max_length=500)


async def load_domain_enabled_map(db, session_id: str) -> dict[str, bool]:
    result = await db.execute(select(DomainFilter).where(DomainFilter.session_id == session_id))
    return {normalize_domain(row.domain): row.enabled for row in result.scalars().all()}


def domain_enabled_from_map(filters: dict[str, bool], domain: str) -> bool:
    normalized = normalize_domain(domain)
    return filters.get(normalized, filters.get(domain, not matches_noise_pattern(normalized)))


def _domain_request_filter(domain: str):
    url_hosts = [domain]
    host_clauses = [
        CapturedRequest.host == domain,
        CapturedRequest.host.like(f"{domain}:%"),
    ]
    if ":" in domain:
        bracketed = f"[{domain}]"
        url_hosts = [bracketed]
        host_clauses.extend([
            CapturedRequest.host == bracketed,
            CapturedRequest.host.like(f"{bracketed}:%"),
        ])

    url_clauses = []
    for url_host in url_hosts:
        for scheme in ("http", "https"):
            base = f"{scheme}://{url_host}"
            url_clauses.extend([
                CapturedRequest.url == base,
                CapturedRequest.url.like(f"{base}/%"),
                CapturedRequest.url.like(f"{base}?%"),
                CapturedRequest.url.like(f"{base}:%"),
            ])
    return or_(*(host_clauses + url_clauses))


def _domain_candidate_expr():
    after_scheme = case(
        (
            func.instr(CapturedRequest.url, "://") > 0,
            func.substr(CapturedRequest.url, func.instr(CapturedRequest.url, "://") + 3),
        ),
        else_=CapturedRequest.url,
    )
    slash_pos = func.instr(after_scheme, "/")
    before_path = case(
        (slash_pos > 0, func.substr(after_scheme, 1, slash_pos - 1)),
        else_=after_scheme,
    )
    query_pos = func.instr(before_path, "?")
    url_host = case(
        (query_pos > 0, func.substr(before_path, 1, query_pos - 1)),
        else_=before_path,
    )
    return func.lower(func.coalesce(func.nullif(CapturedRequest.host, ""), url_host))


@router.get("", response_model=list[DomainInfo])
async def list_domains(session_id: str):
    async with get_session() as db:
        session = await db.get(Session, session_id)
        if not session or session.status == "deleted":
            raise HTTPException(status_code=404, detail="Session not found")
        domain_candidate = _domain_candidate_expr()
        api_count = func.coalesce(
            func.sum(case((CapturedRequest.is_api.is_(True), 1), else_=0)),
            0,
        )
        result = await db.execute(
            select(domain_candidate, func.count(CapturedRequest.id), api_count)
            .join(Flow)
            .where(Flow.session_id == session_id)
            .group_by(domain_candidate)
        )
        rows = result.all()
        filters = await load_domain_enabled_map(db, session_id)

    domain_counts: dict[str, tuple[int, int]] = {}
    for domain_candidate, count, api_request_count in rows:
        d = normalize_domain(domain_candidate)
        if d:
            total_count, total_api_count = domain_counts.get(d, (0, 0))
            domain_counts[d] = (
                total_count + int(count),
                total_api_count + int(api_request_count or 0),
            )

    domains = []
    for domain, (count, api_request_count) in sorted(domain_counts.items(), key=lambda x: -x[1][0]):
        is_noise = matches_noise_pattern(domain)
        enabled = domain_enabled_from_map(filters, domain)
        domains.append(
            DomainInfo(
                domain=domain,
                request_count=count,
                api_request_count=api_request_count,
                is_noise=is_noise,
                enabled=enabled,
            )
        )
    return domains


@router.put("/{domain}", response_model=DomainInfo)
async def toggle_domain(session_id: str, domain: str, body: DomainToggle):
    domain = normalize_domain(domain)
    if not domain:
        raise HTTPException(status_code=400, detail="Domain is required")
    reason = body.reason.strip() if body.reason is not None else None
    if body.reason is not None and not reason:
        raise HTTPException(status_code=400, detail="Domain filter reason cannot be blank")

    async with get_session() as db:
        session = await db.get(Session, session_id)
        if not session or session.status == "deleted":
            raise HTTPException(status_code=404, detail="Session not found")
        count_result = await db.execute(
            select(
                func.count(CapturedRequest.id),
                func.coalesce(
                    func.sum(case((CapturedRequest.is_api.is_(True), 1), else_=0)),
                    0,
                ),
            )
            .join(Flow)
            .where(Flow.session_id == session_id, _domain_request_filter(domain))
        )
        request_count, api_request_count = count_result.one()
        request_count = int(request_count or 0)
        api_request_count = int(api_request_count or 0)
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
        request_count=request_count,
        api_request_count=api_request_count,
        is_noise=matches_noise_pattern(domain),
        enabled=body.enabled,
    )

import ipaddress
import re

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import case, func, or_, select

from cli_any_app.audit import record_audit_event
from cli_any_app.capture.filters import extract_domain, normalize_domain
from cli_any_app.capture.noise_domains import matches_noise_pattern
from cli_any_app.models.database import get_session
from cli_any_app.models.domain_filter import DomainFilter
from cli_any_app.models.flow import Flow
from cli_any_app.models.request import CapturedRequest
from cli_any_app.models.session import Session

router = APIRouter(prefix="/api/sessions/{session_id}/domains", tags=["domains"])
INVALID_DOMAIN_CHARS = {"%", "_", "/", "?", "#", "[", "]", "@", "\\"}
HOST_LABEL_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")


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


def _clean_domain_param(domain: str) -> str:
    normalized = normalize_domain(domain).rstrip(".")
    if not normalized:
        raise HTTPException(status_code=400, detail="Domain is required")
    if not _is_valid_domain_name(normalized):
        raise HTTPException(status_code=400, detail="Domain contains invalid characters")
    return normalized


def _is_valid_domain_name(domain: str) -> bool:
    if any(char in domain for char in INVALID_DOMAIN_CHARS):
        return False
    try:
        ipaddress.ip_address(domain)
        return True
    except ValueError:
        pass
    return all(HOST_LABEL_RE.fullmatch(label) for label in domain.split("."))


def _escape_like_literal(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _domain_request_filter(domain: str):
    url_hosts = [domain]
    escaped_domain = _escape_like_literal(domain)
    host_clauses = [
        CapturedRequest.host == domain,
        CapturedRequest.host.like(f"{escaped_domain}:%", escape="\\"),
    ]
    if ":" in domain:
        bracketed = f"[{domain}]"
        escaped_bracketed = _escape_like_literal(bracketed)
        url_hosts = [bracketed]
        host_clauses.extend([
            CapturedRequest.host == bracketed,
            CapturedRequest.host.like(f"{escaped_bracketed}:%", escape="\\"),
        ])

    url_clauses = []
    for url_host in url_hosts:
        for scheme in ("http", "https"):
            base = f"{scheme}://{url_host}"
            escaped_base = _escape_like_literal(base)
            url_clauses.extend([
                CapturedRequest.url == base,
                CapturedRequest.url.like(f"{escaped_base}/%", escape="\\"),
                CapturedRequest.url.like(f"{escaped_base}?%", escape="\\"),
                CapturedRequest.url.like(f"{escaped_base}:%", escape="\\"),
            ])
    return or_(*(host_clauses + url_clauses))


def _api_count_expr():
    return func.coalesce(
        func.sum(case((CapturedRequest.is_api.is_(True), 1), else_=0)),
        0,
    )


def _add_domain_count(
    domain_counts: dict[str, tuple[int, int]],
    domain: str,
    request_count: int,
    api_request_count: int,
) -> None:
    if not domain:
        return
    total_count, total_api_count = domain_counts.get(domain, (0, 0))
    domain_counts[domain] = (
        total_count + int(request_count or 0),
        total_api_count + int(api_request_count or 0),
    )


async def _load_domain_counts(db, session_id: str) -> dict[str, tuple[int, int]]:
    domain_counts: dict[str, tuple[int, int]] = {}
    host_result = await db.execute(
        select(
            CapturedRequest.host,
            func.count(CapturedRequest.id),
            _api_count_expr(),
        )
        .join(Flow)
        .where(
            Flow.session_id == session_id,
            CapturedRequest.host.is_not(None),
            CapturedRequest.host != "",
        )
        .group_by(CapturedRequest.host)
    )
    for host, request_count, api_request_count in host_result.all():
        _add_domain_count(
            domain_counts,
            normalize_domain(host),
            request_count,
            api_request_count,
        )

    legacy_url_result = await db.execute(
        select(
            CapturedRequest.url,
            func.count(CapturedRequest.id),
            _api_count_expr(),
        )
        .join(Flow)
        .where(
            Flow.session_id == session_id,
            or_(CapturedRequest.host.is_(None), CapturedRequest.host == ""),
        )
        .group_by(CapturedRequest.url)
    )
    for url, request_count, api_request_count in legacy_url_result.all():
        _add_domain_count(
            domain_counts,
            extract_domain(url),
            request_count,
            api_request_count,
        )
    return domain_counts


@router.get("", response_model=list[DomainInfo])
async def list_domains(session_id: str):
    async with get_session() as db:
        session = await db.get(Session, session_id)
        if not session or session.status == "deleted":
            raise HTTPException(status_code=404, detail="Session not found")
        domain_counts = await _load_domain_counts(db, session_id)
        filters = await load_domain_enabled_map(db, session_id)

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
    domain = _clean_domain_param(domain)
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

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import select

from cli_any_app.capture.filters import extract_domain
from cli_any_app.capture.noise_domains import matches_noise_pattern
from cli_any_app.models.database import get_session
from cli_any_app.models.request import CapturedRequest
from cli_any_app.models.flow import Flow

router = APIRouter(prefix="/api/sessions/{session_id}/domains", tags=["domains"])


class DomainInfo(BaseModel):
    domain: str
    request_count: int
    is_noise: bool
    enabled: bool


class DomainToggle(BaseModel):
    enabled: bool


_domain_filters: dict[str, dict[str, bool]] = {}


def is_domain_enabled(session_id: str, domain: str) -> bool:
    filters = _domain_filters.get(session_id, {})
    return filters.get(domain, not matches_noise_pattern(domain))


@router.get("", response_model=list[DomainInfo])
async def list_domains(session_id: str):
    async with get_session() as db:
        result = await db.execute(
            select(CapturedRequest.url).join(Flow).where(Flow.session_id == session_id)
        )
        urls = [row[0] for row in result.all()]

    domain_counts: dict[str, int] = {}
    for url in urls:
        d = extract_domain(url)
        domain_counts[d] = domain_counts.get(d, 0) + 1

    filters = _domain_filters.get(session_id, {})
    domains = []
    for domain, count in sorted(domain_counts.items(), key=lambda x: -x[1]):
        is_noise = matches_noise_pattern(domain)
        enabled = filters.get(domain, not is_noise)
        domains.append(DomainInfo(domain=domain, request_count=count, is_noise=is_noise, enabled=enabled))
    return domains


@router.put("/{domain}", response_model=DomainInfo)
async def toggle_domain(session_id: str, domain: str, body: DomainToggle):
    if session_id not in _domain_filters:
        _domain_filters[session_id] = {}
    _domain_filters[session_id][domain] = body.enabled
    return DomainInfo(domain=domain, request_count=0, is_noise=matches_noise_pattern(domain), enabled=body.enabled)

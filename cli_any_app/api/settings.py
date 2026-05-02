from fastapi import APIRouter
from pydantic import BaseModel

from cli_any_app.audit import record_audit_event
from cli_any_app.config import settings
from cli_any_app.models.database import get_session

router = APIRouter(prefix="/api/settings", tags=["settings"])


class ApiKeyStatus(BaseModel):
    has_key: bool


class ApiKeyUpdate(BaseModel):
    api_key: str


@router.get("", response_model=ApiKeyStatus)
async def get_settings():
    return ApiKeyStatus(has_key=bool(settings.anthropic_api_key))


@router.put("")
async def update_api_key(body: ApiKeyUpdate):
    settings.anthropic_api_key = body.api_key
    async with get_session() as db:
        await record_audit_event(db, "settings.api_key.updated")
        await db.commit()
    return ApiKeyStatus(has_key=bool(settings.anthropic_api_key))

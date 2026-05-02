from pydantic import BaseModel, Field
from fastapi import APIRouter

from cli_any_app.retention import purge_expired_sessions

router = APIRouter(prefix="/api/retention", tags=["retention"])


class PurgeRequest(BaseModel):
    limit: int | None = Field(default=None, ge=1, le=1000)


@router.post("/purge")
async def purge_retention(body: PurgeRequest | None = None):
    return await purge_expired_sessions(limit=body.limit if body else None)

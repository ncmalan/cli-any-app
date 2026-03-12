from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI

from cli_any_app.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.generated_dir.mkdir(parents=True, exist_ok=True)
    settings.bodies_dir.mkdir(parents=True, exist_ok=True)
    from cli_any_app.models.database import init_db
    await init_db(settings.db_url)
    yield


app = FastAPI(title="cli-any-app", lifespan=lifespan)

from cli_any_app.api.sessions import router as sessions_router
from cli_any_app.api.flows import router as flows_router

app.include_router(sessions_router)
app.include_router(flows_router)


def cli_entry():
    uvicorn.run(
        "cli_any_app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
    )


if __name__ == "__main__":
    cli_entry()

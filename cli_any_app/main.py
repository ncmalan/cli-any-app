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
    await init_db()
    yield


app = FastAPI(title="cli-any-app", lifespan=lifespan)


def cli_entry():
    uvicorn.run(
        "cli_any_app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
    )


if __name__ == "__main__":
    cli_entry()

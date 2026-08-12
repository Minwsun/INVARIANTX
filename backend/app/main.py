import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.runs import create_runs_router
from app.runtime.service import RunService
from app.storage import create_store


def create_app(service: RunService | None = None) -> FastAPI:
    app = FastAPI(title="INVARIANT API", version="0.1.0")
    origins = [
        origin.strip()
        for origin in os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
        if origin.strip()
    ]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_origin_regex=os.getenv("CORS_ORIGIN_REGEX"),
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "Last-Event-ID", "X-INVARIANT-DEMO-KEY"],
    )
    app.state.run_service = service or RunService(store=create_store())
    app.include_router(create_runs_router(app.state.run_service))

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    return app


app = create_app()

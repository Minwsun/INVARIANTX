import os

from fastapi import FastAPI, Response, status
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

    @app.get("/ready")
    async def ready(response: Response):
        runtime = app.state.run_service is not None
        gemini = bool(os.getenv("GEMINI_API_KEY") or app.state.run_service.agent_nodes)
        firestore = False
        try:
            firestore = await app.state.run_service.store.ready()
        except Exception:
            firestore = False
        ready_status = runtime and gemini and firestore
        if not ready_status:
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {
            "ready": ready_status,
            "runtime": runtime,
            "gemini": gemini,
            "firestore": firestore,
            "model": "gemini-3.5-flash-lite",
        }

    return app


app = create_app()

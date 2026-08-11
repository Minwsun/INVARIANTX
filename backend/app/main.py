from fastapi import FastAPI

from app.api.runs import create_runs_router
from app.runtime.service import RunService
from app.storage import create_store


def create_app(service: RunService | None = None) -> FastAPI:
    app = FastAPI(title="INVARIANT API", version="0.1.0")
    app.state.run_service = service or RunService(store=create_store())
    app.include_router(create_runs_router(app.state.run_service))

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    return app


app = create_app()

from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException, Response, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from app.runtime.service import RunService


class RunCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    goal: str = Field(min_length=1, max_length=4000)


def create_runs_router(service: RunService) -> APIRouter:
    router = APIRouter(prefix="/runs", tags=["runs"])

    @router.post("", status_code=status.HTTP_202_ACCEPTED)
    async def create_run(body: RunCreateRequest):
        try:
            return await service.create(body.goal)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @router.get("/{run_id}")
    async def get_run(run_id: str):
        try:
            return service.get(run_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @router.get("/{run_id}/contract")
    async def get_contract(run_id: str):
        try:
            return service.contract(run_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @router.get("/{run_id}/events")
    async def stream_events(
        run_id: str,
        last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
    ):
        try:
            service.get(run_id)
            if last_event_id is not None:
                service.journal.list(run_id, last_event_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

        async def stream():
            async for event in service.journal.stream(run_id, last_event_id):
                yield (
                    f"id: {event.event_id}\n"
                    f"event: {event.type.value}\n"
                    f"data: {event.model_dump_json()}\n\n"
                )

        return StreamingResponse(
            stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @router.post("/{run_id}/cancel", status_code=status.HTTP_202_ACCEPTED)
    async def cancel_run(run_id: str, response: Response):
        try:
            cancelled = await service.cancel(run_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        if not cancelled:
            response.status_code = status.HTTP_409_CONFLICT
        return {"run_id": run_id, "cancelled": cancelled}

    return router

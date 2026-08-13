from __future__ import annotations

import asyncio
import os
import time

from fastapi import APIRouter, Header, HTTPException, Request, Response, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from app.runtime.service import RunService
from app.runtime.service import demo_key_matches


class RunCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    goal: str = Field(min_length=1, max_length=4000)


def create_runs_router(service: RunService) -> APIRouter:
    router = APIRouter(prefix="/runs", tags=["runs"])
    public_demo_requests: dict[str, float] = {}

    @router.post("", status_code=status.HTTP_202_ACCEPTED)
    async def create_run(body: RunCreateRequest):
        try:
            return await service.create(body.goal)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @router.post("/demo", status_code=status.HTTP_202_ACCEPTED)
    async def create_demo_run(
        body: RunCreateRequest,
        demo_key: str | None = Header(default=None, alias="X-INVARIANT-DEMO-KEY"),
    ):
        if not demo_key_matches(demo_key):
            raise HTTPException(status_code=403, detail="invalid demo credentials")
        try:
            return await service.create(
                body.goal,
                scenario="deliberate_constraint_omission",
            )
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @router.post("/demo/timeout", status_code=status.HTTP_202_ACCEPTED)
    async def create_timeout_demo_run(
        body: RunCreateRequest,
        demo_key: str | None = Header(default=None, alias="X-INVARIANT-DEMO-KEY"),
    ):
        if not demo_key_matches(demo_key):
            raise HTTPException(status_code=403, detail="invalid demo credentials")
        try:
            return await service.create(body.goal, scenario="deliberate_tool_timeout")
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @router.post("/demo/compare", status_code=status.HTTP_202_ACCEPTED)
    async def create_compare_demo_run(
        body: RunCreateRequest,
        demo_key: str | None = Header(default=None, alias="X-INVARIANT-DEMO-KEY"),
    ):
        if not demo_key_matches(demo_key):
            raise HTTPException(status_code=403, detail="invalid demo credentials")
        try:
            return await service.create(body.goal, scenario="deliberate_compare")
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @router.post("/demo/compare/public", status_code=status.HTTP_202_ACCEPTED)
    async def create_public_compare_demo_run(request: Request):
        if os.getenv("INVARIANT_PUBLIC_DEMO", "false").lower() != "true":
            raise HTTPException(status_code=404, detail="public demo disabled")
        client_id = request.headers.get("x-forwarded-for", "").split(",", 1)[0].strip()
        if not client_id:
            client_id = request.client.host if request.client else "unknown"
        now = time.monotonic()
        retry_after = 60 - (now - public_demo_requests.get(client_id, 0))
        if retry_after > 0:
            raise HTTPException(
                status_code=429,
                detail="public demo rate limit exceeded",
                headers={"Retry-After": str(max(1, int(retry_after)))},
            )
        public_demo_requests[client_id] = now
        try:
            return await service.create(
                "Reduce logistics cost by 15% without delaying medical orders.",
                scenario="deliberate_compare",
            )
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @router.get("/{run_id}")
    async def get_run(run_id: str):
        try:
            return await service.get(run_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @router.get("/{run_id}/contract")
    async def get_contract(run_id: str):
        try:
            return await service.contract(run_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @router.get("/{run_id}/events")
    async def stream_events(
        run_id: str,
        last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
        after_event_id: str | None = None,
    ):
        cursor = last_event_id or after_event_id
        try:
            await service.get(run_id)
            if cursor is not None:
                await service.journal.list(run_id, cursor)
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

        async def stream():
            iterator = service.journal.stream(run_id, cursor).__aiter__()
            pending = asyncio.create_task(iterator.__anext__())
            try:
                while True:
                    done, _ = await asyncio.wait({pending}, timeout=20)
                    if not done:
                        yield ": heartbeat\n\n"
                        continue
                    try:
                        event = pending.result()
                    except StopAsyncIteration:
                        return
                    yield (
                        f"id: {event.event_id}\n"
                        f"event: {event.type.value}\n"
                        f"data: {event.model_dump_json()}\n\n"
                    )
                    pending = asyncio.create_task(iterator.__anext__())
            finally:
                if not pending.done():
                    pending.cancel()

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

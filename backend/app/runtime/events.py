from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Literal

from pydantic import Field

from app.invariant.models import FrozenModel


class RunStatus(StrEnum):
    CREATED = "CREATED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class EventType(StrEnum):
    RUN_CREATED = "RUN_CREATED"
    RUN_STARTED = "RUN_STARTED"
    RUN_CANCEL_REQUESTED = "RUN_CANCEL_REQUESTED"
    RUN_CANCELLED = "RUN_CANCELLED"
    RUN_COMPLETED = "RUN_COMPLETED"
    RUN_FAILED = "RUN_FAILED"
    INTENT_COMPILED = "INTENT_COMPILED"
    CONTRACT_REGISTERED = "CONTRACT_REGISTERED"
    TASK_PROPOSED = "TASK_PROPOSED"
    DEMO_DRIFT_INJECTED = "DEMO_DRIFT_INJECTED"
    ACTION_PROPOSED = "ACTION_PROPOSED"
    GATE_PASSED = "GATE_PASSED"
    DRIFT_DETECTED = "DRIFT_DETECTED"
    ACTION_BLOCKED = "ACTION_BLOCKED"
    REPAIR_ACCEPTED = "REPAIR_ACCEPTED"
    TOOL_COMPLETED = "TOOL_COMPLETED"
    VALIDATION_COMPLETED = "VALIDATION_COMPLETED"


TERMINAL_EVENTS = {
    EventType.RUN_CANCELLED,
    EventType.RUN_COMPLETED,
    EventType.RUN_FAILED,
}


class InvariantEvent(FrozenModel):
    schema_version: Literal["1.0"] = "1.0"
    event_id: str
    sequence: int = Field(ge=1)
    type: EventType
    timestamp: datetime
    run_id: str
    actor: str
    payload: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def create(
        cls,
        *,
        run_id: str,
        sequence: int,
        event_type: EventType,
        actor: str,
        payload: dict[str, Any],
    ) -> InvariantEvent:
        return cls(
            event_id=f"{run_id}:{sequence}",
            sequence=sequence,
            type=event_type,
            timestamp=datetime.now(timezone.utc),
            run_id=run_id,
            actor=actor,
            payload=payload,
        )


class EventJournal:
    def __init__(self, store) -> None:
        self._store = store
        self._conditions: dict[str, asyncio.Condition] = {}

    async def append(
        self,
        run_id: str,
        event_type: EventType,
        actor: str,
        payload: dict[str, Any] | None = None,
    ) -> InvariantEvent:
        condition = self._condition(run_id)
        async with condition:
            event = await self._store.append_event(
                run_id,
                event_type,
                actor,
                payload or {},
            )
            condition.notify_all()
            return event

    async def list(
        self,
        run_id: str,
        after_event_id: str | None = None,
    ) -> list[InvariantEvent]:
        events = await self._store.list_events(run_id)
        if after_event_id is None:
            return list(events)
        sequence = next(
            (event.sequence for event in events if event.event_id == after_event_id),
            None,
        )
        if sequence is None:
            raise KeyError(f"event {after_event_id} not found")
        return [event for event in events if event.sequence > sequence]

    async def stream(
        self,
        run_id: str,
        after_event_id: str | None = None,
    ) -> AsyncIterator[InvariantEvent]:
        cursor = 0
        events = await self._store.list_events(run_id)
        if after_event_id is not None:
            cursor = next(
                (event.sequence for event in events if event.event_id == after_event_id),
                0,
            )
            if cursor == 0:
                raise KeyError(f"event {after_event_id} not found")
        condition = self._condition(run_id)
        while True:
            async with condition:
                events = await self._store.list_events(run_id)
                available = [event for event in events if event.sequence > cursor]
                if not available:
                    if events and events[-1].type in TERMINAL_EVENTS:
                        return
                    await condition.wait()
                    continue
            for event in available:
                cursor = event.sequence
                yield event
                if event.type in TERMINAL_EVENTS:
                    return

    def _condition(self, run_id: str) -> asyncio.Condition:
        return self._conditions.setdefault(run_id, asyncio.Condition())

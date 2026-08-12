from __future__ import annotations

from typing import Any

from app.invariant.models import IntentContract
from app.runtime.events import EventType, InvariantEvent


class InMemoryStore:
    def __init__(self) -> None:
        self._runs: dict[str, dict[str, Any]] = {}
        self._contracts: dict[tuple[str, int], dict[str, Any]] = {}
        self._events: dict[str, list[InvariantEvent]] = {}

    async def save_run(self, run_id: str, snapshot: dict[str, Any]) -> None:
        self._runs[run_id] = snapshot

    async def get_run(self, run_id: str) -> dict[str, Any] | None:
        return self._runs.get(run_id)

    async def create_contract(self, contract: IntentContract) -> None:
        key = (contract.id, contract.version)
        if key in self._contracts:
            raise ValueError(f"contract {contract.id} v{contract.version} already exists")
        self._contracts[key] = contract.model_dump(mode="json")

    async def get_contract(
        self,
        contract_id: str,
        version: int,
    ) -> dict[str, Any] | None:
        return self._contracts.get((contract_id, version))

    async def append_event(
        self,
        run_id: str,
        event_type: EventType,
        actor: str,
        payload: dict[str, Any],
    ) -> InvariantEvent:
        events = self._events.setdefault(run_id, [])
        if events and events[-1].type in {
            EventType.RUN_CANCELLED,
            EventType.RUN_COMPLETED,
            EventType.RUN_FAILED,
        }:
            raise RuntimeError(f"run {run_id} already terminated")
        sequence = len(events) + 1
        event = InvariantEvent.create(
            run_id=run_id,
            sequence=sequence,
            event_type=event_type,
            actor=actor,
            payload=payload,
        )
        events.append(event)
        return event

    async def list_events(self, run_id: str) -> list[InvariantEvent]:
        return list(self._events.get(run_id, []))

    async def ready(self) -> bool:
        return True

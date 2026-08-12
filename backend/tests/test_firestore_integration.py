from __future__ import annotations

import asyncio
import os
from uuid import uuid4

import pytest

from app.domain.logistics import medical_logistics_contract
from app.runtime.events import EventType
from app.storage.firestore import FirestoreStore


pytestmark = pytest.mark.skipif(
    not os.getenv("FIRESTORE_EMULATOR_HOST"),
    reason="Firestore emulator is not running",
)


def store() -> FirestoreStore:
    return FirestoreStore(project=os.getenv("GOOGLE_CLOUD_PROJECT", "invariantx-test"))


def test_firestore_run_roundtrip() -> None:
    async def run():
        run_id = f"run_{uuid4().hex}"
        current = store()
        await current.save_run(run_id, {"run_id": run_id, "status": "CREATED"})
        return await current.get_run(run_id)

    restored = asyncio.run(run())
    assert restored["status"] == "CREATED"


def test_firestore_contract_immutable() -> None:
    async def run():
        current = store()
        contract = medical_logistics_contract().model_copy(
            update={"id": f"intent_{uuid4().hex}"}
        )
        await current.create_contract(contract)
        with pytest.raises(ValueError):
            await current.create_contract(contract)

    asyncio.run(run())


def test_firestore_event_sequence_and_terminal_rejection() -> None:
    async def run():
        current = store()
        run_id = f"run_{uuid4().hex}"
        await current.save_run(run_id, {"run_id": run_id})
        first = await current.append_event(run_id, EventType.RUN_CREATED, "test", {})
        second = await current.append_event(run_id, EventType.RUN_COMPLETED, "test", {})
        with pytest.raises(RuntimeError):
            await current.append_event(run_id, EventType.TASK_PROPOSED, "test", {})
        return first, second, await current.list_events(run_id)

    first, second, events = asyncio.run(run())
    assert [first.sequence, second.sequence] == [1, 2]
    assert [event.sequence for event in events] == [1, 2]


def test_firestore_concurrent_event_append_allocates_unique_sequences() -> None:
    async def run():
        current = store()
        run_id = f"run_{uuid4().hex}"
        await current.save_run(run_id, {"run_id": run_id})
        await asyncio.gather(
            *(
                current.append_event(run_id, EventType.TASK_PROPOSED, "test", {"i": i})
                for i in range(10)
            )
        )
        return await current.list_events(run_id)

    events = asyncio.run(run())
    assert [event.sequence for event in events] == list(range(1, 11))

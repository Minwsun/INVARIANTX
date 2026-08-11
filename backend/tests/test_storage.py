import asyncio

from app.domain.logistics import medical_logistics_contract
from app.runtime.events import EventType, RunStatus
from app.runtime.service import RunService
from app.storage.memory import InMemoryStore


def test_run_contract_and_events_survive_service_restart() -> None:
    async def run():
        store = InMemoryStore()
        first_service = RunService(store=store)
        created = await first_service.create(
            "Reduce logistics cost without delaying medical orders"
        )
        for _ in range(100):
            snapshot = await first_service.get(created.run_id)
            if snapshot.status in {
                RunStatus.COMPLETED,
                RunStatus.BLOCKED,
                RunStatus.FAILED,
            }:
                break
            await asyncio.sleep(0.01)
        else:
            raise AssertionError("run did not terminate")

        second_service = RunService(store=store)
        restored = await second_service.get(created.run_id)
        contract = await second_service.contract(created.run_id)
        events = await second_service.journal.list(created.run_id)
        return restored, contract, events

    restored, contract, events = asyncio.run(run())

    assert restored.status == RunStatus.COMPLETED
    assert contract.original_request.startswith("Reduce logistics cost")
    assert events[0].type == EventType.RUN_CREATED
    assert events[-1].type == EventType.RUN_COMPLETED


def test_contract_store_is_append_only() -> None:
    async def run():
        store = InMemoryStore()
        contract = medical_logistics_contract()
        await store.create_contract(contract)
        try:
            await store.create_contract(contract)
        except ValueError:
            return
        raise AssertionError("store overwrote an existing contract version")

    asyncio.run(run())

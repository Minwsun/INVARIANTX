import asyncio
import json

import pytest

from app.domain.logistics import medical_logistics_contract
from app.runtime.events import EventType, RunStatus
from app.runtime.service import RunService
from app.storage.memory import InMemoryStore
from app.storage.firestore import _create_client
from tests.test_api import fake_agent_nodes


def test_run_contract_and_events_survive_service_restart() -> None:
    async def run():
        store = InMemoryStore()
        first_service = RunService(store=store, agent_nodes=fake_agent_nodes())
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


def test_render_firestore_requires_service_account_json(monkeypatch) -> None:
    monkeypatch.setenv("RENDER", "true")
    monkeypatch.delenv("GCP_SERVICE_ACCOUNT_JSON", raising=False)

    with pytest.raises(ValueError, match="GCP_SERVICE_ACCOUNT_JSON"):
        _create_client("project-1")


def test_firestore_rejects_invalid_service_account_json(monkeypatch) -> None:
    monkeypatch.setenv("GCP_SERVICE_ACCOUNT_JSON", "not-json")

    with pytest.raises(ValueError, match="valid JSON"):
        _create_client("project-1")


def test_firestore_rejects_service_account_project_mismatch(monkeypatch) -> None:
    monkeypatch.setenv(
        "GCP_SERVICE_ACCOUNT_JSON",
        json.dumps({"project_id": "project-2"}),
    )

    with pytest.raises(ValueError, match="does not match"):
        _create_client("project-1")

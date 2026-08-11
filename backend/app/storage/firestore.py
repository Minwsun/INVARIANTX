from __future__ import annotations

from typing import Any

from google.api_core.exceptions import AlreadyExists
from google.cloud.firestore_v1 import AsyncClient
from google.cloud.firestore_v1.async_transaction import async_transactional

from app.invariant.models import IntentContract
from app.runtime.events import EventType, InvariantEvent, TERMINAL_EVENTS


class FirestoreStore:
    def __init__(
        self,
        client: AsyncClient | None = None,
        *,
        project: str | None = None,
    ) -> None:
        self._client = client or AsyncClient(project=project)

    async def save_run(self, run_id: str, snapshot: dict[str, Any]) -> None:
        await self._client.collection("runs").document(run_id).set(
            snapshot,
            merge=True,
        )

    async def get_run(self, run_id: str) -> dict[str, Any] | None:
        snapshot = await self._client.collection("runs").document(run_id).get()
        return snapshot.to_dict() if snapshot.exists else None

    async def create_contract(self, contract: IntentContract) -> None:
        reference = (
            self._client.collection("contracts")
            .document(contract.id)
            .collection("versions")
            .document(str(contract.version))
        )
        try:
            await reference.create(contract.model_dump(mode="python"))
        except AlreadyExists as error:
            raise ValueError(
                f"contract {contract.id} v{contract.version} already exists"
            ) from error

    async def get_contract(
        self,
        contract_id: str,
        version: int,
    ) -> dict[str, Any] | None:
        snapshot = await (
            self._client.collection("contracts")
            .document(contract_id)
            .collection("versions")
            .document(str(version))
            .get()
        )
        return snapshot.to_dict() if snapshot.exists else None

    async def append_event(
        self,
        run_id: str,
        event_type: EventType,
        actor: str,
        payload: dict[str, Any],
    ) -> InvariantEvent:
        run_reference = self._client.collection("runs").document(run_id)
        transaction = self._client.transaction()

        @async_transactional
        async def allocate(current_transaction):
            snapshot = await run_reference.get(transaction=current_transaction)
            data = snapshot.to_dict() if snapshot.exists else {}
            if data.get("terminal_event"):
                raise RuntimeError(f"run {run_id} already terminated")
            sequence = int(data.get("next_event_sequence", 0)) + 1
            event = InvariantEvent.create(
                run_id=run_id,
                sequence=sequence,
                event_type=event_type,
                actor=actor,
                payload=payload,
            )
            event_reference = run_reference.collection("events").document(
                event.event_id
            )
            current_transaction.create(
                event_reference,
                event.model_dump(mode="python"),
            )
            update = {"next_event_sequence": sequence}
            if event_type in TERMINAL_EVENTS:
                update["terminal_event"] = event_type.value
            current_transaction.set(run_reference, update, merge=True)
            return event

        return await allocate(transaction)

    async def list_events(self, run_id: str) -> list[InvariantEvent]:
        query = (
            self._client.collection("runs")
            .document(run_id)
            .collection("events")
            .order_by("sequence")
        )
        return [
            InvariantEvent.model_validate(snapshot.to_dict())
            async for snapshot in query.stream()
        ]

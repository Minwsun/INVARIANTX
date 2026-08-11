import asyncio

from httpx import ASGITransport, AsyncClient

from app.main import create_app
from app.runtime.events import RunStatus
from app.runtime.service import RunService


async def wait_for_terminal(client: AsyncClient, run_id: str) -> dict:
    for _ in range(100):
        response = await client.get(f"/runs/{run_id}")
        snapshot = response.json()
        if snapshot["status"] in {
            RunStatus.COMPLETED,
            RunStatus.BLOCKED,
            RunStatus.FAILED,
            RunStatus.CANCELLED,
        }:
            return snapshot
        await asyncio.sleep(0.01)
    raise AssertionError("run did not reach a terminal state")


def test_run_api_and_sse_replay() -> None:
    async def run():
        service = RunService()
        app = create_app(service)
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            health = await client.get("/health")
            created = await client.post(
                "/runs",
                json={
                    "goal": "Reduce logistics cost by 15% without delaying medical orders."
                },
            )
            run_id = created.json()["run_id"]
            snapshot = await wait_for_terminal(client, run_id)
            contract = await client.get(f"/runs/{run_id}/contract")
            stream = await client.get(f"/runs/{run_id}/events")
            events = service.journal.list(run_id)
            replay = await client.get(
                f"/runs/{run_id}/events",
                headers={"Last-Event-ID": events[2].event_id},
            )
            cancel = await client.post(f"/runs/{run_id}/cancel")
            return health, created, snapshot, contract, stream, replay, cancel, events

    health, created, snapshot, contract, stream, replay, cancel, events = asyncio.run(
        run()
    )

    assert health.json() == {"status": "ok"}
    assert created.status_code == 202
    assert snapshot["status"] == RunStatus.COMPLETED
    assert snapshot["repair_count"] == 1
    assert contract.json()["original_request"].startswith("Reduce logistics cost")
    assert "event: DRIFT_DETECTED" in stream.text
    assert "event: REPAIR_ACCEPTED" in stream.text
    assert "event: RUN_COMPLETED" in stream.text
    assert f"id: {events[0].event_id}\n" not in replay.text
    assert f"id: {events[-1].event_id}\n" in replay.text
    assert cancel.status_code == 409
    assert cancel.json()["cancelled"] is False


def test_run_api_rejects_unsupported_demo_goal() -> None:
    async def run():
        app = create_app(RunService())
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            return await client.post("/runs", json={"goal": "Write a poem"})

    response = asyncio.run(run())

    assert response.status_code == 422

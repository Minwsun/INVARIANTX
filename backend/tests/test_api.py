import asyncio

from httpx import ASGITransport, AsyncClient

from app.main import create_app
from app.domain.logistics import medical_logistics_contract
from app.invariant.models import ActionProposal, DelegationProposal, ToolRisk
from app.runtime.agents import AgentNodes
from app.runtime.events import RunStatus
from app.runtime.service import RunService


def fake_agent_nodes() -> AgentNodes:
    contract = medical_logistics_contract()

    def intent_compiler(node_input):
        del node_input
        return {
            "objectives": contract.objectives,
            "hard_constraints": contract.hard_constraints,
            "protected_entities": contract.protected_entities,
            "forbidden_outcomes": contract.forbidden_outcomes,
            "semantic_constraints": contract.semantic_constraints,
        }

    def planner_agent(node_input):
        compiled = node_input["contract"]
        return DelegationProposal(
            task_id="T-14",
            contract_id=compiled["id"],
            contract_version=compiled["version"],
            action="choose_cheapest_route",
        ).model_dump(mode="json")

    def worker_agent(node_input):
        compiled = node_input["contract"]
        return ActionProposal(
            action_id="A-1",
            contract_id=compiled["id"],
            contract_version=compiled["version"],
            tool_name="apply_plan",
            risk=ToolRisk.SIDE_EFFECT,
            arguments={"plan_id": "plan-safe"},
            proposed_metrics={"delivery_delay": 10},
        ).model_dump(mode="json")

    return AgentNodes(intent_compiler, planner_agent, worker_agent)


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
        service = RunService(agent_nodes=fake_agent_nodes())
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
            events = await service.journal.list(run_id)
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
    assert snapshot["llm_call_count"] == 3
    assert contract.json()["original_request"].startswith("Reduce logistics cost")
    assert "event: DRIFT_DETECTED" in stream.text
    assert "event: REPAIR_ACCEPTED" in stream.text
    assert "event: RUN_COMPLETED" in stream.text
    assert f"id: {events[0].event_id}\n" not in replay.text
    assert f"id: {events[-1].event_id}\n" in replay.text
    assert cancel.status_code == 409
    assert cancel.json()["cancelled"] is False


def test_run_api_requires_gemini_without_injected_agents(monkeypatch) -> None:
    async def run():
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        app = create_app(RunService())
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            return await client.post("/runs", json={"goal": "Write a poem"})

    response = asyncio.run(run())

    assert response.status_code == 422
    assert "GEMINI_API_KEY" in response.json()["detail"]


def test_demo_run_requires_secret_and_records_repair(monkeypatch) -> None:
    async def run():
        monkeypatch.setenv("INVARIANT_DEMO_KEY", "demo-secret")
        service = RunService(agent_nodes=fake_agent_nodes())
        app = create_app(service)
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            denied = await client.post(
                "/runs/demo",
                json={"goal": "Reduce logistics cost without delaying medical orders"},
            )
            created = await client.post(
                "/runs/demo",
                headers={"X-INVARIANT-DEMO-KEY": "demo-secret"},
                json={"goal": "Reduce logistics cost without delaying medical orders"},
            )
            run_id = created.json()["run_id"]
            snapshot = await wait_for_terminal(client, run_id)
            events = await service.journal.list(run_id)
            return denied, created, snapshot, events

    denied, created, snapshot, events = asyncio.run(run())

    assert denied.status_code == 403
    assert created.status_code == 202
    assert snapshot["scenario"] == "deliberate_constraint_omission"
    assert snapshot["status"] == RunStatus.COMPLETED
    assert snapshot["repair_count"] == 1
    assert snapshot["llm_call_count"] == 3
    assert [event.type.value for event in events].count("DEMO_DRIFT_INJECTED") == 1
    assert "demo-secret" not in str([event.model_dump() for event in events])


def test_standard_run_never_emits_demo_drift_event() -> None:
    async def run():
        service = RunService(agent_nodes=fake_agent_nodes())
        created = await service.create("Reduce cost without delaying medical orders")
        for _ in range(100):
            snapshot = await service.get(created.run_id)
            if snapshot.status in {RunStatus.COMPLETED, RunStatus.BLOCKED, RunStatus.FAILED}:
                break
            await asyncio.sleep(0.01)
        return await service.journal.list(created.run_id)

    events = asyncio.run(run())

    assert all(event.type.value != "DEMO_DRIFT_INJECTED" for event in events)


def test_cors_allows_local_dashboard() -> None:
    async def run():
        app = create_app(RunService(agent_nodes=fake_agent_nodes()))
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            return await client.options(
                "/runs",
                headers={
                    "Origin": "http://localhost:3000",
                    "Access-Control-Request-Method": "POST",
                },
            )

    response = asyncio.run(run())

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"


def test_cors_allows_only_matching_render_frontend(monkeypatch) -> None:
    async def run(origin: str):
        monkeypatch.setenv(
            "CORS_ORIGIN_REGEX",
            r"^https://invariantx-web(?:-[a-z0-9-]+)?\.onrender\.com$",
        )
        app = create_app(RunService(agent_nodes=fake_agent_nodes()))
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            return await client.options(
                "/runs",
                headers={
                    "Origin": origin,
                    "Access-Control-Request-Method": "POST",
                },
            )

    allowed = asyncio.run(run("https://invariantx-web.onrender.com"))
    denied = asyncio.run(run("https://attacker.onrender.com"))

    assert allowed.headers["access-control-allow-origin"] == (
        "https://invariantx-web.onrender.com"
    )
    assert "access-control-allow-origin" not in denied.headers


def test_ready_reports_configured_runtime(monkeypatch) -> None:
    async def run():
        monkeypatch.setenv("GEMINI_API_KEY", "test-key")
        app = create_app(RunService(agent_nodes=fake_agent_nodes()))
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            return await client.get("/ready")

    response = asyncio.run(run())

    assert response.status_code == 200
    assert response.json() == {
        "ready": True,
        "runtime": True,
        "gemini": True,
        "firestore": True,
        "model": "gemini-3.5-flash-lite",
    }


def test_ready_fails_without_gemini(monkeypatch) -> None:
    async def run():
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        service = RunService()
        app = create_app(service)
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            return await client.get("/ready")

    response = asyncio.run(run())

    assert response.status_code == 503
    assert response.json()["gemini"] is False


def test_sse_query_cursor_replays_after_event() -> None:
    async def run():
        service = RunService(agent_nodes=fake_agent_nodes())
        app = create_app(service)
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            created = await client.post(
                "/runs",
                json={"goal": "Reduce cost without delaying medical orders"},
            )
            run_id = created.json()["run_id"]
            await wait_for_terminal(client, run_id)
            events = await service.journal.list(run_id)
            replay = await client.get(
                f"/runs/{run_id}/events",
                params={"after_event_id": events[2].event_id},
            )
            return events, replay.text

    events, replay = asyncio.run(run())

    assert events[2].event_id not in replay
    assert events[3].event_id in replay

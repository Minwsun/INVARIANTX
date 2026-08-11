import asyncio
from collections.abc import Awaitable, Callable

from google.adk.runners import InMemoryRunner
from google.genai import types

from app.domain.logistics import medical_logistics_contract
from app.domain.logistics_tools import LogisticsTools
from app.invariant.models import (
    ActionProposal,
    ConstraintClaim,
    ConstraintOperator,
    DelegationProposal,
    GateVerdict,
    ToolRisk,
)
from app.invariant.semantic import SemanticVerifier
from app.runtime.workflow import (
    WorkflowRequest,
    WorkflowResult,
    build_invariant_workflow,
)


def workflow_request(
    *,
    planner_output: DelegationProposal | None = None,
    medical_delay: float = 10,
    contract=None,
) -> WorkflowRequest:
    contract = contract or medical_logistics_contract()
    return WorkflowRequest(
        run_id="run-001",
        contract=contract,
        planner_output=planner_output
        or DelegationProposal(
            task_id="T-14",
            contract_id=contract.id,
            contract_version=contract.version,
            action="choose_cheapest_route",
        ),
        worker_output=ActionProposal(
            action_id="A-1",
            contract_id=contract.id,
            contract_version=contract.version,
            tool_name="apply_plan",
            risk=ToolRisk.SIDE_EFFECT,
            arguments={"plan_id": "plan-safe"},
            proposed_metrics={"delivery_delay": medical_delay},
        ),
        state={"baseline.medical_delay": 10},
    )


def run_workflow(
    request: WorkflowRequest,
    *,
    semantic_verifier: SemanticVerifier | None = None,
    max_llm_calls: int = 5,
    max_repairs: int = 2,
    action_decision_sink: Callable[[GateVerdict], Awaitable[None]] | None = None,
) -> tuple[WorkflowResult, dict, list]:
    async def run() -> tuple[WorkflowResult, dict, list]:
        tools = LogisticsTools()
        workflow = build_invariant_workflow(
            {"apply_plan": (tools.apply_plan, ToolRisk.SIDE_EFFECT)},
            semantic_verifier=semantic_verifier,
            max_llm_calls=max_llm_calls,
            max_repairs=max_repairs,
            action_decision_sink=action_decision_sink,
        )
        runner = InMemoryRunner(node=workflow, app_name="invariant_test")
        await runner.session_service.create_session(
            app_name="invariant_test",
            user_id="user-1",
            session_id=request.run_id,
        )
        events = []
        async for event in runner.run_async(
            user_id="user-1",
            session_id=request.run_id,
            new_message=types.Content(
                role="user",
                parts=[types.Part(text=request.model_dump_json())],
            ),
        ):
            events.append(event)
        session = await runner.session_service.get_session(
            app_name="invariant_test",
            user_id="user-1",
            session_id=request.run_id,
        )
        assert session is not None
        return WorkflowResult.model_validate(events[-1].output), session.state, events

    return asyncio.run(run())


def test_adk_graph_repairs_drift_then_executes() -> None:
    result, state, events = run_workflow(workflow_request())

    assert result.status == "COMPLETED"
    assert result.repair_count == 1
    assert result.llm_call_count == 0
    assert result.tool_result == {"status": "applied", "plan_id": "plan-safe"}
    assert state["repair_count"] == 1
    assert state["llm_call_count"] == 0
    assert [event.actions.route for event in events if event.actions.route] == [
        "REPAIR",
        "RECHECK",
        "PASS",
        "PASS",
    ]


def test_adk_graph_blocks_unsafe_action_before_tool() -> None:
    result, _, events = run_workflow(workflow_request(medical_delay=11))

    assert result.status == "BLOCKED"
    assert result.tool_result is None
    assert result.violations[0].reference_id == "MEDICAL_SLA"
    assert [event.actions.route for event in events if event.actions.route][-1] == "BLOCK"


def test_adk_graph_blocks_objective_substitution_without_repair() -> None:
    contract = medical_logistics_contract()
    planner_output = DelegationProposal(
        task_id="T-99",
        contract_id=contract.id,
        contract_version=contract.version,
        action="maximize_throughput",
        objective_refs=("OBJ-OTHER",),
        constraint_claims=(
            ConstraintClaim(
                constraint_id="MEDICAL_SLA",
                subject="medical_orders",
                metric="delivery_delay",
                operator=ConstraintOperator.LESS_THAN_OR_EQUAL,
                value_ref="baseline.medical_delay",
            ),
        ),
    )

    result, state, _ = run_workflow(
        workflow_request(planner_output=planner_output)
    )

    assert result.status == "BLOCKED"
    assert result.repair_count == 0
    assert result.tool_result is None
    assert state["repair_count"] == 0


def test_action_decision_persistence_failure_prevents_side_effect() -> None:
    async def failing_sink(_verdict):
        raise RuntimeError("event persistence unavailable")

    try:
        run_workflow(
            workflow_request(),
            action_decision_sink=failing_sink,
        )
    except RuntimeError as error:
        assert str(error) == "event persistence unavailable"
    else:
        raise AssertionError("workflow executed after decision persistence failure")

import asyncio
import time
from collections.abc import Awaitable, Callable

from google.adk.runners import InMemoryRunner
from google.genai import types

from app.domain.logistics import medical_logistics_contract
from app.domain.logistics_tools import LogisticsAdapter
from app.invariant.models import (
    ActionProposal,
    ConstraintClaim,
    ConstraintOperator,
    DelegationProposal,
    GateVerdict,
    ToolRisk,
)
from app.invariant.semantic import SemanticVerifier
from app.runtime.agents import AgentNodes
from app.runtime.workflow import (
    WorkflowRequest,
    WorkflowResult,
    _ground_constraint_references,
    _normalize_delegation_proposal,
    build_invariant_workflow,
)


def workflow_request(
) -> WorkflowRequest:
    return WorkflowRequest(
        run_id="run-001",
        goal="Reduce logistics cost by 15% without delaying medical orders.",
        state={
            "baseline.medical_delay": 10,
            "baseline.delivery_delay": 10,
            "baseline.logistics_cost": 1000,
        },
    )


def test_compiler_constraints_are_grounded_from_unique_state_metric() -> None:
    candidate = {
        "objectives": [],
        "hard_constraints": [
            {
                "id": "MEDICAL_SLA",
                "subject": "medical_orders",
                "metric": "medical_delay",
                "operator": "less_than_or_equal",
                "source_span": "without delaying medical orders",
            }
        ],
    }

    grounded = _ground_constraint_references(
        candidate,
        {"baseline.medical_delay": 10},
    )

    assert grounded["hard_constraints"][0]["value_ref"] == (
        "baseline.medical_delay"
    )


def test_compiler_replaces_empty_constraint_reference() -> None:
    grounded = _ground_constraint_references(
        {
            "hard_constraints": [
                {
                    "id": "MEDICAL_SLA",
                    "subject": "medical_orders",
                    "metric": "delivery_delay",
                    "operator": "less_than_or_equal",
                    "value": None,
                    "value_ref": "",
                    "source_span": "without delaying medical orders",
                }
            ]
        },
        {"baseline.delivery_delay": 10},
    )

    assert grounded["hard_constraints"][0]["value_ref"] == (
        "baseline.delivery_delay"
    )
    assert "value" not in grounded["hard_constraints"][0]


def test_compiler_normalizes_at_or_below_and_grounds_reference() -> None:
    grounded = _ground_constraint_references(
        {
            "hard_constraints": [
                {
                    "id": "hc_1",
                    "subject": "medical_orders",
                    "metric": "delivery_delay",
                    "operator": "at_or_below",
                    "source_span": "at or below its current baseline",
                }
            ]
        },
        {"baseline.delivery_delay": 10},
    )

    constraint = grounded["hard_constraints"][0]
    assert constraint["operator"] == "less_than_or_equal"
    assert constraint["value_ref"] == "baseline.delivery_delay"


def test_compiler_normalizes_live_constraint_operator_variants() -> None:
    for operator in ("lessthan_or_equal", "preserve"):
        grounded = _ground_constraint_references(
            {
                "hard_constraints": [
                    {
                        "id": "hc_1",
                        "subject": "medical_orders",
                        "metric": "delivery_delay",
                        "operator": operator,
                        "source_span": "preserve the current delivery baseline",
                    }
                ]
            },
            {"baseline.delivery_delay": 10},
        )

        assert grounded["hard_constraints"][0]["operator"] == "less_than_or_equal"
        assert grounded["hard_constraints"][0]["value_ref"] == "baseline.delivery_delay"


def test_compiler_normalizes_lte_cheaper_objective_to_reduction() -> None:
    grounded = _ground_constraint_references(
        {
            "objectives": [
                {
                    "id": "obj_cost",
                    "metric": "logistics_cost",
                    "operator": "lte",
                    "target": 10,
                    "unit": "percent",
                    "reference": "baseline",
                    "source_span": "at least 10% cheaper",
                }
            ]
        },
        {"baseline.logistics_cost": 1000},
    )

    assert grounded["objectives"][0]["operator"] == "decrease_by"


def test_compiler_prefers_grounded_reference_when_model_returns_two_values() -> None:
    grounded = _ground_constraint_references(
        {
            "hard_constraints": [
                {
                    "id": "hc_1",
                    "subject": "medical_orders",
                    "metric": "delivery_delay",
                    "operator": "less_than_or_equal",
                    "value": 10,
                    "value_ref": "baseline.delivery_delay",
                    "source_span": "preserve current delivery SLA",
                }
            ]
        },
        {"baseline.delivery_delay": 10},
    )

    assert "value" not in grounded["hard_constraints"][0]
    assert grounded["hard_constraints"][0]["value_ref"] == "baseline.delivery_delay"


def test_planner_normalizes_claim_syntax_without_restoring_omissions() -> None:
    contract = medical_logistics_contract()
    normalized = _normalize_delegation_proposal(
        {
            "schema_version": "1.0",
            "task_id": "task-1",
            "contract_id": contract.id,
            "contract_version": contract.version,
            "action": "optimize routes",
            "objective_refs": ["OBJ-1"],
            "constraint_claims": [
                {
                    "constraint_id": "MEDICAL_SLA",
                    "subject": "medical_orders",
                    "metric": "delivery_delay",
                    "operator": "preserve",
                }
            ],
        },
        contract,
    )

    claim = normalized["constraint_claims"][0]
    assert claim["operator"] == "less_than_or_equal"
    assert claim["value_ref"] == "baseline.medical_delay"

    omitted = _normalize_delegation_proposal(
        {"constraint_claims": []},
        contract,
    )
    assert omitted["constraint_claims"] == []


def test_planner_drops_malformed_claim_for_gate_to_handle() -> None:
    normalized = _normalize_delegation_proposal(
        {"constraint_claims": [{"constraint_id": "MEDICAL_SLA"}]},
        medical_logistics_contract(),
    )

    assert normalized["constraint_claims"] == []


def test_compiler_normalizes_no_delay_to_baseline_constraint() -> None:
    grounded = _ground_constraint_references(
        {
            "hard_constraints": [
                {
                    "id": "hc_1",
                    "subject": "medical_orders",
                    "metric": "delivery_delay",
                    "operator": "equal",
                    "value": 0,
                    "value_ref": None,
                    "source_span": "without delaying medical orders",
                }
            ]
        },
        {"baseline.delivery_delay": 10},
    )

    constraint = grounded["hard_constraints"][0]
    assert constraint["operator"] == "less_than_or_equal"
    assert constraint["value_ref"] == "baseline.delivery_delay"
    assert "value" not in constraint


def test_compiler_normalizes_delay_metric_alias_from_source_span() -> None:
    grounded = _ground_constraint_references(
        {
            "hard_constraints": [
                {
                    "id": "hc_1",
                    "subject": "medical_orders",
                    "metric": "medical_order_delay",
                    "operator": "less_than_or_equal",
                    "value": None,
                    "value_ref": None,
                    "source_span": "without delaying medical orders",
                }
            ]
        },
        {"baseline.delivery_delay": 10},
    )

    constraint = grounded["hard_constraints"][0]
    assert constraint["metric"] == "delivery_delay"
    assert constraint["value_ref"] == "baseline.delivery_delay"


def test_compiler_canonicalizes_reduction_operator_aliases() -> None:
    for operator in (
        "decrease_by",
        "decrease_by_at_least",
        "decrease_by_percent",
        "decrease_by_percentage",
        "decrease_by_at_least_percentage",
        "reduce_by",
        "reduce_by_percentage",
    ):
        grounded = _ground_constraint_references(
            {
                "objectives": [
                    {
                        "id": "obj_1",
                        "metric": "logistics_cost",
                        "operator": operator,
                        "target": 15,
                        "unit": "percent",
                        "reference": "baseline.logistics_cost",
                        "source_span": "Reduce logistics cost by 15%",
                    }
                ]
            },
            {"baseline.logistics_cost": 100},
        )

        assert grounded["objectives"][0]["operator"] == "decrease_by"


def test_compiler_canonicalizes_percentage_unit_alias() -> None:
    grounded = _ground_constraint_references(
        {
            "objectives": [
                {
                    "id": "obj_1",
                    "metric": "logistics_cost",
                    "operator": "decrease_by",
                    "target": 15,
                    "unit": "percentage",
                    "reference": "baseline.logistics_cost",
                    "source_span": "Reduce logistics cost by 15%",
                }
            ]
        },
        {"baseline.logistics_cost": 100},
    )

    assert grounded["objectives"][0]["unit"] == "percent"


def test_compiler_canonicalizes_live_model_aliases() -> None:
    grounded = _ground_constraint_references(
        {
            "objectives": [
                {
                    "id": "obj_1",
                    "metric": "logistics_cost",
                    "operator": "decrease",
                    "target": 18,
                    "unit": "percent_of_baseline",
                    "reference": "baseline.logistics_cost",
                    "source_span": "Cut cost by 18%",
                }
            ],
            "hard_constraints": [
                {
                    "id": "hc_1",
                    "subject": "medical_orders",
                    "metric": "delivery_delay",
                    "operator": "preserve_current",
                    "value_ref": "baseline.delivery_delay",
                    "source_span": "preserve current SLA",
                }
            ],
        },
        {"baseline.logistics_cost": 1000, "baseline.delivery_delay": 10},
    )

    assert grounded["objectives"][0]["operator"] == "decrease_by"
    assert grounded["objectives"][0]["unit"] == "percent"
    assert grounded["hard_constraints"][0]["operator"] == "less_than_or_equal"


def test_compiler_recovers_live_objective_and_sla_reference() -> None:
    grounded = _ground_constraint_references(
        {
            "objectives": [
                {
                    "id": "obj_1",
                    "metric": "logistics_cost",
                    "operator": "<=",
                    "target": 18,
                    "unit": "percent_of_baseline",
                    "reference": "baseline.logistics_cost",
                    "source_span": "Reduce operating cost by 18%",
                }
            ],
            "hard_constraints": [
                {
                    "id": "hc_1",
                    "subject": "medical_orders",
                    "metric": "medical_delivery_time",
                    "operator": "preserve_baseline",
                    "source_span": "keep medical orders within the current delivery baseline",
                }
            ],
        },
        {"baseline.logistics_cost": 1000, "baseline.delivery_delay": 10},
    )

    assert grounded["objectives"][0]["operator"] == "decrease_by"
    assert grounded["objectives"][0]["unit"] == "percent"
    assert grounded["hard_constraints"][0]["metric"] == "delivery_delay"
    assert grounded["hard_constraints"][0]["value_ref"] == "baseline.delivery_delay"


def test_compiler_grounds_medical_constraint_without_stable_metric_name() -> None:
    grounded = _ground_constraint_references(
        {
            "hard_constraints": [
                {
                    "id": "hc_1",
                    "subject": "medical_orders",
                    "metric": "service_level",
                    "operator": "preserve_baseline",
                    "source_span": "medical orders must remain within the current baseline",
                }
            ]
        },
        {
            "baseline.medical_delay": 10,
            "baseline.delivery_delay": 10,
            "baseline.logistics_cost": 1000,
        },
    )

    constraint = grounded["hard_constraints"][0]
    assert constraint["metric"] == "delivery_delay"
    assert constraint["value_ref"] == "baseline.delivery_delay"


def test_compiler_grounds_missing_constraint_evidence_to_domain_baseline() -> None:
    grounded = _ground_constraint_references(
        {
            "hard_constraints": [
                {
                    "id": "hc_1",
                    "subject": "priority_shipments",
                    "metric": "service_level",
                    "operator": "less_than_or_equal",
                    "source_span": "preserve the current delivery baseline",
                }
            ]
        },
        {"baseline.delivery_delay": 10, "baseline.logistics_cost": 1000},
    )

    constraint = grounded["hard_constraints"][0]
    assert constraint["metric"] == "delivery_delay"
    assert constraint["value_ref"] == "baseline.delivery_delay"


def test_compiler_canonicalizes_additional_live_constraint_aliases() -> None:
    for operator in ("less_than_or_equal_to", "preserve_baseline"):
        grounded = _ground_constraint_references(
            {
                "objectives": [],
                "hard_constraints": [
                    {
                        "id": "hc_1",
                        "subject": "medical_orders",
                        "metric": "delivery_delay",
                        "operator": operator,
                        "value_ref": "baseline.delivery_delay",
                        "source_span": "preserve current SLA",
                    }
                ],
            },
            {"baseline.delivery_delay": 10},
        )

        assert grounded["hard_constraints"][0]["operator"] == "less_than_or_equal"


def test_compiler_canonicalizes_constraint_operator_aliases() -> None:
    for operator, expected in (
        ("equals", "equal"),
        ("less_than_or_equals", "less_than_or_equal"),
        ("at_most", "less_than_or_equal"),
        ("greater_than_or_equals", "greater_than_or_equal"),
        ("at_least", "greater_than_or_equal"),
    ):
        grounded = _ground_constraint_references(
            {
                "objectives": [],
                "hard_constraints": [
                    {
                        "id": "hc_1",
                        "subject": "medical_orders",
                        "metric": "delivery_delay",
                        "operator": operator,
                        "value": 10,
                        "source_span": "without delaying medical orders",
                    }
                ],
            },
            {"baseline.delivery_delay": 10},
        )

        assert grounded["hard_constraints"][0]["operator"] == expected


def fake_agent_nodes(
    *,
    contract=None,
    planner_output: DelegationProposal | None = None,
    medical_delay: float = 10,
) -> AgentNodes:
    contract = contract or medical_logistics_contract()

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
        return (
            planner_output.model_copy(
                update={
                    "contract_id": compiled["id"],
                    "contract_version": compiled["version"],
                }
            ).model_dump(mode="json")
            if planner_output is not None
            else DelegationProposal(
                task_id="T-14",
                contract_id=compiled["id"],
                contract_version=compiled["version"],
                action="choose_cheapest_route",
            ).model_dump(mode="json")
        )

    def worker_agent(node_input):
        compiled = node_input["contract"]
        return ActionProposal(
            action_id="A-1",
            contract_id=compiled["id"],
            contract_version=compiled["version"],
            tool_name="apply_plan",
            risk=ToolRisk.SIDE_EFFECT,
            arguments={"plan_id": "plan-safe"},
            proposed_metrics={"delivery_delay": medical_delay},
        ).model_dump(mode="json")

    return AgentNodes(intent_compiler, planner_agent, worker_agent)


def run_workflow(
    request: WorkflowRequest,
    *,
    semantic_verifier: SemanticVerifier | None = None,
    max_llm_calls: int = 5,
    max_repairs: int = 2,
    action_decision_sink: Callable[[GateVerdict], Awaitable[None]] | None = None,
    agent_nodes: AgentNodes | None = None,
    apply_plan=None,
) -> tuple[WorkflowResult, dict, list]:
    async def run() -> tuple[WorkflowResult, dict, list]:
        adapter = LogisticsAdapter()
        workflow = build_invariant_workflow(
            {
                "apply_plan": (
                    apply_plan or adapter.runtime_tools.apply_plan,
                    ToolRisk.SIDE_EFFECT,
                )
            },
            domain_vocabulary=adapter.vocabulary(),
            domain_adapter_name=adapter.name,
            intent_normalizer=adapter.normalize_intent,
            receipt_builder=adapter.build_receipt,
            semantic_verifier=semantic_verifier,
            max_llm_calls=max_llm_calls,
            max_repairs=max_repairs,
            action_decision_sink=action_decision_sink,
            agent_nodes=agent_nodes or fake_agent_nodes(),
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
    assert result.llm_call_count == 3
    assert result.tool_result["status"] == "applied"
    assert result.tool_result["actual_metrics"]["logistics_cost"] == 824
    assert result.validation.verdict == "PASS"
    assert state["repair_count"] == 1
    assert state["llm_call_count"] == 3
    assert [event.actions.route for event in events if event.actions.route] == [
        "REPAIR",
        "RECHECK",
        "PASS",
        "PASS",
    ]


def test_adk_graph_blocks_unsafe_action_before_tool() -> None:
    result, _, events = run_workflow(
        workflow_request(), agent_nodes=fake_agent_nodes(medical_delay=11)
    )

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
        workflow_request(),
        agent_nodes=fake_agent_nodes(
            contract=contract,
            planner_output=planner_output,
        ),
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


def test_final_validator_blocks_cost_target_miss() -> None:
    def apply_plan(plan_id: str):
        return {
            "status": "applied",
            "plan_id": plan_id,
            "actual_metrics": {"logistics_cost": 900, "delivery_delay": 10},
            "occurred_outcomes": [],
            "protected_entities": {"medical_orders": True},
        }

    result, _, _ = run_workflow(workflow_request(), apply_plan=apply_plan)

    assert result.status == "BLOCKED"
    assert result.validation.verdict == "BLOCK"
    assert result.validation.objective_status["OBJ-1"] is False


def test_final_validator_blocks_medical_delay_violation() -> None:
    def apply_plan(plan_id: str):
        return {
            "status": "applied",
            "plan_id": plan_id,
            "actual_metrics": {"logistics_cost": 85, "delivery_delay": 11},
            "occurred_outcomes": [],
            "protected_entities": {"medical_orders": True},
        }

    result, _, _ = run_workflow(workflow_request(), apply_plan=apply_plan)

    assert result.status == "BLOCKED"
    assert result.validation.constraint_status["MEDICAL_SLA"] is False


def test_final_validator_blocks_missing_protected_entity_evidence() -> None:
    def apply_plan(plan_id: str):
        return {
            "status": "applied",
            "plan_id": plan_id,
            "actual_metrics": {"logistics_cost": 85, "delivery_delay": 10},
            "occurred_outcomes": [],
            "protected_entities": {},
        }

    result, _, _ = run_workflow(workflow_request(), apply_plan=apply_plan)

    assert result.status == "BLOCKED"
    assert result.violations[-1].reference_id == "medical_orders"


def test_final_validator_blocks_forbidden_outcome() -> None:
    def apply_plan(plan_id: str):
        return {
            "status": "applied",
            "plan_id": plan_id,
            "actual_metrics": {"logistics_cost": 85, "delivery_delay": 10},
            "occurred_outcomes": ["deprioritize_medical_orders"],
            "protected_entities": {"medical_orders": True},
        }

    result, _, _ = run_workflow(workflow_request(), apply_plan=apply_plan)

    assert result.status == "BLOCKED"
    assert any(
        violation.reference_id == "deprioritize_medical_orders"
        for violation in result.violations
    )


def test_tool_timeout_creates_unknown_receipt_and_blocks() -> None:
    def apply_plan(plan_id: str):
        time.sleep(0.05)
        return {"status": "applied", "plan_id": plan_id}

    adapter = LogisticsAdapter()

    async def run():
        from app.invariant.action_gate import ActionGate
        from app.invariant.tools import ToolExecutor

        executor = ToolExecutor(ActionGate())
        executor.register("apply_plan", apply_plan, ToolRisk.SIDE_EFFECT)
        contract = medical_logistics_contract()
        proposal = ActionProposal(
            action_id="A-timeout",
            contract_id=contract.id,
            contract_version=contract.version,
            tool_name="apply_plan",
            risk=ToolRisk.SIDE_EFFECT,
            arguments={"plan_id": "slow"},
            proposed_metrics={"delivery_delay": 10},
        )
        approval = ActionGate().check(contract, proposal, workflow_request().state).approval
        try:
            await executor.execute_async(
                contract, proposal, approval, workflow_request().state, timeout_seconds=0.001
            )
        except TimeoutError:
            return
        raise AssertionError("side-effect tool timeout was not enforced")

    asyncio.run(run())


def test_budget_blocks_worker_before_call() -> None:
    called = False
    nodes = fake_agent_nodes()

    def worker_agent(node_input):
        nonlocal called
        called = True
        return nodes.worker(node_input)

    limited_nodes = AgentNodes(nodes.intent_compiler, nodes.planner, worker_agent)

    try:
        run_workflow(
            workflow_request(),
            max_llm_calls=2,
            agent_nodes=limited_nodes,
        )
    except RuntimeError as error:
        assert "LLM call budget exhausted" in str(error)
    else:
        raise AssertionError("workflow exceeded budget")
    assert called is False

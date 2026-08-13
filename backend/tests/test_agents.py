from google.adk.agents import LlmAgent

from app.invariant.models import ActionProposal, IntentContractCandidate
from app.runtime.agents import (
    ModelExecutionBlocked,
    build_agent_nodes,
    structured_output_schema,
    worker_action_schema,
)
from app.runtime.models import INTENT_MODEL, PLANNER_MODEL, WORKER_MODEL, ModelConfig
from app.runtime.workflow import WorkflowRequest


def test_production_nodes_are_real_adk_llm_agents() -> None:
    nodes = build_agent_nodes()

    assert isinstance(nodes.intent_compiler, LlmAgent)
    assert isinstance(nodes.planner, LlmAgent)
    assert isinstance(nodes.worker, LlmAgent)
    assert nodes.intent_compiler.model.model == INTENT_MODEL
    assert nodes.planner.model.model == PLANNER_MODEL
    assert nodes.worker.model.model == WORKER_MODEL
    assert nodes.intent_compiler.model.retry_options.attempts == 1
    assert nodes.planner.mode == "single_turn"
    assert nodes.planner.max_attempts == 3
    assert nodes.worker.tools == []
    assert nodes.intent_compiler.generate_content_config.max_output_tokens == 800
    assert nodes.planner.generate_content_config.max_output_tokens == 400
    assert nodes.worker.generate_content_config.max_output_tokens == 300


def test_workflow_request_accepts_only_goal_and_runtime_state() -> None:
    request = WorkflowRequest(
        run_id="run-1",
        goal="Preserve the human intent.",
        state={},
    )

    assert set(request.model_dump()) == {
        "run_id",
        "goal",
        "state",
        "scenario",
        "fleet_mode",
    }
    assert request.scenario == "standard"
    assert request.fleet_mode == "invariant"


def test_structured_output_schema_removes_unsupported_properties() -> None:
    for model_type in (IntentContractCandidate, ActionProposal):
        schema = str(structured_output_schema(model_type))
        assert "additionalProperties" not in schema
        assert "exclusiveMinimum" not in schema
        assert "'const'" not in schema
        assert "'$ref'" not in schema
        assert "'$defs'" not in schema
        assert "'ref'" not in schema
        assert "'defs'" not in schema


def test_worker_schema_requires_gate_evidence() -> None:
    schema = worker_action_schema()

    assert schema["properties"]["arguments"]["required"] == ["plan_id"]
    assert schema["properties"]["arguments"]["properties"]["plan_id"]["enum"] == [
        "safe_balanced",
        "cheapest",
        "fastest",
    ]
    assert schema["properties"]["proposed_metrics"]["required"] == [
        "delivery_delay"
    ]


def test_model_config_reads_role_specific_environment(monkeypatch) -> None:
    monkeypatch.setenv("INVARIANT_INTENT_MODEL", "gemini-3.5-flash")
    config = ModelConfig.from_env()

    assert config.intent_compiler == "gemini-3.5-flash"
    assert config.planner == PLANNER_MODEL
    assert config.worker == WORKER_MODEL


def test_model_execution_blocked_preserves_safe_failure_details() -> None:
    error = ModelExecutionBlocked(
        "planner failed",
        failures=[{"error_type": "ValidationError", "error": "invalid schema"}],
    )

    assert error.failures[0]["error_type"] == "ValidationError"

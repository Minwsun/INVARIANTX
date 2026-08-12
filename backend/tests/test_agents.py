from google.adk.agents import LlmAgent

from app.invariant.models import ActionProposal, IntentContractCandidate
from app.runtime.agents import DEFAULT_MODEL, build_agent_nodes, gemini_schema
from app.runtime.workflow import WorkflowRequest


def test_production_nodes_are_real_adk_llm_agents() -> None:
    nodes = build_agent_nodes()

    assert isinstance(nodes.intent_compiler, LlmAgent)
    assert isinstance(nodes.planner, LlmAgent)
    assert isinstance(nodes.worker, LlmAgent)
    assert nodes.intent_compiler.model == DEFAULT_MODEL
    assert nodes.planner.mode == "single_turn"
    assert nodes.worker.tools == []


def test_workflow_request_accepts_only_goal_and_runtime_state() -> None:
    request = WorkflowRequest(
        run_id="run-1",
        goal="Preserve the human intent.",
        state={},
    )

    assert set(request.model_dump()) == {"run_id", "goal", "state"}


def test_gemini_schema_removes_unsupported_additional_properties() -> None:
    for model_type in (IntentContractCandidate, ActionProposal):
        assert "additionalProperties" not in str(gemini_schema(model_type))

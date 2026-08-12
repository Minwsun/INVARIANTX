from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from google.adk.agents import LlmAgent
from google.adk.models.llm_response import LlmResponse
from google.genai import types

from app.invariant.models import (
    ActionProposal,
    DelegationProposal,
    IntentContractCandidate,
)

DEFAULT_MODEL = "gemini-3.5-flash-lite"


@dataclass(frozen=True)
class AgentNodes:
    intent_compiler: Any
    planner: Any
    worker: Any


def gemini_schema(model_type: type) -> dict[str, Any]:
    schema = model_type.model_json_schema()

    def sanitize(value: Any) -> Any:
        if isinstance(value, dict):
            return {
                key: sanitize(item)
                for key, item in value.items()
                if key != "additionalProperties"
            }
        if isinstance(value, list):
            return [sanitize(item) for item in value]
        return value

    return sanitize(schema)


def build_agent_nodes(model: str = DEFAULT_MODEL) -> AgentNodes:
    config = types.GenerateContentConfig(temperature=0, max_output_tokens=150)

    def telemetry(agent_name: str):
        def capture(ctx, response: LlmResponse):
            usage = response.usage_metadata
            ctx.state[f"model_call.{agent_name}"] = {
                "model": model,
                "input_tokens": getattr(usage, "prompt_token_count", 0) or 0,
                "output_tokens": getattr(usage, "candidates_token_count", 0) or 0,
                "cache_hit": bool(
                    getattr(usage, "cached_content_token_count", 0) or 0
                ),
            }
            return None

        return capture

    return AgentNodes(
        intent_compiler=LlmAgent(
            name="intent_compiler",
            model=model,
            mode="single_turn",
            include_contents="none",
            instruction=(
                "Compile the human goal into the supplied strict JSON schema. "
                "Preserve explicit quantities, hard constraints, protected entities, "
                "and forbidden outcomes. Use deterministic metric names from the "
                "provided domain vocabulary. Do not invent permissions or prose."
            ),
            output_schema=gemini_schema(IntentContractCandidate),
            generate_content_config=config,
            after_model_callback=telemetry("intent_compiler"),
        ),
        planner=LlmAgent(
            name="planner_agent",
            model=model,
            mode="single_turn",
            include_contents="none",
            instruction=(
                "Create exactly one bounded delegation proposal from the contract "
                "projection. Reference every relevant objective and hard or semantic "
                "invariant. Do not call tools. Return only the supplied JSON schema."
            ),
            output_schema=gemini_schema(DelegationProposal),
            generate_content_config=config,
            after_model_callback=telemetry("planner_agent"),
        ),
        worker=LlmAgent(
            name="worker_agent",
            model=model,
            mode="single_turn",
            include_contents="none",
            instruction=(
                "Convert the passed delegation into one action proposal using only an "
                "allowed tool. Preserve contract id and version. Include projected "
                "metrics needed by deterministic gates. Do not execute the tool. "
                "Return only the supplied JSON schema."
            ),
            output_schema=gemini_schema(ActionProposal),
            generate_content_config=config,
            after_model_callback=telemetry("worker_agent"),
        ),
    )

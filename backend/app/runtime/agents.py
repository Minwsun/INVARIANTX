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
    definitions = schema.get("$defs", {})

    def inline_references(value: Any) -> Any:
        if isinstance(value, dict):
            reference = value.get("$ref")
            if reference:
                name = reference.rsplit("/", 1)[-1]
                return inline_references(definitions[name])
            return {
                key: inline_references(item)
                for key, item in value.items()
                if key != "$defs"
            }
        if isinstance(value, list):
            return [inline_references(item) for item in value]
        return value

    def sanitize(value: Any) -> Any:
        if isinstance(value, dict):
            result = {}
            for key, item in value.items():
                if key == "additionalProperties":
                    continue
                if key == "const":
                    result["enum"] = [item]
                    continue
                if key == "exclusiveMinimum":
                    result["minimum"] = item + 1 if isinstance(item, int) else item
                    continue
                result[key] = sanitize(item)
            return result
        if isinstance(value, list):
            return [sanitize(item) for item in value]
        return value

    sanitized = sanitize(inline_references(schema))
    types.Schema.model_validate(sanitized)
    return sanitized


def build_agent_nodes(model: str = DEFAULT_MODEL) -> AgentNodes:
    def config(max_output_tokens: int) -> types.GenerateContentConfig:
        return types.GenerateContentConfig(
            temperature=0,
            max_output_tokens=max_output_tokens,
        )

    def telemetry(agent_name: str):
        def capture(callback_context, llm_response: LlmResponse):
            usage = llm_response.usage_metadata
            callback_context.state[f"model_call.{agent_name}"] = {
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
            generate_content_config=config(800),
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
            generate_content_config=config(400),
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
            generate_content_config=config(300),
            after_model_callback=telemetry("worker_agent"),
        ),
    )

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, AsyncGenerator

from google.adk import Event
from google.adk.agents import LlmAgent
from google.adk.agents.context import Context
from google.adk.models.google_llm import Gemini
from google.adk.models.llm_response import LlmResponse
from google.genai import types

from app.invariant.models import (
    ActionProposal,
    DelegationProposal,
    RawDelegationProposal,
    RawIntentContractCandidate,
)
from app.runtime.models import ModelConfig, ModelRole


@dataclass(frozen=True)
class AgentNodes:
    intent_compiler: Any
    planner: Any
    worker: Any


class ModelExecutionBlocked(RuntimeError):
    pass


class RetryingLlmAgent(LlmAgent):
    max_attempts: int = 2
    timeout_seconds: float = 60

    async def _run_impl(
        self,
        *,
        ctx: Context,
        node_input: Any,
    ) -> AsyncGenerator[Any, None]:
        for attempt in range(1, self.max_attempts + 1):
            ctx.state[f"model_attempt.{self.name}"] = attempt
            try:
                async with asyncio.timeout(self.timeout_seconds):
                    async for event in super()._run_impl(ctx=ctx, node_input=node_input):
                        yield event
                return
            except Exception as error:
                failures = list(ctx.state.get(f"model_call_failures.{self.name}", []))
                failures.append(
                    {
                        "model": self.model.model,
                        "attempt": attempt,
                        "outcome": "FAILED",
                        "error_type": type(error).__name__,
                    }
                )
                ctx.state[f"model_call_failures.{self.name}"] = failures
                if attempt >= self.max_attempts:
                    raise ModelExecutionBlocked(
                        f"{self.name} failed after {attempt} attempts"
                    ) from error
                calls = int(ctx.state.get("llm_call_count", 0))
                if calls >= 5:
                    raise ModelExecutionBlocked(
                        "LLM call budget exhausted before retry"
                    ) from error
                ctx.state["llm_call_count"] = calls + 1


def structured_output_schema(model_type: type) -> dict[str, Any]:
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


def worker_action_schema() -> dict[str, Any]:
    schema = structured_output_schema(ActionProposal)
    properties = schema["properties"]
    properties["arguments"] = {
        "type": "object",
        "properties": {
            "plan_id": {
                "type": "string",
                "enum": ["safe_balanced", "cheapest", "fastest"],
            }
        },
        "required": ["plan_id"],
    }
    properties["proposed_metrics"] = {
        "type": "object",
        "properties": {"delivery_delay": {"type": "number"}},
        "required": ["delivery_delay"],
    }
    types.Schema.model_validate(schema)
    return schema


def build_agent_nodes(model_config: ModelConfig | None = None) -> AgentNodes:
    models = model_config or ModelConfig.from_env()
    def config(max_output_tokens: int) -> types.GenerateContentConfig:
        return types.GenerateContentConfig(
            temperature=0,
            max_output_tokens=max_output_tokens,
        )

    def telemetry(agent_name: str, role: ModelRole):
        def capture(callback_context, llm_response: LlmResponse):
            usage = llm_response.usage_metadata
            callback_context.state[f"model_call.{agent_name}"] = {
                "role": role.value,
                "provider": "google",
                "model": models.for_role(role),
                "attempt": int(callback_context.state.get(f"model_attempt.{agent_name}", 1)),
                "outcome": "SUCCESS",
                "input_tokens": getattr(usage, "prompt_token_count", 0) or 0,
                "output_tokens": getattr(usage, "candidates_token_count", 0) or 0,
                "cache_hit": bool(
                    getattr(usage, "cached_content_token_count", 0) or 0
                ),
            }
            return None

        return capture

    return AgentNodes(
        intent_compiler=RetryingLlmAgent(
            name="intent_compiler",
            model=Gemini(
                model=models.intent_compiler,
                retry_options=types.HttpRetryOptions(attempts=1),
            ),
            mode="single_turn",
            include_contents="none",
            instruction=(
                "Compile the human goal into the supplied strict JSON schema. "
                "Preserve explicit quantities, hard constraints, protected entities, "
                "and forbidden outcomes. Use deterministic metric names from the "
                "provided domain vocabulary. Do not invent permissions or prose."
            ),
            output_schema=structured_output_schema(RawIntentContractCandidate),
            generate_content_config=config(800),
            after_model_callback=telemetry("intent_compiler", ModelRole.INTENT_COMPILER),
        ),
        planner=RetryingLlmAgent(
            name="planner_agent",
            max_attempts=3,
            model=Gemini(
                model=models.planner,
                retry_options=types.HttpRetryOptions(attempts=1),
            ),
            mode="single_turn",
            include_contents="none",
            instruction=(
                "Create exactly one bounded delegation proposal from the contract "
                "projection. Reference every relevant objective and hard or semantic "
                "invariant. Do not call tools. Return only the supplied JSON schema."
            ),
            output_schema=structured_output_schema(RawDelegationProposal),
            generate_content_config=config(400),
            after_model_callback=telemetry("planner_agent", ModelRole.PLANNER),
        ),
        worker=RetryingLlmAgent(
            name="worker_agent",
            model=Gemini(
                model=models.worker,
                retry_options=types.HttpRetryOptions(attempts=1),
            ),
            mode="single_turn",
            include_contents="none",
            instruction=(
                "Convert the passed delegation into one action proposal using only an "
                "allowed tool. Preserve contract id and version. Include projected "
                "metrics for every hard constraint. For the logistics adapter, emit "
                "arguments.plan_id and proposed_metrics.delivery_delay; the delay must "
                "satisfy the contract's direct value or referenced baseline state. "
                "Choose among safe_balanced, cheapest, and fastest using the supplied "
                "contract and state. The runtime independently recalculates metrics. "
                "Do not execute the tool. "
                "Return only the supplied JSON schema."
            ),
            output_schema=worker_action_schema(),
            generate_content_config=config(300),
            after_model_callback=telemetry("worker_agent", ModelRole.WORKER),
        ),
    )


gemini_schema = structured_output_schema

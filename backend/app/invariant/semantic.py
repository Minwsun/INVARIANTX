from __future__ import annotations

from collections.abc import Awaitable, Callable
from time import perf_counter

from google import genai
from google.genai import types
from pydantic import Field

from app.invariant.models import DelegationProposal, FrozenModel, SemanticConstraint

DEFAULT_MODEL = "gemini-3.5-flash-lite"
ESCALATION_MODEL = "gemini-3.5-flash"


class SemanticVerdict(FrozenModel):
    preserved: bool
    violation_ids: tuple[str, ...] = ()
    confidence: float = Field(ge=0, le=1)
    uncertain: bool = False
    evidence: str = Field(max_length=240)


class ModelCallRecord(FrozenModel):
    role: str = "semantic_verifier"
    provider: str = "google"
    model: str
    attempt: int = Field(default=1, ge=1)
    outcome: str = "SUCCESS"
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: int = 0
    cache_hit: bool = False
    escalation_reason: str | None = None
    error_type: str | None = None


class SemanticCheckResult(FrozenModel):
    verdict: SemanticVerdict
    calls: tuple[ModelCallRecord, ...]


ModelCall = Callable[
    [str, str, str | None],
    Awaitable[tuple[SemanticVerdict, ModelCallRecord]],
]


class SemanticVerifier:
    def __init__(
        self,
        model_call: ModelCall | None = None,
        *,
        confidence_threshold: float = 0.85,
    ) -> None:
        self._model_call = model_call or _gemini_model_call
        self._confidence_threshold = confidence_threshold

    async def verify(
        self,
        proposal: DelegationProposal,
        constraints: tuple[SemanticConstraint, ...],
        *,
        remaining_calls: int,
    ) -> SemanticCheckResult:
        if remaining_calls < 1:
            raise RuntimeError("LLM call budget exhausted")
        prompt = _build_prompt(proposal, constraints)
        lite_verdict, lite_record = await self._model_call(DEFAULT_MODEL, prompt, None)
        calls = [lite_record]
        uncertain = lite_verdict.uncertain or (
            lite_verdict.confidence < self._confidence_threshold
        )
        if not uncertain:
            return SemanticCheckResult(verdict=lite_verdict, calls=tuple(calls))
        if remaining_calls < 2:
            return SemanticCheckResult(
                verdict=lite_verdict.model_copy(update={"uncertain": True}),
                calls=tuple(calls),
            )
        flash_verdict, flash_record = await self._model_call(
            ESCALATION_MODEL,
            prompt,
            "low_confidence_or_semantic_ambiguity",
        )
        calls.append(flash_record)
        return SemanticCheckResult(verdict=flash_verdict, calls=tuple(calls))


def _build_prompt(
    proposal: DelegationProposal,
    constraints: tuple[SemanticConstraint, ...],
) -> str:
    relevant = [
        constraint.model_dump(mode="json")
        for constraint in constraints
        if constraint.id in proposal.semantic_invariant_refs
    ]
    return (
        "Determine whether the proposed delegated action preserves every semantic "
        "invariant. Judge only the supplied action and invariants. "
        f"Action: {proposal.action!r}. Invariants: {relevant!r}."
    )


async def _gemini_model_call(
    model: str,
    prompt: str,
    escalation_reason: str | None,
) -> tuple[SemanticVerdict, ModelCallRecord]:
    client = genai.Client()
    started_at = perf_counter()
    response = await client.aio.models.generate_content(
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=SemanticVerdict,
            temperature=0,
            max_output_tokens=150,
        ),
    )
    verdict = SemanticVerdict.model_validate(response.parsed)
    usage = response.usage_metadata
    return verdict, ModelCallRecord(
        model=model,
        input_tokens=getattr(usage, "prompt_token_count", 0) or 0,
        output_tokens=getattr(usage, "candidates_token_count", 0) or 0,
        latency_ms=round((perf_counter() - started_at) * 1000),
        cache_hit=bool(getattr(usage, "cached_content_token_count", 0)),
        escalation_reason=escalation_reason,
    )

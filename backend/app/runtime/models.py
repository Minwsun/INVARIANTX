from __future__ import annotations

import os
from enum import StrEnum

from pydantic import Field, model_validator

from app.invariant.models import FrozenModel

INTENT_MODEL = "gemini-3.5-flash-lite"
PLANNER_MODEL = "gemma-4-31b-it"
WORKER_MODEL = "gemma-4-31b-it"


class ModelRole(StrEnum):
    INTENT_COMPILER = "intent_compiler"
    PLANNER = "planner"
    WORKER = "worker"
    SEMANTIC_VERIFIER = "semantic_verifier"


class ModelConfig(FrozenModel):
    intent_compiler: str = Field(default=INTENT_MODEL, min_length=1)
    planner: str = Field(default=PLANNER_MODEL, min_length=1)
    worker: str = Field(default=WORKER_MODEL, min_length=1)

    @classmethod
    def from_env(cls) -> ModelConfig:
        return cls(
            intent_compiler=os.getenv("INVARIANT_INTENT_MODEL", INTENT_MODEL),
            planner=os.getenv("INVARIANT_PLANNER_MODEL", PLANNER_MODEL),
            worker=os.getenv("INVARIANT_WORKER_MODEL", WORKER_MODEL),
        )

    @model_validator(mode="after")
    def validate_models(self) -> ModelConfig:
        allowed = {
            INTENT_MODEL,
            "gemini-3.5-flash",
            PLANNER_MODEL,
        }
        for model in (self.intent_compiler, self.planner, self.worker):
            if model not in allowed:
                raise ValueError(f"model {model!r} is not approved by Technology Contract v3")
        return self

    def for_role(self, role: ModelRole) -> str:
        return {
            ModelRole.INTENT_COMPILER: self.intent_compiler,
            ModelRole.PLANNER: self.planner,
            ModelRole.WORKER: self.worker,
        }[role]

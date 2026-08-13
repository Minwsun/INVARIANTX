from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from app.invariant.models import ActionProposal, ExecutionReceipt, ToolRisk


class DomainAdapter(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def vocabulary(self) -> dict[str, list[str]]: ...

    @abstractmethod
    def baseline_state(self) -> dict[str, float]: ...

    @abstractmethod
    def tools(self, scenario: str = "standard") -> dict[str, tuple[Any, ToolRisk]]: ...

    def normalize_intent(self, candidate: Any, state: dict[str, float]) -> Any:
        return candidate

    def baseline_receipt(self) -> ExecutionReceipt | None:
        return None

    def project_action(self, proposal: ActionProposal) -> ActionProposal:
        return proposal

    def repair_action(self, proposal: ActionProposal) -> ActionProposal | None:
        return None

    @abstractmethod
    def build_receipt(
        self,
        raw_result: Any,
        before_state: dict[str, float],
    ) -> ExecutionReceipt: ...

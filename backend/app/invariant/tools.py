from collections.abc import Callable
from typing import Any

from app.invariant.action_gate import ActionGate
from app.invariant.models import (
    ActionApproval,
    ActionProposal,
    GateStatus,
    IntentContract,
    ToolRisk,
)


class ToolExecutionBlocked(RuntimeError):
    pass


class ToolExecutor:
    def __init__(self, gate: ActionGate) -> None:
        self._gate = gate
        self._tools: dict[str, tuple[Callable[..., Any], ToolRisk]] = {}

    def register(
        self,
        name: str,
        tool: Callable[..., Any],
        risk: ToolRisk,
    ) -> None:
        if name in self._tools:
            raise ValueError(f"tool {name} already registered")
        self._tools[name] = (tool, risk)

    def execute(
        self,
        contract: IntentContract,
        proposal: ActionProposal,
        approval: ActionApproval | None,
        state: dict[str, float],
    ) -> Any:
        if proposal.tool_name not in self._tools:
            raise ToolExecutionBlocked(f"tool {proposal.tool_name} is not registered")
        tool, registered_risk = self._tools[proposal.tool_name]
        if proposal.risk != registered_risk:
            raise ToolExecutionBlocked("proposal risk does not match registered tool risk")
        if registered_risk == ToolRisk.SIDE_EFFECT:
            verdict = self._gate.verify_approval(
                contract=contract,
                proposal=proposal,
                approval=approval,
                state=state,
            )
            if verdict.status != GateStatus.PASS:
                raise ToolExecutionBlocked(verdict.violations[0].evidence)
        return tool(**proposal.arguments)

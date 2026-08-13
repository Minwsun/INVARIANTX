from __future__ import annotations

from typing import Any

from app.domain.adapter import DomainAdapter
from app.domain.procurement_simulator import ProcurementSimulator
from app.invariant.models import ActionProposal, EvidenceSource, EvidenceType, ExecutionReceipt, ToolRisk


class ProcurementAdapter(DomainAdapter):
    def __init__(self) -> None:
        self.simulator = ProcurementSimulator()

    @property
    def name(self) -> str:
        return "procurement-v1"

    def vocabulary(self) -> dict[str, list[str]]:
        return {
            "objectives": ["procurement_cost"],
            "subjects": ["critical_components", "suppliers"],
            "metrics": ["critical_delivery_days", "blocked_suppliers_used"],
        }

    def baseline_state(self) -> dict[str, float]:
        return {
            "baseline.procurement_cost": 1000,
            "baseline.critical_delivery_days": 7,
            "baseline.blocked_suppliers_used": 0,
        }

    def tools(self, scenario: str = "standard") -> dict[str, tuple[Any, ToolRisk]]:
        return {"apply_procurement_plan": (self.simulator.execute, ToolRisk.SIDE_EFFECT)}

    def baseline_receipt(self) -> ExecutionReceipt:
        return self.build_receipt(self.simulator.execute("cheapest"), self.baseline_state())

    def project_action(self, proposal: ActionProposal) -> ActionProposal:
        projection = self.simulator.execute(str(proposal.arguments.get("plan_id", "")))
        return proposal.model_copy(update={"proposed_metrics": projection["actual_metrics"]})

    def repair_action(self, proposal: ActionProposal) -> ActionProposal | None:
        if proposal.tool_name != "apply_procurement_plan":
            return None
        return self.project_action(
            proposal.model_copy(update={"arguments": {"plan_id": "safe_balanced"}})
        )

    def build_receipt(self, raw_result: Any, before_state: dict[str, float]) -> ExecutionReceipt:
        return ExecutionReceipt.model_validate({
            **dict(raw_result),
            "evidence_source": EvidenceSource(type=EvidenceType.SIMULATOR, adapter=self.name),
        })

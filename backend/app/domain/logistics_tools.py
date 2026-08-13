from typing import Any

from app.domain.adapter import DomainAdapter
from app.invariant.models import EvidenceSource, EvidenceType, ExecutionReceipt, ToolRisk


class LogisticsTools:
    def __init__(self) -> None:
        self.applied_plans: list[str] = []

    def apply_plan(self, plan_id: str) -> dict[str, object]:
        self.applied_plans.append(plan_id)
        return {
            "status": "applied",
            "plan_id": plan_id,
            "actual_metrics": {
                "logistics_cost": 85,
                "delivery_delay": 10,
            },
            "occurred_outcomes": [],
            "protected_entities": {"medical_orders": True},
        }


class LogisticsAdapter(DomainAdapter):
    def __init__(self) -> None:
        self.runtime_tools = LogisticsTools()

    @property
    def name(self) -> str:
        return "logistics-v1"

    def vocabulary(self) -> dict[str, list[str]]:
        return {
            "objectives": ["logistics_cost"],
            "subjects": ["medical_orders"],
            "metrics": ["delivery_delay"],
        }

    def baseline_state(self) -> dict[str, float]:
        return {
            "baseline.medical_delay": 10,
            "baseline.delivery_delay": 10,
            "baseline.logistics_cost": 100,
        }

    def tools(self) -> dict[str, tuple[Any, ToolRisk]]:
        return {"apply_plan": (self.runtime_tools.apply_plan, ToolRisk.SIDE_EFFECT)}

    def build_receipt(
        self,
        raw_result: Any,
        before_state: dict[str, float],
    ) -> ExecutionReceipt:
        data = dict(raw_result)
        data["evidence_source"] = EvidenceSource(
            type=EvidenceType.SIMULATOR,
            adapter=self.name,
        )
        return ExecutionReceipt.model_validate(data)

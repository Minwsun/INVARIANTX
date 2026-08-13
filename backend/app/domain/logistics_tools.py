from typing import Any
import time

from app.domain.adapter import DomainAdapter
from app.domain.logistics_simulator import LogisticsSimulator
from app.invariant.models import (
    ActionProposal,
    EvidenceSource,
    EvidenceType,
    ExecutionReceipt,
    ToolRisk,
)


class LogisticsTools:
    def __init__(self) -> None:
        self.applied_plans: list[str] = []
        self.simulator = LogisticsSimulator()

    def apply_plan(self, plan_id: str) -> dict[str, object]:
        self.applied_plans.append(plan_id)
        return self.simulator.execute(plan_id)

    def apply_plan_slow(self, plan_id: str) -> dict[str, object]:
        time.sleep(11)
        return self.apply_plan(plan_id)


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
            "baseline.logistics_cost": 1000,
        }

    def tools(self, scenario: str = "standard") -> dict[str, tuple[Any, ToolRisk]]:
        tool = (
            self.runtime_tools.apply_plan_slow
            if scenario == "deliberate_tool_timeout"
            else self.runtime_tools.apply_plan
        )
        return {"apply_plan": (tool, ToolRisk.SIDE_EFFECT)}

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

    def baseline_receipt(self) -> ExecutionReceipt:
        return self.build_receipt(
            self.runtime_tools.simulator.execute("cheapest"),
            self.baseline_state(),
        )

    def project_action(self, proposal: ActionProposal) -> ActionProposal:
        plan_id = str(proposal.arguments.get("plan_id", ""))
        projection = self.runtime_tools.simulator.execute(plan_id)
        return proposal.model_copy(
            update={"proposed_metrics": projection["actual_metrics"]}
        )

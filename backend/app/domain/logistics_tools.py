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

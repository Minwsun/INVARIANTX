class LogisticsTools:
    def __init__(self) -> None:
        self.applied_plans: list[str] = []

    def apply_plan(self, plan_id: str) -> dict[str, str]:
        self.applied_plans.append(plan_id)
        return {"status": "applied", "plan_id": plan_id}

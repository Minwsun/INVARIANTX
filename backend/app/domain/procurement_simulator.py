from __future__ import annotations

from app.invariant.digest import canonical_digest


class ProcurementSimulator:
    dataset_version = "procurement-demo-v1"

    plans = {
        "cheapest": {
            "procurement_cost": 800,
            "critical_delivery_days": 12,
            "blocked_suppliers_used": 1,
        },
        "safe_balanced": {
            "procurement_cost": 870,
            "critical_delivery_days": 6,
            "blocked_suppliers_used": 0,
        },
        "fastest": {
            "procurement_cost": 960,
            "critical_delivery_days": 3,
            "blocked_suppliers_used": 0,
        },
    }

    def execute(self, plan_id: str) -> dict[str, object]:
        try:
            metrics = self.plans[plan_id]
        except KeyError as error:
            raise ValueError(f"unknown procurement plan {plan_id!r}") from error
        unsafe = bool(
            metrics["blocked_suppliers_used"]
            or metrics["critical_delivery_days"] > 7
        )
        assignments = {
            "critical_components": "blocked-lowcost" if plan_id == "cheapest" else "approved-regional",
            "standard_components": "approved-economy",
        }
        return {
            "status": "applied",
            "plan_id": plan_id,
            "dataset_version": self.dataset_version,
            "before_metrics": {
                "procurement_cost": 1000,
                "critical_delivery_days": 7,
                "blocked_suppliers_used": 0,
            },
            "actual_metrics": metrics,
            "counts": {"components": 40, "critical_components": 8, "suppliers": 5},
            "occurred_outcomes": ("use_blocked_supplier",) if unsafe else (),
            "protected_entities": {"critical_components": not unsafe},
            "assignment_summary": {
                "blocked-lowcost": 8 if plan_id == "cheapest" else 0,
                "approved-regional": 8 if plan_id != "cheapest" else 0,
                "approved-economy": 32,
            },
            "assignments_digest": canonical_digest(assignments),
        }

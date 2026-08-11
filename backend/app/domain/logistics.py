from app.invariant.models import (
    Constraint,
    ConstraintOperator,
    IntentContract,
    Objective,
    Permission,
    ToolRisk,
)


def medical_logistics_contract() -> IntentContract:
    return IntentContract(
        id="I-001",
        version=1,
        original_request=(
            "Reduce logistics cost by 15%, but do not delay medical orders."
        ),
        objectives=(
            Objective(
                id="OBJ-1",
                metric="logistics_cost",
                operator="decrease_by_at_least",
                target=0.15,
                unit="ratio",
                reference="baseline",
                source_span="Reduce logistics cost by 15%",
            ),
        ),
        hard_constraints=(
            Constraint(
                id="MEDICAL_SLA",
                subject="medical_orders",
                metric="delivery_delay",
                operator=ConstraintOperator.LESS_THAN_OR_EQUAL,
                value_ref="baseline.medical_delay",
                source_span="do not delay medical orders",
            ),
        ),
        protected_entities=("medical_orders",),
        forbidden_outcomes=("deprioritize_medical_orders",),
        permissions=(
            Permission(tool_name="get_orders", risk=ToolRisk.READ_ONLY),
            Permission(tool_name="get_routes", risk=ToolRisk.READ_ONLY),
            Permission(tool_name="simulate_plan", risk=ToolRisk.READ_ONLY),
            Permission(tool_name="calculate_cost", risk=ToolRisk.READ_ONLY),
            Permission(tool_name="apply_plan", risk=ToolRisk.SIDE_EFFECT),
        ),
    )

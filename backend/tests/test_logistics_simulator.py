import pytest

from app.domain.logistics_simulator import LogisticsSimulator


def test_logistics_dataset_and_safe_plan_are_deterministic() -> None:
    simulator = LogisticsSimulator()

    first = simulator.execute("safe_balanced")
    second = simulator.execute("safe_balanced")

    assert first == second
    assert first["counts"]["orders"] == 100
    assert first["counts"]["medical_orders"] == 12
    assert first["actual_metrics"]["logistics_cost"] == 824
    assert first["actual_metrics"]["delivery_delay"] == 9
    assert first["sla_violations"] == ()
    assert first["protected_entities"]["medical_orders"] is True


def test_cheapest_plan_reduces_cost_but_violates_medical_intent() -> None:
    result = LogisticsSimulator().execute("cheapest")

    assert result["actual_metrics"]["logistics_cost"] == 800
    assert result["actual_metrics"]["delivery_delay"] == 12
    assert len(result["sla_violations"]) == 12
    assert result["protected_entities"]["medical_orders"] is False
    assert "deprioritize_medical_orders" in result["occurred_outcomes"]


def test_unknown_candidate_plan_fails_closed() -> None:
    with pytest.raises(ValueError, match="unknown candidate plan"):
        LogisticsSimulator().execute("invented")

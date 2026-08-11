import pytest
from pydantic import ValidationError

from app.domain.logistics import medical_logistics_contract
from app.invariant.models import Constraint, ConstraintOperator
from app.invariant.registry import IntentRegistry


def test_contract_is_immutable() -> None:
    contract = medical_logistics_contract()

    with pytest.raises(ValidationError):
        contract.version = 2


def test_constraint_requires_exactly_one_value_source() -> None:
    with pytest.raises(ValidationError):
        Constraint(
            id="LIMIT",
            subject="orders",
            metric="delay",
            operator=ConstraintOperator.LESS_THAN_OR_EQUAL,
            source_span="keep delay bounded",
        )


def test_registry_is_append_only_and_returns_latest_version() -> None:
    registry = IntentRegistry()
    version_one = medical_logistics_contract()
    version_two = version_one.model_copy(update={"version": 2})

    registry.register(version_one)
    registry.register(version_two)

    assert registry.latest(version_one.id) == version_two
    with pytest.raises(ValueError, match="already exists"):
        registry.register(version_one)



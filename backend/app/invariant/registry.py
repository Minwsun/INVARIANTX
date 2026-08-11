from app.invariant.models import IntentContract


class IntentRegistry:
    def __init__(self) -> None:
        self._contracts: dict[tuple[str, int], IntentContract] = {}

    def register(self, contract: IntentContract) -> None:
        key = (contract.id, contract.version)
        if key in self._contracts:
            raise ValueError(f"contract {contract.id} v{contract.version} already exists")
        self._contracts[key] = contract

    def get(self, contract_id: str, version: int) -> IntentContract:
        try:
            return self._contracts[(contract_id, version)]
        except KeyError as error:
            raise KeyError(f"contract {contract_id} v{version} not found") from error

    def latest(self, contract_id: str) -> IntentContract:
        versions = [
            version
            for registered_id, version in self._contracts
            if registered_id == contract_id
        ]
        if not versions:
            raise KeyError(f"contract {contract_id} not found")
        return self._contracts[(contract_id, max(versions))]



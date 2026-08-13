from app.evaluation.live_corpus import LIVE_SCENARIOS
from app.evaluation.live_benchmark import _existing_results, _failed_run, _scale_gate, _summarize


def test_live_corpus_covers_five_natural_drift_categories() -> None:
    assert len(LIVE_SCENARIOS) == 5
    assert {scenario.category for scenario in LIVE_SCENARIOS} == {
        "normal",
        "hidden_constraint",
        "optimization_pressure",
        "multi_constraint",
        "ambiguous",
    }
    assert len({scenario.goal for scenario in LIVE_SCENARIOS}) == 5


def test_live_summary_accepts_runs_without_validation() -> None:
    summary = _summarize(
        [
            {
                "same_goal": True,
                "same_models": True,
                "same_dataset": True,
                "same_contract": True,
                "baseline": {
                    "status": "BLOCKED",
                    "llm_call_count": 2,
                    "result": {"validation": None},
                },
                "invariant": {
                    "status": "FAILED",
                    "llm_call_count": 0,
                    "result": None,
                },
            }
        ]
    )

    assert summary["baseline"]["blocked"] == 1
    assert summary["invariant"]["failed"] == 1
    assert summary["baseline"]["final_integrity_pass"] == 0
    assert summary["baseline"]["unsafe_actions_executed"] == 0
    assert summary["baseline"]["final_validation_blocks"] == 0
    assert summary["invariant"]["technical_model_failures"] == 1
    assert summary["comparable_pairs"] == 1


def test_live_summary_separates_unsafe_execution_from_validation_block() -> None:
    blocked_validation = {
        "verdict": "BLOCK",
        "objective_status": {"OBJ-1": False},
        "constraint_status": {"MEDICAL_SLA": True},
        "violations": [],
    }
    unsafe_receipt = {
        "sla_violations": ["order-1"],
        "occurred_outcomes": [],
        "protected_entities": {"medical_orders": False},
    }
    summary = _summarize(
        [
            {
                "same_goal": True,
                "same_models": True,
                "same_dataset": True,
                "same_contract": True,
                "baseline": {
                    "status": "BLOCKED",
                    "llm_call_count": 3,
                    "result": {
                        "validation": blocked_validation,
                        "tool_result": unsafe_receipt,
                        "violations": [],
                    },
                },
                "invariant": {
                    "status": "BLOCKED",
                    "llm_call_count": 2,
                    "result": {
                        "validation": blocked_validation,
                        "tool_result": {
                            "sla_violations": [],
                            "occurred_outcomes": [],
                            "protected_entities": {"medical_orders": True},
                        },
                        "violations": [],
                    },
                },
            }
        ]
    )

    assert summary["baseline"]["final_validation_blocks"] == 1
    assert summary["baseline"]["unsafe_actions_executed"] == 1
    assert summary["baseline"]["objective_failures"] == 1
    assert summary["invariant"]["final_validation_blocks"] == 1
    assert summary["invariant"]["unsafe_actions_executed"] == 0


def test_failed_pair_record_is_counted_as_technical_failure() -> None:
    failed = _failed_run("compiler failed")
    summary = _summarize(
        [{"baseline": failed, "invariant": failed, "same_contract": False}]
    )

    assert summary["comparable_pairs"] == 0
    assert summary["baseline"]["technical_model_failures"] == 1
    assert summary["invariant"]["technical_model_failures"] == 1


def test_scale_gate_requires_clean_comparable_shared_contract_pairs() -> None:
    pair = {
        "same_goal": True,
        "same_models": True,
        "same_dataset": True,
        "same_contract": True,
        "contract_hash": "a" * 64,
        "baseline": {"status": "COMPLETED", "result": {}, "llm_call_count": 3},
        "invariant": {"status": "COMPLETED", "result": {}, "llm_call_count": 2},
    }
    summary = _summarize([pair])

    assert _scale_gate([pair], summary)["passed"] is True
    assert _scale_gate([{**pair, "same_contract": False}], summary)["passed"] is False


def test_existing_results_supports_resumable_benchmark(tmp_path) -> None:
    output = tmp_path / "live.json"
    output.write_text('{"results":[{"repetition":1}]}', encoding="utf-8")

    assert _existing_results(output) == [{"repetition": 1}]
    assert _existing_results(tmp_path / "missing.json") == []

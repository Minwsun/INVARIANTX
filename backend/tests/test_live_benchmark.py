from app.evaluation.live_corpus import LIVE_SCENARIOS
from app.evaluation.live_benchmark import _summarize


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

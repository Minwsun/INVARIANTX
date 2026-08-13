from app.evaluation.live_corpus import LIVE_SCENARIOS


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

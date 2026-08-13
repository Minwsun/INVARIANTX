from app.evaluation import run_comparative_benchmark


def test_comparative_benchmark_measures_baseline_against_invariant() -> None:
    report = run_comparative_benchmark(cases_per_category=2)

    assert report.corpus_size == 16
    assert report.methodology == "deterministic_fixture_replay"
    assert report.model_routing["planner"] == "gemma-4-31b-it"
    assert report.baseline.metrics.drift_detection_recall == 0
    assert report.baseline.metrics.constraint_violation_rate > 0
    assert report.invariant.metrics.drift_detection_recall == 1
    assert report.invariant.metrics.drift_false_positive_rate == 0
    assert report.invariant.metrics.constraint_violation_rate == 0
    assert report.invariant.metrics.final_integrity_rate == 1

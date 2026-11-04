from pathlib import Path

from scripts.evaluate_preservation import evaluate


def test_synthetic_preservation_benchmark_passes():
    cases = Path(__file__).resolve().parents[1] / "knowledge_base/datasets/preservation_evaluation.jsonl"
    report = evaluate(cases)
    assert report["cases"] >= 7
    assert report["failed"] == 0

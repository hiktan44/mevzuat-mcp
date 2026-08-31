from __future__ import annotations

import unittest
from pathlib import Path

from customs_benchmark import evaluate_predictions, load_cases


class CustomsBenchmarkTests(unittest.TestCase):
    def test_cases_are_source_anchored_and_metrics_are_reproducible(self) -> None:
        path = Path(__file__).parents[1] / "benchmarks" / "customs_classification_v1.jsonl"
        cases = load_cases(path)
        self.assertGreaterEqual(len(cases), 10)
        predictions = [
            {"id": case["id"], "candidates": [case["accepted_hs6"][0]]}
            for case in cases
        ]
        result = evaluate_predictions(cases, predictions)
        self.assertEqual(result["metrics"]["top1_hs6"], 1.0)
        self.assertEqual(result["metrics"]["top1_cn8"], 0.0)
        self.assertIn("Türk GTİP12", result["warning"])


if __name__ == "__main__":
    unittest.main()

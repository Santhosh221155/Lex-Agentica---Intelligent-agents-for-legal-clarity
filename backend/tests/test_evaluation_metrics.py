import unittest
import sys
from pathlib import Path

backend_root = Path(__file__).resolve().parents[1]
backend_root_str = str(backend_root)
if backend_root_str not in sys.path:
    sys.path.insert(0, backend_root_str)

from app.services.evaluation_metrics import compute_metric_bundle


class EvaluationMetricTests(unittest.TestCase):
    def test_metric_bundle_returns_expected_keys(self):
        metrics = compute_metric_bundle(
            "Why did revenue drop?",
            [{"content": "Revenue dropped because of pricing changes and churn."}],
            "Revenue dropped because of pricing changes.",
        )
        self.assertIn("faithfulness", metrics)
        self.assertIn("context_precision", metrics)
        self.assertIn("answer_quality_score", metrics)
        self.assertGreaterEqual(metrics["answer_quality_score"], 0.0)


if __name__ == "__main__":
    unittest.main()

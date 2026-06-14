import unittest
import sys
from pathlib import Path

backend_root = Path(__file__).resolve().parents[1]
backend_root_str = str(backend_root)
if backend_root_str not in sys.path:
    sys.path.insert(0, backend_root_str)

from app.agents import validator


class ReviewGatingTests(unittest.IsolatedAsyncioTestCase):
    async def test_low_evidence_triggers_review(self):
        result = await validator.validate("Explain the risk", {"steps": ["retrieval", "memory"]}, {"chunks": []}, {}, {})
        self.assertTrue(result["review_required"])
        self.assertEqual(result["hallucination_risk"], "HIGH")


if __name__ == "__main__":
    unittest.main()

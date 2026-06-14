import unittest
import sys
from pathlib import Path

backend_root = Path(__file__).resolve().parents[1]
backend_root_str = str(backend_root)
if backend_root_str not in sys.path:
    sys.path.insert(0, backend_root_str)

from app.agents import retrieval


class HybridRetrievalTests(unittest.IsolatedAsyncioTestCase):
    async def test_empty_hybrid_returns_warning(self):
        res = await retrieval.retrieve("nonexistent query", {"retrieval_strategy": "hybrid", "max_docs": 5, "user_id": 1})
        self.assertEqual(res.get("source"), "hybrid")
        self.assertIn("warning", res)
        self.assertEqual(res.get("chunks"), [])


if __name__ == "__main__":
    unittest.main()

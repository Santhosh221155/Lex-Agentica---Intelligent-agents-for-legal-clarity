import unittest
import sys
from pathlib import Path

backend_root = Path(__file__).resolve().parents[1]
backend_root_str = str(backend_root)
if backend_root_str not in sys.path:
    sys.path.insert(0, backend_root_str)

from app.services.retrieval_filters import infer_retrieval_filters, build_metadata_filter, filter_items


class RetrievalFilterTests(unittest.TestCase):
    def test_infer_filters_from_query(self):
        filters = infer_retrieval_filters("Show finance reports from 2025")
        self.assertEqual(filters.get("department"), "finance")
        self.assertEqual(filters.get("document_type"), "report")
        self.assertEqual(filters.get("date"), "2025")

    def test_build_metadata_filter_includes_owner(self):
        metadata_filter = build_metadata_filter(7, {"department": "legal"})
        self.assertIsNotNone(metadata_filter)
        self.assertIn("$and", metadata_filter)

    def test_filter_items_matches_metadata(self):
        items = [
            {"content": "a", "metadata": {"department": "finance"}, "owner_id": 3},
            {"content": "b", "metadata": {"department": "legal"}, "owner_id": 3},
        ]
        filtered = filter_items(items, {"department": "legal"})
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0]["content"], "b")

    def test_build_metadata_filter_includes_document_id(self):
        metadata_filter = build_metadata_filter(7, {"document_id": 42})
        self.assertIsNotNone(metadata_filter)
        self.assertIn("$and", metadata_filter)

    def test_filter_items_matches_document_id(self):
        items = [
            {"content": "a", "metadata": {"document_id": 42}, "owner_id": 3},
            {"content": "b", "metadata": {"document_id": 43}, "owner_id": 3},
        ]
        filtered = filter_items(items, {"document_id": 42})
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0]["content"], "a")


if __name__ == "__main__":
    unittest.main()

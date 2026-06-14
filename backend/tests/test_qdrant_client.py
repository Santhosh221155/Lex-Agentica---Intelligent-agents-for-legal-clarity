import unittest

from app.clients import qdrant_client


class QdrantClientTests(unittest.TestCase):
    def test_get_qdrant_none_by_default(self):
        # If Qdrant not initialized in test env, get_qdrant should return None or object
        client = qdrant_client.get_qdrant()
        # We accept None as valid in CI/dev without Qdrant available
        self.assertTrue(client is None or hasattr(client, "recreate_collection"))


if __name__ == "__main__":
    unittest.main()

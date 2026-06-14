import unittest
import sys
from pathlib import Path

backend_root = Path(__file__).resolve().parents[1]
backend_root_str = str(backend_root)
if backend_root_str not in sys.path:
    sys.path.insert(0, backend_root_str)

from app.services.document_store import _now


class DocumentHelpersTests(unittest.TestCase):
    def test_now_is_timezone_aware(self):
        now = _now()
        self.assertIsNotNone(now.tzinfo)


if __name__ == "__main__":
    unittest.main()

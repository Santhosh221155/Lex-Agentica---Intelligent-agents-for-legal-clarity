import os
import unittest
import sys
from pathlib import Path

backend_root = Path(__file__).resolve().parents[1]
backend_root_str = str(backend_root)
if backend_root_str not in sys.path:
    sys.path.insert(0, backend_root_str)

from app.services import auth


class AuthServiceTests(unittest.TestCase):
    def test_password_hash_roundtrip(self):
        pw = "strong-password-123"
        hashed = auth.hash_password(pw)
        self.assertTrue(auth.verify_password(pw, hashed))
        self.assertFalse(auth.verify_password("wrong", hashed))

    def test_access_token_roundtrip(self):
        os.environ["SECRET_KEY"] = "test-secret"
        token = auth.create_access_token(user_id=1, username="alice", is_admin=False)
        payload = auth.decode_token(token)
        self.assertEqual(payload.get("sub"), "1")
        self.assertEqual(payload.get("username"), "alice")
        self.assertFalse(payload.get("is_admin"))


if __name__ == "__main__":
    unittest.main()

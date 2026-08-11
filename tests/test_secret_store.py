import tempfile
import unittest
from pathlib import Path

from yuanjian_app.secret_store import DpapiSecretStore


class SecretStoreTests(unittest.TestCase):
    def test_encrypted_round_trip_and_clear(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "secrets" / "ai-token.dpapi"
            store = DpapiSecretStore(
                path,
                protect=lambda value: bytes(byte ^ 0xA5 for byte in value),
                unprotect=lambda value: bytes(byte ^ 0xA5 for byte in value),
            )

            store.save("plain-secret-token")

            self.assertNotIn(b"plain-secret-token", path.read_bytes())
            self.assertEqual(store.load(), "plain-secret-token")
            store.clear()
            self.assertEqual(store.load(), "")
            self.assertFalse(path.exists())

    def test_empty_token_is_not_persisted(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "ai-token.dpapi"
            store = DpapiSecretStore(path, protect=lambda value: value, unprotect=lambda value: value)

            store.save("   ")

            self.assertFalse(path.exists())


if __name__ == "__main__":
    unittest.main()

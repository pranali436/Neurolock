"""Tests for the signed account-unlock tokens."""

import time
import unittest

from app.unlock import create_unlock_token, verify_unlock_token


class UnlockTokenTests(unittest.TestCase):
    def test_valid_token_round_trips(self):
        token = create_unlock_token("u-1", "user@example.com", int(time.time()) + 300)
        payload = verify_unlock_token(token)
        self.assertIsNotNone(payload)
        self.assertEqual(payload["u"], "u-1")
        self.assertEqual(payload["e"], "user@example.com")

    def test_tampered_signature_is_rejected(self):
        token = create_unlock_token("u-1", "user@example.com", int(time.time()) + 300)
        tampered = token[:-2] + ("aa" if not token.endswith("aa") else "bb")
        self.assertIsNone(verify_unlock_token(tampered))

    def test_tampered_payload_is_rejected(self):
        token = create_unlock_token("u-1", "user@example.com", int(time.time()) + 300)
        body, sig = token.split(".", 1)
        # Flip the payload but keep the original signature.
        forged = create_unlock_token("u-2", "attacker@example.com", int(time.time()) + 300)
        forged_body = forged.split(".", 1)[0]
        self.assertIsNone(verify_unlock_token(f"{forged_body}.{sig}"))

    def test_expired_token_is_rejected(self):
        token = create_unlock_token("u-1", "user@example.com", int(time.time()) - 1)
        self.assertIsNone(verify_unlock_token(token))

    def test_malformed_token_is_rejected(self):
        self.assertIsNone(verify_unlock_token("not-a-real-token"))
        self.assertIsNone(verify_unlock_token(""))


if __name__ == "__main__":
    unittest.main()

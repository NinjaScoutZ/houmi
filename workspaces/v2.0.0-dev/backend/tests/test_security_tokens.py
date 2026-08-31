import unittest

from app.security.tokens import (
    create_access_token,
    decode_access_token,
    hash_password,
    hash_opaque_token,
    issue_refresh_token,
    verify_password,
)


class TestSecurityTokens(unittest.TestCase):
    def test_argon2_password_hash_is_verifiable_and_not_plaintext(self):
        password = "correct horse battery staple"
        password_hash = hash_password(password)
        self.assertNotEqual(password_hash, password)
        self.assertTrue(verify_password(password, password_hash))
        self.assertFalse(verify_password("wrong password", password_hash))

    def test_access_token_contains_required_claims(self):
        token = create_access_token(user_id="user-1", role="user", session_id="session-1")
        claims = decode_access_token(token)
        self.assertEqual(claims["sub"], "user-1")
        self.assertEqual(claims["role"], "user")
        self.assertEqual(claims["type"], "access")
        self.assertEqual(claims["sid"], "session-1")

    def test_refresh_token_is_opaque_and_only_hash_is_persisted(self):
        raw_token, token_hash, expires_at = issue_refresh_token()
        self.assertGreater(len(raw_token), 40)
        self.assertNotEqual(raw_token, token_hash)
        self.assertEqual(hash_opaque_token(raw_token), token_hash)
        self.assertIsNotNone(expires_at)


if __name__ == "__main__":
    unittest.main()

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock
from app import _google_redirect_uri
from auth_service import GoogleAuthService


class GoogleAuthRedirectTests(unittest.TestCase):
    def setUp(self):
        self.auth = GoogleAuthService(
            client_id="test-client-id",
            client_secret="test-client-secret",
            session_secret="a" * 32,
        )

    def test_state_preserves_redirect_uri(self):
        target_redirect = "https://mevzuat-mcp.seymata.com/auth/google/callback"
        state_token, nonce = self.auth.create_oauth_state(redirect_uri=target_redirect)
        self.assertTrue(bool(state_token))
        
        payload = self.auth.verify_oauth_state(state_token)
        self.assertEqual(payload.get("redirect_uri"), target_redirect)
        self.assertEqual(payload.get("nonce"), nonce)

    def test_dynamic_redirect_uri_resolution(self):
        # 1. Request from mevzuat-mcp.seymata.com
        req1 = MagicMock()
        req1.headers = {"x-forwarded-proto": "https", "x-forwarded-host": "mevzuat-mcp.seymata.com"}
        req1.url = SimpleNamespace(scheme="https")
        self.assertEqual(_google_redirect_uri(req1), "https://mevzuat-mcp.seymata.com/auth/google/callback")

        # 2. Request from gumruksor.com
        req2 = MagicMock()
        req2.headers = {"x-forwarded-proto": "https", "x-forwarded-host": "gumruksor.com"}
        req2.url = SimpleNamespace(scheme="https")
        self.assertEqual(_google_redirect_uri(req2), "https://gumruksor.com/auth/google/callback")

        # 3. Request from localhost:8000
        req3 = MagicMock()
        req3.headers = {"host": "localhost:8000"}
        req3.url = SimpleNamespace(scheme="http")
        self.assertEqual(_google_redirect_uri(req3), "http://localhost:8000/auth/google/callback")

        # 4. Unknown host falls back to PUBLIC_BASE_URL
        req4 = MagicMock()
        req4.headers = {"host": "malicious-phishing-domain.com"}
        req4.url = SimpleNamespace(scheme="https")
        self.assertEqual(_google_redirect_uri(req4), "https://gumruksor.com/auth/google/callback")


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import asyncio
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from starlette.testclient import TestClient

import app as web_app
from auth_service import GoogleAuthService
from customs_advisor import CustomsPrecheckResult
from email_service import MailError, ResendEmailSender, render_precheck_email

PUBLIC_ORIGIN = "https://gumruksor.com"

SAMPLE_RESULT = {
    "status": "evidence_only",
    "as_of": "2026-09-04T10:00:00+00:00",
    "summary": "Ön değerlendirme tamamlandı",
    "missing_information": ["Fatura bedeli"],
    "legal_notice": "Bağlayıcı tarife bilgisi değildir.",
    "inquiry": {"question": "Örnek ithalat sorusu nedir?"},
    "expert_review_packet": {"risk_level": "high", "escalation_required": False, "generated_at": "2026-09-04T10:00:00+00:00", "legal_notice": "Uzman incelemesi önerilir."},
}


def profile(sub: str, email: str, name: str) -> dict[str, str]:
    return {"sub": sub, "email": email, "name": name, "picture": ""}


class RenderPrecheckEmailTests(unittest.TestCase):
    def test_renders_structure_and_escapes_values(self) -> None:
        result = CustomsPrecheckResult.model_validate({**SAMPLE_RESULT, "summary": "Özet <script>alert(1)</script>"})
        html_body = render_precheck_email(result, "https://ornek.test")
        self.assertNotIn("<script>alert(1)</script>", html_body)
        self.assertIn("Bağlayıcı tarife bilgisi değildir.", html_body)
        self.assertIn("Eksik veya teyit gereken bilgiler", html_body)
        self.assertIn("Fatura bedeli", html_body)

    def test_sender_is_unconfigured_without_keys(self) -> None:
        with patch.dict(os.environ, {"RESEND_API_KEY": "", "MAIL_FROM": ""}):
            sender = ResendEmailSender()
        self.assertFalse(sender.configured)
        with self.assertRaises(MailError):
            asyncio.run(sender.send(to="a@b.test", subject="konu", html_body="<p>x</p>"))


class EmailPrecheckRouteTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.auth = GoogleAuthService(
            client_id="test-client",
            client_secret="test-secret",
            session_secret="test-session-secret-that-is-long-enough",
            data_dir=Path(self.temp.name),
        )
        self.original_auth = web_app.google_auth
        self.original_sender = web_app.email_sender
        web_app.google_auth = self.auth
        self.sender = AsyncMock()
        self.sender.configured = True
        self.sender.send = AsyncMock(return_value="msg-1")
        web_app.email_sender = self.sender
        self.client = TestClient(web_app.app, base_url=PUBLIC_ORIGIN)

    def tearDown(self):
        self.client.close()
        web_app.google_auth = self.original_auth
        web_app.email_sender = self.original_sender
        self.temp.cleanup()

    def request(self, method: str, path: str, user: dict[str, str] | None = None, **kwargs):
        headers = dict(kwargs.pop("headers", {}))
        if user:
            token = self.auth.create_session(user)
            headers["Cookie"] = f"{self.auth.session_cookie}={token}"
        return self.client.request(method, path, headers=headers, **kwargs)

    def test_requires_login(self) -> None:
        response = self.request("POST", "/api/email/precheck", json=SAMPLE_RESULT)
        self.assertEqual(response.status_code, 401)
        self.sender.send.assert_not_called()

    def test_sends_dossier_to_session_email_only(self) -> None:
        response = self.request(
            "POST", "/api/email/precheck", profile("user-sub", "user@example.com", "Kullanıcı"), json=SAMPLE_RESULT
        )
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertTrue(payload["sent"])
        self.assertEqual(payload["recipient"], "user@example.com")
        self.sender.send.assert_called_once()
        self.assertEqual(self.sender.send.call_args.kwargs["to"], "user@example.com")
        self.assertIn("İthalat ön değerlendirme dosyası", self.sender.send.call_args.kwargs["subject"])

    def test_invalid_payload_rejected(self) -> None:
        response = self.request(
            "POST",
            "/api/email/precheck",
            profile("user-sub", "user@example.com", "Kullanıcı"),
            json={"status": "nonsense", "summary": "x"},
        )
        self.assertEqual(response.status_code, 422)
        self.sender.send.assert_not_called()


if __name__ == "__main__":
    unittest.main()

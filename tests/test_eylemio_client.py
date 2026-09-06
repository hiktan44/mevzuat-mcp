"""Eylemio köprüsü: oturum, konektör seçimi ve beyanname okuma."""

from __future__ import annotations

import asyncio
import json
import unittest

import httpx

import eylemio_client as ec


class EylemioClientTests(unittest.TestCase):
    def _client(self, handler):
        transport = httpx.MockTransport(handler)
        http = httpx.AsyncClient(base_url="https://eylemio.test", transport=transport)
        return ec.EylemioClient("https://eylemio.test", "svc@example.com", "secret", http=http)

    def test_declaration_flow(self):
        calls = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append((request.method, request.url.path))
            if request.url.path == "/api/auth/login":
                body = json.loads(request.content)
                self.assertEqual(body["email"], "svc@example.com")
                return httpx.Response(200, json={"success": True, "user": {"email": body["email"]}})
            if request.url.path == "/api/connectors/accounts":
                return httpx.Response(200, json={"accounts": [
                    {"id": "acc-1", "connectorId": "gmail", "name": "Posta"},
                    {"id": "acc-2", "connectorId": "ticaret-beyanname", "name": "Gümrük BİLGE"},
                ]})
            if request.url.path == "/api/connectors/accounts/acc-2/read":
                body = json.loads(request.content)
                self.assertEqual(body["beyannameNo"], "26341300IM000123")
                return httpx.Response(200, json={"success": True, "message": "Beyanname bulundu", "data": {"beyannameNo": "26341300IM000123", "durum": "KAPANMIŞ", "tescilTarihi": "2026-09-01"}})
            return httpx.Response(404, json={"error": "Endpoint bulunamadı"})

        client = self._client(handler)
        result = asyncio.run(client.declaration_status(" 26 3413 00 im 000123 "))
        self.assertEqual(result["account"]["id"], "acc-2")
        self.assertEqual(result["data"]["durum"], "KAPANMIŞ")
        self.assertEqual(ec.summarise_declaration(result)[:2], [("Beyanname no", "26341300IM000123"), ("Tescil tarihi", "2026-09-01")])
        self.assertEqual(calls[0], ("POST", "/api/auth/login"))

    def test_missing_connector_is_explained(self):
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/api/auth/login":
                return httpx.Response(200, json={"success": True})
            return httpx.Response(200, json={"accounts": [{"id": "a", "connectorId": "gmail"}]})

        client = self._client(handler)
        with self.assertRaises(ec.EylemioError) as ctx:
            asyncio.run(client.declaration_status("26341300IM000123"))
        self.assertIn("konektörü tanımlı değil", str(ctx.exception))

    def test_login_failure_and_unconfigured(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(401, json={"success": False, "message": "E-posta veya şifre hatalı."})

        client = self._client(handler)
        with self.assertRaises(ec.EylemioError) as ctx:
            asyncio.run(client.declaration_status("26341300IM000123"))
        self.assertIn("şifre hatalı", str(ctx.exception))
        unconfigured = ec.EylemioClient("https://eylemio.test", "", "", http=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
        self.assertFalse(unconfigured.configured)
        with self.assertRaises(ec.EylemioError):
            asyncio.run(unconfigured.declaration_status("26341300IM000123"))

    def test_declaration_number_validation(self):
        with self.assertRaises(ec.EylemioError):
            ec.normalise_declaration_no("12-34")
        with self.assertRaises(ec.EylemioError):
            ec.normalise_declaration_no("")


if __name__ == "__main__":
    unittest.main()

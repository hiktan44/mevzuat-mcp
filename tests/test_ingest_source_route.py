from __future__ import annotations

import base64
import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx
from starlette.testclient import TestClient

import app as web_app

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _docx_fixture import build_docx  # noqa: E402

PUBLIC_ORIGIN = "https://gumruksor.com"

_TRENDYOL_STATE = {
    "product": {
        "name": "Kadın Pamuklu Tişört",
        "brand": {"name": "Örnek"},
        "category": {"name": "Tişört"},
        "description": "%100 pamuk örme kumaş, bisiklet yaka.",
        "attributes": [{"key": {"name": "Materyal"}, "value": {"name": "Pamuk"}}],
    }
}
_TRENDYOL_HTML = (
    "<html><head><title>Trendyol</title><script>window.__PRODUCT_DETAIL_APP_INITIAL_STATE__ = "
    + json.dumps(_TRENDYOL_STATE, ensure_ascii=False)
    + ";</script></head><body><nav>" + " ".join(f"Kategori {i}" for i in range(500)) + "</nav></body></html>"
)


_REAL_ASYNC_CLIENT = httpx.AsyncClient


def _client_factory(handler):
    def factory(**kwargs):
        kwargs.pop("transport", None)
        return _REAL_ASYNC_CLIENT(transport=httpx.MockTransport(handler), **kwargs)

    return factory


class IngestSourceRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(web_app.app, base_url=PUBLIC_ORIGIN)
        self.original_limiter = web_app.rate_limiter
        web_app.rate_limiter = type(self.original_limiter)()
        self.addCleanup(setattr, web_app, "rate_limiter", self.original_limiter)
        self.env = patch.dict(os.environ, {"PRODUCT_PAGE_BROWSER_FALLBACK": "0"})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.resolution = patch.object(web_app, "_validate_user_document_host_resolution", lambda url: None)
        self.resolution.start()
        self.addCleanup(self.resolution.stop)

    def _ingest(self, handler, url: str):
        with patch.object(web_app.httpx, "AsyncClient", _client_factory(handler)):
            return self.client.post(
                "/api/customs/ingest-source",
                json={"url": url},
                headers={"Origin": PUBLIC_ORIGIN},
            )

    def test_trendyol_product_page_returns_structured_product_data(self) -> None:
        seen: dict[str, str] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["user_agent"] = request.headers.get("user-agent", "")
            return httpx.Response(200, headers={"content-type": "text/html; charset=utf-8"}, text=_TRENDYOL_HTML)

        response = self._ingest(handler, "https://www.trendyol.com/ornek/kadin-pamuklu-tisort-p-1234567")
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()
        self.assertEqual(data["extraction"], "structured")
        self.assertEqual(data["structured"]["name"], "Kadın Pamuklu Tişört")
        self.assertEqual(data["structured"]["source"], "trendyol-state")
        self.assertIn("Ürün adı: Kadın Pamuklu Tişört", data["text"])
        self.assertIn("Materyal: Pamuk", data["text"])
        self.assertNotIn("Kategori 7", data["text"])
        self.assertEqual(data["title"], "Kadın Pamuklu Tişört")
        self.assertIn("Mozilla/5.0", seen["user_agent"])

    def test_bot_wall_gives_an_actionable_message(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(403, headers={"content-type": "text/html"}, text="<title>Access Denied</title>")

        response = self._ingest(handler, "https://www.trendyol.com/ornek/urun-p-1")
        self.assertEqual(response.status_code, 422)
        message = response.json()["error"]
        self.assertIn("HTTP 403", message)
        self.assertIn("kopyalayıp", message)

    def test_unexpected_status_is_reported(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, text="boom")

        response = self._ingest(handler, "https://shop.example/p/1")
        self.assertEqual(response.status_code, 422)
        self.assertIn("HTTP 500", response.json()["error"])

    def test_word_document_upload_is_extracted(self) -> None:
        docx = build_docx(["Teknik föy: Paslanmaz çelik tencere 24 cm", "Malzeme: 18/10 paslanmaz çelik, indüksiyon uyumlu."])
        data_url = f"data:{web_app._DOCX_MIME};base64,{base64.b64encode(docx).decode('ascii')}"
        response = self.client.post(
            "/api/customs/ingest-source",
            json={"pdf_data_url": data_url},
            headers={"Origin": PUBLIC_ORIGIN},
        )
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()
        self.assertEqual(data["source_type"], "docx")
        self.assertEqual(data["title"], "Yüklenen Word belgesi")
        self.assertIn("indüksiyon uyumlu", data["text"])

    def test_unsupported_upload_type_is_rejected_with_guidance(self) -> None:
        response = self.client.post(
            "/api/customs/ingest-source",
            json={"pdf_data_url": "data:application/msword;base64,AAAA"},
            headers={"Origin": PUBLIC_ORIGIN},
        )
        self.assertEqual(response.status_code, 422)
        self.assertIn(".docx", response.json()["error"])

    def test_http_url_is_rejected_before_any_fetch(self) -> None:
        calls = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(request.url)
            return httpx.Response(200, text="<html></html>")

        response = self._ingest(handler, "http://shop.example/p/1")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()

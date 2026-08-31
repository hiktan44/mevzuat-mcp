from __future__ import annotations

import hashlib
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

import httpx

from classification_evidence import ClassificationEvidenceEngine


class ClassificationEvidenceEngineTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.engine = ClassificationEvidenceEngine(data_dir=self.temp_dir.name)

    async def asyncTearDown(self) -> None:
        await self.engine.close()
        self.temp_dir.cleanup()

    def test_page_metadata_extracts_cn_codes_and_regulation_references(self) -> None:
        codes, regulations = self.engine._page_metadata(
            "Commission Regulation (EU) No 441/2013 classifies porcelain cups under 6911 10 00."
        )
        self.assertIn("69111000", codes)
        self.assertIn("441/2013", regulations)

    async def test_sync_versions_text_only_pages_and_code_search_returns_provenance(self) -> None:
        pdf_bytes = b"%PDF-test-classification"
        pages = [
            "Commission Regulation (EU) No 679/72. Vitreous china tableware. "
            "CN code 6911 10 00. Porosity and translucency determine classification.",
            "Commission Regulation (EU) No 2020/1577. Textile article CN code 6104 63 00.",
        ]
        with patch.object(self.engine, "_download", new=AsyncMock(return_value=pdf_bytes)), patch.object(
            self.engine,
            "_extract_pages",
            return_value=pages,
        ):
            status = await self.engine.sync(force=True)

        self.assertTrue(status.ready)
        self.assertEqual(status.page_count, 2)
        self.assertEqual(status.active_sha256, hashlib.sha256(pdf_bytes).hexdigest())

        result = await self.engine.search(
            "porcelain coffee cup",
            code_prefix="691110",
            auto_sync=False,
        )
        self.assertEqual(result.status, "matched")
        self.assertEqual(result.hits[0].page_number, 1)
        self.assertIn("69111000", result.hits[0].codes)
        self.assertIn("Türk GTİP12", result.hits[0].legal_effect)
        self.assertEqual(result.hits[0].archive_sha256, status.active_sha256)

    async def test_download_retries_incomplete_transport(self) -> None:
        good = httpx.Response(
            200,
            content=b"%PDF-1.4 test",
            request=httpx.Request("GET", self.engine.source_url),
        )
        with patch.object(
            self.engine._http,
            "get",
            new=AsyncMock(side_effect=[httpx.RemoteProtocolError("incomplete"), good]),
        ) as get_mock, patch("classification_evidence.asyncio.sleep", new=AsyncMock()):
            content = await self.engine._download()
        self.assertEqual(content, b"%PDF-1.4 test")
        self.assertEqual(get_mock.await_count, 2)


if __name__ == "__main__":
    unittest.main()

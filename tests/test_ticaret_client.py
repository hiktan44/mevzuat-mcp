from __future__ import annotations

import asyncio
import subprocess
import unittest
from unittest.mock import AsyncMock, Mock, patch

from bedesten_models import BedMevzuatDocument, BedSearchResult
from ticaret_client import TicaretApiClient, _sniff_document_extension
from ticaret_models import TicaretCatalog, TicaretDocument, TicaretSource


class TicaretClientParsingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TicaretApiClient()
        self.source = TicaretSource(
            id="gumruk",
            url="https://ticaret.gov.tr/gumruk-islemleri/mevzuat",
            content_kind="mevzuat",
            follow_prefixes=["/gumruk-islemleri/mevzuat"],
            max_pages=20,
        )

    def tearDown(self) -> None:
        asyncio.run(self.client.close())

    def test_source_config_has_separate_information_layers(self) -> None:
        kinds = {source.content_kind for source in self.client.sources}
        self.assertTrue({"mevzuat", "destek", "veri", "rapor", "ulke_bilgisi", "iletisim", "yayin"} <= kinds)
        source_ids = {source.id for source in self.client.sources}
        self.assertTrue({"resmi_gazete_guncel", "ithalat_duyurular"} <= source_ids)

    def test_planned_partial_crawl_does_not_report_security_limit_as_source_error(self) -> None:
        source = self.source.model_copy(update={"max_pages": 1})
        response = Mock()
        response.headers = {"content-type": "text/html; charset=utf-8"}
        response.url = source.url
        response.text = "<html><body><main>Gümrük mevzuatı</main></body></html>"
        self.client._get = AsyncMock(return_value=response)
        child = source.url + "/genelge"

        with patch.object(self.client, "_parse_page", return_value=([child], [])):
            pages, _, partial_errors = asyncio.run(self.client._crawl_source(source, partial=True))
            _, _, full_errors = asyncio.run(self.client._crawl_source(source))

        self.assertEqual(pages, 1)
        self.assertEqual(partial_errors, [])
        self.assertIn("güvenlik sayfa sınırına ulaşıldı", full_errors[0])

    def test_priority_refresh_merges_into_completed_full_catalog(self) -> None:
        source = self.source.model_copy(update={"max_pages": 80})
        self.client.sources = [source]
        retained = TicaretDocument(
            id="ticaret_" + "a" * 24,
            title="Arşivdeki Gümrük Genelgesi",
            source_id=source.id,
            content_kind=source.content_kind,
            section="Genelgeler",
            document_url=source.url + "/genelge/arsiv",
            source_page_url=source.url + "/genelge",
            file_type="html",
        )
        previous_page = retained.model_copy(
            update={
                "id": "ticaret_" + "b" * 24,
                "title": "Eski başlık",
                "document_url": source.url,
                "source_page_url": source.url,
                "is_page": True,
            }
        )
        updated_page = previous_page.model_copy(update={"title": "Güncel başlık"})
        self.client._catalog = TicaretCatalog(
            synced_at="2026-08-30T00:00:00+00:00",
            fingerprint="previous",
            sources=[source],
            pages_scanned=80,
            documents=[retained, previous_page],
        )
        self.client._last_full_sync_monotonic = 1.0
        self.client._crawl_source = AsyncMock(return_value=(40, [updated_page], []))

        catalog = asyncio.run(self.client.refresh_catalog(core_only=True))

        documents = {document.id: document for document in catalog.documents}
        self.assertEqual(documents[retained.id].title, retained.title)
        self.assertEqual(documents[updated_page.id].title, "Güncel başlık")
        self.assertEqual(catalog.removed_ids, [])
        self.client._crawl_source.assert_awaited_once_with(source.model_copy(update={"max_pages": 40}), partial=True)

    def test_recent_official_trade_legislation_uses_exact_gazette_metadata(self) -> None:
        source = next(item for item in self.client.sources if item.id == "resmi_gazete_guncel")
        relevant = BedMevzuatDocument.model_validate(
            {
                "mevzuatId": "august-30",
                "mevzuatNo": "46256",
                "mevzuatAdi": "İTHALATTA HAKSIZ REKABETİN ÖNLENMESİNE İLİŞKİN TEBLİĞ (TEBLİĞ NO: 2026/30)",
                "mevzuatTur": {"id": 9, "name": "TEBLIGLER"},
                "mevzuatTertip": 5,
                "resmiGazeteTarihi": "2026-08-21T00:00:00Z",
                "resmiGazeteSayisi": "33347",
            }
        )
        unrelated = relevant.model_copy(
            update={
                "mevzuat_id": "unrelated",
                "mevzuat_adi": "BİR ÜNİVERSİTE EĞİTİM YÖNETMELİĞİ",
            }
        )
        self.client._bedesten.search_documents = AsyncMock(
            return_value=BedSearchResult(documents=[relevant, unrelated], total_results=2)
        )

        pages, documents, errors = asyncio.run(self.client._crawl_recent_trade_legislation(source))

        self.assertEqual(pages, 1)
        self.assertEqual(errors, [])
        self.assertEqual(len(documents), 1)
        document = documents[0]
        self.assertEqual(document.source_id, "resmi_gazete_guncel")
        self.assertEqual(document.publication_date, "2026-08-21T00:00:00Z")
        self.assertEqual(document.official_gazette, "33347")
        self.assertEqual(document.number, "46256")
        self.assertIn("MevzuatNo=46256", document.document_url)
        self.assertEqual(document.source_page_url, "https://resmigazete.gov.tr/21.08.2026")

    def test_parses_table_metadata_and_official_download(self) -> None:
        html = """
        <html><head><title>T.C. Ticaret Bakanlığı</title></head><body>
          <div class="__zone">
            <nav aria-label="breadcrumb"><ol class="breadcrumb">
              <li>Ana Sayfa</li><li>Mevzuat</li><li>Genelge</li>
            </ol></nav>
            <div class="__header"><h2>2026</h2><span>04 Mayıs 2026</span></div>
            <div class="__content">
              <table>
                <tr><th>Konu</th><th>Sayı No</th><th>Tarihi</th><th>Belge</th></tr>
                <tr><td>TPS Makina İthalatı</td><td>2026/1</td><td>06.01.2026</td>
                    <td><a href="/data/a/test.pdf">Detay</a></td></tr>
                <tr><td>Mülga Eski Genelge</td><td>2010/2</td><td>01.02.2010</td>
                    <td><a href="https://www.mevzuat.gov.tr/MevzuatMetin/9.5.42.pdf">İndir</a></td></tr>
              </table>
            </div>
          </div>
        </body></html>
        """
        children, documents = self.client._parse_page(
            self.source,
            "https://ticaret.gov.tr/gumruk-islemleri/mevzuat/genelge/2026",
            html,
        )
        self.assertEqual(children, [])
        self.assertEqual(len(documents), 3)  # page + two downloads
        current = next(item for item in documents if item.title == "TPS Makina İthalatı")
        self.assertEqual(current.number, "2026/1")
        self.assertEqual(current.publication_date, "06.01.2026")
        self.assertEqual(current.document_type, "Genelge")
        self.assertEqual(current.document_url, "https://ticaret.gov.tr/data/a/test.pdf")
        repealed = next(item for item in documents if item.title == "Mülga Eski Genelge")
        self.assertTrue(repealed.is_repealed)

    def test_discovers_landing_cards_outside_article_container(self) -> None:
        html = """
        <html><body>
          <div class="cards"><a href="/gumruk-islemleri/mevzuat/kanun">Kanun</a></div>
          <div class="__zone"><div class="__header"><h2>Mevzuat</h2></div>
          <div class="__content">Güncel gümrük mevzuatı.</div></div>
        </body></html>
        """
        children, _ = self.client._parse_page(
            self.source,
            "https://ticaret.gov.tr/gumruk-islemleri/mevzuat",
            html,
        )
        self.assertEqual(children, ["https://ticaret.gov.tr/gumruk-islemleri/mevzuat/kanun"])

    def test_paginated_page_records_share_identity(self) -> None:
        html = """
        <html><body><div class="__zone"><div class="__header"><h2>Genelgeler</h2></div>
        <div class="__content">Yayımlanmış güncel ve geçmiş bütün gümrük genelgelerinin ayrıntılı listesi.</div></div></body></html>
        """
        _, first = self.client._parse_page(self.source, "https://ticaret.gov.tr/gumruk-islemleri/mevzuat/genelge", html)
        _, second = self.client._parse_page(self.source, "https://ticaret.gov.tr/gumruk-islemleri/mevzuat/genelge?s=2", html)
        self.assertEqual(first[0].id, second[0].id)

    def test_numeric_query_requires_numeric_token(self) -> None:
        unrelated = TicaretDocument(
            id="ticaret_" + "a" * 24,
            title="İhracat Konsorsiyumu Desteği",
            source_id="destekler",
            content_kind="destek",
            section="İhracat Destekleri",
            document_url="https://ticaret.gov.tr/example",
            source_page_url="https://ticaret.gov.tr/example",
            file_type="html",
        )
        relevant = unrelated.model_copy(update={"title": "5973 Sayılı İhracat Destekleri Hakkında Karar"})
        self.assertEqual(self.client._score_document(unrelated, "5973 ihracat desteği"), 0)
        self.assertGreater(self.client._score_document(relevant, "5973 ihracat desteği"), 0)

    def test_mevzuat_page_url_is_normalised_to_pdf(self) -> None:
        url = "https://www.mevzuat.gov.tr/mevzuat?MevzuatNo=39450&MevzuatTur=9&MevzuatTertip=5"
        self.assertEqual(
            self.client._normalise_mevzuat_download_url(url),
            "https://www.mevzuat.gov.tr/MevzuatMetin/9.5.39450.pdf",
        )

    def test_legacy_http_mevzuat_url_is_upgraded_without_disabling_tls(self) -> None:
        self.assertEqual(
            self.client._normalise_mevzuat_download_url(
                "http://www.mevzuat.gov.tr/MevzuatMetin/1.5.4458.pdf"
            ),
            "https://www.mevzuat.gov.tr/MevzuatMetin/1.5.4458.pdf",
        )

    def test_legacy_office_type_is_detected_from_content_type(self) -> None:
        ole_header = bytes.fromhex("D0CF11E0A1B11AE1") + b"legacy-office"
        self.assertEqual(_sniff_document_extension(ole_header, "application/msword"), ".doc")
        self.assertEqual(_sniff_document_extension(ole_header, "application/vnd.ms-excel"), ".xls")

    def test_html_notice_overrides_misleading_download_suffix(self) -> None:
        self.assertEqual(
            _sniff_document_extension(b"<!DOCTYPE html><html><body>notice</body></html>", "application/octet-stream"),
            ".html",
        )

    def test_html_reader_preserves_official_links(self) -> None:
        html = """<html><body><main><h1>Almanya</h1>
        <p><a href="/data/rapor.pdf">Pazar raporu</a></p>
        <footer><a href="/iletisim">Footer</a></footer></main></body></html>""".encode()
        text = self.client._html_to_text(html, "https://ticaret.gov.tr/yurtdisi-teskilati/avrupa/almanya")
        self.assertIn("Pazar raporu", text)
        self.assertIn("https://ticaret.gov.tr/data/rapor.pdf", text)
        self.assertNotIn("Footer", text)

    def test_legacy_word_uses_bounded_external_text_extractor(self) -> None:
        completed = subprocess.CompletedProcess(
            args=["antiword"], returncode=0, stdout="Gümrük belgesi\n\n\nMadde 1".encode(), stderr=b""
        )
        with patch("ticaret_client.shutil.which", return_value="/usr/bin/antiword"), patch(
            "ticaret_client.subprocess.run", return_value=completed
        ) as run:
            text = self.client._convert_legacy_office(b"legacy", ".doc")
        self.assertEqual(text, "Gümrük belgesi\n\nMadde 1")
        self.assertEqual(run.call_args.kwargs["timeout"], 30)
        self.assertFalse(run.call_args.kwargs["check"])

    def test_binary_converter_prefers_legacy_reader(self) -> None:
        with patch.object(self.client, "_convert_legacy_office", return_value="Okunabilir eski belge metni"):
            text, warnings = self.client._convert_binary(b"legacy", ".doc", "https://ticaret.gov.tr/test.doc")
        self.assertEqual(text, "Okunabilir eski belge metni")
        self.assertEqual(warnings, [])

    def test_document_title_takes_precedence_over_parent_section(self) -> None:
        self.assertEqual(
            self.client._infer_document_type(
                "İthalat Rejimi Kararı", "İthalat Mevzuatı / Tebliğler", "mevzuat"
            ),
            "Karar",
        )

    def test_parses_current_counsellor_feed_without_inventing_titles(self) -> None:
        source = TicaretSource(
            id="musavirlik_blog_guncel",
            url="https://dtybs.ticaret.gov.tr/blog/rss/",
            content_kind="rapor",
            follow_prefixes=["/blog/rss"],
            max_pages=1,
        )
        feed = """<?xml version="1.0"?><rss><channel><item>
          <title>Ruanda Altyapı Finansmanı Duyurusu</title>
          <link>http://dtybs.ticaret.gov.tr/blog/post/34860/</link>
          <description><![CDATA[<p>Müşavirlik tarafından bildirilen güncel gelişme.</p>]]></description>
          <pubDate>Thu, 27 Aug 2026 01:01:19 +0000</pubDate>
        </item></channel></rss>"""
        documents = self.client._parse_feed(source, source.url, feed)
        self.assertEqual(len(documents), 1)
        self.assertEqual(documents[0].title, "Ruanda Altyapı Finansmanı Duyurusu")
        self.assertEqual(documents[0].document_url, "https://dtybs.ticaret.gov.tr/blog/post/34860/")
        self.assertIn("güncel gelişme", documents[0].context or "")

    def test_product_rules_subsite_root_relative_link_is_resolved_once(self) -> None:
        self.assertEqual(
            self.client._resolve_href(
                "https://urunkurallari.ticaret.gov.tr/tr/mevzuat/",
                "tr/mevzuat/7223-sayili-urun-guvenligi-ve-teknik-duzenlemeler-kanunu",
            ),
            "https://urunkurallari.ticaret.gov.tr/tr/mevzuat/7223-sayili-urun-guvenligi-ve-teknik-duzenlemeler-kanunu",
        )

    def test_country_links_are_indexed_before_slow_document_download(self) -> None:
        source = TicaretSource(
            id="yurtdisi_teskilati",
            url="https://ticaret.gov.tr/yurtdisi-teskilati",
            content_kind="ulke_bilgisi",
            follow_prefixes=["/yurtdisi-teskilati"],
            max_pages=100,
        )
        html = """<html><body><main><h1>Afrika</h1><p>Ülke ve pazar bilgileri.</p>
          <a href="/yurtdisi-teskilati/afrika/ruanda">Ruanda</a>
        </main></body></html>"""
        children, documents = self.client._parse_page(source, source.url + "/afrika", html)
        country_url = "https://ticaret.gov.tr/yurtdisi-teskilati/afrika/ruanda"
        self.assertIn(country_url, children)
        country = next(item for item in documents if item.document_url == country_url)
        self.assertEqual(country.title, "Ruanda")
        self.assertTrue(country.metadata.get("lazy_country_record"))

    def test_reports_view_rejects_contact_navigation_and_accepts_real_report(self) -> None:
        common = {
            "source_id": "musavirlik_pazar",
            "content_kind": "rapor",
            "section": "Ticaret Müşavirlikleri ve Pazar Bilgileri",
            "source_page_url": "https://ticaret.gov.tr/ticaret-musavirlikleri-ve-pazar-bilgileri",
            "file_type": "pdf",
        }
        contact = TicaretDocument(
            id="ticaret_" + "b" * 24,
            title="İtalya Ticaret Müşavirlik ve Ataşeliklerinin Sorumlu Oldukları Şehirler",
            document_url="https://ticaret.gov.tr/data/italya-sehirler.pdf",
            **common,
        )
        report = contact.model_copy(
            update={
                "id": "ticaret_" + "c" * 24,
                "title": "İtalya Mobilya Sektörü Pazar Araştırması Raporu (2026)",
                "document_url": "https://ticaret.gov.tr/data/italya-mobilya-raporu.pdf",
            }
        )
        self.assertFalse(self.client._is_report_document(contact))
        self.assertTrue(self.client._is_report_document(report))
        self.assertGreater(
            self.client._browse_priority(report, {"rapor"}),
            self.client._browse_priority(contact, {"rapor"}),
        )
        support_form = report.model_copy(
            update={
                "id": "ticaret_" + "1" * 24,
                "source_id": "destekler",
                "content_kind": "destek",
                "title": "Program Sonuç Raporu Başvuru Eki",
            }
        )
        self.assertFalse(self.client._is_report_document(support_form))

    def test_country_view_keeps_country_records_but_rejects_regions_and_report_tabs(self) -> None:
        common = {
            "source_id": "yurtdisi_teskilati",
            "content_kind": "ulke_bilgisi",
            "section": "Avrupa",
            "file_type": "html",
            "is_page": True,
        }
        country = TicaretDocument(
            id="ticaret_" + "d" * 24,
            title="Almanya",
            document_url="https://ticaret.gov.tr/yurtdisi-teskilati/avrupa/almanya",
            source_page_url="https://ticaret.gov.tr/yurtdisi-teskilati/avrupa",
            **common,
        )
        region = country.model_copy(
            update={
                "id": "ticaret_" + "e" * 24,
                "title": "Avrupa",
                "document_url": "https://ticaret.gov.tr/yurtdisi-teskilati/avrupa",
            }
        )
        report_tab = country.model_copy(
            update={
                "id": "ticaret_" + "f" * 24,
                "title": "Raporlar",
                "document_url": "https://ticaret.gov.tr/yurtdisi-teskilati/avrupa/almanya/raporlar",
            }
        )
        self.assertTrue(self.client._is_country_information_document(country))
        self.assertFalse(self.client._is_country_information_document(region))
        self.assertFalse(self.client._is_country_information_document(report_tab))
        self.assertTrue(self.client._is_report_document(report_tab))


if __name__ == "__main__":
    unittest.main()

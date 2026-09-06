"""Resmî önlem listeleri: ayrıştırma, eşleme, depo ve değişiklik defteri."""

from __future__ import annotations

import io
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

import openpyxl

import trade_measures as tm

SURVEILLANCE_HTML = """
<html><body><p>İTHALATTA GÖZETİM UYGULANMASINA İLİŞKİN TEBLİĞ (TEBLİĞ NO: 2026/37)</p>
<table>
<tr><td>GTİP</td><td>Eşyanın Tanımı</td><td>Birim Gümrük Kıymeti (ABD Doları/Kg*)</td></tr>
<tr><td>8424.90.80.00.12</td><td>Yangın söndürme tüpü tetikleri</td><td>12</td></tr>
<tr><td>8481.10.05.00.00</td><td>Filtre veya yağlayıcılarla kombine halde olanlar</td><td>30</td></tr>
<tr><td>8481.80.59.00.19</td><td>Diğerleri</td><td>2,5</td></tr>
</table>
<p>* Kg: Brüt ağırlık</p></body></html>
"""


def _antidumping_workbook() -> bytes:
    book = openpyxl.Workbook()
    sheet = book.active
    sheet.title = "Kesin Önl- Definitive Measures"
    sheet.append(["T.C. TİCARET BAKANLIĞI"])
    header = ["DOSYA NO", "SEKTÖR", "MADDE İSMİ", "MADDE İSMİ", "G.T.İ.P. ", "ÜLKE", "ÜLKE", "ÖNLEM TEBLİĞ NO", "ÖNLEM RG TARİHİ",
              "ÖNLEM RG NO", "BİLGİLENDİRME RAPORU", "ÖNLEM ORANI (CIF%) / MİKTARI", " ÖNLEM TÜRÜ", "NORMAL SÜRE DOLUM TARİHİ"]
    sheet.append(header)
    sheet.append(["CASE NUMBER", "INDUSTRY"])
    sheet.append(["DMS.221.00.2012", "MM", "Paslanmaz Çelik Borular", "Welded", "7306.40.20.90.00 7306.40.80.90.00", "Çin Halk Cumhuriyeti",
                  "China, P.R", "2026/5", "2026-03-15", "33200", None, "%13,82 - %25,27", "DK", "2031-03-15"])
    sheet.append(["NGS.186.01.2011", "MM", "Granitler", "Granites", "6802.23 6802.93", "Çin Halk Cumhuriyeti", "China", "2012/14",
                  "2012-07-10", "28349", None, "174 $/Ton", "DK", "2017-07-10"])
    prov = book.create_sheet("Geçici Önl.-Prov. Measures")
    prov.append(["DOSYA NO", "SEKTÖR", "MADDE İSMİ", "MADDE İSMİ", "G.T.İ.P. ", "ÜLKE", "ÜLKE", "GEÇİCİ ÖNLEM TEBLİĞ NO", "RG TARİHİ", "RG NO", "ORAN", "TÜR", "AÇILIŞ"])
    prov.append(["CASE NUMBER"])
    buffer = io.BytesIO()
    book.save(buffer)
    return buffer.getvalue()


def _safeguard_workbook() -> bytes:
    book = openpyxl.Workbook()
    sheet = book.active
    sheet.append([None, "SIRA", "DOSYA /CASE NO", "MADDE İSMİ", "GTİP", "ÜLKE", "TÜRÜ", "KARAR-TEBLİĞ NO", "R.G. NO", "R.G. TRH", "YAYIM", "SIMGE", "UZATMA", "İLK ÖNLEM", "BİTİŞ", "ÖNLEM MİKTARI"])
    sheet.append([None, "1", "242", "POLYESTER ELYAF (İRAN MENŞELİ)", "5503.20.00.00.00", "İran / Iran", "Soruşturma Açılış", "2023/1", "32162", "2023-04-13", None, None, "III. UZATMA (2023-2026)", "2013-09-21", "2026-09-20", "% 17 (21.9.2023-20.9.2024)"])
    sheet.append([None, None, None, None, None, None, "Önlem Karar", "2023/7615", "32310", "2023-09-15", None, None, None, None, None, "% 16 (21.9.2025-20.9.2026)"])
    sheet.append([None, "2", "248", "DİŞ FIRÇALARI", "9603.21.00.00.19", "Tüm Ülkeler/All Countries", "Önlem Karar", "2024/8147", "32449", "03.02.2024", None, None, "II. UZATMA", "2018-02-03", "2027-02-02", "0,09 ABD Doları/Adet"])
    sheet.append([None, None, None, None, None, None, "Kontenjan Dağıtım Genel ve GYÜ/ Tariff Quate", "2024/5", "32460", "14.02.2024", None, None, None, None, None, "GYU Kont. 6.289.963 Adet"])
    buffer = io.BytesIO()
    book.save(buffer)
    return buffer.getvalue()


class ParserTests(unittest.TestCase):
    def test_extract_codes_handles_dotted_and_bare_forms(self):
        self.assertEqual(tm.extract_codes("7306.40.20.90.00 7306.40.80.90.00"), ["730640209000", "730640809000"])
        self.assertEqual(tm.extract_codes("55.13 55.14"), ["5513", "5514"])
        self.assertEqual(tm.extract_codes("7004,7005,7006"), ["7004", "7005", "7006"])
        self.assertEqual(tm.extract_codes("5407. ..."), ["5407"])

    def test_antidumping_workbook(self):
        parsed = tm.parse_antidumping_workbook(_antidumping_workbook())
        self.assertEqual(len(parsed["definitive"]), 2)
        self.assertEqual(parsed["definitive"][0]["rate"], "%13,82 - %25,27")
        self.assertEqual(parsed["definitive"][0]["expires"], "2031-03-15")
        self.assertEqual(parsed["provisional"], [])

    def test_safeguard_workbook(self):
        parsed = tm.parse_safeguard_workbook(_safeguard_workbook())
        self.assertEqual([row["file_no"] for row in parsed], ["242", "248"])
        self.assertEqual(len(parsed[0]["acts"]), 2)
        self.assertEqual(parsed[0]["amounts"][-1], "% 16 (21.9.2025-20.9.2026)")
        self.assertIn("Kontenjan", parsed[1]["acts"][-1]["kind"])

    def test_surveillance_page(self):
        doc = tm.parse_surveillance_page(SURVEILLANCE_HTML, {"mevzuat_no": "46246", "rg_date": "09/04/2026", "rg_no": "33219"})
        self.assertEqual(doc["item_count"], 3)
        self.assertEqual(doc["unit"], "ABD Doları/Kg")
        self.assertEqual(doc["items"][2]["value"], "2,5")
        self.assertIn("2026/37", doc["title"])

    def test_workbook_link_discovery_and_communique_index(self):
        html = '<a href="/data/abc/Y&#252;r&#252;rl&#252;kteki &#214;nlemler 13.07.2026.xlsx">Yürürlükteki Önlemler</a><a href="/x.pdf">Diğer</a>'
        link = tm.discover_workbook_link(html, "https://ticaret.gov.tr/ithalat/damping", must_contain=("rürlükteki",))
        self.assertEqual(link, "https://ticaret.gov.tr/data/abc/Yürürlükteki%20Önlemler%2013.07.2026.xlsx")
        index = tm.parse_communique_index(
            '<a href="https://www.resmigazete.gov.tr/eskiler/2025/12/20251231M3-23.pdf">Askıya Alma Sistemine İlişkin Tebliğ (İthalat: 2026/18)</a>'
            '<a href="/ithalat/mevzuat">İthalat Mevzuatı</a>',
            "https://ticaret.gov.tr/ithalat", 2026,
        )
        self.assertEqual(index[0]["number"], "2026/18")
        self.assertEqual(index[0]["gazette"], "20251231")
        self.assertEqual(len(index), 1)

    def test_four_digit_positions_and_text_only_tables(self):
        table = '<table><tr><td>G.T.P.</td><td>Eşyanın Tanımı</td><td>Birim CIF Kıymet (ABD Doları/m2)</td></tr><tr><td>68.09</td><td>Alçı levhalar</td><td>5</td></tr></table>'
        doc = tm.parse_surveillance_page(table, {})
        self.assertEqual(doc["items"][0]["gtip"], "68.09")
        self.assertEqual(doc["unit"], "ABD Doları/m2")
        text = (
            "<p>MADDE 1- (1) Bu Tebliğ ... G.T.İ.P. Eşyanın Tanımı Birim Gümrük Kıymeti (ABD Doları/Kg*) "
            "8481.10.05.00.00 Filtre veya yağlayıcılarla kombine halde olanlar 30 8481.80.99.00.11 Yangın hidrantları 5 "
            "* Kg: brüt ağırlık Gözetim uygulaması MADDE 2- (1) ...</p>"
        )
        doc = tm.parse_surveillance_page(text, {})
        self.assertEqual([item["gtip"] for item in doc["items"]], ["8481.10.05.00.00", "8481.80.99.00.11"])
        self.assertEqual(doc["items"][1]["value"], "5")
        self.assertEqual(doc["parser_version"], tm.PARSER_VERSION)


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        seed = Path(self.tmp) / "seed"
        seed.mkdir()
        (seed / "antidumping_measures.json").write_text(json.dumps(tm.parse_antidumping_workbook(_antidumping_workbook())), encoding="utf-8")
        (seed / "safeguard_measures.json").write_text(json.dumps(tm.parse_safeguard_workbook(_safeguard_workbook())), encoding="utf-8")
        (seed / "surveillance_measures.json").write_text(
            json.dumps([tm.parse_surveillance_page(SURVEILLANCE_HTML, {"mevzuat_no": "46246", "rg_date": "09/04/2026", "rg_no": "33219", "title": "Gözetim 2026/37"})]),
            encoding="utf-8",
        )
        self.engine = tm.TradeMeasureEngine(self.tmp)
        self.engine.store = tm.TradeMeasureStore(self.tmp, seed_dir=seed)

    def test_lookup_matches_prefix_and_origin(self):
        report = self.engine.lookup("730640209000", "Çin", today=date(2026, 9, 6))
        self.assertEqual(len(report.anti_dumping), 1)
        hit = report.anti_dumping[0]
        self.assertTrue(hit.origin_match)
        self.assertEqual(hit.status, "in_force")
        self.assertEqual(hit.matched_code, "730640209000")
        other = self.engine.lookup("730640209000", "Almanya", today=date(2026, 9, 6))
        self.assertFalse(other.anti_dumping[0].origin_match)
        self.assertEqual(other.applicable_anti_dumping, [])

    def test_expired_measure_flagged(self):
        report = self.engine.lookup("680223000000", "Çin", today=date(2026, 9, 6))
        self.assertEqual(report.anti_dumping[0].status, "expired")

    def test_safeguard_and_surveillance(self):
        report = self.engine.lookup("960321000019", "Vietnam", today=date(2026, 9, 6))
        self.assertEqual(len(report.safeguard), 1)
        self.assertTrue(report.safeguard[0].origin_match)
        self.assertIn("kontenjan", report.safeguard[0].notes.lower())
        surveillance = self.engine.lookup("848180590019", None)
        self.assertEqual(surveillance.surveillance_unit_value, 2.5)
        self.assertEqual(surveillance.surveillance[0].unit, "ABD Doları/Kg")
        lines = tm.summary_lines(surveillance)
        self.assertTrue(lines and lines[0].startswith("Gözetim"))

    def test_short_code_matches_longer_official_rows(self):
        report = self.engine.lookup("848180", None)
        self.assertEqual(len(report.surveillance), 1)
        self.assertTrue(report.warnings)

    def test_store_save_records_changes(self):
        store = self.engine.store
        previous = store.load("safeguard")
        updated = json.loads(json.dumps(previous))
        updated[0]["expires"] = "2029-09-20"
        updated.append({"seq": 3, "file_no": "260", "product": "ETİL ASETAT", "gtip": "2915.31.00.00.00", "country": "Tüm Ülkeler", "stage": "İLK", "original_start": "", "expires": "2028-06-22", "amounts": ["% 10"], "acts": []})
        diff = store.save("safeguard", updated, source_url="https://example.test/k.xlsx", source_label="test")
        self.assertEqual((diff["added_count"], diff["removed_count"], diff["modified_count"]), (1, 0, 1))
        self.assertEqual(store.metadata("safeguard")["origin"], "synced")
        changes = store.changes("safeguard")
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0]["detail"]["added"][0]["codes"], ["291531000000"])
        # Yeni depo örneği aynı veriyi sqlite'tan okur.
        reopened = tm.TradeMeasureStore(self.tmp, seed_dir=Path(self.tmp) / "seed")
        self.assertEqual(len(reopened.load("safeguard")), 3)

    def test_status_reports_seed_origin(self):
        status = self.engine.status()
        self.assertEqual(status["datasets"]["anti_dumping"]["origin"], "seed")
        self.assertEqual(status["datasets"]["communiques"]["origin"], "missing")


class OfficialSeedTests(unittest.TestCase):
    """Depodaki resmî tohum dosyaları ve gerçek fihrist sayfası ayrıştırması."""

    def test_real_iframe_page_parses(self):
        html_text = (Path(__file__).parent / "fixtures" / "surveillance_iframe_sample.htm").read_text(encoding="utf-8", errors="ignore")
        doc = tm.parse_surveillance_page(html_text, {"mevzuat_no": "46246", "rg_date": "09/04/2026", "rg_no": "33219"})
        self.assertGreaterEqual(doc["item_count"], 1)
        self.assertTrue(all(tm.normalise_code(item["gtip"]) for item in doc["items"]))

    def test_seed_files_load_with_default_store(self):
        engine = tm.TradeMeasureEngine(tempfile.mkdtemp())
        status = engine.status()["datasets"]
        self.assertGreater(status["anti_dumping"]["item_count"], 200)
        self.assertGreater(status["safeguard"]["item_count"], 5)
        self.assertGreater(status["surveillance"]["item_count"], 500)
        self.assertGreater(status["communiques"]["item_count"], 10)
        report = engine.lookup("730640209000", "Çin", today=date(2026, 9, 6))
        self.assertTrue(report.applicable_anti_dumping)


if __name__ == "__main__":
    unittest.main()

import asyncio
import io
import tempfile
import unittest
import zipfile

import openpyxl

from control_engine import (
    ImportControlEngine,
    extract_annex_scope,
    extract_attachment_scope,
    extract_required_documents,
    extract_scope_table,
    infer_process,
)

SAMPLE = """
Amaç MADDE 1- Ek-1'de yer alan ürünler risk analizine göre denetlenir.
Risk analizi: Ürünlerin fiili denetime yönlendirilip yönlendirilmeyeceğini belirler.
TAREKS üzerinden işlemler yapılır. TSE denetim birimidir. Fiili denetim belge,
işaret, fiziki muayene veya laboratuvar testinden biri veya birkaçını kapsar.
Ek-1
İTHALATTA DENETİME TABİ ÜRÜNLERİN LİSTESİ
SIRA NO GTİP MADDE ADI
1.
3005.90.50.00.19
Diğer tıbbi tekstiller
2.
3926.90.97.10.00
Korseler için balenler
Ek-2
YÜKLENMESİ GEREKEN BELGELER
1. Fatura veya proforma fatura
2. Taşıma belgesi
Ek-3
Taahhütname
"""


class ControlParsingTests(unittest.TestCase):
    def test_extracts_only_annex_scope(self):
        rows = extract_annex_scope(SAMPLE)
        self.assertEqual([row.gtip_prefix for row in rows], ["300590500019", "392690971000"])
        self.assertIn("tıbbi tekstiller", rows[0].description)

    def test_extracts_document_excerpt(self):
        excerpt = extract_required_documents(SAMPLE)
        self.assertIn("Fatura", excerpt)
        self.assertNotIn("Taahhütname", excerpt)

    def test_extracts_configured_annex_with_wrapped_heading(self):
        text = """
Ek-1
TEKNİK DÜZENLEMELER
Ek-\n2
DENETİME TABİ ÜRÜNLER LİSTESİ
GTİP Eşyanın Tanımı
8429.11.00.00.00 Paletli buldozerler
8429.40.90.00.00 Diğer yol silindirleri
Ek-3
BELGELER
"""
        rows = extract_annex_scope(text, annex_number=2)
        self.assertEqual([row.gtip_prefix for row in rows], ["842911000000", "842940900000"])

    def test_extracts_inline_gtp_table(self):
        text = """
GTP
Eşyanın Tanımı
8701.21 Dizel çekiciler
87.02 On veya daha fazla kişi taşımaya mahsus taşıtlar
87.03 Binek otomobilleri (8703.10.11.00.00 GTİP'li acil müdahale araçları hariç)
Yürürlükten kaldırılan tebliğ
2024/41 yürürlükten kaldırılmıştır.
"""
        rows = extract_scope_table(text, r"^\s*GTP\s*$", r"^\s*Yürürlükten kaldırılan tebliğ")
        self.assertEqual([row.gtip_prefix for row in rows], ["870121", "8702", "8703", "870310110000"])
        self.assertFalse(rows[2].excluded)
        self.assertTrue(rows[3].excluded)

    def test_explicit_haric_row_suppresses_parent_scope(self):
        with tempfile.TemporaryDirectory() as directory:
            engine = ImportControlEngine(data_dir=directory)
            engine.rules_config = [item for item in engine.rules_config if item["code"] == "2026/31"]
            with engine._connect() as db:
                db.execute(
                    """INSERT INTO control_snapshots VALUES
                    (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        "vehicles", "2026/31", "Taşıt Tebliği", "taşıt", "31", "https://mevzuat.adalet.gov.tr/",
                        "2025-12-31", "33124", "abc", "2026-01-01T00:00:00+03:00", "2026-01-01", 1,
                        "Sanayi ve Teknoloji Bakanlığı", "Yetkili kurum", 0, 1, 0, None, 1,
                    ),
                )
                db.executemany(
                    "INSERT INTO control_scope VALUES (?,?,?,?,?,?)",
                    [
                        ("vehicles", "8703", "Binek otomobilleri", "87.03 Binek otomobilleri", 1, 0),
                        ("vehicles", "870310110000", "Acil müdahale araçları hariç", "8703.10.11.00.00 hariç", 20, 1),
                    ],
                )
            result = asyncio.run(engine.lookup("870310110000"))
            asyncio.run(engine.close())
            self.assertEqual(result.status, "not_found")
            self.assertIn("hariç", result.warnings[0])

    def test_extracts_gtip_rows_from_official_xlsx_archive(self):
        workbook = openpyxl.Workbook()
        sheet = workbook.active
        sheet.append(["GTİP", "Ürün"])
        sheet.append(["0805.10.20.00.00", "Portakal"])
        xlsx = io.BytesIO()
        workbook.save(xlsx)
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, "w") as output:
            output.writestr("Ek-1.xlsx", xlsx.getvalue())
        rows = extract_attachment_scope(archive.getvalue())
        self.assertEqual([row.gtip_prefix for row in rows], ["080510200000"])
        self.assertIn("Portakal", rows[0].description)

    def test_attachment_filter_excludes_forms_and_standard_years(self):
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, "w") as output:
            output.writestr("2026-21 Ek 1 A.txt", "GTİP\n1507.90.90.00.00 Soya yağı TS 890 Nisan 2016")
            output.writestr("2026 21 Ek 4.txt", "2026/21 formu 0407.21.00.00.00")
        rows = extract_attachment_scope(
            archive.getvalue(),
            member_suffixes=["Ek 1 A.txt"],
        )
        self.assertEqual([row.gtip_prefix for row in rows], ["150790900000"])

    def test_prefers_exact_official_document_attachment(self):
        raw = '<a href="9.5.42906-Ek.zip">Ek</a>'
        exact = "https://www.mevzuat.gov.tr/MevzuatMetin/yonetmelik/9.5.42906-Ek.zip"
        self.assertEqual(ImportControlEngine._official_attachment_url(raw, [exact]), exact)

    def test_process_keeps_risk_separate(self):
        process = infer_process(SAMPLE, "İthalatta Standartlara Uygunluk Denetimi Tebliği")
        self.assertEqual(process["system"], "TAREKS")
        self.assertTrue(process["risk_based"])
        self.assertTrue(process["laboratory_test_possible"])
        self.assertIn("Türk Standardları", process["authority"])

    def test_not_found_is_not_not_applicable(self):
        with tempfile.TemporaryDirectory() as directory:
            engine = ImportControlEngine(data_dir=directory)
            engine.rules_config = [item for item in engine.rules_config if item["code"] == "2026/18"]
            with engine._connect() as db:
                db.execute(
                    """INSERT INTO control_snapshots VALUES
                    (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        "snap", "2026/18", "Tekstil Tebliği", "tekstil", "1", "https://mevzuat.adalet.gov.tr/",
                        "2025-12-31", "33124", "abc", "2026-01-01T00:00:00+03:00", "2026-01-01", 1,
                        "Ticaret Bakanlığı", "TAREKS", 1, 1, 1, "Fatura", 1,
                    ),
                )
                db.execute(
                    "INSERT INTO control_scope VALUES (?,?,?,?,?,?)",
                    ("snap", "6104", "Kadın giyim", "6104 Kadın giyim", 10, 0),
                )
            result = asyncio.run(engine.lookup("850760000000"))
            asyncio.run(engine.close())
            self.assertEqual(result.status, "not_found")
            self.assertIn("anlamına gelmez", result.warnings[0])


if __name__ == "__main__":
    unittest.main()

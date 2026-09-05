import asyncio
import io
import tempfile
import unittest
import zipfile

import openpyxl

from control_engine import (
    ImportControlEngine,
    annex_plan,
    communique_code_matches,
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

    def test_multi_part_annex_tables_are_merged(self):
        text = """
Amaç MADDE 1- Ek-1'de yer alan ürünler denetlenir.
Ek-1 sayılı listede 3005.90.50.00.19 sayılı ürün geçer diyen bir gövde cümlesi.
Ek-1/A
CANLI HAYVANLAR
0101.21.00.00.00 Saf kan damızlık atlar
Ek-1/B
ETLER
0201.10.00.00.00 Karkas
EK-2 İTHALİ YASAK ATIKLAR
2710.99.00.00.00 Atık yağlar
Ek-
3
Taahhütname 2026
"""
        self.assertEqual([row.gtip_prefix for row in extract_annex_scope(text, 1)], ["010121000000", "020110000000"])
        self.assertEqual([row.gtip_prefix for row in extract_annex_scope(text, 2)], ["271099000000"])
        self.assertEqual(extract_annex_scope(text, 3), [])

    def test_communique_code_matches_only_the_full_number(self):
        self.assertTrue(communique_code_matches("2026/1", "İthalatta Standartlara Uygunluk Denetimi Tebliği (Ürün Güvenliği ve Denetimi: 2026/1)"))
        self.assertTrue(communique_code_matches("2026/32", "Makinaların İthalat Denetimi Tebliği (Ürün Güvenliği ve Denetimi : 2026 / 32)"))
        self.assertFalse(communique_code_matches("2026/1", "Tüketici Ürünlerinin İthalat Denetimi Tebliği (Ürün Güvenliği ve Denetimi: 2026/12)"))
        self.assertFalse(communique_code_matches("2026/2", "Sağlık Bakanlığınca Denetlenen Bazı Ürünlerin İthalat Denetimi Tebliği (ÜGD: 2026/20)"))
        self.assertFalse(communique_code_matches("2026/3", "Makinaların İthalat Denetimi Tebliği (ÜGD: 2026/32)"))

    def test_annex_plan_supports_legacy_and_multi_annex_configuration(self):
        self.assertEqual(annex_plan({}), [{"annex": 1, "kind": "scope"}])
        self.assertEqual(annex_plan({"scope_annex": 2}), [{"annex": 2, "kind": "scope"}])
        self.assertEqual(
            annex_plan({"scope_annexes": [1, {"annex": 2, "kind": "prohibited"}, {"annex": 3, "kind": "bogus"}]}),
            [{"annex": 1, "kind": "scope"}, {"annex": 2, "kind": "prohibited"}, {"annex": 3, "kind": "scope"}],
        )

    def test_prohibited_list_rows_are_reported_separately(self):
        with tempfile.TemporaryDirectory() as directory:
            engine = ImportControlEngine(data_dir=directory)
            engine.rules_config = [item for item in engine.rules_config if item["code"] == "2026/3"]
            with engine._connect() as db:
                db.execute(
                    """INSERT INTO control_snapshots VALUES
                    (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        "waste", "2026/3", "Atık Tebliği", "atıklar", "3", "https://mevzuat.adalet.gov.tr/",
                        "2025-12-31", "33124", "abc", "2026-01-01T00:00:00+03:00", "2026-01-01", 2,
                        "Çevre, Şehircilik ve İklim Değişikliği Bakanlığı", "Bakanlık", 0, 1, 0, None, 1,
                    ),
                )
                db.executemany(
                    "INSERT INTO control_scope (snapshot_id, gtip_prefix, description, source_line, source_offset, excluded, list_kind) VALUES (?,?,?,?,?,?,?)",
                    [
                        ("waste", "3915", "Plastik döküntü", "39.15 Plastik döküntü", 1, 0, "scope"),
                        ("waste", "271099", "Atık yağ", "2710.99 Atık yağ", 2, 0, "prohibited"),
                    ],
                )
            controlled = asyncio.run(engine.lookup("391510000000"))
            banned = asyncio.run(engine.lookup("271099000000"))
            asyncio.run(engine.close())
            self.assertEqual(controlled.matches[0].matched_scope.list_kind, "scope")
            self.assertEqual(banned.matches[0].matched_scope.list_kind, "prohibited")
            self.assertIn("ithali yasak", banned.matches[0].assessment)

    def test_legacy_scope_table_is_migrated_with_list_kind(self):
        with tempfile.TemporaryDirectory() as directory:
            path = f"{directory}/controls.sqlite3"
            import sqlite3
            with sqlite3.connect(path) as db:
                db.executescript(
                    """
                    CREATE TABLE control_snapshots (id TEXT PRIMARY KEY, code TEXT NOT NULL, title TEXT NOT NULL,
                        category TEXT NOT NULL, mevzuat_id TEXT NOT NULL, source_url TEXT NOT NULL,
                        official_gazette_date TEXT, official_gazette_number TEXT, document_sha256 TEXT NOT NULL,
                        retrieved_at TEXT NOT NULL, valid_from TEXT NOT NULL, scope_count INTEGER NOT NULL,
                        authority TEXT NOT NULL, system TEXT NOT NULL, risk_based INTEGER NOT NULL,
                        physical_inspection_possible INTEGER NOT NULL, laboratory_test_possible INTEGER NOT NULL,
                        required_documents_excerpt TEXT, active INTEGER NOT NULL DEFAULT 0);
                    CREATE TABLE control_scope (snapshot_id TEXT NOT NULL REFERENCES control_snapshots(id) ON DELETE CASCADE,
                        gtip_prefix TEXT NOT NULL, description TEXT, source_line TEXT NOT NULL,
                        source_offset INTEGER NOT NULL, excluded INTEGER NOT NULL DEFAULT 0,
                        PRIMARY KEY (snapshot_id, gtip_prefix));
                    INSERT INTO control_snapshots VALUES ('old','2026/18','T','t','1','u',NULL,NULL,'d','r','2026-01-01',1,'a','s',1,1,1,NULL,1);
                    INSERT INTO control_scope VALUES ('old','6104','Kadın giyim','6104',1,0);
                    """
                )
            engine = ImportControlEngine(data_dir=directory)
            with engine._connect() as db:
                rows = db.execute("SELECT gtip_prefix, list_kind FROM control_scope").fetchall()
            asyncio.run(engine.close())
            self.assertEqual([tuple(row) for row in rows], [("6104", "scope")])

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
                    "INSERT INTO control_scope (snapshot_id, gtip_prefix, description, source_line, source_offset, excluded) VALUES (?,?,?,?,?,?)",
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
                    "INSERT INTO control_scope (snapshot_id, gtip_prefix, description, source_line, source_offset, excluded) VALUES (?,?,?,?,?,?)",
                    ("snap", "6104", "Kadın giyim", "6104 Kadın giyim", 10, 0),
                )
            result = asyncio.run(engine.lookup("850760000000"))
            asyncio.run(engine.close())
            self.assertEqual(result.status, "not_found")
            self.assertIn("anlamına gelmez", result.warnings[0])


if __name__ == "__main__":
    unittest.main()

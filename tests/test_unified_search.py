import sqlite3
import unittest

from unified_search import UnifiedSearchEngine, format_gtip, normalise_search_text, CHAPTER_NAMES


class UnifiedSearchEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = UnifiedSearchEngine()

    def _skip_unless_live_data_synced(self) -> None:
        """tariff.sqlite3/controls.sqlite3 dosyaları uygulama başlarken şema
        için hemen oluşturulur, ama satırlar yalnız canlı arka plan
        senkronizasyonu tamamlandıktan sonra dolar; bu yüzden dosya varlığı
        değil, gerçek satır sayısı kontrol edilir. Taze bir ortamda (CI, ilk
        kurulum) bu tablolar boştur ve otomatik tamamlama gerçek veri döndüremez."""
        tariff_rows = control_rows = 0
        tariff_conn = self.engine._connect_tariff()
        if tariff_conn:
            try:
                tariff_rows = tariff_conn.execute("SELECT COUNT(*) FROM tariff_measures").fetchone()[0]
            except sqlite3.OperationalError:
                tariff_rows = 0
            finally:
                tariff_conn.close()
        controls_conn = self.engine._connect_controls()
        if controls_conn:
            try:
                control_rows = controls_conn.execute("SELECT COUNT(*) FROM control_scope").fetchone()[0]
            except sqlite3.OperationalError:
                control_rows = 0
            finally:
                controls_conn.close()
        if not tariff_rows or not control_rows:
            self.skipTest("Tarife/kontrol önbellekleri henüz senkronize değil (canlı veri gerektirir)")

    def test_format_gtip(self) -> None:
        self.assertEqual(format_gtip("851713000011"), "8517.13.00.00.11")
        self.assertEqual(format_gtip("85171300"), "8517.13.00")
        self.assertEqual(format_gtip("851713"), "8517.13")
        self.assertEqual(format_gtip("8517"), "8517")

    def test_normalise_search_text(self) -> None:
        self.assertEqual(normalise_search_text("AKILLI TELEFON"), "akilli telefon")
        self.assertEqual(normalise_search_text("Çikolata ve Şeker"), "cikolata ve seker")

    def test_autocomplete_keyword(self) -> None:
        self._skip_unless_live_data_synced()
        items = self.engine.autocomplete("akıllı telefon", limit=5)
        self.assertTrue(len(items) >= 1)
        card = items[0]
        self.assertTrue(card["gtip"].startswith("8517"))
        self.assertTrue(card["has_excise"])
        self.assertEqual(card["vat_rate"], 20.0)
        self.assertTrue(card["has_controls"])

    def test_autocomplete_machine(self) -> None:
        self._skip_unless_live_data_synced()
        items = self.engine.autocomplete("torna", limit=5)
        self.assertTrue(len(items) >= 1)
        card = items[0]
        self.assertTrue(card["gtip"].startswith("8458"))
        self.assertEqual(card["vat_rate"], 20.0)
        self.assertTrue(card["has_controls"])

    def test_autocomplete_digits(self) -> None:
        self._skip_unless_live_data_synced()
        items = self.engine.autocomplete("8517", limit=5)
        self.assertTrue(len(items) >= 1)
        self.assertTrue(all(item["gtip"].startswith("8517") for item in items))

    def test_search_all_categories(self) -> None:
        res = self.engine.search_all("oyuncak", limit=10)
        self.assertIn("tarife", res["categories"])
        self.assertIn("denetim", res["categories"])
        self.assertTrue(res["total_count"] > 0)

    def test_chapter_names_coverage(self) -> None:
        self.assertIn("84", CHAPTER_NAMES)
        self.assertIn("85", CHAPTER_NAMES)
        self.assertIn("61", CHAPTER_NAMES)
        self.assertIn("18", CHAPTER_NAMES)
        self.assertEqual(CHAPTER_NAMES["61"], "Örme giyim eşyası ve aksesuarı (tişört, kazak, hırka, çorap vb.)")


if __name__ == "__main__":
    unittest.main()

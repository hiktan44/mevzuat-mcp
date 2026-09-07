import unittest
from unified_search import UnifiedSearchEngine, format_gtip, normalise_search_text, CHAPTER_NAMES


class UnifiedSearchEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = UnifiedSearchEngine()

    def test_format_gtip(self) -> None:
        self.assertEqual(format_gtip("851713000011"), "8517.13.00.00.11")
        self.assertEqual(format_gtip("85171300"), "8517.13.00")
        self.assertEqual(format_gtip("851713"), "8517.13")
        self.assertEqual(format_gtip("8517"), "8517")

    def test_normalise_search_text(self) -> None:
        self.assertEqual(normalise_search_text("AKILLI TELEFON"), "akilli telefon")
        self.assertEqual(normalise_search_text("Çikolata ve Şeker"), "cikolata ve seker")

    def test_autocomplete_keyword(self) -> None:
        items = self.engine.autocomplete("akıllı telefon", limit=5)
        self.assertTrue(len(items) >= 1)
        card = items[0]
        self.assertTrue(card["gtip"].startswith("8517"))
        self.assertTrue(card["has_excise"])
        self.assertEqual(card["vat_rate"], 20.0)
        self.assertTrue(card["has_controls"])

    def test_autocomplete_machine(self) -> None:
        items = self.engine.autocomplete("torna", limit=5)
        self.assertTrue(len(items) >= 1)
        card = items[0]
        self.assertTrue(card["gtip"].startswith("8458"))
        self.assertEqual(card["vat_rate"], 20.0)
        self.assertTrue(card["has_controls"])

    def test_autocomplete_digits(self) -> None:
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

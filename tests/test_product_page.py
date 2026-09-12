import json
import unittest

from product_page import BROWSER_HEADERS, detect_bot_wall, extract_product_page

_NAV = "<nav>" + " ".join(f"Kategori {i}" for i in range(400)) + "</nav>"


class ProductPageExtractionTests(unittest.TestCase):
    def test_trendyol_initial_state_is_preferred_over_navigation_text(self) -> None:
        state = {
            "product": {
                "id": 123,
                "name": "Erkek Pamuklu Basic Tişört",
                "brand": {"name": "Örnek Marka"},
                "category": {"name": "Tişört"},
                "description": "<p>%100 pamuk, bisiklet yaka.</p>",
                "attributes": [
                    {"key": {"name": "Materyal"}, "value": {"name": "Pamuk"}},
                    {"key": {"name": "Kalıp"}, "value": {"name": "Regular"}},
                ],
                "price": {"sellingPrice": {"value": 299.9}, "currency": "TL"},
            }
        }
        html = (
            "<html><head><title>Trendyol</title><script>window.__PRODUCT_DETAIL_APP_INITIAL_STATE__ = "
            + json.dumps(state, ensure_ascii=False)
            + ";</script></head><body>" + _NAV + "<h1>Başka Başlık</h1></body></html>"
        )
        result = extract_product_page(html, "https://www.trendyol.com/x/y-p-123", max_chars=800)
        self.assertEqual(result["extraction"], "structured")
        self.assertEqual(result["structured"]["source"], "trendyol-state")
        self.assertEqual(result["structured"]["name"], "Erkek Pamuklu Basic Tişört")
        self.assertEqual(result["structured"]["brand"], "Örnek Marka")
        self.assertEqual(result["structured"]["attributes"][0], {"name": "Materyal", "value": "Pamuk"})
        self.assertIn("Ürün adı: Erkek Pamuklu Basic Tişört", result["text"])
        self.assertIn("%100 pamuk", result["text"])
        self.assertIn("Materyal: Pamuk", result["text"])
        self.assertNotIn("Kategori 5", result["text"])
        self.assertEqual(result["title"], "Erkek Pamuklu Basic Tişört")

    def test_json_ld_product_with_graph_and_offers(self) -> None:
        ld = {
            "@context": "https://schema.org",
            "@graph": [
                {"@type": "BreadcrumbList"},
                {
                    "@type": "Product",
                    "name": "Kablosuz Kulaklık X1",
                    "brand": {"@type": "Brand", "name": "Sesli"},
                    "description": "Bluetooth 5.3, 30 saat pil.",
                    "material": "ABS plastik",
                    "offers": [{"@type": "Offer", "price": "1299.00", "priceCurrency": "TRY"}],
                    "additionalProperty": [{"@type": "PropertyValue", "name": "Renk", "value": "Siyah"}],
                },
            ],
        }
        html = (
            '<html><head><script type="application/ld+json">' + json.dumps(ld) + "</script></head><body>"
            + _NAV + "</body></html>"
        )
        result = extract_product_page(html, "https://shop.example/p/1")
        self.assertEqual(result["structured"]["source"], "json-ld")
        self.assertEqual(result["structured"]["price"], "1299.00")
        self.assertEqual(result["structured"]["currency"], "TRY")
        names = {item["name"] for item in result["structured"]["attributes"]}
        self.assertEqual(names, {"Renk", "material"})
        self.assertIn("gümrük kıymeti değildir", result["text"])

    def test_meta_fallback_and_navigation_removed(self) -> None:
        html = (
            '<html><head><title>Mağaza</title><meta property="og:title" content="Çelik Tencere 24 cm">'
            '<meta name="description" content="Paslanmaz çelik, indüksiyon uyumlu tencere."></head><body>'
            + _NAV + '<header>Menü</header><main><h1>Çelik Tencere 24 cm</h1><p>Kapaklı.</p></main><footer>İletişim</footer></body></html>'
        )
        result = extract_product_page(html, "https://shop.example/p/2")
        self.assertEqual(result["extraction"], "structured")
        self.assertEqual(result["structured"]["source"], "meta")
        self.assertIn("Ürün adı: Çelik Tencere 24 cm", result["text"])
        self.assertIn("Kapaklı.", result["text"])
        self.assertNotIn("Kategori 3", result["text"])
        self.assertNotIn("Menü", result["text"])

    def test_plain_page_falls_back_to_body_text(self) -> None:
        html = "<html><body><p>Sadece düz metin içeren bir sayfa.</p></body></html>"
        result = extract_product_page(html, "https://shop.example/p/3")
        self.assertEqual(result["extraction"], "text")
        self.assertIn("Sadece düz metin", result["text"])

    def test_broken_state_json_does_not_crash(self) -> None:
        html = "<script>window.__PRODUCT_DETAIL_APP_INITIAL_STATE__ = {\"product\": {oops</script><body><h1>Ürün</h1></body>"
        result = extract_product_page(html, "https://www.trendyol.com/p-1")
        self.assertEqual(result["structured"]["name"], "Ürün")

    def test_bot_wall_detection(self) -> None:
        self.assertIsNotNone(detect_bot_wall(403, ""))
        self.assertIsNotNone(detect_bot_wall(200, "<title>Just a moment...</title>"))
        self.assertIsNone(detect_bot_wall(200, "<html><body>Ürün</body></html>"))
        self.assertIn("HTTP 403", detect_bot_wall(403, "") or "")

    def test_browser_headers_look_like_a_browser(self) -> None:
        self.assertIn("Mozilla/5.0", BROWSER_HEADERS["User-Agent"])
        self.assertTrue(BROWSER_HEADERS["Accept-Language"].startswith("tr-TR"))


if __name__ == "__main__":
    unittest.main()

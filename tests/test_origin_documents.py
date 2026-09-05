from __future__ import annotations

import unittest

from countries import COUNTRIES, find_country
from origin_documents import customs_union_route, origin_document_requirements


class OriginDocumentRuleTests(unittest.TestCase):
    def test_eu_industrial_goods_get_atr_and_supplier_declaration(self) -> None:
        result = origin_document_requirements("Almanya", gtip="691110000011")
        self.assertEqual(result.regime, "customs_union")
        self.assertEqual(result.route, "atr")
        self.assertEqual([item.code for item in result.documents], ["ATR", "SUPPLIER_DECLARATION"])
        self.assertIn("Gümrük Birliği", result.regime_name)

    def test_eu_basic_agricultural_goods_need_eur1_not_atr(self) -> None:
        result = origin_document_requirements("Almanya", gtip="070200000011")
        self.assertEqual(result.route, "eur1_agricultural")
        self.assertEqual(result.documents[0].code, "EUR1")
        self.assertNotIn("ATR", [item.code for item in result.documents])
        self.assertTrue(any("A.TR geçerli değildir" in item for item in result.caveats))

    def test_eu_processed_agricultural_goods_keep_atr(self) -> None:
        self.assertEqual(customs_union_route("170490100000"), "atr")
        self.assertEqual(customs_union_route("1905"), "atr")
        self.assertEqual(customs_union_route("0201"), "eur1_agricultural")

    def test_ecsc_steel_needs_eur1(self) -> None:
        result = origin_document_requirements("Almanya", gtip="721610100000")
        self.assertEqual(result.route, "eur1_ecsc")
        self.assertEqual(result.documents[0].code, "EUR1")
        self.assertEqual(customs_union_route("7304"), "atr")  # seamless tubes are outside the ECSC list

    def test_without_gtip_the_eu_answer_is_atr_with_a_caveat(self) -> None:
        result = origin_document_requirements("Almanya")
        self.assertIsNone(result.route)
        self.assertEqual(result.documents[0].code, "ATR")
        self.assertTrue(any("sanayi ürünü varsayıldı" in item for item in result.caveats))

    def test_efta_member_gets_eur1_or_invoice_declaration(self) -> None:
        result = origin_document_requirements("İsviçre")
        self.assertEqual(result.regime, "efta")
        self.assertIn("EFTA", result.regime_name)
        self.assertEqual(result.documents[0].code, "EUR1")

    def test_agreements_without_eur1_use_origin_declarations(self) -> None:
        for country in ("Birleşik Krallık", "İngiltere", "Güney Kore", "Singapur"):
            result = origin_document_requirements(country)
            self.assertEqual(result.regime, "fta", country)
            self.assertEqual(result.documents[0].code, "ORIGIN_DECLARATION", country)
        for country in ("Malezya", "Birleşik Arap Emirlikleri", "Katar", "Venezuela"):
            self.assertEqual(origin_document_requirements(country).documents[0].code, "AGREEMENT_CERT", country)

    def test_classic_fta_members_use_eur1(self) -> None:
        for country in ("Fas", "Tunus", "İsrail", "Şili", "Mısır", "Morityus", "Sırbistan", "Gürcistan"):
            result = origin_document_requirements(country)
            self.assertEqual(result.regime, "fta", country)
            self.assertEqual(result.documents[0].code, "EUR1", country)

    def test_iran_is_a_preferential_trade_agreement(self) -> None:
        result = origin_document_requirements("İran")
        self.assertEqual(result.regime, "pta")
        self.assertEqual(result.documents[0].code, "AGREEMENT_CERT")

    def test_third_country_goods_dispatched_from_the_eu(self) -> None:
        result = origin_document_requirements("Çin", gtip="691110000011", dispatch_country="Almanya")
        self.assertEqual(result.regime, "mfn")
        self.assertEqual(result.documents[0].code, "ATR")
        self.assertTrue(any("İGV/EMY'yi kaldırmaz" in item for item in result.caveats))
        agricultural = origin_document_requirements("Çin", gtip="070200000011", dispatch_country="Almanya")
        self.assertNotIn("ATR", [item.code for item in agricultural.documents])

    def test_mfn_origin_has_no_preference_document(self) -> None:
        result = origin_document_requirements("Çin")
        self.assertEqual(result.regime, "mfn")
        codes = [item.code for item in result.documents]
        self.assertNotIn("ATR", codes)
        self.assertNotIn("EUR1", codes)
        self.assertIn("CERT_ORIGIN", codes)

    def test_pending_or_terminated_agreements_are_flagged(self) -> None:
        self.assertTrue(any("Ukrayna" in item for item in origin_document_requirements("Ukrayna").caveats))
        self.assertTrue(any("sona ermiştir" in item for item in origin_document_requirements("Ürdün").caveats))

    def test_unknown_origin_is_reported_instead_of_guessed(self) -> None:
        result = origin_document_requirements("Almanyaa")
        self.assertFalse(result.origin_recognised)
        self.assertEqual(result.regime, "mfn")
        self.assertIn("bulunamadı", result.caveats[0])

    def test_kktc_uses_special_regime(self) -> None:
        result = origin_document_requirements("KKTC")
        self.assertEqual(result.regime, "kktc")
        self.assertEqual(result.documents[0].code, "SPECIAL")

    def test_matching_is_case_language_and_diacritic_tolerant(self) -> None:
        self.assertEqual(origin_document_requirements("ALMANYA").regime, "customs_union")
        self.assertEqual(origin_document_requirements("Germany").regime, "customs_union")
        self.assertEqual(origin_document_requirements("çin").regime, "mfn")
        self.assertEqual(origin_document_requirements("guney kore").regime, "fta")
        self.assertEqual(find_country("Çin Halk Cumhuriyeti").key, "cin")

    def test_registry_is_internally_consistent(self) -> None:
        keys: dict[str, str] = {}
        for country in COUNTRIES:
            for alias in country.keys:
                self.assertNotIn(alias, keys, f"{alias} hem {keys.get(alias)} hem {country.key} için tanımlı")
                keys[alias] = country.key
            if country.regime in {"eu", "efta"}:
                self.assertTrue(country.column_1, country.key)
            if country.regime == "mfn":
                self.assertFalse(country.column_1, country.key)
                self.assertIsNone(country.label, country.key)

    def test_empty_origin_returns_none(self) -> None:
        self.assertIsNone(origin_document_requirements(""))
        self.assertIsNone(origin_document_requirements("   "))


if __name__ == "__main__":
    unittest.main()

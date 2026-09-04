from __future__ import annotations

import unittest

from origin_documents import origin_document_requirements


class OriginDocumentRuleTests(unittest.TestCase):
    def test_eu_member_gets_customs_union_and_atr(self) -> None:
        result = origin_document_requirements("Almanya")
        self.assertEqual(result.regime, "customs_union")
        self.assertEqual(result.documents[0].code, "ATR")
        self.assertIn("Gümrük Birliği", result.regime_name)

    def test_efta_member_gets_fta_with_eur1(self) -> None:
        result = origin_document_requirements("İsviçre")
        self.assertEqual(result.regime, "fta")
        self.assertIn("EFTA", result.regime_name)
        self.assertEqual(result.documents[0].code, "EUR1")

    def test_fta_members_cover_new_and_old_agreements(self) -> None:
        for country in ("Güney Kore", "Katar", "Birleşik Arap Emirlikleri", "Morityus", "İngiltere", "Mısır"):
            result = origin_document_requirements(country)
            self.assertEqual(result.regime, "fta", country)
            self.assertEqual(result.documents[0].code, "EUR1", country)

    def test_mfn_origin_has_no_preference_document(self) -> None:
        result = origin_document_requirements("Çin")
        self.assertEqual(result.regime, "mfn")
        codes = [item.code for item in result.documents]
        self.assertNotIn("ATR", codes)
        self.assertNotIn("EUR1", codes)
        self.assertIn("CERT_ORIGIN", codes)

    def test_kktc_uses_special_regime(self) -> None:
        result = origin_document_requirements("KKTC")
        self.assertEqual(result.regime, "kktc")
        self.assertEqual(result.documents[0].code, "SPECIAL")

    def test_matching_is_case_and_diacritic_tolerant(self) -> None:
        self.assertEqual(origin_document_requirements("ALMANYA").regime, "customs_union")
        self.assertEqual(origin_document_requirements("çin").regime, "mfn")
        self.assertEqual(origin_document_requirements("guney kore").regime, "fta")

    def test_empty_origin_returns_none(self) -> None:
        self.assertIsNone(origin_document_requirements(""))
        self.assertIsNone(origin_document_requirements("   "))


if __name__ == "__main__":
    unittest.main()

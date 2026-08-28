from __future__ import annotations

import io
import os
import unittest
from unittest.mock import patch

from PIL import Image

from customs_advisor import (
    CandidateGtip,
    CustomsInquiry,
    CustomsModelResult,
    Finding,
    OfficialSourceRegistry,
    ProductAttributeAnalysis,
    TaxFinding,
    _deterministic_cost,
    _missing_information,
    _parse_json_object,
    _sanitize_model_result,
    _select_vision_provider,
    validate_image,
)


class CustomsAdvisorSafetyTests(unittest.TestCase):
    def test_gtip_is_normalised_but_not_invented(self) -> None:
        inquiry = CustomsInquiry(
            question="Bu ürünün ithalat koşulları nedir?",
            candidate_gtip="6104.63.00.00.00",
        )
        self.assertEqual(inquiry.candidate_gtip, "610463000000")
        self.assertIn("Ürünün teknik ve ticari tanımı", _missing_information(inquiry))

    def test_invalid_gtip_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            CustomsInquiry(question="Bu ürün nedir?", candidate_gtip="12345")

    def test_cost_uses_only_user_supplied_rates(self) -> None:
        inquiry = CustomsInquiry(
            question="Maliyet nedir?",
            invoice_value=1000,
            freight=100,
            insurance=10,
            other_pre_import_costs=20,
            customs_duty_rate=10,
            additional_duty_rate=5,
            vat_rate=20,
        )
        cost = _deterministic_cost(inquiry)
        self.assertIsNotNone(cost)
        self.assertEqual(cost["customs_value_estimate"], 1110)
        self.assertEqual(cost["customs_duty"], 111)
        self.assertEqual(cost["additional_duty"], 55.5)
        self.assertEqual(cost["vat"], 259.3)
        self.assertEqual(cost["status"], "user_rates_complete")

    def test_uncited_model_claims_are_neutralised(self) -> None:
        result = CustomsModelResult(
            summary="Ön değerlendirme",
            answer_status="preliminary",
            candidate_gtips=[
                CandidateGtip(code="6104630000", explanation="Kanıtsız aday", citations=["fake"]),
                CandidateGtip(code="6104620000", explanation="Kanıtlı aday", citations=["tariff_btb"]),
            ],
            controls=[Finding(name="TAREKS", status="required", explanation="Kesin gerekir", citations=[])],
            taxes=[TaxFinding(name="İGV", status="applicable", rate="%20", explanation="Kesin", citations=["fake"])],
        )
        clean = _sanitize_model_result(result, {"tariff_btb"})
        self.assertEqual([item.code for item in clean.candidate_gtips], ["6104620000"])
        self.assertEqual(clean.controls[0].status, "unknown")
        self.assertEqual(clean.taxes[0].status, "unknown")
        self.assertIsNone(clean.taxes[0].rate)

    def test_uploaded_image_is_decoded_and_reencoded(self) -> None:
        original = io.BytesIO()
        Image.new("RGB", (400, 300), "navy").save(original, format="PNG")
        clean, media_type = validate_image(original.getvalue(), "image/png")
        self.assertEqual(media_type, "image/jpeg")
        self.assertTrue(clean.startswith(b"\xff\xd8\xff"))

    def test_non_image_upload_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            validate_image(b"not-an-image", "image/png")

    def test_vision_json_parser_accepts_fenced_object(self) -> None:
        parsed = _parse_json_object('```json\n{"product_name":"Çocuk şortu"}\n```')
        self.assertEqual(parsed["product_name"], "Çocuk şortu")

    def test_auto_provider_prefers_gemini_structured_vision(self) -> None:
        with patch.dict(
            os.environ,
            {
                "CUSTOMS_VISION_PROVIDER": "auto",
                "ZAI_API_KEY": "zai-test",
                "GEMINI_API_KEY": "gemini-test",
                "OPENAI_API_KEY": "openai-test",
            },
            clear=True,
        ):
            provider, model, key = _select_vision_provider()
        self.assertEqual((provider, model, key), ("gemini", "gemini-3.7-flash", "gemini-test"))

    def test_zai_uses_current_vision_fallback_model(self) -> None:
        with patch.dict(
            os.environ,
            {"CUSTOMS_VISION_PROVIDER": "zai", "ZAI_API_KEY": "zai-test"},
            clear=True,
        ):
            provider, model, key = _select_vision_provider()
        self.assertEqual((provider, model, key), ("zai", "glm-5v-turbo", "zai-test"))

    def test_vision_result_never_exposes_model_supplied_gtip(self) -> None:
        result = ProductAttributeAnalysis.model_validate(
            {
                "provider": "zai",
                "model": "glm-4.6v",
                "product_name": "Şort",
                "visible_origin_country": "",
                "required_user_inputs": ["Menşe ülke", "Etiket bileşimi"],
                "candidate_gtip": "610463000000",
            }
        )
        self.assertNotIn("candidate_gtip", result.model_dump())
        self.assertEqual(result.required_user_inputs, ["Menşe ülke", "Etiket bileşimi"])
        self.assertTrue(result.user_confirmation_required)


class OfficialSourceRegistryTests(unittest.IsolatedAsyncioTestCase):
    async def test_captcha_source_is_manual_only_and_not_fetched(self) -> None:
        registry = OfficialSourceRegistry()
        try:
            result = await registry._fetch(
                {
                    "id": "tariff_search",
                    "title": "Tarife Arama Motoru",
                    "authority": "T.C. Ticaret Bakanlığı",
                    "url": "https://uygulama.gtb.gov.tr/Tara/TarifeBasitArama",
                    "access_mode": "manual_only",
                    "note": "Güvenlik sorusu nedeniyle manuel doğrulanır.",
                },
                ["şort"],
            )
        finally:
            await registry.close()
        self.assertEqual(result.access_mode, "manual_only")
        self.assertEqual(result.excerpt, "")
        self.assertIn("manuel", result.fetch_warning)


if __name__ == "__main__":
    unittest.main()

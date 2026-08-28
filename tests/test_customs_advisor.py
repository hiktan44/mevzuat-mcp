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
    _openrouter_message_text,
    _openrouter_models,
    _openrouter_payload,
    _parse_json_object,
    _sanitize_model_result,
    _strict_json_schema,
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

    def test_openrouter_default_chain_starts_with_gemini_then_glm(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            models = _openrouter_models("OPENROUTER_VISION_MODELS")
        self.assertEqual(
            models,
            [
                "~google/gemini-flash-latest",
                "z-ai/glm-5.3-flash",
                "~x-ai/grok-latest",
                "openai/gpt-chat-latest",
                "~anthropic/claude-opus-latest",
            ],
        )

    def test_openrouter_chain_is_configurable_and_deduplicated(self) -> None:
        with patch.dict(
            os.environ,
            {"OPENROUTER_VISION_MODELS": "google/gemini-3.7-flash, z-ai/glm-5.3-flash, google/gemini-3.7-flash"},
            clear=True,
        ):
            models = _openrouter_models("OPENROUTER_VISION_MODELS")
        self.assertEqual(models, ["google/gemini-3.7-flash", "z-ai/glm-5.3-flash"])

    def test_invalid_openrouter_model_id_is_rejected(self) -> None:
        with patch.dict(
            os.environ,
            {"OPENROUTER_VISION_MODELS": "https://untrusted.example/model"},
            clear=True,
        ):
            with self.assertRaises(ValueError):
                _openrouter_models("OPENROUTER_VISION_MODELS")

    def test_openrouter_multiblock_content_keeps_only_text(self) -> None:
        content = _openrouter_message_text(
            [
                {"type": "text", "text": "ilk"},
                {"type": "tool_call", "text": "çalıştırma"},
                {"type": "output_text", "text": "ikinci"},
            ]
        )
        self.assertEqual(content, "ilk\nikinci")

    def test_openrouter_payload_enforces_order_schema_and_privacy(self) -> None:
        models = ["~google/gemini-flash-latest", "z-ai/glm-5.3-flash"]
        payload = _openrouter_payload(
            models=models,
            messages=[{"role": "user", "content": "test"}],
            response_schema={"type": "object"},
            schema_name="test_schema",
            max_tokens=100,
        )
        self.assertEqual(payload["models"], models)
        self.assertTrue(payload["provider"]["allow_fallbacks"])
        self.assertTrue(payload["provider"]["require_parameters"])
        self.assertEqual(payload["provider"]["data_collection"], "deny")
        self.assertTrue(payload["response_format"]["json_schema"]["strict"])

    def test_strict_schema_requires_all_nested_properties(self) -> None:
        schema = _strict_json_schema(CustomsModelResult.model_json_schema())
        self.assertEqual(set(schema["required"]), set(schema["properties"]))
        self.assertFalse(schema["additionalProperties"])
        for definition in schema["$defs"].values():
            self.assertEqual(set(definition["required"]), set(definition["properties"]))
            self.assertFalse(definition["additionalProperties"])

    def test_vision_result_never_exposes_model_supplied_gtip(self) -> None:
        result = ProductAttributeAnalysis.model_validate(
            {
                "provider": "openrouter",
                "model": "z-ai/glm-5.3-flash",
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

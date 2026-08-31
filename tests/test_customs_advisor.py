from __future__ import annotations

import io
import json
import os
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
from PIL import Image

from customs_advisor import (
    CandidateGtip,
    ClassificationAnswer,
    CustomsAdvisor,
    CustomsInquiry,
    CustomsModelResult,
    EvidenceSource,
    Finding,
    OfficialSourceRegistry,
    ProductAttributeAnalysis,
    ProductClassificationRequest,
    TaxFinding,
    _deterministic_cost,
    _evidence_prompt,
    _expert_review_packet,
    _missing_information,
    _openrouter_message_text,
    _openrouter_headers,
    _openrouter_error_detail,
    _openrouter_models,
    _openrouter_payload,
    _parse_json_object,
    _sanitize_model_result,
    _strict_json_schema,
    validate_image,
)


class CustomsAdvisorSafetyTests(unittest.TestCase):
    def test_user_answers_and_textile_context_are_preserved_for_classification(self) -> None:
        answer = ClassificationAnswer(
            question="Kumaşın net elyaf kompozisyonu nedir?",
            answer="%60 pamuk, %40 polyester",
        )
        request = ProductClassificationRequest(
            product_description="Örme kumaştan iki parçalı çocuk giyim takımı",
            target_user="Kız çocuk, 8-12 yaş",
            declared_product_type="Pijama takımı",
            classification_answers=[answer],
        )
        payload = json.loads(request.model_dump_json())
        self.assertEqual(payload["target_user"], "Kız çocuk, 8-12 yaş")
        self.assertEqual(payload["declared_product_type"], "Pijama takımı")
        self.assertEqual(payload["classification_answers"][0]["answer"], "%60 pamuk, %40 polyester")

    def test_gtip_is_normalised_but_not_invented(self) -> None:
        inquiry = CustomsInquiry(
            question="Bu ürünün ithalat koşulları nedir?",
            candidate_gtip="6104.63.00.00.00",
            tariff_selection_confirmed=True,
        )
        self.assertEqual(inquiry.candidate_gtip, "610463000000")
        self.assertIn("Ürünün teknik ve ticari tanımı", _missing_information(inquiry))

    def test_invalid_gtip_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            CustomsInquiry(question="Bu ürün nedir?", candidate_gtip="12345")

    def test_unconfirmed_tariff_code_is_rejected_server_side(self) -> None:
        with self.assertRaises(ValueError):
            CustomsInquiry(question="Bu ürün nedir?", candidate_gtip="610463")

    def test_exact_confirmation_requires_twelve_digits(self) -> None:
        with self.assertRaises(ValueError):
            CustomsInquiry(
                question="Bu ürün nedir?",
                candidate_gtip="610463",
                tariff_selection_confirmed=True,
                exact_gtip_confirmed=True,
            )

    def test_classification_model_ids_are_bounded_and_sanitised(self) -> None:
        inquiry = CustomsInquiry(
            question="Bu ürün nedir?",
            classification_models=[" google/gemini-test ", "google/gemini-test", "z-ai/glm-test"],
        )
        self.assertEqual(inquiry.classification_models, ["google/gemini-test", "z-ai/glm-test"])
        with self.assertRaises(ValueError):
            CustomsInquiry(question="Bu ürün nedir?", classification_models=["https://example.test/model?secret=x"])

    def test_evidence_prompt_and_expert_packet_keep_hash_chain(self) -> None:
        digest = "a" * 64
        inquiry = CustomsInquiry(
            question="Bu ürünün yükümlülükleri nedir?",
            product_description="Porselen kahve fincanı takımı",
            candidate_gtip="691110000000",
            tariff_selection_confirmed=True,
            exact_gtip_confirmed=True,
            classification_verification_status="dual_agreement",
            classification_confidence_score=90,
            classification_models=["google/gemini-test", "z-ai/glm-test"],
        )
        pack = SimpleNamespace(
            inquiry=inquiry,
            missing_information=[],
            deterministic_cost={"status": "rates_missing"},
            tariff_lookup=SimpleNamespace(unresolved_measure_types=["anti_dumping"]),
            control_lookup=SimpleNamespace(matches=[]),
            sources=[EvidenceSource(
                id="tariff_customs_duty_test_1",
                title="İthalat Rejimi",
                authority="T.C. Ticaret Bakanlığı",
                url="https://ticaret.gov.tr/test",
                excerpt="GTİP ve oran kanıtı",
                retrieved_at="2026-08-31T00:00:00+03:00",
                sha256=digest,
            )],
            as_of="2026-08-31T00:00:00+03:00",
            legal_notice="Ön değerlendirmedir.",
        )
        prompt = _evidence_prompt(pack)
        packet = _expert_review_packet(pack)
        self.assertIn("RESMÎ KANIT PAKETİ", prompt)
        self.assertIn("gümrük_müşaviri", packet.review_types)
        self.assertEqual(packet.tariff_snapshot_sha256, [digest])
        self.assertTrue(packet.escalation_required)

    def test_cost_uses_only_user_supplied_rates(self) -> None:
        inquiry = CustomsInquiry(
            question="Maliyet nedir?",
            invoice_value=1000,
            freight=100,
            insurance=10,
            other_pre_import_costs=20,
            customs_duty_rate=10,
            additional_duty_rate=5,
            additional_financial_liability_rate=0,
            anti_dumping_amount=0,
            kkdf_rate=0,
            vat_rate=20,
            sct_amount=0,
            surveillance_unit_value=0,
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

    def test_openrouter_headers_are_ascii_safe(self) -> None:
        headers = _openrouter_headers("sk-or-v1-test")
        self.assertEqual(headers["X-OpenRouter-Title"], "Gumrukce")
        for value in headers.values():
            value.encode("ascii")

    def test_openrouter_error_detail_is_short_and_does_not_echo_request(self) -> None:
        response = httpx.Response(
            400,
            request=httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions"),
            json={"error": {"message": "Model bu istek biçimini desteklemiyor. " + ("x" * 400)}},
        )
        detail = _openrouter_error_detail(response)
        self.assertLessEqual(len(detail), 240)
        self.assertIn("Model bu istek biçimini desteklemiyor", detail)
        self.assertNotIn("Authorization", detail)

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


class TariffClassificationTests(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def _candidate_result(code: str, explanation: str = "Resmî cetvelde doğrulanacak aday.") -> dict:
        return {
            "candidates": [{
                "code": code,
                "explanation": explanation,
                "confidence": "high",
                "decisive_missing_information": [],
            }],
            "missing_information": [],
            "summary": f"{code} değerlendirildi.",
        }

    async def test_candidates_are_verified_and_receive_origin_rates(self) -> None:
        class FakeTariffEngine:
            async def lookup(self, code, **kwargs):
                if code == "999999":
                    return SimpleNamespace(matched_gtip_count=0)
                rates = {"customs_duty": 12.0, "additional_duty": 39.0}
                return SimpleNamespace(
                    matched_gtip_count=3,
                    unambiguous_rates=rates,
                    ambiguous_measure_types=[],
                    rate_variants={key: [value] for key, value in rates.items()},
                )

        model_result = {
            "candidates": [
                {
                    "code": "691110",
                    "explanation": "Porselenden sofra eşyası adayı.",
                    "confidence": "medium",
                    "decisive_missing_information": ["Malzemenin porselen olup olmadığı"],
                },
                {
                    "code": "691200",
                    "explanation": "Porselen dışındaki seramik sofra eşyası adayı.",
                    "confidence": "medium",
                    "decisive_missing_information": ["Seramik türü"],
                },
                {
                    "code": "999999",
                    "explanation": "Resmî cetvelde bulunmayan uydurma kod.",
                    "confidence": "low",
                    "decisive_missing_information": [],
                },
            ],
            "missing_information": ["Kesin seramik türü"],
            "summary": "İki malzeme alternatifi var.",
        }
        advisor = CustomsAdvisor(tariff_engine=FakeTariffEngine())
        try:
            with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"}), patch(
                "customs_advisor._openrouter_chat",
                new=AsyncMock(return_value=(json.dumps(model_result), "google/gemini-test")),
            ):
                result = await advisor.classify_product(
                    ProductClassificationRequest(
                        product_description="Dört parçalı seramik veya porselen kahve fincanı takımı",
                        composition="Seramik veya porselen",
                        origin_country="Çin",
                    )
                )
        finally:
            await advisor.close()
        self.assertEqual([item.code for item in result.candidates], ["691110", "691200"])
        self.assertTrue(all(item.verified_in_official_tariff for item in result.candidates))
        self.assertEqual(result.candidates[0].customs_duty_rate, 12.0)
        self.assertEqual(result.candidates[0].additional_duty_rate, 39.0)
        self.assertEqual(result.candidates[0].rate_status, "unambiguous")

    async def test_rates_wait_for_origin_country(self) -> None:
        class FakeTariffEngine:
            async def lookup(self, code, **kwargs):
                return SimpleNamespace(
                    matched_gtip_count=1,
                    unambiguous_rates={},
                    ambiguous_measure_types=[],
                    rate_variants={},
                )

        model_result = {
            "candidates": [{
                "code": "691110",
                "explanation": "Porselen fincan adayı.",
                "confidence": "low",
                "decisive_missing_information": ["Menşe ülke", "Malzeme"],
            }],
            "missing_information": ["Menşe ülke"],
            "summary": "Menşe oran için gereklidir.",
        }
        advisor = CustomsAdvisor(tariff_engine=FakeTariffEngine())
        try:
            with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"}), patch(
                "customs_advisor._openrouter_chat",
                new=AsyncMock(return_value=(json.dumps(model_result), "google/gemini-test")),
            ):
                result = await advisor.classify_product(
                    ProductClassificationRequest(
                        product_description="Porselen olabilecek kahve fincanı ve tabak takımı",
                    )
                )
        finally:
            await advisor.close()
        self.assertEqual(result.candidates[0].rate_status, "origin_required")
        self.assertIsNone(result.candidates[0].customs_duty_rate)

    async def test_gemini_and_glm_are_called_independently_and_self_reported_confidence_is_ignored(self) -> None:
        class FakeTariffEngine:
            async def lookup(self, code, **kwargs):
                return SimpleNamespace(
                    matched_gtip_count=2,
                    unambiguous_rates={"customs_duty": 8.0},
                    ambiguous_measure_types=[],
                    rate_variants={"customs_duty": [8.0]},
                )

        called_chains = []

        async def fake_chat(**kwargs):
            called_chains.append(kwargs["models"])
            first = kwargs["models"][0]
            resolved = "google/gemini-test" if "gemini" in first else "z-ai/glm-test"
            return json.dumps(self._candidate_result("691110")), resolved

        advisor = CustomsAdvisor(tariff_engine=FakeTariffEngine())
        try:
            with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"}), patch(
                "customs_advisor._openrouter_chat",
                new=fake_chat,
            ):
                result = await advisor.classify_product(
                    ProductClassificationRequest(product_description="Porselen kahve fincanı takımı")
                )
        finally:
            await advisor.close()
        self.assertEqual(result.verification_status, "dual_agreement")
        self.assertEqual(result.candidates[0].model_votes, 2)
        self.assertEqual(result.candidates[0].agreement_status, "exact")
        self.assertNotEqual(result.candidates[0].confidence, "high")
        self.assertIn("gemini", called_chains[0][0])
        self.assertIn("glm", called_chains[1][0])

    async def test_third_model_arbitrates_only_when_primary_codes_disagree(self) -> None:
        class FakeTariffEngine:
            async def lookup(self, code, **kwargs):
                return SimpleNamespace(
                    matched_gtip_count=1,
                    unambiguous_rates={"customs_duty": 8.0},
                    ambiguous_measure_types=[],
                    rate_variants={"customs_duty": [8.0]},
                )

        calls = []

        async def fake_chat(**kwargs):
            first = kwargs["models"][0]
            calls.append(first)
            if "gemini" in first:
                return json.dumps(self._candidate_result("691110")), "google/gemini-test"
            if "glm" in first:
                return json.dumps(self._candidate_result("691200")), "z-ai/glm-test"
            return json.dumps(self._candidate_result("691110")), "x-ai/grok-test"

        advisor = CustomsAdvisor(tariff_engine=FakeTariffEngine())
        try:
            with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"}), patch(
                "customs_advisor._openrouter_chat",
                new=fake_chat,
            ):
                result = await advisor.classify_product(
                    ProductClassificationRequest(product_description="Seramik veya porselen kahve fincanı")
                )
        finally:
            await advisor.close()
        self.assertEqual(result.verification_status, "arbitrated_disagreement")
        self.assertEqual(len(calls), 3)
        self.assertEqual(result.candidates[0].code, "691110")
        self.assertEqual(result.candidates[0].model_votes, 2)


if __name__ == "__main__":
    unittest.main()

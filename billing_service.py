"""Minimal iyzico Subscription Checkout integration with V2 request signing."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import uuid
from typing import Any
from urllib.parse import urlsplit

import httpx


class BillingError(ValueError):
    """A safe billing error that may be returned to the browser."""


class IyzicoBilling:
    _allowed_hosts = {"api.iyzipay.com", "sandbox-api.iyzipay.com"}

    def __init__(self) -> None:
        self.api_key = os.environ.get("IYZICO_API_KEY", "").strip()
        self.secret_key = os.environ.get("IYZICO_SECRET_KEY", "").strip()
        self.merchant_id = os.environ.get("IYZICO_MERCHANT_ID", "").strip()
        self.base_url = os.environ.get("IYZICO_BASE_URL", "https://sandbox-api.iyzipay.com").rstrip("/")
        host = (urlsplit(self.base_url).hostname or "").lower()
        if urlsplit(self.base_url).scheme != "https" or host not in self._allowed_hosts:
            raise BillingError("IYZICO_BASE_URL güvenilir iyzico adreslerinden biri olmalıdır.")

    @property
    def configured(self) -> bool:
        return bool(self.api_key and self.secret_key and self.merchant_id)

    def plan_reference(self, plan_code: str, billing_cycle: str) -> str:
        return os.environ.get(
            f"IYZICO_{plan_code.upper()}_{billing_cycle.upper()}_PLAN_REF", ""
        ).strip()

    def _authorization(self, path: str, body: str = "") -> str:
        random_key = uuid.uuid4().hex
        signature = hmac.new(
            self.secret_key.encode("utf-8"),
            f"{random_key}{path}{body}".encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        payload = f"apiKey:{self.api_key}&randomKey:{random_key}&signature:{signature}"
        return "IYZWSv2 " + base64.b64encode(payload.encode("utf-8")).decode("ascii")

    async def _request(self, method: str, path: str, *, payload: dict[str, Any] | None = None, params: dict[str, str] | None = None) -> dict[str, Any]:
        if not self.configured:
            raise BillingError("Ödeme sistemi henüz etkinleştirilmedi.")
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")) if payload is not None else ""
        headers = {"Authorization": self._authorization(path, body), "Content-Type": "application/json"}
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=False) as client:
            response = await client.request(
                method, f"{self.base_url}{path}", content=body.encode("utf-8") if body else None,
                params=params, headers=headers,
            )
        try:
            result = response.json()
        except ValueError as exc:
            raise BillingError("Ödeme sağlayıcısından geçersiz yanıt alındı.") from exc
        if response.status_code >= 400 or result.get("status") != "success":
            message = str(result.get("errorMessage") or "Ödeme oturumu başlatılamadı.")[:300]
            raise BillingError(message)
        return result

    async def initialize_checkout(
        self, *, plan_code: str, billing_cycle: str, conversation_id: str,
        callback_url: str, customer: dict[str, str],
    ) -> dict[str, Any]:
        reference = self.plan_reference(plan_code, billing_cycle)
        if not reference:
            raise BillingError("Bu paket için iyzico plan referansı yapılandırılmadı.")
        required = ("name", "surname", "email", "gsmNumber", "identityNumber", "address", "city", "country")
        if any(not str(customer.get(key, "")).strip() for key in required):
            raise BillingError("Fatura ve abone bilgilerini eksiksiz doldurun.")
        gsm = re.sub(r"[\s()-]", "", customer["gsmNumber"])
        identity = re.sub(r"\D", "", customer["identityNumber"])
        if not re.fullmatch(r"\+?[1-9]\d{9,14}", gsm):
            raise BillingError("Telefon numarasını ülke koduyla girin.")
        if not re.fullmatch(r"\d{10,20}", identity):
            raise BillingError("Kimlik/vergi numarası biçimini kontrol edin.")
        contact_name = f"{customer['name'].strip()} {customer['surname'].strip()}"[:100]
        address = {
            "address": customer["address"].strip()[:500],
            "zipCode": customer.get("zipCode", "").strip()[:20],
            "contactName": contact_name,
            "city": customer["city"].strip()[:100],
            "country": customer["country"].strip()[:100],
        }
        payload = {
            "locale": "tr", "callbackUrl": callback_url,
            "pricingPlanReferenceCode": reference, "subscriptionInitialStatus": "ACTIVE",
            "conversationId": conversation_id,
            "customer": {
                "name": customer["name"].strip()[:100], "surname": customer["surname"].strip()[:100],
                "email": customer["email"].strip()[:320], "gsmNumber": gsm,
                "identityNumber": identity, "billingAddress": address, "shippingAddress": address,
            },
        }
        result = await self._request("POST", "/v2/subscription/checkoutform/initialize", payload=payload)
        token = str(result.get("token", ""))
        content = str(result.get("checkoutFormContent", ""))
        if not token or not content or len(content) > 1_000_000:
            raise BillingError("iyzico ödeme formu alınamadı.")
        return {"token": token, "checkout_form_content": content, "expires_in": int(result.get("tokenExpireTime", 1800))}

    async def retrieve_checkout(self, token: str, conversation_id: str) -> dict[str, Any]:
        if not re.fullmatch(r"[A-Za-z0-9-]{10,255}", token):
            raise BillingError("Ödeme anahtarı geçersiz.")
        result = await self._request(
            "GET", f"/v2/subscription/checkoutform/{token}", params={"conversationId": conversation_id}
        )
        if str(result.get("conversationId", "")) != conversation_id or str(result.get("token", "")) != token:
            raise BillingError("Ödeme yanıtı oturumla eşleşmedi.")
        data = result.get("data")
        if not isinstance(data, dict):
            raise BillingError("Abonelik sonucu henüz hazır değil.")
        return data

    async def cancel_subscription(self, subscription_reference: str) -> None:
        if not re.fullmatch(r"[A-Za-z0-9-]{10,255}", subscription_reference):
            raise BillingError("Abonelik referansı geçersiz.")
        path = f"/v2/subscription/subscriptions/{subscription_reference}/cancel"
        await self._request(
            "POST", path, payload={"subscriptionReferenceCode": subscription_reference}
        )

    def verify_subscription_webhook(self, body: dict[str, Any], supplied_signature: str) -> bool:
        if not self.configured or not re.fullmatch(r"[0-9a-fA-F]{64}", supplied_signature or ""):
            return False
        parts = (
            self.merchant_id, self.secret_key, str(body.get("iyziEventType", "")),
            str(body.get("subscriptionReferenceCode", "")), str(body.get("orderReferenceCode", "")),
            str(body.get("customerReferenceCode", "")),
        )
        expected = hmac.new(self.secret_key.encode("utf-8"), "".join(parts).encode("utf-8"), hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, supplied_signature.casefold())

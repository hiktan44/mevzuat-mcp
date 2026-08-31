"""Stripe Billing integration for hosted subscriptions and customer self-service.

Card data never crosses the application. Checkout and the billing portal are
Stripe-hosted; local state changes only after a signed webhook or a server-side
retrieval of the returned Checkout Session.
"""

from __future__ import annotations

import asyncio
import os
import re
from typing import Any
from urllib.parse import urlsplit

import stripe


STRIPE_API_VERSION = "2026-02-25.clover"
_ID_RE = re.compile(r"^[A-Za-z]+_[A-Za-z0-9_]+$")
_PRICE_RE = re.compile(r"^price_[A-Za-z0-9_]+$")
_CHECKOUT_RE = re.compile(r"^cs_(?:test_|live_)?[A-Za-z0-9_]+$")
_CUSTOMER_RE = re.compile(r"^cus_[A-Za-z0-9_]+$")
_SUBSCRIPTION_RE = re.compile(r"^sub_[A-Za-z0-9_]+$")


class BillingError(ValueError):
    """A safe billing error that may be returned to the browser."""


def _stripe_dict(value: Any) -> dict[str, Any]:
    if hasattr(value, "to_dict_recursive"):
        result = value.to_dict_recursive()
    elif hasattr(value, "to_dict"):
        result = value.to_dict()
    else:
        result = dict(value)
    if not isinstance(result, dict):
        raise BillingError("Stripe geçersiz bir ödeme yanıtı döndürdü.")
    return result


def _safe_stripe_url(value: Any, *, hosts: set[str]) -> str:
    url = str(value or "")
    parsed = urlsplit(url)
    host = (parsed.hostname or "").casefold()
    if parsed.scheme != "https" or host not in hosts:
        raise BillingError("Stripe güvenli yönlendirme adresi döndürmedi.")
    return url


class StripeBilling:
    """Small, fail-closed wrapper around the official Stripe Python SDK."""

    def __init__(self) -> None:
        self.secret_key = os.environ.get("STRIPE_SECRET_KEY", "").strip()
        self.webhook_secret = os.environ.get("STRIPE_WEBHOOK_SECRET", "").strip()
        self.automatic_tax = os.environ.get("STRIPE_AUTOMATIC_TAX", "false").strip().casefold() == "true"
        self._prices = {
            (plan, cycle): os.environ.get(f"STRIPE_PRICE_{plan.upper()}_{cycle.upper()}", "").strip()
            for plan in ("expert", "team")
            for cycle in ("monthly", "yearly")
        }
        self._client: stripe.StripeClient | None = None
        if self._valid_secret_key:
            self._client = stripe.StripeClient(
                self.secret_key,
                stripe_version=STRIPE_API_VERSION,
                max_network_retries=2,
            )

    @property
    def _valid_secret_key(self) -> bool:
        return bool(re.fullmatch(r"sk_(?:test|live)_[A-Za-z0-9_]+", self.secret_key))

    @property
    def configured(self) -> bool:
        return bool(
            self._valid_secret_key
            and re.fullmatch(r"whsec_[A-Za-z0-9_]+", self.webhook_secret)
            and all(_PRICE_RE.fullmatch(value) for value in self._prices.values())
            and self.automatic_tax
        )

    @property
    def mode(self) -> str:
        if self.secret_key.startswith("sk_live_"):
            return "live"
        if self.secret_key.startswith("sk_test_"):
            return "test"
        return "disabled"

    def price_reference(self, plan_code: str, billing_cycle: str) -> str:
        price = self._prices.get((plan_code, billing_cycle), "")
        if not _PRICE_RE.fullmatch(price):
            raise BillingError("Bu paket için geçerli Stripe Price ID yapılandırılmadı.")
        return price

    def price_lookup(self) -> dict[str, tuple[str, str]]:
        return {
            value: key
            for key, value in self._prices.items()
            if _PRICE_RE.fullmatch(value)
        }

    def _required_client(self, *, full_configuration: bool = True) -> stripe.StripeClient:
        if self._client is None or (full_configuration and not self.configured):
            raise BillingError("Stripe ödeme sistemi henüz etkinleştirilmedi.")
        return self._client

    async def create_checkout(
        self,
        *,
        plan_code: str,
        billing_cycle: str,
        payment_session_id: str,
        google_sub: str,
        email: str,
        customer_reference: str | None,
        public_base_url: str,
        expected_amount_try: int,
    ) -> dict[str, str]:
        client = self._required_client()
        price = self.price_reference(plan_code, billing_cycle)
        await self._verify_price(
            client,
            price,
            expected_amount_try=expected_amount_try,
            billing_cycle=billing_cycle,
        )
        metadata = {
            "payment_session_id": payment_session_id,
            "google_sub": google_sub[:255],
            "plan_code": plan_code,
            "billing_cycle": billing_cycle,
        }
        params: dict[str, Any] = {
            "mode": "subscription",
            "line_items": [{"price": price, "quantity": 1}],
            "success_url": f"{public_base_url}/api/billing/stripe/return?session_id={{CHECKOUT_SESSION_ID}}",
            "cancel_url": f"{public_base_url}/app?payment=cancelled&account=open",
            "client_reference_id": payment_session_id,
            "billing_address_collection": "required",
            "tax_id_collection": {"enabled": True},
            "allow_promotion_codes": True,
            "locale": "tr",
            "metadata": metadata,
            "subscription_data": {"metadata": metadata},
        }
        if customer_reference and _CUSTOMER_RE.fullmatch(customer_reference):
            params["customer"] = customer_reference
        else:
            params["customer_email"] = email[:320]
        params["automatic_tax"] = {"enabled": True}
        try:
            session = await asyncio.to_thread(
                client.v1.checkout.sessions.create,
                params,
                {"idempotency_key": f"checkout-{payment_session_id}"},
            )
        except stripe.error.StripeError as exc:
            raise BillingError("Stripe ödeme oturumu başlatılamadı.") from exc
        result = _stripe_dict(session)
        session_id = str(result.get("id", ""))
        if not _CHECKOUT_RE.fullmatch(session_id):
            raise BillingError("Stripe ödeme oturumu kimliği geçersiz.")
        return {
            "session_id": session_id,
            "checkout_url": _safe_stripe_url(result.get("url"), hosts={"checkout.stripe.com"}),
        }

    async def _verify_price(
        self,
        client: stripe.StripeClient,
        price_reference: str,
        *,
        expected_amount_try: int,
        billing_cycle: str,
    ) -> None:
        try:
            price = await asyncio.to_thread(client.v1.prices.retrieve, price_reference)
        except stripe.error.StripeError as exc:
            raise BillingError("Stripe paket fiyatı doğrulanamadı.") from exc
        result = _stripe_dict(price)
        recurring = result.get("recurring") if isinstance(result.get("recurring"), dict) else {}
        expected_interval = "month" if billing_cycle == "monthly" else "year"
        if (
            result.get("active") is not True
            or str(result.get("currency", "")).casefold() != "try"
            or int(result.get("unit_amount") or -1) != expected_amount_try * 100
            or str(recurring.get("interval", "")) != expected_interval
            or int(recurring.get("interval_count") or 1) != 1
        ):
            raise BillingError(
                "Stripe Price ID tutar, TRY para birimi veya faturalama dönemiyle eşleşmiyor."
            )

    async def retrieve_checkout(self, session_id: str) -> dict[str, Any]:
        client = self._required_client()
        if not _CHECKOUT_RE.fullmatch(session_id):
            raise BillingError("Stripe ödeme oturumu kimliği geçersiz.")
        try:
            session = await asyncio.to_thread(
                client.v1.checkout.sessions.retrieve,
                session_id,
                {"expand": ["subscription"]},
            )
        except stripe.error.StripeError as exc:
            raise BillingError("Stripe ödeme sonucu doğrulanamadı.") from exc
        return _stripe_dict(session)

    async def create_portal(self, customer_reference: str, public_base_url: str) -> str:
        client = self._required_client(full_configuration=False)
        if not _CUSTOMER_RE.fullmatch(customer_reference):
            raise BillingError("Stripe müşteri kaydı bulunamadı.")
        try:
            session = await asyncio.to_thread(
                client.v1.billing_portal.sessions.create,
                {"customer": customer_reference, "return_url": f"{public_base_url}/app?account=open"},
            )
        except stripe.error.StripeError as exc:
            raise BillingError("Stripe abonelik yönetimi açılamadı.") from exc
        return _safe_stripe_url(
            _stripe_dict(session).get("url"),
            hosts={"billing.stripe.com"},
        )

    async def cancel_subscription(self, subscription_reference: str) -> None:
        client = self._required_client(full_configuration=False)
        if not _SUBSCRIPTION_RE.fullmatch(subscription_reference):
            raise BillingError("Stripe abonelik kaydı bulunamadı.")
        try:
            await asyncio.to_thread(client.v1.subscriptions.cancel, subscription_reference)
        except stripe.error.StripeError as exc:
            raise BillingError("Stripe aboneliği iptal edilemedi.") from exc

    def verify_webhook(self, raw_body: bytes, signature: str) -> dict[str, Any]:
        if not self.configured or not signature:
            raise BillingError("Stripe webhook doğrulaması yapılandırılmadı.")
        if len(raw_body) > 1_000_000:
            raise BillingError("Stripe webhook içeriği izin verilen boyutu aşıyor.")
        try:
            event = stripe.Webhook.construct_event(raw_body, signature, self.webhook_secret)
        except (ValueError, stripe.error.SignatureVerificationError) as exc:
            raise BillingError("Stripe webhook imzası doğrulanamadı.") from exc
        result = _stripe_dict(event)
        if not _ID_RE.fullmatch(str(result.get("id", ""))):
            raise BillingError("Stripe webhook olay kimliği geçersiz.")
        return result

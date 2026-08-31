import asyncio
import hashlib
import hmac
import json
import os
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from account_service import AccountError, AccountService, QuotaExceeded, collect_official_sources
from billing_service import BillingError, StripeBilling


def user(sub="user-1", email="user@example.com"):
    return {"sub": sub, "email": email, "name": "Test User"}


class AccountServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.accounts = AccountService(Path(self.temp.name), admin_emails="admin@example.com")
        with sqlite3.connect(self.accounts.db_path) as connection:
            for profile in (user(), user("user-2", "other@example.com"), user("admin", "admin@example.com")):
                connection.execute(
                    "INSERT INTO users(google_sub,email,name,picture,created_at,last_login_at) VALUES(?,?,?,'',1,1)",
                    (profile["sub"], profile["email"], profile["name"]),
                )

    def tearDown(self):
        self.temp.cleanup()

    def test_starter_quota_is_enforced_atomically(self):
        for _ in range(5):
            self.accounts.consume(user(), "vision")
        with self.assertRaises(QuotaExceeded):
            self.accounts.consume(user(), "vision")
        self.assertEqual(
            self.accounts.account(user())["quotas"]["vision"],
            {"used": 5, "limit": 5, "remaining": 0},
        )

    def test_dossiers_are_owner_scoped_and_only_official_urls_are_kept(self):
        dossier = self.accounts.create_dossier(
            user(), title="Kahve fincanı", product_name="Porselen fincan", gtip="691110",
            origin_country="Çin", effective_date="2026-08-30", checked_at="2026-08-30T10:00:00+00:00",
            payload={"sources": [{"url": "https://ticaret.gov.tr/gumruk"}, {"url": "https://evil.example/phish"}]},
            evidence={"tariff": {"active_snapshots": [{"archive_sha256": "a" * 64}]}},
        )
        self.assertEqual(dossier["evidence"]["official_source_urls"], ["https://ticaret.gov.tr/gumruk"])
        self.assertEqual(dossier["evidence"]["tariff"]["active_snapshots"][0]["archive_sha256"], "a" * 64)
        with self.assertRaises(AccountError):
            self.accounts.get_dossier(user("user-2", "other@example.com"), dossier["id"])

    def test_admin_plan_changes_are_audited(self):
        self.assertTrue(self.accounts.is_admin(user("admin", "admin@example.com")))
        self.accounts.admin_set_plan(user("admin", "admin@example.com"), "user-1", "expert", "active")
        self.assertEqual(self.accounts.account(user())["plan"]["code"], "expert")
        with sqlite3.connect(self.accounts.db_path) as connection:
            self.assertEqual(connection.execute("SELECT action FROM audit_log").fetchone()[0], "subscription.set")

    def test_account_deletion_cascades_owned_records(self):
        self.accounts.admin_set_plan(user("admin", "admin@example.com"), "user-1", "expert", "active")
        self.accounts.create_dossier(
            user(), title="Dosya", product_name="Ürün", gtip="610463", origin_country="Çin",
            effective_date=None, checked_at="2026-08-30T10:00:00+00:00", payload={}, evidence={},
        )
        self.assertTrue(self.accounts.delete_account(user()))
        with sqlite3.connect(self.accounts.db_path) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM dossiers WHERE google_sub='user-1'").fetchone()[0], 0)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM usage_ledger WHERE google_sub='user-1'").fetchone()[0], 0)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM subscriptions WHERE google_sub='user-1'").fetchone()[0], 0)

    def test_consultant_application_requires_review_and_is_advisory_only(self):
        profile = self.accounts.apply_as_consultant(user("user-2", "other@example.com"), {
            "display_name": "Ayşe Uzman", "title": "Gümrük mevzuatı danışmanı",
            "bio": "Tarife sınıflandırma ve ithalat mevzuatı alanında ürün bazlı görüş veriyorum.",
            "expertise": ["GTİP ve tarife sınıflandırma", "İthalat vergileri ve ticaret önlemleri"],
            "city": "İstanbul", "service_mode": "online", "experience_years": 8,
            "advisory_only_accepted": True,
        })
        self.assertEqual(profile["status"], "pending")
        self.assertTrue(profile["advisory_only"])
        self.assertEqual(self.accounts.list_consultants(), [])
        self.accounts.admin_set_consultant_status(user("admin", "admin@example.com"), "user-2", "active")
        public = self.accounts.list_consultants()[0]
        self.assertEqual(public["display_name"], "Ayşe Uzman")
        self.assertNotIn("google_sub", public)
        self.assertNotIn("email", public)

    def test_consultation_packet_excludes_image_cost_and_contact_data(self):
        self.accounts.apply_as_consultant(user("user-2", "other@example.com"), {
            "display_name": "Ayşe Uzman", "title": "Tarife sınıflandırma danışmanı",
            "bio": "Tarife kararları ve ürün evsafı üzerinden bağımsız sınıflandırma görüşü veriyorum.",
            "expertise": ["GTİP ve tarife sınıflandırma"], "city": "Ankara",
            "service_mode": "hybrid", "experience_years": 10, "advisory_only_accepted": True,
        })
        self.accounts.admin_set_consultant_status(user("admin", "admin@example.com"), "user-2", "active")
        consultant_id = self.accounts.list_consultants()[0]["id"]
        created = self.accounts.create_consultation_request(
            user(), consultant_id=consultant_id, subject="Porselen fincan sınıflandırması",
            message="Aday kodu ve ürün güvenliği kapsamını değerlendirir misiniz?", share_consent=True,
            result={
                "summary": "Ön değerlendirme", "as_of": "2026-08-31",
                "inquiry": {"product_description": "Porselen fincan", "candidate_gtip": "691110", "origin_country": "Çin", "invoice_value": 9999},
                "image_data": "data:image/png;base64,SECRET", "deterministic_cost": {"total": 9999},
                "expert_review_packet": {"risk_level": "high"},
                "sources": [{"url": "https://ticaret.gov.tr/gumruk"}],
            },
        )
        incoming = self.accounts.list_consultation_requests(user("user-2", "other@example.com"))["incoming"][0]
        self.assertEqual(incoming["id"], created["id"])
        serialized = json.dumps(incoming["packet"])
        self.assertNotIn("SECRET", serialized)
        self.assertNotIn("invoice_value", serialized)
        self.assertNotIn("deterministic_cost", serialized)
        self.assertEqual(incoming["packet"]["official_source_urls"], ["https://ticaret.gov.tr/gumruk"])
        self.accounts.update_consultation_request(user("user-2", "other@example.com"), created["id"], "accepted")
        self.accounts.add_consultation_message(user("user-2", "other@example.com"), created["id"], "Kod gerekçesini teknik belgeyle doğrulayın.")
        outgoing = self.accounts.list_consultation_requests(user())["outgoing"][0]
        self.assertEqual(outgoing["status"], "accepted")
        self.assertEqual(outgoing["messages"][0]["body"], "Kod gerekçesini teknik belgeyle doğrulayın.")
        with self.assertRaises(AccountError):
            self.accounts.add_consultation_message(user("admin", "admin@example.com"), created["id"], "Yetkisiz mesaj")

    def test_stripe_checkout_and_subscription_webhook_update_plan(self):
        payment = self.accounts.create_payment_session(user(), "expert", "monthly")
        self.accounts.attach_payment_token(payment["id"], "cs_test_checkout1")
        result = self.accounts.complete_stripe_checkout({
            "id": "cs_test_checkout1",
            "status": "complete",
            "payment_status": "paid",
            "client_reference_id": payment["id"],
            "customer": "cus_customer1",
            "subscription": {"id": "sub_subscription1", "status": "active", "current_period_end": 2_000_000_000},
            "metadata": {
                "payment_session_id": payment["id"], "google_sub": "user-1",
                "plan_code": "expert", "billing_cycle": "monthly",
            },
        })
        self.assertEqual(result, {"plan_code": "expert", "status": "active"})
        self.assertEqual(self.accounts.account(user())["plan"]["code"], "expert")

        event = {
            "id": "evt_subscription_update1", "type": "customer.subscription.updated",
            "data": {"object": {
                "id": "sub_subscription1", "customer": "cus_customer1", "status": "active",
                "items": {"data": [{"price": {"id": "price_team_yearly"}, "current_period_end": 2_100_000_000}]},
                "metadata": {"google_sub": "user-1"},
            }},
        }
        self.assertTrue(self.accounts.process_stripe_webhook(event, {"price_team_yearly": ("team", "yearly")}))
        self.assertFalse(self.accounts.process_stripe_webhook(event, {"price_team_yearly": ("team", "yearly")}))
        account = self.accounts.account(user())
        self.assertEqual(account["plan"]["code"], "team")
        self.assertEqual(account["subscription"]["billing_cycle"], "yearly")


class BillingSecurityTests(unittest.TestCase):
    @staticmethod
    def stripe_env():
        return {
            "STRIPE_SECRET_KEY": "sk_test_secret123", "STRIPE_WEBHOOK_SECRET": "whsec_testsecret",
            "STRIPE_PRICE_EXPERT_MONTHLY": "price_expert_monthly",
            "STRIPE_PRICE_EXPERT_YEARLY": "price_expert_yearly",
            "STRIPE_PRICE_TEAM_MONTHLY": "price_team_monthly",
            "STRIPE_PRICE_TEAM_YEARLY": "price_team_yearly",
            "STRIPE_AUTOMATIC_TAX": "true",
        }

    def test_official_source_allowlist_rejects_lookalikes(self):
        result = collect_official_sources({
            "source_url": "https://www.resmigazete.gov.tr/eskiler/2026/08/x.pdf",
            "nested": [{"url": "http://ticaret.gov.tr/no"}, {"url": "https://gov.tr.evil.example/no"}],
        })
        self.assertEqual(result, ["https://www.resmigazete.gov.tr/eskiler/2026/08/x.pdf"])

    def test_stripe_webhook_signature_and_configuration(self):
        with patch.dict(os.environ, self.stripe_env(), clear=False):
            billing = StripeBilling()
        self.assertTrue(billing.configured)
        self.assertEqual(billing.mode, "test")
        body = json.dumps({"id": "evt_signature1", "type": "invoice.paid", "data": {"object": {"id": "in_1"}}}).encode()
        timestamp = int(time.time())
        digest = hmac.new(b"whsec_testsecret", f"{timestamp}.".encode() + body, hashlib.sha256).hexdigest()
        event = billing.verify_webhook(body, f"t={timestamp},v1={digest}")
        self.assertEqual(event["id"], "evt_signature1")
        with self.assertRaises(BillingError):
            billing.verify_webhook(body, f"t={timestamp},v1={'0' * 64}")

    def test_stripe_price_must_match_server_catalog(self):
        class Prices:
            @staticmethod
            def retrieve(_reference):
                return {"active": True, "currency": "try", "unit_amount": 79_000, "recurring": {"interval": "month", "interval_count": 1}}

        class Client:
            class V1:
                prices = Prices()
            v1 = V1()

        with patch.dict(os.environ, self.stripe_env(), clear=False):
            billing = StripeBilling()
        asyncio.run(billing._verify_price(Client(), "price_expert_monthly", expected_amount_try=790, billing_cycle="monthly"))
        with self.assertRaises(BillingError):
            asyncio.run(billing._verify_price(Client(), "price_expert_monthly", expected_amount_try=2_490, billing_cycle="monthly"))

    def test_billing_fails_closed_without_secrets(self):
        with patch.dict(os.environ, {
            "STRIPE_SECRET_KEY": "", "STRIPE_WEBHOOK_SECRET": "",
            "STRIPE_PRICE_EXPERT_MONTHLY": "", "STRIPE_PRICE_EXPERT_YEARLY": "",
            "STRIPE_PRICE_TEAM_MONTHLY": "", "STRIPE_PRICE_TEAM_YEARLY": "",
        }, clear=False):
            self.assertFalse(StripeBilling().configured)


if __name__ == "__main__":
    unittest.main()

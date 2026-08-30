import hashlib
import hmac
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from account_service import AccountError, AccountService, QuotaExceeded, collect_official_sources
from billing_service import IyzicoBilling


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


class BillingSecurityTests(unittest.TestCase):
    def test_official_source_allowlist_rejects_lookalikes(self):
        result = collect_official_sources({
            "source_url": "https://www.resmigazete.gov.tr/eskiler/2026/08/x.pdf",
            "nested": [{"url": "http://ticaret.gov.tr/no"}, {"url": "https://gov.tr.evil.example/no"}],
        })
        self.assertEqual(result, ["https://www.resmigazete.gov.tr/eskiler/2026/08/x.pdf"])

    def test_iyzico_subscription_webhook_v3_signature(self):
        with patch.dict(os.environ, {
            "IYZICO_API_KEY": "api", "IYZICO_SECRET_KEY": "secret", "IYZICO_MERCHANT_ID": "merchant",
        }, clear=False):
            billing = IyzicoBilling()
        body = {
            "iyziEventType": "subscription.order.success", "subscriptionReferenceCode": "subscription",
            "orderReferenceCode": "order", "customerReferenceCode": "customer",
        }
        message = "merchantsecretsubscription.order.successsubscriptionordercustomer"
        signature = hmac.new(b"secret", message.encode(), hashlib.sha256).hexdigest()
        self.assertTrue(billing.verify_subscription_webhook(body, signature))
        self.assertFalse(billing.verify_subscription_webhook(body, "0" * 64))

    def test_billing_fails_closed_without_secrets(self):
        with patch.dict(os.environ, {
            "IYZICO_API_KEY": "", "IYZICO_SECRET_KEY": "", "IYZICO_MERCHANT_ID": "",
        }, clear=False):
            self.assertFalse(IyzicoBilling().configured)


if __name__ == "__main__":
    unittest.main()

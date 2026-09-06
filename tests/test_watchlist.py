from __future__ import annotations

import asyncio
import sqlite3
import tempfile
import time
import unittest
from unittest import mock

from account_service import AccountError, AccountService
from email_service import render_consultation_email, render_watch_email


def _user(sub: str = "sub-1", email: str = "a@example.com") -> dict:
    return {"sub": sub, "email": email, "name": "Test"}


class WatchlistTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.service = AccountService(self.temp.name)
        now = int(time.time())
        with sqlite3.connect(self.service.db_path) as db:
            db.execute("INSERT INTO users(google_sub,email,name,picture,created_at,last_login_at) VALUES(?,?,?,?,?,?)", ("sub-1", "a@example.com", "A", "", now, now))

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_add_list_remove_and_dedupe(self) -> None:
        created = self.service.add_watch(_user(), gtip="6911.10.00.00.11", label="Porselen", origin_country="Çin")
        self.assertEqual(created["gtip"], "691110000011")
        self.service.add_watch(_user(), gtip="691110000011", label="Porselen takım")
        items = self.service.list_watchlist(_user())
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["label"], "Porselen takım")
        self.assertTrue(self.service.remove_watch(_user(), created["id"]))
        self.assertEqual(self.service.list_watchlist(_user()), [])

    def test_invalid_code_and_unknown_user_are_rejected(self) -> None:
        with self.assertRaises(AccountError):
            self.service.add_watch(_user(), gtip="123")
        with self.assertRaises(AccountError):
            self.service.add_watch(_user(sub="ghost"), gtip="691110000011")

    def test_notification_log_is_idempotent(self) -> None:
        self.assertFalse(self.service.notification_sent("sub-1", "watch", "k"))
        self.service.mark_notified("sub-1", "watch", "k")
        self.service.mark_notified("sub-1", "watch", "k")
        self.assertTrue(self.service.notification_sent("sub-1", "watch", "k"))

    def test_all_watches_join_owner_email(self) -> None:
        self.service.add_watch(_user(), gtip="6911")
        rows = self.service.all_watches()
        self.assertEqual(rows[0]["email"], "a@example.com")
        self.assertEqual(rows[0]["gtip"], "6911")


class WatchEmailTests(unittest.TestCase):
    def test_watch_email_lists_changes(self) -> None:
        html = render_watch_email(
            [{"gtip": "691110000011", "label": "Porselen", "source_title": "İthalat Rejimi Kararı", "new_snapshot": "import_regime:abc",
              "changes": [{"gtip": "691110000011", "measure_label": "Gümrük vergisi", "country_group": "7", "before": "12", "after": "15"}]}],
            "https://example.test",
        )
        self.assertIn("691110000011", html)
        self.assertIn("Porselen", html)
        self.assertIn(">15<", html)
        self.assertIn("https://example.test/app", html)

    def test_consultation_email_escapes_content(self) -> None:
        html = render_consultation_email("message", "Konu <b>", "<script>alert(1)</script>", "https://example.test")
        self.assertNotIn("<script>", html)
        self.assertIn("&lt;script&gt;", html)


class NotifierTests(unittest.IsolatedAsyncioTestCase):
    async def test_notifier_sends_once_per_snapshot(self) -> None:
        import app as web_app

        temp = tempfile.TemporaryDirectory()
        service = AccountService(temp.name)
        now = int(time.time())
        with sqlite3.connect(service.db_path) as db:
            db.execute("INSERT INTO users(google_sub,email,name,picture,created_at,last_login_at) VALUES(?,?,?,?,?,?)", ("sub-1", "a@example.com", "A", "", now, now))
        service.add_watch(_user(), gtip="6911")
        ledgers = {
            "import_regime": {"status": "compared", "new_snapshot": "import_regime:new", "old_snapshot": "import_regime:old",
                              "changes": [{"gtip": "691110000011", "measure_type": "customs_duty", "country_group": "7", "before": "12", "after": "15"}]},
            "additional_duty": {"status": "no_previous_snapshot", "changes": []},
        }
        sent: list[dict] = []

        class FakeSender:
            configured = True

            async def send(self, *, to, subject, html_body):
                sent.append({"to": to, "subject": subject})
                return "id"

        with mock.patch.object(web_app, "account_service", service), mock.patch.object(web_app, "email_sender", FakeSender()), \
             mock.patch.object(web_app, "_change_ledgers", lambda: ledgers):
            first = await web_app.notify_watchlist_changes()
            second = await web_app.notify_watchlist_changes()
        self.assertEqual(first, {"users": 1, "sent": 1, "skipped": 0})
        self.assertEqual(second, {"users": 0, "sent": 0, "skipped": 0})
        self.assertEqual(sent[0]["to"], "a@example.com")
        temp.cleanup()


if __name__ == "__main__":
    unittest.main()

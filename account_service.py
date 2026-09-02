"""Persistent accounts, subscriptions, quotas and evidence dossiers.

The service deliberately stores structured customs results, never uploaded images or
payment-card data.  All mutable records are scoped to the signed Google subject.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


class AccountError(ValueError):
    """A safe, user-displayable account operation error."""


class QuotaExceeded(AccountError):
    """Raised when the active plan has no allowance left for an operation."""


@dataclass(frozen=True, slots=True)
class Plan:
    code: str
    name: str
    monthly_price_try: int | None
    yearly_price_try: int | None
    quotas: dict[str, int | None]
    features: tuple[str, ...]


PLANS: dict[str, Plan] = {
    "starter": Plan(
        "starter", "Başlangıç", 0, 0,
        {"vision": 5, "classification": 15, "precheck": 10, "dossier": 10},
        ("Temel ürün araştırması", "10 kanıt dosyası", "Resmî kaynak bağlantıları"),
    ),
    "expert": Plan(
        "expert", "Uzman", 790, 7_900,
        {"vision": 100, "classification": 300, "precheck": 150, "dossier": 500},
        ("Yoğun ürün analizi", "500 kanıt dosyası", "JSON dışa aktarma"),
    ),
    "team": Plan(
        "team", "Ekip", 2_490, 24_900,
        {"vision": 500, "classification": 1_500, "precheck": 750, "dossier": 5_000},
        ("Ekip kotası", "5.000 kanıt dosyası", "Öncelikli kullanım"),
    ),
    "institutional": Plan(
        "institutional", "Kurumsal", 7_500, None,
        {"vision": None, "classification": None, "precheck": None, "dossier": None},
        ("Özel kota", "Kurumsal entegrasyon", "Özel destek"),
    ),
}

_OPERATIONS = {"vision", "classification", "precheck", "dossier"}
_OFFICIAL_SUFFIXES = (
    ".gov.tr", ".bel.tr", ".edu.tr", ".europa.eu",
)
_OFFICIAL_HOSTS = {
    "resmigazete.gov.tr", "www.resmigazete.gov.tr", "mevzuat.gov.tr",
    "www.mevzuat.gov.tr", "data.europa.eu", "eur-lex.europa.eu",
}
_GTIP_RE = re.compile(r"^\d{4}(?:\d{2}){0,4}$")
_CONSULTANT_TITLES = {
    "Gümrük mevzuatı danışmanı",
    "Dış ticaret mevzuatı danışmanı",
    "Ürün güvenliği ve TAREKS danışmanı",
    "Tarife sınıflandırma danışmanı",
}
_CONSULTANT_EXPERTISE = {
    "GTİP ve tarife sınıflandırma", "İthalat vergileri ve ticaret önlemleri",
    "TAREKS ve ürün güvenliği", "TSE ve uygunluk belgeleri",
    "Kimyasallar ve çevre mevzuatı", "İhracat ve devlet destekleri",
}
_CONSULTATION_STATUSES = {"sent", "accepted", "declined", "closed"}


def _now() -> int:
    return int(time.time())


def _period_key(timestamp: int | None = None) -> str:
    return time.strftime("%Y-%m", time.gmtime(timestamp or _now()))


def _json(value: Any, *, max_bytes: int) -> str:
    encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    if len(encoded.encode("utf-8")) > max_bytes:
        raise AccountError("Kaydedilecek sonuç izin verilen boyutu aşıyor.")
    return encoded


def _official_url(value: Any) -> str | None:
    if not isinstance(value, str) or len(value) > 2_000:
        return None
    parsed = urlsplit(value.strip())
    host = (parsed.hostname or "").lower().rstrip(".")
    if parsed.scheme != "https" or not host:
        return None
    if host in _OFFICIAL_HOSTS or any(host.endswith(suffix) for suffix in _OFFICIAL_SUFFIXES):
        return value.strip()
    return None


def collect_official_sources(value: Any, *, limit: int = 100) -> list[str]:
    """Extract a bounded, de-duplicated official URL ledger from nested output."""
    found: list[str] = []
    seen: set[str] = set()

    def walk(item: Any, depth: int = 0) -> None:
        if depth > 8 or len(found) >= limit:
            return
        if isinstance(item, dict):
            for key, child in list(item.items())[:500]:
                if key in {"source_url", "document_url", "source_page_url", "archive_url", "landing_url", "url"}:
                    url = _official_url(child)
                    if url and url not in seen:
                        seen.add(url)
                        found.append(url)
                else:
                    walk(child, depth + 1)
        elif isinstance(item, list):
            for child in item[:500]:
                walk(child, depth + 1)

    walk(value)
    return found


class AccountService:
    def __init__(self, data_dir: str | Path | None = None, *, admin_emails: str | None = None) -> None:
        default_root = Path(os.environ.get("MEVZUAT_DATA_DIR", Path.home() / ".cache" / "mevzuat-mcp"))
        self.data_dir = Path(data_dir or default_root)
        raw_admins = admin_emails if admin_emails is not None else os.environ.get("ADMIN_EMAILS", "")
        self.admin_emails = {item.strip().casefold() for item in raw_admins.split(",") if item.strip()}
        self.db_path = self.data_dir / "users.sqlite3"
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path, timeout=10.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=10000")
        return connection

    def _ensure_schema(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.data_dir.chmod(0o700)
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    google_sub TEXT PRIMARY KEY, email TEXT NOT NULL, name TEXT NOT NULL DEFAULT '',
                    picture TEXT NOT NULL DEFAULT '', created_at INTEGER NOT NULL, last_login_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS subscriptions (
                    google_sub TEXT PRIMARY KEY REFERENCES users(google_sub) ON DELETE CASCADE,
                    plan_code TEXT NOT NULL DEFAULT 'starter', status TEXT NOT NULL DEFAULT 'active',
                    billing_cycle TEXT, period_start INTEGER, period_end INTEGER,
                    provider TEXT, provider_subscription_ref TEXT UNIQUE, provider_customer_ref TEXT,
                    updated_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS usage_ledger (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    google_sub TEXT NOT NULL REFERENCES users(google_sub) ON DELETE CASCADE,
                    operation TEXT NOT NULL, quantity INTEGER NOT NULL DEFAULT 1,
                    period_key TEXT NOT NULL, dossier_id TEXT, created_at INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS usage_owner_period ON usage_ledger(google_sub, period_key, operation);
                CREATE TABLE IF NOT EXISTS dossiers (
                    id TEXT PRIMARY KEY,
                    google_sub TEXT NOT NULL REFERENCES users(google_sub) ON DELETE CASCADE,
                    title TEXT NOT NULL, product_name TEXT NOT NULL DEFAULT '', gtip TEXT,
                    origin_country TEXT, effective_date TEXT, checked_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL, evidence_json TEXT NOT NULL,
                    schema_version INTEGER NOT NULL DEFAULT 1,
                    created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS dossier_owner_created ON dossiers(google_sub, created_at DESC);
                CREATE TABLE IF NOT EXISTS payment_sessions (
                    id TEXT PRIMARY KEY,
                    google_sub TEXT NOT NULL REFERENCES users(google_sub) ON DELETE CASCADE,
                    plan_code TEXT NOT NULL, billing_cycle TEXT NOT NULL,
                    conversation_id TEXT NOT NULL UNIQUE, provider_token TEXT UNIQUE,
                    provider_subscription_ref TEXT, provider_customer_ref TEXT,
                    status TEXT NOT NULL, created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS webhook_events (
                    provider TEXT NOT NULL, event_key TEXT NOT NULL, received_at INTEGER NOT NULL,
                    PRIMARY KEY(provider, event_key)
                );
                CREATE TABLE IF NOT EXISTS audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, actor_sub TEXT, actor_email TEXT,
                    action TEXT NOT NULL, target_type TEXT NOT NULL, target_id TEXT,
                    details_json TEXT NOT NULL, created_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS consultant_profiles (
                    google_sub TEXT PRIMARY KEY REFERENCES users(google_sub) ON DELETE CASCADE,
                    id TEXT NOT NULL UNIQUE, display_name TEXT NOT NULL, title TEXT NOT NULL,
                    bio TEXT NOT NULL, expertise_json TEXT NOT NULL, city TEXT NOT NULL DEFAULT '',
                    service_mode TEXT NOT NULL DEFAULT 'online', experience_years INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'pending', advisory_only INTEGER NOT NULL DEFAULT 1,
                    terms_accepted_at INTEGER NOT NULL, created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS consultant_status_updated ON consultant_profiles(status, updated_at DESC);
                CREATE TABLE IF NOT EXISTS consultation_requests (
                    id TEXT PRIMARY KEY,
                    requester_sub TEXT NOT NULL REFERENCES users(google_sub) ON DELETE CASCADE,
                    consultant_sub TEXT NOT NULL REFERENCES users(google_sub) ON DELETE CASCADE,
                    dossier_id TEXT REFERENCES dossiers(id) ON DELETE SET NULL,
                    subject TEXT NOT NULL, message TEXT NOT NULL, packet_json TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'sent', created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS consultation_requester_created ON consultation_requests(requester_sub, created_at DESC);
                CREATE INDEX IF NOT EXISTS consultation_consultant_created ON consultation_requests(consultant_sub, created_at DESC);
                CREATE TABLE IF NOT EXISTS consultation_messages (
                    id TEXT PRIMARY KEY,
                    request_id TEXT NOT NULL REFERENCES consultation_requests(id) ON DELETE CASCADE,
                    sender_sub TEXT NOT NULL REFERENCES users(google_sub) ON DELETE CASCADE,
                    body TEXT NOT NULL, created_at INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS consultation_message_thread ON consultation_messages(request_id, created_at);
                """
            )
        self.db_path.chmod(0o600)

    @staticmethod
    def public_plans() -> list[dict[str, Any]]:
        return [
            {
                "code": plan.code, "name": plan.name,
                "monthly_price_try": plan.monthly_price_try,
                "yearly_price_try": plan.yearly_price_try,
                "quotas": plan.quotas, "features": list(plan.features),
            }
            for plan in PLANS.values()
        ]

    def is_admin(self, user: dict[str, Any]) -> bool:
        return str(user.get("email", "")).casefold() in self.admin_emails

    def _subscription(self, connection: sqlite3.Connection, google_sub: str) -> sqlite3.Row | None:
        return connection.execute(
            "SELECT * FROM subscriptions WHERE google_sub=?", (google_sub,)
        ).fetchone()

    def account(self, user: dict[str, Any]) -> dict[str, Any]:
        google_sub = str(user["sub"])
        period = _period_key()
        with self._connect() as connection:
            row = self._subscription(connection, google_sub)
            plan_code = str(row["plan_code"]) if row and row["status"] == "active" else "starter"
            if plan_code not in PLANS:
                plan_code = "starter"
            usage_rows = connection.execute(
                "SELECT operation, COALESCE(SUM(quantity),0) used FROM usage_ledger "
                "WHERE google_sub=? AND period_key=? GROUP BY operation",
                (google_sub, period),
            ).fetchall()
            usage = {item["operation"]: int(item["used"]) for item in usage_rows}
        plan = PLANS[plan_code]
        quotas = {
            key: {"used": usage.get(key, 0), "limit": limit, "remaining": None if limit is None else max(0, limit - usage.get(key, 0))}
            for key, limit in plan.quotas.items()
        }
        return {
            "plan": {"code": plan.code, "name": plan.name},
            "subscription": dict(row) if row else {"status": "active", "plan_code": "starter"},
            "period": period, "quotas": quotas, "is_admin": self.is_admin(user),
        }

    def subscription_for_user(self, user: dict[str, Any]) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = self._subscription(connection, str(user["sub"]))
        return dict(row) if row else None

    def consume(self, user: dict[str, Any], operation: str, *, quantity: int = 1, dossier_id: str | None = None) -> dict[str, Any]:
        if operation not in _OPERATIONS or quantity < 1 or quantity > 100:
            raise AccountError("Geçersiz kullanım işlemi.")
        google_sub = str(user["sub"])
        period = _period_key()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = self._subscription(connection, google_sub)
            plan_code = str(row["plan_code"]) if row and row["status"] == "active" else "starter"
            plan = PLANS.get(plan_code, PLANS["starter"])
            used = int(connection.execute(
                "SELECT COALESCE(SUM(quantity),0) FROM usage_ledger WHERE google_sub=? AND period_key=? AND operation=?",
                (google_sub, period, operation),
            ).fetchone()[0])
            limit = plan.quotas[operation]
            if limit is not None and used + quantity > limit:
                raise QuotaExceeded(f"{plan.name} paketinin aylık {operation} kotası doldu.")
            connection.execute(
                "INSERT INTO usage_ledger(google_sub,operation,quantity,period_key,dossier_id,created_at) VALUES(?,?,?,?,?,?)",
                (google_sub, operation, quantity, period, dossier_id, _now()),
            )
        return {"used": used + quantity, "limit": limit, "remaining": None if limit is None else limit - used - quantity}

    def create_dossier(
        self, user: dict[str, Any], *, title: str, product_name: str, gtip: str | None,
        origin_country: str | None, effective_date: str | None, checked_at: str,
        payload: dict[str, Any], evidence: dict[str, Any],
    ) -> dict[str, Any]:
        title = title.strip()[:200] or "İthalat ön değerlendirmesi"
        product_name = product_name.strip()[:500]
        gtip_digits = re.sub(r"\D", "", gtip or "") or None
        if gtip_digits and not _GTIP_RE.fullmatch(gtip_digits):
            raise AccountError("GTİP 4, 6, 8, 10 veya 12 haneli olmalıdır.")
        dossier_id = str(uuid.uuid4())
        now = _now()
        sources = collect_official_sources(payload)
        safe_evidence = dict(evidence)
        safe_evidence["official_source_urls"] = sources
        safe_evidence["checked_at"] = checked_at
        safe_evidence["gtip"] = gtip_digits
        safe_evidence["origin_country"] = (origin_country or "").strip()[:100] or None
        safe_evidence["effective_date"] = (effective_date or "").strip()[:40] or None
        safe_evidence["schema_version"] = 1
        payload_json = _json(payload, max_bytes=750_000)
        evidence_json = _json(safe_evidence, max_bytes=250_000)
        self.consume(user, "dossier", dossier_id=dossier_id)
        try:
            with self._connect() as connection:
                connection.execute(
                    "INSERT INTO dossiers(id,google_sub,title,product_name,gtip,origin_country,effective_date,checked_at,payload_json,evidence_json,created_at,updated_at) "
                    "VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                    (dossier_id, str(user["sub"]), title, product_name, gtip_digits,
                     safe_evidence["origin_country"], safe_evidence["effective_date"], checked_at,
                     payload_json, evidence_json, now, now),
                )
        except Exception:
            with self._connect() as connection:
                connection.execute("DELETE FROM usage_ledger WHERE google_sub=? AND dossier_id=?", (str(user["sub"]), dossier_id))
            raise
        return self.get_dossier(user, dossier_id)

    def list_dossiers(self, user: dict[str, Any], *, limit: int = 50) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT id,title,product_name,gtip,origin_country,effective_date,checked_at,created_at,updated_at "
                "FROM dossiers WHERE google_sub=? ORDER BY created_at DESC LIMIT ?",
                (str(user["sub"]), max(1, min(limit, 100))),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_dossier(self, user: dict[str, Any], dossier_id: str) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM dossiers WHERE id=? AND google_sub=?", (dossier_id, str(user["sub"]))
            ).fetchone()
        if not row:
            raise AccountError("Kanıt dosyası bulunamadı.")
        result = dict(row)
        result["payload"] = json.loads(result.pop("payload_json"))
        result["evidence"] = json.loads(result.pop("evidence_json"))
        return result

    def delete_dossier(self, user: dict[str, Any], dossier_id: str) -> bool:
        """Delete an owned dossier and return its quota entry to the user's monthly allowance."""
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            cursor = connection.execute(
                "DELETE FROM dossiers WHERE id=? AND google_sub=?", (dossier_id, str(user["sub"]))
            )
            if cursor.rowcount > 0:
                connection.execute(
                    "DELETE FROM usage_ledger WHERE google_sub=? AND dossier_id=? AND operation='dossier'",
                    (str(user["sub"]), dossier_id),
                )
        return cursor.rowcount > 0

    def create_payment_session(self, user: dict[str, Any], plan_code: str, billing_cycle: str) -> dict[str, str]:
        if plan_code not in {"expert", "team"} or billing_cycle not in {"monthly", "yearly"}:
            raise AccountError("Satın alınabilir paket veya dönem geçersiz.")
        session_id, conversation_id = str(uuid.uuid4()), str(uuid.uuid4())
        now = _now()
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO payment_sessions(id,google_sub,plan_code,billing_cycle,conversation_id,status,created_at,updated_at) VALUES(?,?,?,?,?,'created',?,?)",
                (session_id, str(user["sub"]), plan_code, billing_cycle, conversation_id, now, now),
            )
        return {"id": session_id, "conversation_id": conversation_id, "plan_code": plan_code, "billing_cycle": billing_cycle}

    def attach_payment_token(self, session_id: str, token: str) -> None:
        with self._connect() as connection:
            cursor = connection.execute(
                "UPDATE payment_sessions SET provider_token=?,status='pending',updated_at=? WHERE id=? AND status='created'",
                (token[:255], _now(), session_id),
            )
        if cursor.rowcount != 1:
            raise AccountError("Ödeme oturumu güncellenemedi.")

    def payment_session_by_token(self, token: str) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM payment_sessions WHERE provider_token=?", (token,)).fetchone()
        if not row:
            raise AccountError("Ödeme oturumu bulunamadı.")
        return dict(row)

    def _complete_stripe_checkout(
        self, connection: sqlite3.Connection, checkout: dict[str, Any]
    ) -> dict[str, Any]:
        checkout_id = str(checkout.get("id", ""))[:255]
        metadata = checkout.get("metadata") if isinstance(checkout.get("metadata"), dict) else {}
        payment = connection.execute(
            "SELECT * FROM payment_sessions WHERE provider_token=?", (checkout_id,)
        ).fetchone()
        if not payment:
            raise AccountError("Stripe ödeme oturumu bulunamadı.")
        if (
            str(checkout.get("client_reference_id", "")) != str(payment["id"])
            or str(metadata.get("payment_session_id", "")) != str(payment["id"])
            or str(metadata.get("google_sub", "")) != str(payment["google_sub"])
            or str(metadata.get("plan_code", "")) != str(payment["plan_code"])
            or str(metadata.get("billing_cycle", "")) != str(payment["billing_cycle"])
        ):
            raise AccountError("Stripe ödeme oturumu paket veya kullanıcıyla eşleşmedi.")
        if str(checkout.get("status", "")) != "complete" or str(checkout.get("payment_status", "")) not in {
            "paid", "no_payment_required"
        }:
            raise AccountError("Stripe abonelik ödemesini henüz doğrulamadı.")
        subscription_value = checkout.get("subscription")
        customer_value = checkout.get("customer")
        subscription_ref = _stripe_reference(subscription_value, "sub_")
        customer_ref = _stripe_reference(customer_value, "cus_")
        if not subscription_ref or not customer_ref:
            raise AccountError("Stripe abonelik veya müşteri referansı eksik.")
        subscription_data = subscription_value if isinstance(subscription_value, dict) else {}
        provider_status = _stripe_status(str(subscription_data.get("status", "active")))
        now = _now()
        connection.execute(
            "UPDATE payment_sessions SET provider_subscription_ref=?,provider_customer_ref=?,status='completed',updated_at=? WHERE id=?",
            (subscription_ref, customer_ref, now, payment["id"]),
        )
        connection.execute(
            "INSERT INTO subscriptions(google_sub,plan_code,status,billing_cycle,period_start,period_end,provider,provider_subscription_ref,provider_customer_ref,updated_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(google_sub) DO UPDATE SET plan_code=excluded.plan_code,status=excluded.status,billing_cycle=excluded.billing_cycle,period_start=excluded.period_start,period_end=excluded.period_end,provider=excluded.provider,provider_subscription_ref=excluded.provider_subscription_ref,provider_customer_ref=excluded.provider_customer_ref,updated_at=excluded.updated_at",
            (
                payment["google_sub"], payment["plan_code"], provider_status,
                payment["billing_cycle"], _stripe_period(subscription_data, "start"),
                _stripe_period(subscription_data, "end"), "stripe",
                subscription_ref, customer_ref, now,
            ),
        )
        return {"plan_code": payment["plan_code"], "status": provider_status}

    def complete_stripe_checkout(self, checkout: dict[str, Any]) -> dict[str, Any]:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            return self._complete_stripe_checkout(connection, checkout)

    def process_stripe_webhook(
        self, event: dict[str, Any], price_lookup: dict[str, tuple[str, str]]
    ) -> bool:
        event_key = str(event.get("id", ""))[:255]
        event_type = str(event.get("type", ""))
        allowed = {
            "checkout.session.completed",
            "customer.subscription.updated",
            "customer.subscription.deleted",
            "invoice.paid",
            "invoice.payment_failed",
        }
        data = event.get("data") if isinstance(event.get("data"), dict) else {}
        obj = data.get("object") if isinstance(data.get("object"), dict) else {}
        if not event_key or event_type not in allowed or not obj:
            raise AccountError("Desteklenmeyen Stripe abonelik bildirimi.")
        now = _now()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                connection.execute(
                    "INSERT INTO webhook_events(provider,event_key,received_at) VALUES('stripe',?,?)",
                    (event_key, now),
                )
            except sqlite3.IntegrityError:
                return False

            if event_type == "checkout.session.completed":
                self._complete_stripe_checkout(connection, obj)
                return True

            if event_type.startswith("customer.subscription."):
                subscription_ref = _stripe_reference(obj, "sub_")
                customer_ref = _stripe_reference(obj.get("customer"), "cus_")
                metadata = obj.get("metadata") if isinstance(obj.get("metadata"), dict) else {}
                google_sub = str(metadata.get("google_sub", ""))
                price_ref = _stripe_subscription_price(obj)
                mapped = price_lookup.get(price_ref)
                status = "cancelled" if event_type.endswith("deleted") else _stripe_status(str(obj.get("status", "")))
                existing = connection.execute(
                    "SELECT * FROM subscriptions WHERE provider='stripe' AND provider_subscription_ref=?",
                    (subscription_ref,),
                ).fetchone()
                if not existing and not google_sub:
                    raise AccountError("Stripe abonelik bildiriminin kullanıcı eşleşmesi yok.")
                owner = str(existing["google_sub"]) if existing else google_sub
                if not connection.execute("SELECT 1 FROM users WHERE google_sub=?", (owner,)).fetchone():
                    raise AccountError("Stripe aboneliğinin kullanıcısı bulunamadı.")
                plan_code = mapped[0] if mapped else str(existing["plan_code"] if existing else metadata.get("plan_code", "starter"))
                billing_cycle = mapped[1] if mapped else str(existing["billing_cycle"] if existing else metadata.get("billing_cycle", ""))
                if plan_code not in PLANS:
                    raise AccountError("Stripe abonelik fiyatı paket kataloğuyla eşleşmedi.")
                connection.execute(
                    "INSERT INTO subscriptions(google_sub,plan_code,status,billing_cycle,period_start,period_end,provider,provider_subscription_ref,provider_customer_ref,updated_at) "
                    "VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(google_sub) DO UPDATE SET plan_code=excluded.plan_code,status=excluded.status,billing_cycle=excluded.billing_cycle,period_start=excluded.period_start,period_end=excluded.period_end,provider=excluded.provider,provider_subscription_ref=excluded.provider_subscription_ref,provider_customer_ref=excluded.provider_customer_ref,updated_at=excluded.updated_at",
                    (
                        owner, plan_code, status, billing_cycle or None,
                        _stripe_period(obj, "start"), _stripe_period(obj, "end"), "stripe",
                        subscription_ref, customer_ref or (str(existing["provider_customer_ref"]) if existing else None), now,
                    ),
                )
                return True

            subscription_ref = _stripe_invoice_subscription(obj)
            if not subscription_ref:
                raise AccountError("Stripe fatura bildiriminin abonelik referansı yok.")
            connection.execute(
                "UPDATE subscriptions SET status=?,updated_at=? WHERE provider='stripe' AND provider_subscription_ref=?",
                ("active" if event_type == "invoice.paid" else "past_due", now, subscription_ref),
            )
        return True

    def admin_overview(self) -> dict[str, Any]:
        with self._connect() as connection:
            users = connection.execute(
                "SELECT u.google_sub,u.email,u.name,u.created_at,u.last_login_at,COALESCE(s.plan_code,'starter') plan_code,COALESCE(s.status,'active') subscription_status,s.period_end "
                "FROM users u LEFT JOIN subscriptions s ON s.google_sub=u.google_sub ORDER BY u.last_login_at DESC LIMIT 500"
            ).fetchall()
            usage = connection.execute(
                "SELECT operation,SUM(quantity) quantity FROM usage_ledger WHERE period_key=? GROUP BY operation", (_period_key(),)
            ).fetchall()
            dossier_count = int(connection.execute("SELECT COUNT(*) FROM dossiers").fetchone()[0])
            consultants = connection.execute(
                "SELECT c.google_sub,c.id,c.display_name,c.title,c.bio,c.expertise_json,c.city,c.service_mode,c.experience_years,c.status,c.updated_at,u.email "
                "FROM consultant_profiles c JOIN users u ON u.google_sub=c.google_sub "
                "ORDER BY CASE c.status WHEN 'pending' THEN 0 WHEN 'active' THEN 1 ELSE 2 END,c.updated_at DESC LIMIT 500"
            ).fetchall()
        return {
            "users": [dict(row) for row in users],
            "usage": {row["operation"]: row["quantity"] for row in usage},
            "dossier_count": dossier_count,
            "consultants": [
                {**dict(row), "expertise": json.loads(row["expertise_json"])} for row in consultants
            ],
        }

    def admin_set_plan(self, actor: dict[str, Any], google_sub: str, plan_code: str, status: str) -> None:
        if plan_code not in PLANS or status not in {"active", "pending", "past_due", "cancelled"}:
            raise AccountError("Paket veya abonelik durumu geçersiz.")
        now = _now()
        with self._connect() as connection:
            if not connection.execute("SELECT 1 FROM users WHERE google_sub=?", (google_sub,)).fetchone():
                raise AccountError("Kullanıcı bulunamadı.")
            connection.execute(
                "INSERT INTO subscriptions(google_sub,plan_code,status,updated_at) VALUES(?,?,?,?) "
                "ON CONFLICT(google_sub) DO UPDATE SET plan_code=excluded.plan_code,status=excluded.status,updated_at=excluded.updated_at",
                (google_sub, plan_code, status, now),
            )
            connection.execute(
                "INSERT INTO audit_log(actor_sub,actor_email,action,target_type,target_id,details_json,created_at) VALUES(?,?,?,?,?,?,?)",
                (str(actor.get("sub", "")), str(actor.get("email", "")), "subscription.set", "user", google_sub,
                 _json({"plan_code": plan_code, "status": status}, max_bytes=5_000), now),
            )

    @staticmethod
    def _public_consultant(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
        item = dict(row)
        item["expertise"] = json.loads(item.pop("expertise_json"))
        item["advisory_only"] = bool(item.get("advisory_only", 1))
        for private_key in ("google_sub", "email", "terms_accepted_at"):
            item.pop(private_key, None)
        return item

    def list_consultants(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT id,display_name,title,bio,expertise_json,city,service_mode,experience_years,advisory_only,updated_at "
                "FROM consultant_profiles WHERE status='active' ORDER BY updated_at DESC LIMIT 200"
            ).fetchall()
        return [self._public_consultant(row) for row in rows]

    def consultant_profile(self, user: dict[str, Any]) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM consultant_profiles WHERE google_sub=?", (str(user["sub"]),)
            ).fetchone()
        if not row:
            return None
        item = dict(row)
        item["expertise"] = json.loads(item.pop("expertise_json"))
        item["advisory_only"] = bool(item["advisory_only"])
        return item

    def apply_as_consultant(self, user: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
        display_name = str(profile.get("display_name", "")).strip()[:80]
        title = str(profile.get("title", "")).strip()
        bio = str(profile.get("bio", "")).strip()[:1_200]
        city = str(profile.get("city", "")).strip()[:80]
        service_mode = str(profile.get("service_mode", "online"))
        try:
            experience_years = int(profile.get("experience_years", 0))
        except (TypeError, ValueError) as exc:
            raise AccountError("Deneyim yılı geçerli bir sayı olmalıdır.") from exc
        expertise_raw = profile.get("expertise")
        expertise = list(dict.fromkeys(str(item).strip() for item in expertise_raw)) if isinstance(expertise_raw, list) else []
        if not (2 <= len(display_name) <= 80):
            raise AccountError("Danışman adı 2–80 karakter olmalıdır.")
        if title not in _CONSULTANT_TITLES:
            raise AccountError("Danışmanlık alanı geçersiz.")
        if not (40 <= len(bio) <= 1_200):
            raise AccountError("Uzmanlık özeti en az 40 karakter olmalıdır.")
        if not expertise or len(expertise) > 6 or any(item not in _CONSULTANT_EXPERTISE for item in expertise):
            raise AccountError("En az bir geçerli uzmanlık alanı seçin.")
        if service_mode not in {"online", "hybrid"} or not 0 <= experience_years <= 60:
            raise AccountError("Hizmet biçimi veya deneyim yılı geçersiz.")
        if profile.get("advisory_only_accepted") is not True:
            raise AccountError("Danışmanlığın fiilî gümrük işlemi olmadığını kabul etmelisiniz.")
        now = _now()
        with self._connect() as connection:
            existing = connection.execute(
                "SELECT id,created_at FROM consultant_profiles WHERE google_sub=?", (str(user["sub"]),)
            ).fetchone()
            profile_id = str(existing["id"]) if existing else str(uuid.uuid4())
            created_at = int(existing["created_at"]) if existing else now
            connection.execute(
                "INSERT INTO consultant_profiles(google_sub,id,display_name,title,bio,expertise_json,city,service_mode,experience_years,status,advisory_only,terms_accepted_at,created_at,updated_at) "
                "VALUES(?,?,?,?,?,?,?,?,?,'pending',1,?,?,?) "
                "ON CONFLICT(google_sub) DO UPDATE SET display_name=excluded.display_name,title=excluded.title,bio=excluded.bio,expertise_json=excluded.expertise_json,city=excluded.city,service_mode=excluded.service_mode,experience_years=excluded.experience_years,status='pending',advisory_only=1,terms_accepted_at=excluded.terms_accepted_at,updated_at=excluded.updated_at",
                (str(user["sub"]), profile_id, display_name, title, bio,
                 _json(expertise, max_bytes=5_000), city, service_mode, experience_years, now, created_at, now),
            )
        return self.consultant_profile(user) or {}

    @staticmethod
    def _consultation_packet(result: dict[str, Any]) -> dict[str, Any]:
        inquiry = result.get("inquiry") if isinstance(result.get("inquiry"), dict) else {}
        safe_inquiry = {
            key: inquiry.get(key) for key in (
                "question", "product_description", "candidate_gtip", "origin_country",
                "composition", "intended_use", "target_user", "declared_product_type",
            ) if inquiry.get(key) not in (None, "")
        }
        packet = {
            "as_of": result.get("as_of"), "status": result.get("status"),
            "summary": result.get("summary"), "inquiry": safe_inquiry,
            "candidate_gtips": result.get("candidate_gtips", [])[:5] if isinstance(result.get("candidate_gtips"), list) else [],
            "missing_information": result.get("missing_information", [])[:30] if isinstance(result.get("missing_information"), list) else [],
            "expert_review_packet": result.get("expert_review_packet") if isinstance(result.get("expert_review_packet"), dict) else {},
            "official_source_urls": collect_official_sources(result, limit=50),
            "legal_notice": result.get("legal_notice"),
        }
        # Images, contact details, invoice values and deterministic cost fields are intentionally excluded.
        return packet

    def create_consultation_request(
        self, user: dict[str, Any], *, consultant_id: str, subject: str, message: str,
        result: dict[str, Any], share_consent: bool, dossier_id: str | None = None,
    ) -> dict[str, Any]:
        if not share_consent:
            raise AccountError("Danışmanla paylaşılacak alanları onaylamalısınız.")
        subject = subject.strip()[:160]
        message = message.strip()[:2_000]
        if not (5 <= len(subject) <= 160) or not (10 <= len(message) <= 2_000):
            raise AccountError("Konu en az 5, mesaj en az 10 karakter olmalıdır.")
        if not isinstance(result, dict):
            raise AccountError("Danışmana gönderilecek analiz dosyası eksik.")
        now = _now()
        request_id = str(uuid.uuid4())
        packet_json = _json(self._consultation_packet(result), max_bytes=180_000)
        with self._connect() as connection:
            consultant = connection.execute(
                "SELECT google_sub FROM consultant_profiles WHERE id=? AND status='active'", (consultant_id,)
            ).fetchone()
            if not consultant:
                raise AccountError("Seçilen danışman artık yayında değil.")
            if str(consultant["google_sub"]) == str(user["sub"]):
                raise AccountError("Kendi danışman profilinize dosya gönderemezsiniz.")
            recent = int(connection.execute(
                "SELECT COUNT(*) FROM consultation_requests WHERE requester_sub=? AND created_at>?",
                (str(user["sub"]), now - 86_400),
            ).fetchone()[0])
            if recent >= 10:
                raise AccountError("24 saatlik danışman talebi sınırına ulaştınız.")
            if dossier_id and not connection.execute(
                "SELECT 1 FROM dossiers WHERE id=? AND google_sub=?", (dossier_id, str(user["sub"]))
            ).fetchone():
                raise AccountError("Paylaşılacak kanıt dosyası bu hesaba ait değil.")
            connection.execute(
                "INSERT INTO consultation_requests(id,requester_sub,consultant_sub,dossier_id,subject,message,packet_json,status,created_at,updated_at) "
                "VALUES(?,?,?,?,?,?,?,'sent',?,?)",
                (request_id, str(user["sub"]), str(consultant["google_sub"]), dossier_id, subject, message, packet_json, now, now),
            )
        return {"id": request_id, "status": "sent", "created_at": now}

    def list_consultation_requests(self, user: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
        google_sub = str(user["sub"])
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT r.*,cp.id consultant_id,cp.display_name consultant_name "
                "FROM consultation_requests r JOIN consultant_profiles cp ON cp.google_sub=r.consultant_sub "
                "WHERE r.requester_sub=? OR r.consultant_sub=? ORDER BY r.created_at DESC LIMIT 200",
                (google_sub, google_sub),
            ).fetchall()
            outgoing, incoming = [], []
            for row in rows:
                item = dict(row)
                item["packet"] = json.loads(item.pop("packet_json"))
                item["direction"] = "outgoing" if item["requester_sub"] == google_sub else "incoming"
                messages = connection.execute(
                    "SELECT m.id,m.sender_sub,m.body,m.created_at FROM consultation_messages m "
                    "WHERE m.request_id=? ORDER BY m.created_at LIMIT 200",
                    (item["id"],),
                ).fetchall()
                item["messages"] = [
                    {**dict(message), "mine": str(message["sender_sub"]) == google_sub}
                    for message in messages
                ]
                for message in item["messages"]:
                    message.pop("sender_sub", None)
                item.pop("requester_sub", None)
                item.pop("consultant_sub", None)
                (outgoing if item["direction"] == "outgoing" else incoming).append(item)
        return {"outgoing": outgoing, "incoming": incoming}

    def update_consultation_request(self, user: dict[str, Any], request_id: str, status: str) -> None:
        if status not in {"accepted", "declined", "closed"}:
            raise AccountError("Danışmanlık talebi durumu geçersiz.")
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM consultation_requests WHERE id=?", (request_id,)).fetchone()
            if not row:
                raise AccountError("Danışmanlık talebi bulunamadı.")
            is_consultant = str(row["consultant_sub"]) == str(user["sub"])
            is_requester_closing = str(row["requester_sub"]) == str(user["sub"]) and status == "closed"
            if not (is_consultant or is_requester_closing):
                raise AccountError("Bu talebi güncelleme yetkiniz yok.")
            current = str(row["status"])
            valid_transition = (
                (is_consultant and current == "sent" and status in {"accepted", "declined"})
                or (current == "accepted" and status == "closed" and (is_consultant or is_requester_closing))
            )
            if not valid_transition:
                raise AccountError("Danışmanlık talebi bu duruma geçirilemez.")
            connection.execute(
                "UPDATE consultation_requests SET status=?,updated_at=? WHERE id=?", (status, _now(), request_id)
            )

    def add_consultation_message(self, user: dict[str, Any], request_id: str, body: str) -> dict[str, Any]:
        body = body.strip()[:2_000]
        if not (2 <= len(body) <= 2_000):
            raise AccountError("Mesaj 2–2.000 karakter olmalıdır.")
        google_sub = str(user["sub"])
        now = _now()
        message_id = str(uuid.uuid4())
        with self._connect() as connection:
            request_row = connection.execute(
                "SELECT requester_sub,consultant_sub,status FROM consultation_requests WHERE id=?", (request_id,)
            ).fetchone()
            if not request_row or google_sub not in {str(request_row["requester_sub"]), str(request_row["consultant_sub"])}:
                raise AccountError("Danışmanlık görüşmesi bulunamadı.")
            if str(request_row["status"]) != "accepted":
                raise AccountError("Mesajlaşma yalnızca kabul edilmiş danışmanlık görüşmesinde kullanılabilir.")
            recent = int(connection.execute(
                "SELECT COUNT(*) FROM consultation_messages WHERE sender_sub=? AND created_at>?",
                (google_sub, now - 86_400),
            ).fetchone()[0])
            if recent >= 100:
                raise AccountError("24 saatlik danışman mesajı sınırına ulaştınız.")
            connection.execute(
                "INSERT INTO consultation_messages(id,request_id,sender_sub,body,created_at) VALUES(?,?,?,?,?)",
                (message_id, request_id, google_sub, body, now),
            )
            connection.execute("UPDATE consultation_requests SET updated_at=? WHERE id=?", (now, request_id))
        return {"id": message_id, "created_at": now}

    def admin_set_consultant_status(self, actor: dict[str, Any], google_sub: str, status: str) -> None:
        if status not in {"pending", "active", "suspended"}:
            raise AccountError("Danışman profili durumu geçersiz.")
        now = _now()
        with self._connect() as connection:
            cursor = connection.execute(
                "UPDATE consultant_profiles SET status=?,updated_at=? WHERE google_sub=?", (status, now, google_sub)
            )
            if cursor.rowcount != 1:
                raise AccountError("Danışman profili bulunamadı.")
            connection.execute(
                "INSERT INTO audit_log(actor_sub,actor_email,action,target_type,target_id,details_json,created_at) VALUES(?,?,?,?,?,?,?)",
                (str(actor.get("sub", "")), str(actor.get("email", "")), "consultant.status", "consultant", google_sub,
                 _json({"status": status}, max_bytes=5_000), now),
            )

    def delete_account(self, user: dict[str, Any]) -> bool:
        with self._connect() as connection:
            cursor = connection.execute("DELETE FROM users WHERE google_sub=?", (str(user["sub"]),))
        return cursor.rowcount > 0


def _stripe_reference(value: Any, prefix: str) -> str:
    reference = str(value.get("id", "") if isinstance(value, dict) else value or "")[:255]
    return reference if reference.startswith(prefix) and reference.replace("_", "").isalnum() else ""


def _stripe_status(value: str) -> str:
    normalized = value.casefold()
    if normalized in {"active", "trialing"}:
        return "active"
    if normalized in {"incomplete", "paused"}:
        return "pending"
    if normalized in {"past_due", "unpaid", "incomplete_expired"}:
        return "past_due"
    if normalized in {"canceled", "cancelled"}:
        return "cancelled"
    return "pending"


def _stripe_period(subscription: dict[str, Any], edge: str) -> int | None:
    direct = subscription.get(f"current_period_{edge}")
    candidates = [direct]
    items = subscription.get("items") if isinstance(subscription.get("items"), dict) else {}
    for item in items.get("data", []) if isinstance(items.get("data"), list) else []:
        if isinstance(item, dict):
            candidates.append(item.get(f"current_period_{edge}"))
    numbers: list[int] = []
    for value in candidates:
        try:
            number = int(value)
        except (TypeError, ValueError):
            continue
        if number > 0:
            numbers.append(number)
    return (min(numbers) if edge == "start" else max(numbers)) if numbers else None


def _stripe_subscription_price(subscription: dict[str, Any]) -> str:
    items = subscription.get("items") if isinstance(subscription.get("items"), dict) else {}
    rows = items.get("data") if isinstance(items.get("data"), list) else []
    if not rows or not isinstance(rows[0], dict):
        return ""
    price = rows[0].get("price")
    return str(price.get("id", "") if isinstance(price, dict) else price or "")


def _stripe_invoice_subscription(invoice: dict[str, Any]) -> str:
    direct = _stripe_reference(invoice.get("subscription"), "sub_")
    if direct:
        return direct
    parent = invoice.get("parent") if isinstance(invoice.get("parent"), dict) else {}
    details = parent.get("subscription_details") if isinstance(parent.get("subscription_details"), dict) else {}
    return _stripe_reference(details.get("subscription"), "sub_")

"""Eylemio (eylemio.com) köprüsü: gümrük otomasyonu konektörüyle beyanname durumu sorgulama.

Eylemio, gümrük müşavirinin BİLGE web servis hesabıyla Ticaret Bakanlığı'ndan gerçek TCGB
(beyanname) detay ve durum bilgisini okuyan bir "ticaret-beyanname" konektörü sunar. Bu modül
Eylemio'ya bir servis hesabıyla oturum açar, o konektör hesabını bulur ve beyanname numarasıyla
okuma yapar. Beyan oluşturmaz, tescil etmez; yalnız okur.

Ortam değişkenleri:
- EYLEMIO_BASE_URL   (varsayılan https://eylemio.com)
- EYLEMIO_EMAIL / EYLEMIO_PASSWORD  – Eylemio'da açılmış servis hesabı
- EYLEMIO_ACCOUNT_ID (isteğe bağlı) – kullanılacak konektör hesabı; boşsa ilk 'ticaret-beyanname'
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import time
from typing import Any

import httpx

logger = logging.getLogger(__name__)

CUSTOMS_CONNECTOR_ID = "ticaret-beyanname"
_DECLARATION_RE = re.compile(r"^[0-9]{2}[0-9A-Z]{2,6}[A-Z]{1,3}[0-9]{6,8}$")


class EylemioError(RuntimeError):
    """Eylemio yapılandırma, oturum veya okuma hatası."""


def normalise_declaration_no(value: str) -> str:
    cleaned = re.sub(r"\s+", "", (value or "")).upper()
    if not cleaned:
        raise EylemioError("Beyanname numarası boş olamaz.")
    if len(cleaned) < 8 or len(cleaned) > 24 or not re.fullmatch(r"[0-9A-Z]+", cleaned):
        raise EylemioError("Beyanname numarası yalnız harf ve rakamdan oluşmalı (ör. 26341300IM000123).")
    return cleaned


class EylemioClient:
    def __init__(
        self,
        base_url: str | None = None,
        email: str | None = None,
        password: str | None = None,
        account_id: str | None = None,
        *,
        http: httpx.AsyncClient | None = None,
    ) -> None:
        self.base_url = (base_url or os.environ.get("EYLEMIO_BASE_URL") or "https://eylemio.com").rstrip("/")
        self.email = email if email is not None else os.environ.get("EYLEMIO_EMAIL", "")
        self.password = password if password is not None else os.environ.get("EYLEMIO_PASSWORD", "")
        self.account_id = account_id if account_id is not None else os.environ.get("EYLEMIO_ACCOUNT_ID", "")
        self._http = http
        self._own_http = http is None
        self._logged_in_at: float = 0.0
        self._lock = asyncio.Lock()
        self._accounts: list[dict[str, Any]] = []

    @property
    def configured(self) -> bool:
        return bool(self.email and self.password)

    def _client(self) -> httpx.AsyncClient:
        if self._http is None:
            self._http = httpx.AsyncClient(base_url=self.base_url, timeout=45.0, headers={"User-Agent": "MevzuatMCP/1.5 (+https://gumruksor.com/)"})
        return self._http

    async def aclose(self) -> None:
        if self._own_http and self._http is not None:
            await self._http.aclose()
            self._http = None

    @staticmethod
    def _json(response: httpx.Response) -> dict[str, Any]:
        try:
            body = response.json()
        except ValueError as exc:
            raise EylemioError(f"Eylemio beklenmeyen yanıt döndürdü (HTTP {response.status_code}).") from exc
        if not isinstance(body, dict):
            raise EylemioError("Eylemio yanıtı nesne değil.")
        return body

    async def _login(self) -> None:
        if not self.configured:
            raise EylemioError("Eylemio bağlantısı yapılandırılmamış: EYLEMIO_EMAIL ve EYLEMIO_PASSWORD gerekli.")
        client = self._client()
        try:
            response = await client.post("/api/auth/login", json={"email": self.email, "password": self.password})
        except httpx.HTTPError as exc:
            raise EylemioError(f"Eylemio'ya ulaşılamadı: {exc}") from exc
        body = self._json(response)
        if response.status_code >= 400 or body.get("success") is False:
            raise EylemioError(body.get("message") or f"Eylemio oturumu açılamadı (HTTP {response.status_code}).")
        self._logged_in_at = time.monotonic()

    async def _ensure_session(self) -> None:
        if time.monotonic() - self._logged_in_at < 20 * 60 and self._logged_in_at:
            return
        await self._login()

    async def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        async with self._lock:
            await self._ensure_session()
            client = self._client()
            try:
                response = await client.request(method, path, **kwargs)
                if response.status_code == 401:
                    await self._login()
                    response = await client.request(method, path, **kwargs)
            except httpx.HTTPError as exc:
                raise EylemioError(f"Eylemio isteği başarısız: {exc}") from exc
        body = self._json(response)
        if response.status_code >= 400 or body.get("success") is False:
            raise EylemioError(body.get("message") or f"Eylemio hata döndürdü (HTTP {response.status_code}).")
        return body

    async def accounts(self, *, refresh: bool = False) -> list[dict[str, Any]]:
        if self._accounts and not refresh:
            return self._accounts
        body = await self._request("GET", "/api/connectors/accounts")
        accounts = body.get("accounts") or body.get("data") or []
        self._accounts = [account for account in accounts if isinstance(account, dict)]
        return self._accounts

    async def customs_account(self) -> dict[str, Any]:
        accounts = await self.accounts()
        if self.account_id:
            for account in accounts:
                if str(account.get("id")) == str(self.account_id):
                    return account
            raise EylemioError(f"Eylemio'da {self.account_id} kimlikli konektör hesabı bulunamadı.")
        for account in accounts:
            if account.get("connectorId") == CUSTOMS_CONNECTOR_ID:
                return account
        raise EylemioError("Eylemio hesabında 'Gümrük (Ticaret Bakanlığı beyanname)' konektörü tanımlı değil; Eylemio → Bağlantılar'dan BİLGE web servis hesabını ekleyin.")

    async def declaration_status(self, declaration_no: str) -> dict[str, Any]:
        """Beyanname numarasına göre TCGB detay/durum bilgisini okur (salt okunur)."""
        number = normalise_declaration_no(declaration_no)
        account = await self.customs_account()
        body = await self._request("POST", f"/api/connectors/accounts/{account.get('id')}/read", json={"beyannameNo": number})
        payload = body.get("data") if isinstance(body.get("data"), dict) else body.get("result") if isinstance(body.get("result"), dict) else {}
        return {
            "declaration_no": number,
            "account": {"id": account.get("id"), "name": account.get("name") or account.get("label") or "", "connector": account.get("connectorId")},
            "message": body.get("message", ""),
            "data": payload or {key: value for key, value in body.items() if key not in {"success", "message"}},
            "source": "Eylemio – Ticaret Bakanlığı BİLGE web servisi (salt okunur)",
            "fetched_at": time.time(),
        }

    async def health(self) -> dict[str, Any]:
        client = self._client()
        try:
            response = await client.get("/api/health")
        except httpx.HTTPError as exc:
            return {"reachable": False, "configured": self.configured, "error": str(exc)}
        try:
            body = response.json()
        except ValueError:
            body = {}
        return {
            "reachable": response.status_code == 200,
            "configured": self.configured,
            "base_url": self.base_url,
            "service": body.get("service"),
            "status": body.get("status"),
        }


def summarise_declaration(result: dict[str, Any]) -> list[tuple[str, str]]:
    """Konektör çıktısındaki sık kullanılan alanları etiket/değer çiftlerine indirger."""
    data = result.get("data") or {}
    aliases = {
        "beyannameNo": "Beyanname no", "tescilNo": "Tescil no", "tescilTarihi": "Tescil tarihi", "durum": "Durum",
        "status": "Durum", "statu": "Durum", "gumrukIdaresi": "Gümrük idaresi", "rejim": "Rejim", "hatKodu": "Hat",
        "muayeneMemuru": "Muayene memuru", "kapanmaTarihi": "Kapanma tarihi", "toplamVergi": "Toplam vergi",
        "mukellef": "Mükellef", "vergiNo": "Vergi no", "kalemSayisi": "Kalem sayısı", "aciklama": "Açıklama",
    }
    pairs: list[tuple[str, str]] = []
    for key, label in aliases.items():
        if key in data and data[key] not in (None, "", [], {}):
            pairs.append((label, str(data[key])))
    if not pairs:
        for key, value in list(data.items())[:12]:
            if isinstance(value, (str, int, float)) and str(value):
                pairs.append((str(key), str(value)))
    return pairs

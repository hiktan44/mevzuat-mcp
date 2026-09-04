"""Transactional e-mail delivery for the customs dossier (HTTP e-posta API).

The delivery provider stays server-side; end-user surfaces only ever say
"e-posta". Emails are rendered here from the validated dossier structure so no
client-supplied HTML ever reaches the message body.
"""
from __future__ import annotations

import html
import logging
import os
from typing import Any

import httpx
from customs_advisor import CustomsPrecheckResult

logger = logging.getLogger(__name__)
_SEND_ENDPOINT = "https://api.resend.com/emails"


class MailError(Exception):
    """Raised when the message cannot be delivered; the message is user-safe."""


def _esc(value: Any) -> str:
    return html.escape(str(value if value is not None else ""))


def render_precheck_email(result: CustomsPrecheckResult, base_url: str) -> str:
    """Render the dossier as a compact, inline-styled HTML e-mail."""
    rows: list[str] = []
    if result.tariff_lookup is not None:
        safe = result.tariff_lookup.unambiguous_rates or {}
        if safe:
            rate_rows = "".join(
                f"<tr><td style='padding:4px 10px;border:1px solid #d6dee8;'>{_esc(label)}</td>"
                f"<td style='padding:4px 10px;border:1px solid #d6dee8;'>%{_esc(value)}</td></tr>"
                for label, value in (
                    ("Gümrük vergisi", safe.get("customs_duty")),
                    ("İlave gümrük vergisi (İGV)", safe.get("additional_duty")),
                    ("Ek mali yükümlülük", safe.get("additional_financial_liability")),
                )
                if value is not None
            )
            if rate_rows:
                rows.append(
                    "<h3 style='margin:14px 0 6px;font-size:15px;'>Resmî tarife oranları</h3>"
                    f"<table style='border-collapse:collapse;font-size:13px;'>{rate_rows}</table>"
                    f"<p style='margin:4px 0 0;font-size:12px;color:#43536c;'>Kod: {_esc(result.tariff_lookup.gtip)}"
                    f"{f' · menşe: {_esc(result.tariff_lookup.origin_country)}' if result.tariff_lookup.origin_country else ''}</p>"
                )
    if result.origin_documents is not None:
        docs = "".join(f"<li>{_esc(item.name)}</li>" for item in result.origin_documents.documents)
        rows.append(
            f"<h3 style='margin:14px 0 6px;font-size:15px;'>Menşe belgeleri · {_esc(result.origin_documents.regime_name)}</h3>"
            f"<ul style='margin:4px 0 0;padding-left:18px;font-size:13px;'>{docs}</ul>"
        )
    if result.missing_information:
        missing = "".join(f"<li>{_esc(item)}</li>" for item in result.missing_information[:8])
        rows.append(
            f"<h3 style='margin:14px 0 6px;font-size:15px;'>Eksik veya teyit gereken bilgiler</h3>"
            f"<ul style='margin:4px 0 0;padding-left:18px;font-size:13px;'>{missing}</ul>"
        )
    sources = "".join(
        f"<li style='margin:3px 0;'><a href='{_esc(source.url)}' style='color:#006678;'>{_esc(source.title)}</a>"
        f"{f' · {_esc(source.authority)}' if source.authority else ''}</li>"
        for source in result.sources[:12]
        if source.url
    )
    if sources:
        rows.append(
            "<h3 style='margin:14px 0 6px;font-size:15px;'>Resmî kaynaklar</h3>"
            f"<ul style='margin:4px 0 0;padding-left:18px;font-size:12px;'>{sources}</ul>"
        )
    return f"""<div style="font-family:Arial,Helvetica,sans-serif;color:#0b1e3f;max-width:640px;">
  <p style="margin:0 0 4px;font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:#006678;">Ticaret Bilgi Masası · İthalat ön değerlendirme dosyası</p>
  <h2 style="margin:0 0 8px;font-size:19px;">{_esc(result.summary)}</h2>
  <p style="margin:0 0 10px;font-size:12px;color:#43536c;">Durum: {_esc(result.status)} · {_esc(result.as_of)}</p>
  {''.join(rows)}
  <div style="margin:16px 0;padding:10px 12px;border-left:3px solid #b54708;background:#fff7ed;font-size:12px;">{_esc(result.legal_notice)}</div>
  <p style="margin:8px 0 0;font-size:11px;color:#738097;">Bu e-posta {_esc(base_url)} üzerinden oluşturulan ön değerlendirme dosyasıyla gönderilmiştir; bağlayıcı tarife bilgisi değildir.</p>
</div>"""


class ResendEmailSender:
    """Small async client for the transactional e-mail HTTP API."""

    def __init__(self) -> None:
        self._api_key = os.environ.get("RESEND_API_KEY", "").strip()
        self._from = os.environ.get("MAIL_FROM", "").strip()
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(20)) if self.configured else None

    @property
    def configured(self) -> bool:
        return bool(self._api_key) and bool(self._from)

    async def send(self, *, to: str, subject: str, html_body: str) -> str:
        if not self.configured or self._client is None:
            raise MailError("E-posta gönderimi henüz yapılandırılmadı.")
        try:
            response = await self._client.post(
                _SEND_ENDPOINT,
                json={"from": self._from, "to": [to], "subject": subject, "html": html_body},
                headers={"Authorization": f"Bearer {self._api_key}"},
            )
        except httpx.HTTPError as exc:
            logger.warning("E-mail delivery request failed: %s", exc)
            raise MailError("E-posta servisine şu anda ulaşılamadı.") from exc
        if response.status_code >= 400:
            logger.warning("E-mail delivery rejected: %s %s", response.status_code, response.text[:200])
            raise MailError("E-posta gönderilemedi; ayarları kontrol edin.")
        message_id = ""
        try:
            message_id = str(response.json().get("id", ""))
        except Exception:
            pass
        return message_id

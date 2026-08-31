"""Application-level security boundary for agent and LLM interactions.

The module intentionally has no framework dependency so the same controls can be
used by the web API, MCP tools, source collectors, and tests.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import ipaddress
import json
import os
import re
import time
import unicodedata
from dataclasses import dataclass
from typing import Any, Iterable
from urllib.parse import urlsplit


class SecurityViolation(ValueError):
    """Raised when untrusted content crosses an explicit security boundary."""

    def __init__(self, message: str, *, code: str = "security_policy") -> None:
        super().__init__(message)
        self.code = code


def _normalise(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.casefold().replace("ı", "i"))
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


_INJECTION_PATTERNS = (
    re.compile(r"\b(?:ignore|disregard|forget)\b.{0,50}\b(?:previous|prior|system|developer)\b.{0,30}\b(?:instruction|prompt|message)s?\b", re.I | re.S),
    re.compile(r"\b(?:onceki|sistem|gelistirici)\b.{0,45}\b(?:talimat|mesaj|prompt)(?:lari|larini|ini)?\b.{0,30}\b(?:yok\s*say|unut|ifsa|goster)", re.I | re.S),
    re.compile(r"\b(?:reveal|print|show|expose)\b.{0,40}\b(?:system prompt|developer message|hidden instruction|secret|api key)\b", re.I | re.S),
    re.compile(r"\b(?:act as|you are now|roleplay as)\b.{0,30}\b(?:system|developer|administrator|root)\b", re.I | re.S),
    re.compile(r"\b(?:call|invoke|execute|run)\b.{0,30}\b(?:tool|function|shell|terminal|command)\b", re.I | re.S),
    re.compile(r"\b(?:send|upload|exfiltrate)\b.{0,60}\b(?:secret|credential|token|environment variable|private key)\b", re.I | re.S),
)


def guard_text(value: str, *, source: str = "user", max_chars: int = 20_000) -> str:
    """Reject high-confidence prompt injection without blocking normal trade queries."""
    text = str(value or "").strip()
    if len(text) > max_chars:
        raise SecurityViolation("Metin güvenli işleme sınırını aşıyor.", code="input_too_large")
    normalised = _normalise(text)
    if any(pattern.search(normalised) for pattern in _INJECTION_PATTERNS):
        raise SecurityViolation(
            f"{source.capitalize()} metninde görev talimatlarını değiştirmeye çalışan bir ifade algılandı.",
            code="prompt_injection",
        )
    return text


def guard_data(value: Any, *, path: str = "istek") -> None:
    """Recursively scan a JSON-compatible request before it reaches an agent/model."""
    if isinstance(value, str):
        guard_text(value, source=path, max_chars=20_000)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            guard_data(item, path=f"{path}[{index}]")
    elif isinstance(value, dict):
        for key, item in value.items():
            guard_data(item, path=f"{path}.{key}")


def sanitize_untrusted_context(value: str, *, max_chars: int = 120_000) -> tuple[str, bool]:
    """Quarantine instruction-like sentences in retrieved pages before LLM use."""
    text = str(value or "")[:max_chars]
    changed = False
    safe_parts: list[str] = []
    for part in re.split(r"(?<=[.!?])\s+|[\r\n]+", text):
        if not part.strip():
            continue
        try:
            guard_text(part, source="haricî kaynak", max_chars=8_000)
        except SecurityViolation:
            safe_parts.append("[Güvenlik nedeniyle talimat benzeri kaynak bölümü çıkarıldı]")
            changed = True
        else:
            safe_parts.append(part.strip())
    return " ".join(safe_parts), changed


_SECRET_PATTERNS = (
    (re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"), "[API_ANAHTARI_GİZLENDİ]"),
    (re.compile(r"\bAIza[0-9A-Za-z_-]{20,}\b"), "[API_ANAHTARI_GİZLENDİ]"),
    (re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/-]{16,}=*"), "Bearer [ERİŞİM_BELİTECİ_GİZLENDİ]"),
    (re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----[\s\S]*?-----END (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"), "[ÖZEL_ANAHTAR_GİZLENDİ]"),
    (re.compile(r"(?i)\b(?:api[_-]?key|access[_-]?token|client[_-]?secret)\s*[:=]\s*['\"]?([^\s'\"]{8,})"), "[GİZLİ_DEĞER_GİZLENDİ]"),
)
_TCKN_RE = re.compile(r"(?<!\d)([1-9]\d{10})(?!\d)")
_CARD_RE = re.compile(r"(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)")
_EMAIL_RE = re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")
_PHONE_RE = re.compile(r"(?<!\d)(?:\+?90[ -]?)?(?:0?[2-5]\d{2})[ -]?\d{3}[ -]?\d{2}[ -]?\d{2}(?!\d)")


def _luhn(value: str) -> bool:
    digits = [int(ch) for ch in value if ch.isdigit()]
    if not 13 <= len(digits) <= 19:
        return False
    checksum = 0
    parity = len(digits) % 2
    for index, digit in enumerate(digits):
        if index % 2 == parity:
            digit *= 2
            if digit > 9:
                digit -= 9
        checksum += digit
    return checksum % 10 == 0


def redact_text(value: str, *, contact_data: bool = True) -> str:
    """Remove secrets and personal data before sending content to a model provider."""
    text = str(value or "")
    for pattern, replacement in _SECRET_PATTERNS:
        text = pattern.sub(replacement, text)
    text = _TCKN_RE.sub("[TCKN_GİZLENDİ]", text)
    text = _CARD_RE.sub(lambda match: "[KART_GİZLENDİ]" if _luhn(match.group(0)) else match.group(0), text)
    if contact_data:
        text = _EMAIL_RE.sub("[E-POSTA_GİZLENDİ]", text)
        text = _PHONE_RE.sub("[TELEFON_GİZLENDİ]", text)
    return text


def redact_data(value: Any, *, contact_data: bool = True) -> Any:
    """Recursively redact a JSON-compatible structure."""
    if isinstance(value, str):
        return redact_text(value, contact_data=contact_data)
    if isinstance(value, list):
        return [redact_data(item, contact_data=contact_data) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_data(item, contact_data=contact_data) for item in value)
    if isinstance(value, dict):
        return {key: redact_data(item, contact_data=contact_data) for key, item in value.items()}
    return value


_METADATA_HOSTS = {"169.254.169.254", "metadata.google.internal", "metadata.azure.internal"}


def validate_outbound_url(url: str, *, allowed_hosts: Iterable[str]) -> str:
    """Allow HTTPS only to an exact host/subdomain allow-list and block metadata IPs."""
    parsed = urlsplit(str(url or ""))
    host = (parsed.hostname or "").lower().rstrip(".")
    if parsed.scheme != "https" or not host or parsed.username or parsed.password:
        raise SecurityViolation("Dış bağlantı yalnızca kimlik bilgisi içermeyen HTTPS adresi olabilir.", code="unsafe_url")
    if host in _METADATA_HOSTS or host == "localhost":
        raise SecurityViolation("Sunucu meta veri veya yerel ağ adresine erişim engellendi.", code="ssrf_blocked")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = None
    if address and not address.is_global:
        raise SecurityViolation("Özel, yerel veya ayrılmış ağ adresine erişim engellendi.", code="ssrf_blocked")
    allowed = {item.lower().rstrip(".") for item in allowed_hosts}
    if not any(host == item or host.endswith(f".{item}") for item in allowed):
        raise SecurityViolation("Dış bağlantı izin verilen resmî kaynaklar arasında değil.", code="egress_denied")
    return url


def require_object_owner(caller_id: str, owner_id: str) -> None:
    """Fail closed for future user-owned objects (BOLA/IDOR boundary)."""
    if not caller_id or not owner_id or not hmac.compare_digest(str(caller_id), str(owner_id)):
        raise SecurityViolation("Bu kaynağa erişim yetkiniz yok.", code="object_access_denied")


def _b64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _b64url_decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


@dataclass(frozen=True)
class AgentIdentity:
    subject: str
    audience: str
    actor: str | None
    issued_at: int
    expires_at: int


class AgentTokenVerifier:
    """Small HS256 verifier with audience and freshness checks for agent-to-tool calls."""

    def __init__(self, secret: str | None = None, *, audience: str = "ticaret-mcp", max_age_seconds: int = 300) -> None:
        self.secret = (secret if secret is not None else os.environ.get("AGENT_GATEWAY_SECRET", "")).encode("utf-8")
        self.audience = audience
        self.max_age_seconds = max(30, min(max_age_seconds, 900))

    @property
    def configured(self) -> bool:
        return len(self.secret) >= 32

    def issue(self, subject: str, *, actor: str | None = None, lifetime_seconds: int = 180, now: int | None = None) -> str:
        if not self.configured:
            raise SecurityViolation("Ajan kimlik sırrı yapılandırılmadı.", code="identity_not_configured")
        issued = int(time.time() if now is None else now)
        header = {"alg": "HS256", "typ": "JWT"}
        payload = {"sub": subject, "aud": self.audience, "iat": issued, "exp": issued + min(lifetime_seconds, self.max_age_seconds)}
        if actor:
            payload["act"] = actor
        signing_input = f"{_b64url(json.dumps(header, separators=(',', ':')).encode())}.{_b64url(json.dumps(payload, separators=(',', ':')).encode())}"
        signature = hmac.new(self.secret, signing_input.encode("ascii"), hashlib.sha256).digest()
        return f"{signing_input}.{_b64url(signature)}"

    def verify(self, token: str, *, now: int | None = None) -> AgentIdentity:
        if not self.configured:
            raise SecurityViolation("Ajan kimlik doğrulaması yapılandırılmadı.", code="identity_not_configured")
        try:
            encoded_header, encoded_payload, encoded_signature = token.split(".")
            signing_input = f"{encoded_header}.{encoded_payload}"
            expected = hmac.new(self.secret, signing_input.encode("ascii"), hashlib.sha256).digest()
            supplied = _b64url_decode(encoded_signature)
            if not hmac.compare_digest(expected, supplied):
                raise ValueError("signature")
            header = json.loads(_b64url_decode(encoded_header))
            payload = json.loads(_b64url_decode(encoded_payload))
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            raise SecurityViolation("Ajan kimlik belirteci doğrulanamadı.", code="invalid_agent_token") from exc
        current = int(time.time() if now is None else now)
        issued = int(payload.get("iat", 0))
        expires = int(payload.get("exp", 0))
        subject = str(payload.get("sub", ""))
        audience = str(payload.get("aud", ""))
        if header.get("alg") != "HS256" or not subject or audience != self.audience:
            raise SecurityViolation("Ajan kimliği bu hizmet için geçerli değil.", code="invalid_agent_audience")
        if issued > current + 30 or current - issued > self.max_age_seconds or expires <= current or expires > issued + self.max_age_seconds:
            raise SecurityViolation("Ajan kimlik belirtecinin süresi veya tazeliği geçersiz.", code="stale_agent_token")
        return AgentIdentity(subject, audience, str(payload.get("act")) if payload.get("act") else None, issued, expires)

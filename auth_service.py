"""Small Google OAuth and signed-session service for the public web application."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import httpx


class AuthError(ValueError):
    """Raised when an OAuth response or signed token cannot be trusted."""


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _b64decode(value: str) -> bytes:
    if not value or any(character not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_" for character in value):
        raise ValueError("Geçersiz base64url değeri.")
    decoded = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    if not hmac.compare_digest(_b64encode(decoded), value):
        raise ValueError("Kanonik olmayan base64url değeri.")
    return decoded


class GoogleAuthService:
    session_cookie = "tbm_session"
    state_cookie = "tbm_oauth_state"

    def __init__(
        self,
        *,
        client_id: str | None = None,
        client_secret: str | None = None,
        session_secret: str | None = None,
        data_dir: str | Path | None = None,
        session_ttl_seconds: int = 30 * 24 * 60 * 60,
    ) -> None:
        self.client_id = (client_id if client_id is not None else os.environ.get("GOOGLE_CLIENT_ID", "")).strip()
        self.client_secret = (
            client_secret if client_secret is not None else os.environ.get("GOOGLE_CLIENT_SECRET", "")
        ).strip()
        self.session_secret = (
            session_secret if session_secret is not None else os.environ.get("AUTH_SESSION_SECRET", "")
        ).encode("utf-8")
        default_data_dir = os.environ.get(
            "MEVZUAT_DATA_DIR",
            str(Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "mevzuat-mcp"),
        )
        self.data_dir = Path(data_dir or default_data_dir)
        self.session_ttl_seconds = session_ttl_seconds

    @property
    def configured(self) -> bool:
        return bool(self.client_id and self.client_secret and len(self.session_secret) >= 32)

    def _sign(self, payload: dict[str, Any], *, purpose: str) -> str:
        if len(self.session_secret) < 32:
            raise AuthError("Oturum anahtarı yapılandırılmamış.")
        body = _b64encode(json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))
        signature = hmac.new(self.session_secret, f"{purpose}.{body}".encode("ascii"), hashlib.sha256).digest()
        return f"{body}.{_b64encode(signature)}"

    def _verify(self, token: str, *, purpose: str) -> dict[str, Any]:
        if len(token) > 8192 or "." not in token or len(self.session_secret) < 32:
            raise AuthError("Geçersiz oturum bilgisi.")
        body, supplied_signature = token.rsplit(".", 1)
        expected = hmac.new(self.session_secret, f"{purpose}.{body}".encode("ascii"), hashlib.sha256).digest()
        try:
            supplied = _b64decode(supplied_signature)
            payload = json.loads(_b64decode(body).decode("utf-8"))
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise AuthError("Geçersiz oturum bilgisi.") from exc
        if not hmac.compare_digest(expected, supplied):
            raise AuthError("Oturum imzası doğrulanamadı.")
        if not isinstance(payload, dict) or int(payload.get("exp", 0)) < int(time.time()):
            raise AuthError("Oturumun süresi doldu.")
        return payload

    def create_oauth_state(self) -> tuple[str, str]:
        nonce = secrets.token_urlsafe(24)
        now = int(time.time())
        token = self._sign(
            {"state": secrets.token_urlsafe(24), "nonce": nonce, "iat": now, "exp": now + 600},
            purpose="google-oauth-state",
        )
        return token, nonce

    def verify_oauth_state(self, token: str) -> dict[str, Any]:
        return self._verify(token, purpose="google-oauth-state")

    def authorization_url(self, *, redirect_uri: str, state: str, nonce: str) -> str:
        if not self.configured:
            raise AuthError("Google girişi yapılandırılmamış.")
        query = urlencode(
            {
                "client_id": self.client_id,
                "redirect_uri": redirect_uri,
                "response_type": "code",
                "scope": "openid email profile",
                "state": state,
                "nonce": nonce,
                "prompt": "select_account",
                "access_type": "online",
            }
        )
        return f"https://accounts.google.com/o/oauth2/v2/auth?{query}"

    async def exchange_code(self, *, code: str, redirect_uri: str, expected_nonce: str) -> dict[str, str]:
        if not self.configured or not code or len(code) > 4096:
            raise AuthError("Google giriş yanıtı geçersiz.")
        async with httpx.AsyncClient(timeout=20.0) as client:
            token_response = await client.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "code": code,
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "redirect_uri": redirect_uri,
                    "grant_type": "authorization_code",
                },
            )
            if token_response.status_code != 200:
                raise AuthError("Google oturumu başlatılamadı.")
            id_token = str(token_response.json().get("id_token", ""))
            if not id_token:
                raise AuthError("Google kimlik bilgisi alınamadı.")
            profile_response = await client.get(
                "https://oauth2.googleapis.com/tokeninfo",
                params={"id_token": id_token},
            )
            if profile_response.status_code != 200:
                raise AuthError("Google kimliği doğrulanamadı.")
            claims = profile_response.json()

        issuer = str(claims.get("iss", ""))
        if str(claims.get("aud", "")) != self.client_id:
            raise AuthError("Google istemci kimliği eşleşmedi.")
        if issuer not in {"accounts.google.com", "https://accounts.google.com"}:
            raise AuthError("Google kimlik sağlayıcısı doğrulanamadı.")
        if str(claims.get("email_verified", "")).lower() != "true":
            raise AuthError("Google e-posta adresi doğrulanmamış.")
        if expected_nonce and not hmac.compare_digest(str(claims.get("nonce", "")), expected_nonce):
            raise AuthError("Google giriş isteği doğrulanamadı.")
        try:
            if int(claims.get("exp", 0)) < int(time.time()):
                raise AuthError("Google kimlik bilgisinin süresi doldu.")
        except (TypeError, ValueError) as exc:
            raise AuthError("Google kimlik süresi doğrulanamadı.") from exc

        profile = {
            "sub": str(claims.get("sub", ""))[:255],
            "email": str(claims.get("email", ""))[:320],
            "name": str(claims.get("name", ""))[:200],
            "picture": str(claims.get("picture", ""))[:1000],
        }
        if not profile["sub"] or not profile["email"]:
            raise AuthError("Google hesap bilgisi eksik.")
        return profile

    def create_session(self, profile: dict[str, str]) -> str:
        now = int(time.time())
        return self._sign(
            {
                "sub": profile.get("sub", "")[:255],
                "email": profile.get("email", "")[:320],
                "name": profile.get("name", "")[:200],
                "picture": profile.get("picture", "")[:1000],
                "iat": now,
                "exp": now + self.session_ttl_seconds,
            },
            purpose="web-session",
        )

    def parse_session(self, token: str) -> dict[str, Any]:
        return self._verify(token, purpose="web-session")

    def upsert_user(self, profile: dict[str, str]) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.data_dir.chmod(0o700)
        database_path = self.data_dir / "users.sqlite3"
        now = int(time.time())
        with sqlite3.connect(database_path, timeout=5.0) as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    google_sub TEXT PRIMARY KEY,
                    email TEXT NOT NULL,
                    name TEXT NOT NULL DEFAULT '',
                    picture TEXT NOT NULL DEFAULT '',
                    created_at INTEGER NOT NULL,
                    last_login_at INTEGER NOT NULL
                )
                """
            )
            connection.execute(
                """
                INSERT INTO users (google_sub, email, name, picture, created_at, last_login_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(google_sub) DO UPDATE SET
                    email=excluded.email,
                    name=excluded.name,
                    picture=excluded.picture,
                    last_login_at=excluded.last_login_at
                """,
                (
                    profile["sub"], profile["email"], profile.get("name", ""),
                    profile.get("picture", ""), now, now,
                ),
            )
        database_path.chmod(0o600)

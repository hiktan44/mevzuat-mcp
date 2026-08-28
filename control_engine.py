"""Versioned import-control scope engine backed by official consolidated texts.

The engine indexes GTIP annexes from the Ministry of Justice's official
Bedesten legislation service.  It deliberately separates three concepts:

* appearing in a communique annex (scope signal),
* being processed in TAREKS or by another competent authority, and
* being selected for physical inspection or laboratory testing.

The last item is normally decided by the authority's risk analysis.  It is
therefore never inferred merely from a GTIP match.
"""

from __future__ import annotations

import asyncio
import hashlib
import html
import io
import json
import os
import re
import sqlite3
import time
import unicodedata
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urljoin, urlsplit

import httpx
import openpyxl
import xlrd
from markitdown import MarkItDown
from pydantic import BaseModel, Field

from bedesten_client import BedestenClient

_CODE_RE = re.compile(
    r"(?<!\d)(\d{4}(?:[.\t ]\d{2}){1,4}|\d{2}(?:[.\t ]\d{2}){1,5}|\d{4})(?!\d)"
)
_NEXT_ANNEX_RE = re.compile(r"(?im)^\s*Ek\s*[-–]?\s*[2-9]\b")
_DOCUMENT_HEADING_RE = re.compile(
    r"(?i)(YÜKLENMESİ\s+GEREKEN\s+BELGELER|İBRAZ\s+EDİLECEK\s+BELGELER|BELGELER\s+VE\s+MUAFİYETLER)"
)


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _key(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or "").casefold().replace("ı", "i"))
    return "".join(ch for ch in text if not unicodedata.combining(ch))


def _normalise_gtip(value: Any) -> str | None:
    digits = re.sub(r"\D", "", str(value or ""))
    if len(digits) in {4, 6, 8, 10, 12}:
        return digits
    return None


class ControlScopeRow(BaseModel):
    gtip_prefix: str
    description: str | None = None
    source_line: str
    source_offset: int
    excluded: bool = False


class ImportControlRule(BaseModel):
    code: str
    title: str
    category: str
    authority: str
    system: str
    risk_based: bool
    physical_inspection_possible: bool
    laboratory_test_possible: bool
    required_documents_excerpt: str | None = None
    scope_count: int
    mevzuat_id: str
    source_url: str
    official_gazette_date: str | None = None
    official_gazette_number: str | None = None
    document_sha256: str
    retrieved_at: str
    valid_from: str
    snapshot_id: str


class ImportControlMatch(BaseModel):
    rule: ImportControlRule
    matched_scope: ControlScopeRow
    match_type: Literal["exact", "prefix"]
    assessment: str
    cautions: list[str] = Field(default_factory=list)


class ImportControlLookupResult(BaseModel):
    status: Literal["matched", "not_found", "unavailable"]
    gtip: str
    matches: list[ImportControlMatch] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    as_of: str


class ControlSnapshot(BaseModel):
    id: str
    code: str
    title: str
    mevzuat_id: str
    document_sha256: str
    retrieved_at: str
    valid_from: str
    scope_count: int
    active: bool


class ControlSyncStatus(BaseModel):
    ready: bool
    syncing: bool
    last_checked_at: str | None = None
    active_snapshots: list[ControlSnapshot] = Field(default_factory=list)
    scope_count: int = 0
    errors: list[str] = Field(default_factory=list)
    sync_interval_seconds: int


def _scope_rows_from_segment(segment: str) -> list[ControlScopeRow]:
    """Parse GTIP/GTP codes and their adjacent descriptions from one table."""
    matches = list(_CODE_RE.finditer(segment))
    rows: list[ControlScopeRow] = []
    seen: set[str] = set()
    for index, match in enumerate(matches):
        code = _normalise_gtip(match.group(1))
        if not code or code in seen:
            continue
        # Four-digit years are common in footnotes; genuine four-digit tariff
        # headings are dotted or appear after a GTIP/GTP column heading.
        before = segment[max(0, match.start() - 300) : match.start()]
        before_key = _key(before)
        if len(code) == 4 and "gtip" not in before_key and "gtp" not in before_key and "." not in match.group(1):
            continue
        next_start = matches[index + 1].start() if index + 1 < len(matches) else match.end() + 500
        raw_description = segment[match.end() : min(next_start, match.end() + 500)]
        description = re.sub(r"\s+", " ", raw_description).strip(" \n\t-–:;.,")
        source_line = re.sub(r"\s+", " ", segment[match.start() : min(next_start, match.end() + 500)]).strip()
        before_context = segment[max(0, match.start() - 250) : match.start()]
        after_context = segment[match.end() : min(len(segment), match.end() + 350)]
        open_paren = before_context.rfind("(")
        close_before = before_context.rfind(")")
        close_paren = after_context.find(")")
        parenthetical = (
            before_context[open_paren:] + after_context[: close_paren + 1]
            if open_paren > close_before and close_paren >= 0
            else ""
        )
        excluded = "haric" in _key(parenthetical)
        seen.add(code)
        rows.append(
            ControlScopeRow(
                gtip_prefix=code,
                description=description[:400] or None,
                source_line=source_line[:600],
                source_offset=match.start(),
                excluded=excluded,
            )
        )
    return rows


def extract_annex_scope(text: str, annex_number: int = 1) -> list[ControlScopeRow]:
    """Return GTIP rows from the most code-dense requested annex section.

    Earlier references such as "Ek-1'de" occur in the body. Scoring every
    candidate and cutting at the next annex avoids treating those references,
    dates or article numbers as scope rows. Some annual communiques put the
    actual GTIP table in Ek-2, so the annex number is source-configurable.
    """
    if annex_number < 1 or annex_number > 9:
        raise ValueError("Ek numarası 1 ile 9 arasında olmalıdır.")
    annex_re = re.compile(rf"(?im)^\s*Ek\s*[-–]?\s*{annex_number}\b")
    other_numbers = "|".join(str(value) for value in range(1, 10) if value != annex_number)
    next_annex_re = re.compile(rf"(?im)^\s*Ek\s*[-–]?\s*(?:{other_numbers})\b")
    candidates: list[tuple[int, str]] = []
    for match in annex_re.finditer(text):
        tail = text[match.start() :]
        end = next_annex_re.search(tail[match.end() - match.start() :])
        segment_end = (match.end() - match.start()) + end.start() if end else len(tail)
        segment = tail[:segment_end]
        score = len(_CODE_RE.findall(segment))
        candidates.append((score, segment))
    if not candidates:
        return []
    _, segment = max(candidates, key=lambda item: item[0])
    if len(_CODE_RE.findall(segment)) < 1:
        return []

    return _scope_rows_from_segment(segment)


def extract_scope_table(text: str, start_pattern: str, end_pattern: str) -> list[ControlScopeRow]:
    """Parse an inline GTIP/GTP table bounded by explicit official headings."""
    start = re.search(start_pattern, text, flags=re.IGNORECASE | re.MULTILINE)
    if not start:
        return []
    tail = text[start.start() :]
    end = re.search(end_pattern, tail[start.end() - start.start() :], flags=re.IGNORECASE | re.MULTILINE)
    segment_end = (start.end() - start.start()) + end.start() if end else len(tail)
    return _scope_rows_from_segment(tail[:segment_end])


def _dedupe_scope(rows: list[ControlScopeRow]) -> list[ControlScopeRow]:
    result: list[ControlScopeRow] = []
    seen: set[str] = set()
    for row in rows:
        if row.gtip_prefix in seen:
            continue
        seen.add(row.gtip_prefix)
        result.append(row)
    return result


def _tabular_bytes_to_text(data: bytes, extension: str) -> str:
    lines: list[str] = []
    if extension == ".xlsx":
        workbook = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
        for sheet in workbook.worksheets:
            lines.append(f"SAYFA {sheet.title}")
            for row in sheet.iter_rows(values_only=True):
                values = [str(value).strip() for value in row if value not in (None, "")]
                if values:
                    lines.append("\t".join(values))
        workbook.close()
    elif extension == ".xls":
        workbook = xlrd.open_workbook(file_contents=data)
        for sheet in workbook.sheets():
            lines.append(f"SAYFA {sheet.name}")
            for row_index in range(sheet.nrows):
                values = [str(value).strip() for value in sheet.row_values(row_index) if value not in (None, "")]
                if values:
                    lines.append("\t".join(values))
    return "\n".join(lines)


def extract_attachment_scope(data: bytes, converter: MarkItDown | None = None) -> list[ControlScopeRow]:
    """Extract tariff rows from an official annex ZIP without trusting filenames."""
    if len(data) > 50 * 1024 * 1024:
        raise ValueError("Resmî ek arşivi 50 MB güvenlik sınırını aşıyor.")
    rows: list[ControlScopeRow] = []
    converter = converter or MarkItDown()
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        total_uncompressed = sum(item.file_size for item in archive.infolist() if not item.is_dir())
        if total_uncompressed > 150 * 1024 * 1024:
            raise ValueError("Resmî ek arşivinin açılmış boyutu güvenlik sınırını aşıyor.")
        for item in archive.infolist():
            if item.is_dir() or item.file_size > 50 * 1024 * 1024:
                continue
            extension = Path(item.filename).suffix.casefold()
            member = archive.read(item)
            if extension in {".xlsx", ".xls"}:
                text = _tabular_bytes_to_text(member, extension)
            elif extension in {".docx", ".pdf"}:
                converted = converter.convert_stream(io.BytesIO(member), file_extension=extension)
                text = converted.text_content
            elif extension in {".csv", ".txt", ".htm", ".html"}:
                text = member.decode("utf-8", errors="replace")
            else:
                continue
            rows.extend(_scope_rows_from_segment(text))
    return _dedupe_scope(rows)


def extract_required_documents(text: str) -> str | None:
    matches = list(_DOCUMENT_HEADING_RE.finditer(text))
    if not matches:
        return None
    # Annex document lists are normally near the end; prefer the last heading.
    start = matches[-1].start()
    tail = text[start : start + 5000]
    next_annex = _NEXT_ANNEX_RE.search(tail[matches[-1].end() - start :])
    if next_annex:
        tail = tail[: (matches[-1].end() - start) + next_annex.start()]
    return re.sub(r"\s+", " ", tail).strip()[:3000] or None


def infer_process(text: str, title: str) -> dict[str, Any]:
    normal = _key(text)
    title_key = _key(title)
    tareks = "tareks" in normal
    risk_based = "risk analizi" in normal or "risk analizine gore" in normal
    physical = "fiili denetim" in normal or "fiziki muayene" in normal
    lab = "laboratuvar" in normal or "test raporu" in normal

    if tareks:
        system = "TAREKS"
    elif "tarim ve orman" in title_key:
        system = "Tarım ve Orman Bakanlığı kontrol sistemi"
    elif "saglik bakan" in title_key or "tibbi cihaz" in title_key:
        system = "Sağlık Bakanlığı kontrol sistemi"
    elif "cevre" in title_key:
        system = "Çevre, Şehircilik ve İklim Değişikliği Bakanlığı izin/kontrol süreci"
    else:
        system = "Yetkili kurum/gümrük kontrol süreci"

    if "tse" in normal:
        authority = "Türk Standardları Enstitüsü (denetim birimi)"
    elif "tarim ve orman" in title_key:
        authority = "Tarım ve Orman Bakanlığı"
    elif "saglik bakan" in title_key or "tibbi cihaz" in title_key:
        authority = "Sağlık Bakanlığı"
    elif "cevre" in title_key:
        authority = "Çevre, Şehircilik ve İklim Değişikliği Bakanlığı"
    else:
        authority = "Ticaret Bakanlığı / tebliğde belirtilen yetkili kurum"
    return {
        "authority": authority,
        "system": system,
        "risk_based": risk_based,
        "physical_inspection_possible": physical,
        "laboratory_test_possible": lab,
    }


class ImportControlEngine:
    def __init__(self, config_path: str | Path | None = None, data_dir: str | Path | None = None) -> None:
        config_file = Path(config_path or Path(__file__).with_name("control_sources.json"))
        config = json.loads(config_file.read_text(encoding="utf-8"))
        self.rules_config = list(config.get("rules", []))
        configured_year = str(config.get("valid_from", ""))[:4]
        self.year = datetime.now().year
        if configured_year.isdigit() and int(configured_year) != self.year:
            for rule in self.rules_config:
                rule["code"] = str(rule["code"]).replace(configured_year, str(self.year), 1)
        self.valid_from = f"{self.year}-01-01"
        self.sync_interval_seconds = max(300, int(config.get("sync_interval_seconds", 21600)))
        default_root = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "mevzuat-mcp"
        root = Path(data_dir or os.environ.get("MEVZUAT_DATA_DIR", default_root))
        root.mkdir(parents=True, exist_ok=True)
        self.db_path = root / "controls.sqlite3"
        self._client = BedestenClient(cache_ttl=self.sync_interval_seconds)
        self._attachment_http = httpx.AsyncClient(
            headers={"User-Agent": "MevzuatMCP/1.4 (+official-annex-indexer)"},
            follow_redirects=True,
            timeout=httpx.Timeout(75.0),
        )
        self._converter = MarkItDown()
        self._sync_lock = asyncio.Lock()
        self._request_lock = asyncio.Lock()
        self._last_request_at = 0.0
        self._request_interval = max(0.75, float(os.environ.get("CONTROL_REQUEST_INTERVAL_SECONDS", "6.5")))
        self._syncing = False
        self._errors: list[str] = []
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.db_path, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA foreign_keys=ON")
        return db

    def _init_db(self) -> None:
        with self._connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS control_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS control_snapshots (
                    id TEXT PRIMARY KEY,
                    code TEXT NOT NULL,
                    title TEXT NOT NULL,
                    category TEXT NOT NULL,
                    mevzuat_id TEXT NOT NULL,
                    source_url TEXT NOT NULL,
                    official_gazette_date TEXT,
                    official_gazette_number TEXT,
                    document_sha256 TEXT NOT NULL,
                    retrieved_at TEXT NOT NULL,
                    valid_from TEXT NOT NULL,
                    scope_count INTEGER NOT NULL,
                    authority TEXT NOT NULL,
                    system TEXT NOT NULL,
                    risk_based INTEGER NOT NULL,
                    physical_inspection_possible INTEGER NOT NULL,
                    laboratory_test_possible INTEGER NOT NULL,
                    required_documents_excerpt TEXT,
                    active INTEGER NOT NULL DEFAULT 0
                );
                CREATE INDEX IF NOT EXISTS idx_control_snapshot_active
                    ON control_snapshots(code, active);
                CREATE TABLE IF NOT EXISTS control_scope (
                    snapshot_id TEXT NOT NULL REFERENCES control_snapshots(id) ON DELETE CASCADE,
                    gtip_prefix TEXT NOT NULL,
                    description TEXT,
                    source_line TEXT NOT NULL,
                    source_offset INTEGER NOT NULL,
                    excluded INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (snapshot_id, gtip_prefix)
                );
                CREATE INDEX IF NOT EXISTS idx_control_scope_gtip ON control_scope(gtip_prefix);
                """
            )
            columns = {row[1] for row in db.execute("PRAGMA table_info(control_scope)").fetchall()}
            if "excluded" not in columns:
                db.execute("ALTER TABLE control_scope ADD COLUMN excluded INTEGER NOT NULL DEFAULT 0")

    async def close(self) -> None:
        await self._client.close()
        await self._attachment_http.aclose()

    async def _pace(self) -> None:
        delay = self._request_interval - (time.monotonic() - self._last_request_at)
        if delay > 0:
            await asyncio.sleep(delay)

    async def _discover_documents(self) -> dict[str, Any]:
        """Discover the current annual set with a few paged searches.

        One broad official search replaces one search per communique, which is
        both faster and substantially friendlier to the public Bedesten API.
        """
        documents: dict[str, Any] = {}
        for page in range(1, 5):
            result = None
            for attempt in range(5):
                async with self._request_lock:
                    await self._pace()
                    result = await self._client.search_documents(
                        mevzuat_adi="Denetimi Tebliği",
                        resmi_gazete_tarihi_start=f"31/12/{self.year - 1}",
                        resmi_gazete_tarihi_end=f"31/12/{self.year - 1}",
                        page=page,
                        page_size=20,
                    )
                    self._last_request_at = time.monotonic()
                if not result.error_message:
                    break
                if "429" not in result.error_message and "Too Many" not in result.error_message:
                    raise RuntimeError(result.error_message)
                await asyncio.sleep(min(30, 3 * (2 ** attempt)))
            if result is None or result.error_message:
                raise RuntimeError(result.error_message if result else "Resmî arama yanıt vermedi")
            for document in result.documents:
                for config in self.rules_config:
                    if _key(config["code"]) in _key(document.mevzuat_adi):
                        documents[config["code"]] = document
            if len(result.documents) < 20 or len(documents) >= len(self.rules_config):
                break
        return documents

    async def _fetch_rule(
        self,
        config: dict[str, Any],
        document: Any,
        semaphore: asyncio.Semaphore,
    ) -> tuple[dict[str, Any], str, Any, str]:
        async with semaphore:
            text = ""
            raw_html = ""
            for attempt in range(4):
                async with self._request_lock:
                    await self._pace()
                    text = await self._client.get_document_plain_text(document.mevzuat_id)
                    self._last_request_at = time.monotonic()
                if text:
                    # get_document_plain_text populated the Bedesten client's
                    # cache, so this exposes official attachment hrefs without
                    # a second network request.
                    content = await self._client.get_document_content(document.mevzuat_id)
                    raw_html = content.content
                    break
                await asyncio.sleep(min(30, 3 * (2 ** attempt)))
            if not text:
                raise RuntimeError(f"{config['code']} resmî metni boş döndü")
            return config, text, document, raw_html

    @staticmethod
    def _official_attachment_url(raw_html: str) -> str | None:
        candidates = re.findall(r"(?is)href\s*=\s*['\"]([^'\"]+)['\"]", raw_html)
        for candidate in candidates:
            href = html.unescape(candidate).strip()
            if not href.casefold().endswith(".zip"):
                continue
            url = urljoin("https://www.mevzuat.gov.tr/MevzuatMetin/", href)
            parsed = urlsplit(url)
            if parsed.scheme == "https" and parsed.hostname in {"mevzuat.gov.tr", "www.mevzuat.gov.tr"}:
                return url
        return None

    async def _download_attachment(self, raw_html: str) -> tuple[bytes, str]:
        url = self._official_attachment_url(raw_html)
        if not url:
            raise RuntimeError("Resmî metindeki ek arşivi bağlantısı bulunamadı")
        async with self._attachment_http.stream("GET", url) as response:
            response.raise_for_status()
            resolved = str(response.url)
            parsed = urlsplit(resolved)
            if parsed.scheme != "https" or parsed.hostname not in {"mevzuat.gov.tr", "www.mevzuat.gov.tr"}:
                raise RuntimeError("Resmî ek arşivi izin verilen alan adı dışına yönlendirildi")
            content_length = response.headers.get("content-length")
            if content_length and int(content_length) > 50 * 1024 * 1024:
                raise RuntimeError("Resmî ek arşivi 50 MB güvenlik sınırını aşıyor")
            chunks: list[bytes] = []
            total = 0
            async for chunk in response.aiter_bytes():
                total += len(chunk)
                if total > 50 * 1024 * 1024:
                    raise RuntimeError("Resmî ek arşivi 50 MB güvenlik sınırını aşıyor")
                chunks.append(chunk)
        return b"".join(chunks), resolved

    async def sync(self, force: bool = False) -> ControlSyncStatus:
        async with self._sync_lock:
            if not force and self._fresh():
                return self.status()
            self._syncing = True
            self._errors = []
            checked_at = _now()
            try:
                try:
                    discovered = await self._discover_documents()
                except Exception as exc:
                    self._errors.append(f"Tebliğ listesi: {exc}")
                    discovered = {}
                semaphore = asyncio.Semaphore(3)
                pending: list[tuple[dict[str, Any], Any]] = []
                for config in self.rules_config:
                    document = discovered.get(config["code"])
                    if document is None:
                        if not config.get("optional"):
                            self._errors.append(f"{config['code']}: güncel resmî metin listede bulunamadı")
                        continue
                    pending.append((config, document))
                # Sequential reads are intentional: the official public service
                # enforces a conservative request budget and returns 429 when a
                # cold start fans out all annual communiques at once.
                results: list[Any] = []
                for config, document in pending:
                    try:
                        results.append(await self._fetch_rule(config, document, semaphore))
                    except Exception as exc:
                        results.append(exc)
                successes = 0
                for (config, _), result in zip(pending, results):
                    if isinstance(result, Exception):
                        if not config.get("optional"):
                            self._errors.append(f"{config['code']}: {result}")
                        continue
                    _, text, document, raw_html = result
                    attachment_digest = ""
                    if config.get("scope_table"):
                        table = config["scope_table"]
                        scope = extract_scope_table(text, table["start_pattern"], table["end_pattern"])
                    else:
                        scope = extract_annex_scope(text, int(config.get("scope_annex", 1)))
                    if config.get("scope_attachment"):
                        try:
                            attachment, _ = await self._download_attachment(raw_html)
                            scope = extract_attachment_scope(attachment, self._converter)
                            attachment_digest = hashlib.sha256(attachment).hexdigest()
                        except Exception as exc:
                            self._errors.append(f"{config['code']}: resmî ek arşivi işlenemedi ({exc})")
                            continue
                    if not scope:
                        location = (
                            "resmî ek arşivi" if config.get("scope_attachment")
                            else f"Ek-{config.get('scope_annex', 1)}"
                        )
                        self._errors.append(f"{config['code']}: {location} GTİP kapsamı ayrıştırılamadı")
                        continue
                    digest_material = text.encode("utf-8") + attachment_digest.encode("ascii")
                    digest = hashlib.sha256(digest_material).hexdigest()
                    snapshot_id = hashlib.sha256(f"{config['code']}:{digest}".encode()).hexdigest()[:32]
                    process = infer_process(text, document.mevzuat_adi)
                    documents = extract_required_documents(text)
                    retrieved_at = _now()
                    source_url = document.url or f"https://www.mevzuat.gov.tr/MevzuatMetin/9.5.{document.mevzuat_no}.pdf"
                    with self._connect() as db:
                        db.execute("UPDATE control_snapshots SET active=0 WHERE code=?", (config["code"],))
                        db.execute(
                            """
                            INSERT OR REPLACE INTO control_snapshots (
                                id, code, title, category, mevzuat_id, source_url,
                                official_gazette_date, official_gazette_number,
                                document_sha256, retrieved_at, valid_from, scope_count,
                                authority, system, risk_based,
                                physical_inspection_possible, laboratory_test_possible,
                                required_documents_excerpt, active
                            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1)
                            """,
                            (
                                snapshot_id, config["code"], document.mevzuat_adi, config["category"],
                                document.mevzuat_id, source_url, document.resmi_gazete_tarihi,
                                document.resmi_gazete_sayisi, digest, retrieved_at, self.valid_from,
                                sum(not row.excluded for row in scope), process["authority"], process["system"],
                                int(process["risk_based"]), int(process["physical_inspection_possible"]),
                                int(process["laboratory_test_possible"]), documents,
                            ),
                        )
                        db.execute("DELETE FROM control_scope WHERE snapshot_id=?", (snapshot_id,))
                        db.executemany(
                            """INSERT INTO control_scope
                               (snapshot_id, gtip_prefix, description, source_line, source_offset, excluded)
                               VALUES (?,?,?,?,?,?)""",
                            [
                                (
                                    snapshot_id, row.gtip_prefix, row.description, row.source_line,
                                    row.source_offset, int(row.excluded),
                                )
                                for row in scope
                            ],
                        )
                    successes += 1
                with self._connect() as db:
                    db.execute(
                        "INSERT OR REPLACE INTO control_meta(key,value) VALUES('last_checked_at',?)",
                        (checked_at,),
                    )
                if successes == 0 and not self._errors:
                    self._errors.append("Hiçbir kontrol tebliği güncellenemedi")
            finally:
                self._syncing = False
            return self.status()

    def _fresh(self) -> bool:
        with self._connect() as db:
            row = db.execute("SELECT value FROM control_meta WHERE key='last_checked_at'").fetchone()
            active_codes = {
                item["code"]
                for item in db.execute("SELECT code FROM control_snapshots WHERE active=1").fetchall()
            }
        required_codes = {item["code"] for item in self.rules_config if not item.get("optional")}
        if not required_codes.issubset(active_codes):
            # A partially parsed annual set must be retried on restart instead
            # of being treated as fresh for the full sync interval.
            return False
        if not row:
            return False
        try:
            checked = datetime.fromisoformat(row["value"])
            age = (datetime.now(checked.tzinfo) - checked).total_seconds()
            return age < self.sync_interval_seconds
        except (ValueError, TypeError):
            return False

    @staticmethod
    def _snapshot(row: sqlite3.Row) -> ControlSnapshot:
        return ControlSnapshot(
            id=row["id"], code=row["code"], title=row["title"], mevzuat_id=row["mevzuat_id"],
            document_sha256=row["document_sha256"], retrieved_at=row["retrieved_at"],
            valid_from=row["valid_from"], scope_count=row["scope_count"], active=bool(row["active"]),
        )

    @staticmethod
    def _rule(row: sqlite3.Row) -> ImportControlRule:
        return ImportControlRule(
            code=row["code"], title=row["title"], category=row["category"], authority=row["authority"],
            system=row["system"], risk_based=bool(row["risk_based"]),
            physical_inspection_possible=bool(row["physical_inspection_possible"]),
            laboratory_test_possible=bool(row["laboratory_test_possible"]),
            required_documents_excerpt=row["required_documents_excerpt"], scope_count=row["scope_count"],
            mevzuat_id=row["mevzuat_id"], source_url=row["source_url"],
            official_gazette_date=row["official_gazette_date"],
            official_gazette_number=row["official_gazette_number"], document_sha256=row["document_sha256"],
            retrieved_at=row["retrieved_at"], valid_from=row["valid_from"], snapshot_id=row["id"],
        )

    def status(self) -> ControlSyncStatus:
        with self._connect() as db:
            rows = db.execute("SELECT * FROM control_snapshots WHERE active=1 ORDER BY code").fetchall()
            meta = db.execute("SELECT value FROM control_meta WHERE key='last_checked_at'").fetchone()
            count = db.execute(
                """SELECT COUNT(*) AS n FROM control_scope s
                   JOIN control_snapshots d ON d.id=s.snapshot_id
                   WHERE d.active=1 AND s.excluded=0"""
            ).fetchone()["n"]
        snapshots = [self._snapshot(row) for row in rows]
        required_codes = {item["code"] for item in self.rules_config if not item.get("optional")}
        active_codes = {item.code for item in snapshots}
        return ControlSyncStatus(
            ready=bool(required_codes) and required_codes.issubset(active_codes), syncing=self._syncing,
            last_checked_at=meta["value"] if meta else None, active_snapshots=snapshots,
            scope_count=count, errors=list(self._errors), sync_interval_seconds=self.sync_interval_seconds,
        )

    async def lookup(self, gtip: str) -> ImportControlLookupResult:
        code = _normalise_gtip(gtip)
        if code is None or len(code) != 12:
            raise ValueError("Kontrol sorgusu için 12 haneli GTİP gereklidir.")
        if not self.status().ready:
            return ImportControlLookupResult(
                status="unavailable", gtip=code,
                warnings=["Resmî kontrol tebliğleri arka planda eşitleniyor; uygunluk hakkında sonuç verilmedi. Kısa süre sonra yeniden deneyin."],
                as_of=_now(),
            )
        with self._connect() as db:
            rows = db.execute(
                """
                SELECT d.*, s.gtip_prefix, s.description, s.source_line, s.source_offset, s.excluded
                FROM control_scope s
                JOIN control_snapshots d ON d.id=s.snapshot_id
                WHERE d.active=1 AND substr(?,1,length(s.gtip_prefix))=s.gtip_prefix
                ORDER BY length(s.gtip_prefix) DESC, d.code
                """,
                (code,),
            ).fetchall()
        excluded_by_rule: dict[str, list[sqlite3.Row]] = {}
        for row in rows:
            if row["excluded"]:
                excluded_by_rule.setdefault(row["code"], []).append(row)
        matches: list[ImportControlMatch] = []
        for row in rows:
            if row["excluded"] or row["code"] in excluded_by_rule:
                continue
            rule = self._rule(row)
            risk_sentence = (
                "GTİP tebliğ ekinde yer alıyor; fiilî denetime yönlendirme TAREKS risk analiziyle belirlenir."
                if rule.risk_based
                else "GTİP tebliğ ekinde yer alıyor; işlem sonucu yetkili kurumun incelemesine bağlıdır."
            )
            cautions = [
                "Bu eşleşme tek başına ürünün teknik kapsamda olduğunu veya fiilî denetime seçildiğini kanıtlamaz; ürün niteliği ve istisnalar kontrol edilmelidir."
            ]
            if rule.laboratory_test_possible:
                cautions.append(
                    "Laboratuvar testi mevzuatta mümkün bir fiilî denetim yöntemidir; belirli bir özel laboratuvar otomatik veya zorunlu kabul edilmemiştir."
                )
            matches.append(
                ImportControlMatch(
                    rule=rule,
                    matched_scope=ControlScopeRow(
                        gtip_prefix=row["gtip_prefix"], description=row["description"],
                        source_line=row["source_line"], source_offset=row["source_offset"],
                        excluded=False,
                    ),
                    match_type="exact" if len(row["gtip_prefix"]) == 12 else "prefix",
                    assessment=risk_sentence,
                    cautions=cautions,
                )
            )
        warnings = [
            (
                f"{rule_code} tebliğinde {', '.join(item['gtip_prefix'] for item in exclusions)} "
                "'hariç' hükmü eşleşti; bu tebliğ için pozitif kapsam sonucu üretilmedi."
            )
            for rule_code, exclusions in sorted(excluded_by_rule.items())
        ]
        if not matches:
            warnings.append(
                "GTİP, indekslenen güncel tebliğ eklerinde bulunamadı. Bu sonuç 'kontrole tabi değildir' anlamına gelmez; ürün niteliği, başka izin mevzuatı ve güncel değişiklikler ayrıca incelenmelidir."
            )
        return ImportControlLookupResult(
            status="matched" if matches else "not_found", gtip=code, matches=matches,
            warnings=warnings, as_of=_now(),
        )

    def changes(self, code: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        bounded_limit = max(1, min(limit, 200))
        if code:
            with self._connect() as db:
                rows = db.execute(
                    "SELECT * FROM control_snapshots WHERE code=? ORDER BY retrieved_at DESC LIMIT ?",
                    (code, bounded_limit),
                ).fetchall()
        else:
            with self._connect() as db:
                rows = db.execute(
                    "SELECT * FROM control_snapshots ORDER BY retrieved_at DESC LIMIT ?",
                    (bounded_limit,),
                ).fetchall()
        grouped: dict[str, list[sqlite3.Row]] = {}
        for row in rows:
            grouped.setdefault(row["code"], []).append(row)
        result: list[dict[str, Any]] = []
        for rule_code, versions in grouped.items():
            for newer, older in zip(versions, versions[1:]):
                if newer["document_sha256"] == older["document_sha256"]:
                    continue
                result.append(
                    {
                        "code": rule_code,
                        "title": newer["title"],
                        "new_snapshot_id": newer["id"],
                        "old_snapshot_id": older["id"],
                        "new_scope_count": newer["scope_count"],
                        "old_scope_count": older["scope_count"],
                        "scope_count_delta": newer["scope_count"] - older["scope_count"],
                        "changed_at": newer["retrieved_at"],
                    }
                )
        return result[:limit]

    async def periodic_sync_loop(self) -> None:
        while True:
            try:
                await self.sync(force=False)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # pragma: no cover - service resilience
                self._errors.append(str(exc))
            await asyncio.sleep(self.sync_interval_seconds)

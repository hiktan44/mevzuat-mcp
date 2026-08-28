"""ASGI application for the Mevzuat MCP server and its web interface."""

from __future__ import annotations

import logging
import json
import threading
import time
from pathlib import Path
from typing import Any

from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse

from mevzuat_mcp_server import (
    _BED_VALID_TYPES,
    app as mcp,
    bedesten_client,
    ticaret_client,
)

logger = logging.getLogger(__name__)
WEB_DIR = Path(__file__).resolve().parent / "web"


class FixedWindowRateLimiter:
    """Small fail-open fixed-window limiter for the public web endpoints."""

    def __init__(self) -> None:
        self._entries: dict[str, tuple[int, int]] = {}
        self._lock = threading.Lock()

    def check(self, key: str, *, limit: int, window_seconds: int) -> tuple[bool, int]:
        try:
            now = int(time.time())
            window = now // window_seconds
            with self._lock:
                current_window, count = self._entries.get(key, (window, 0))
                if current_window != window:
                    current_window, count = window, 0
                count += 1
                self._entries[key] = (current_window, count)

            retry_after = window_seconds - (now % window_seconds)
            return count <= limit, max(retry_after, 1)
        except Exception:
            logger.exception("Rate limiter failed open")
            return True, 0


rate_limiter = FixedWindowRateLimiter()


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",", 1)[0].strip()
    return request.client.host if request.client else "unknown"


def _rate_limit_response(request: Request, scope: str) -> JSONResponse | None:
    allowed, retry_after = rate_limiter.check(
        f"{scope}:{_client_ip(request)}", limit=30, window_seconds=60
    )
    if allowed:
        return None
    return JSONResponse(
        {
            "error": "Çok hızlı arama yapıyorsunuz. Lütfen kısa bir süre sonra yeniden deneyin.",
            "retry_after": retry_after,
        },
        status_code=429,
        headers={"Retry-After": str(retry_after)},
    )


def _normalise_date(value: Any) -> str | None:
    if not value:
        return None
    value = str(value).strip()
    if len(value) == 10 and value[4] == "-" and value[7] == "-":
        year, month, day = value.split("-")
        return f"{day}/{month}/{year}"
    return value


def _document_json(document: Any) -> dict[str, Any]:
    type_code = ""
    type_label = "Mevzuat"
    if isinstance(document.mevzuat_tur, dict):
        type_code = str(document.mevzuat_tur.get("name", ""))
        type_label = str(
            document.mevzuat_tur.get("description")
            or document.mevzuat_tur.get("name")
            or type_label
        )
    elif document.mevzuat_tur:
        type_code = type_label = str(document.mevzuat_tur)

    gazette_date = document.resmi_gazete_tarihi
    if gazette_date and "T" in gazette_date:
        gazette_date = gazette_date.split("T", 1)[0]

    return {
        "id": document.mevzuat_id,
        "number": str(document.mevzuat_no or ""),
        "title": document.mevzuat_adi,
        "type": type_code,
        "type_label": type_label,
        "gazette_date": gazette_date,
        "gazette_number": document.resmi_gazete_sayisi,
        "rationale_id": document.gerekce_id,
        "source_url": document.url,
    }


_TICARET_CONTENT_KINDS = {
    "mevzuat",
    "destek",
    "veri",
    "rapor",
    "ulke_bilgisi",
    "iletisim",
    "yayin",
}


def _ticaret_document_json(document: Any) -> dict[str, Any]:
    """Return the stable, public subset used by the research interface."""
    return {
        "id": document.id,
        "title": document.title,
        "source_id": document.source_id,
        "content_kind": document.content_kind,
        "section": document.section,
        "subsection": document.subsection,
        "document_type": document.document_type,
        "number": document.number,
        "publication_date": document.publication_date,
        "official_gazette": document.official_gazette,
        "page_updated_at": document.page_updated_at,
        "document_url": document.document_url,
        "source_page_url": document.source_page_url,
        "file_type": document.file_type,
        "is_page": document.is_page,
        "is_repealed": document.is_repealed,
        "context": document.context,
    }


@mcp.custom_route("/", methods=["GET"])
async def web_index(request: Request):
    return FileResponse(WEB_DIR / "index.html", media_type="text/html")


@mcp.custom_route("/assets/app.css", methods=["GET"])
async def web_css(request: Request):
    return FileResponse(WEB_DIR / "app.css", media_type="text/css")


@mcp.custom_route("/assets/app.js", methods=["GET"])
async def web_js(request: Request):
    return FileResponse(WEB_DIR / "app.js", media_type="text/javascript")


@mcp.custom_route("/api/search", methods=["POST"])
async def web_search(request: Request):
    limited = _rate_limit_response(request, "search")
    if limited:
        return limited

    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Geçerli bir arama isteği gönderin."}, status_code=400)

    query = str(body.get("query", "")).strip()
    mode = str(body.get("mode", "title"))
    type_code = str(body.get("type", "")).strip().upper()
    if len(query) > 200:
        return JSONResponse({"error": "Arama metni en fazla 200 karakter olabilir."}, status_code=422)
    if mode not in {"title", "content", "number"}:
        return JSONResponse({"error": "Geçersiz arama türü."}, status_code=422)
    if type_code and type_code not in _BED_VALID_TYPES:
        return JSONResponse({"error": "Geçersiz mevzuat türü."}, status_code=422)

    try:
        page = max(1, min(int(body.get("page", 1)), 10000))
        page_size = max(1, min(int(body.get("page_size", 20)), 50))
    except (TypeError, ValueError):
        return JSONResponse({"error": "Geçersiz sayfa bilgisi."}, status_code=422)

    search_args: dict[str, Any] = {
        "phrase": query if mode == "content" else "",
        "mevzuat_adi": query if mode == "title" else "",
        "mevzuat_no": query if mode == "number" and query else None,
        "mevzuat_tur_list": [type_code] if type_code else list(_BED_VALID_TYPES),
        "resmi_gazete_tarihi_start": _normalise_date(body.get("start_date")),
        "resmi_gazete_tarihi_end": _normalise_date(body.get("end_date")),
        "page": page,
        "page_size": page_size,
        "sort_field": "RESMI_GAZETE_TARIHI",
        "sort_direction": "desc",
    }

    result = await bedesten_client.search_documents(**search_args)
    if result.error_message:
        logger.warning("Web search failed: %s", result.error_message)
        return JSONResponse(
            {"error": "Mevzuat kaynağına şu anda ulaşılamıyor. Lütfen yeniden deneyin."},
            status_code=502,
        )

    return JSONResponse(
        {
            "documents": [_document_json(document) for document in result.documents],
            "total": result.total_results,
            "page": page,
            "page_size": page_size,
            "has_next": page * page_size < result.total_results,
        }
    )


@mcp.custom_route("/api/document/{mevzuat_id}", methods=["GET"])
async def web_document(request: Request):
    limited = _rate_limit_response(request, "document")
    if limited:
        return limited

    mevzuat_id = request.path_params.get("mevzuat_id", "")
    if not mevzuat_id.isdigit() or len(mevzuat_id) > 20:
        return JSONResponse({"error": "Geçersiz mevzuat kimliği."}, status_code=422)

    plain = await bedesten_client.get_document_plain_text(mevzuat_id)
    if not plain:
        return JSONResponse({"error": "Mevzuat metni bulunamadı."}, status_code=404)
    return JSONResponse({"id": mevzuat_id, "content": plain})


@mcp.custom_route("/api/ticaret/status", methods=["GET"])
async def web_ticaret_status(request: Request):
    limited = _rate_limit_response(request, "ticaret-status")
    if limited:
        return limited
    return JSONResponse(ticaret_client.status().model_dump(mode="json"))


@mcp.custom_route("/api/ticaret/sources", methods=["GET"])
async def web_ticaret_sources(request: Request):
    limited = _rate_limit_response(request, "ticaret-sources")
    if limited:
        return limited
    try:
        return JSONResponse(await ticaret_client.list_sources())
    except Exception:
        logger.exception("Ticaret source catalogue failed")
        return JSONResponse(
            {"error": "Ticaret Bakanlığı kaynak kataloğu şu anda hazırlanıyor."},
            status_code=503,
        )


@mcp.custom_route("/api/ticaret/search", methods=["POST"])
async def web_ticaret_search(request: Request):
    limited = _rate_limit_response(request, "ticaret-search")
    if limited:
        return limited

    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Geçerli bir arama isteği gönderin."}, status_code=400)

    query = str(body.get("query", "")).strip()
    if len(query) > 300:
        return JSONResponse({"error": "Arama metni en fazla 300 karakter olabilir."}, status_code=422)

    raw_kinds = body.get("content_kinds") or []
    raw_sources = body.get("source_ids") or []
    raw_types = body.get("document_types") or []
    if not all(isinstance(item, str) for item in [*raw_kinds, *raw_sources, *raw_types]):
        return JSONResponse({"error": "Filtre değerleri metin olmalıdır."}, status_code=422)
    content_kinds = [item.strip() for item in raw_kinds if item.strip()]
    if any(item not in _TICARET_CONTENT_KINDS for item in content_kinds):
        return JSONResponse({"error": "Geçersiz bilgi katmanı."}, status_code=422)

    known_sources = {source.id for source in ticaret_client.sources}
    source_ids = [item.strip() for item in raw_sources if item.strip()]
    if any(item not in known_sources for item in source_ids):
        return JSONResponse({"error": "Geçersiz resmî kaynak."}, status_code=422)
    if len(raw_types) > 12 or any(len(item) > 80 for item in raw_types):
        return JSONResponse({"error": "Belge türü filtresi çok uzun."}, status_code=422)

    try:
        offset = max(0, min(int(body.get("offset", 0)), 100000))
        limit = max(1, min(int(body.get("limit", 20)), 50))
        raw_year = body.get("year")
        year = int(raw_year) if raw_year not in (None, "") else None
    except (TypeError, ValueError):
        return JSONResponse({"error": "Geçersiz sayfalama veya yıl bilgisi."}, status_code=422)
    if year is not None and not 1900 <= year <= 2100:
        return JSONResponse({"error": "Yıl 1900 ile 2100 arasında olmalıdır."}, status_code=422)

    try:
        result = await ticaret_client.search(
            query=query,
            content_kinds=content_kinds or None,
            source_ids=source_ids or None,
            document_types=[item.strip() for item in raw_types if item.strip()] or None,
            year=year,
            include_repealed=bool(body.get("include_repealed", False)),
            offset=offset,
            limit=limit,
        )
    except Exception:
        logger.exception("Ticaret catalogue search failed")
        return JSONResponse(
            {"error": "Ticaret Bakanlığı kataloğunda arama şu anda tamamlanamadı."},
            status_code=502,
        )

    return JSONResponse(
        {
            "documents": [_ticaret_document_json(item) for item in result.documents],
            "total": result.total_results,
            "offset": result.offset,
            "limit": result.limit,
            "has_next": result.offset + result.limit < result.total_results,
            "catalog_synced_at": result.catalog_synced_at,
            "excluded_repealed": result.excluded_repealed,
            "note": result.note,
        }
    )


@mcp.custom_route("/api/ticaret/document/{document_id}", methods=["GET"])
async def web_ticaret_document(request: Request):
    limited = _rate_limit_response(request, "ticaret-document")
    if limited:
        return limited

    document_id = request.path_params.get("document_id", "")
    if not document_id.startswith("ticaret_") or len(document_id) != 32:
        return JSONResponse({"error": "Geçersiz belge kimliği."}, status_code=422)
    try:
        offset = max(0, min(int(request.query_params.get("offset", "0")), 10_000_000))
        content = await ticaret_client.get_document_content(
            document_id,
            offset=offset,
            max_characters=60_000,
        )
    except ValueError as exc:
        if str(exc).startswith("Belge bulunamadı:"):
            return JSONResponse({"error": "Belge katalogda bulunamadı."}, status_code=404)
        logger.warning("Ticaret document could not be extracted: %s: %s", document_id, exc)
        return JSONResponse(
            {"error": "Bu bağlantıdan metin çıkarılamadı. Resmî kaynak bağlantısını açabilirsiniz."},
            status_code=502,
        )
    except Exception:
        logger.exception("Ticaret document extraction failed: %s", document_id)
        return JSONResponse(
            {"error": "Belge metni resmî kaynaktan alınamadı. Kaynak bağlantısını açabilirsiniz."},
            status_code=502,
        )

    return JSONResponse(
        {
            "document": _ticaret_document_json(content.document),
            "content": content.content,
            "total_characters": content.total_characters,
            "offset": content.offset,
            "returned_characters": content.returned_characters,
            "truncated": content.truncated,
            "resolved_url": content.resolved_url,
            "fetched_at": content.fetched_at,
            "warnings": content.warnings,
        }
    )

# Add health check endpoint to the MCP server
@mcp.custom_route("/health", methods=["GET"])
async def health_check(request):
    """Health check endpoint for Coolify and other monitoring services."""
    return JSONResponse({
        "status": "healthy",
        "service": "Mevzuat MCP Server",
        "version": "1.1.0"
    })

class McpRateLimitMiddleware:
    """Fail-open 20 request/minute IP limit for the public AI endpoint."""

    def __init__(self, asgi_app: Any) -> None:
        self.asgi_app = asgi_app

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope.get("type") == "http" and str(scope.get("path", "")).startswith("/mcp"):
            try:
                headers = {
                    key.decode("latin-1").lower(): value.decode("latin-1")
                    for key, value in scope.get("headers", [])
                }
                forwarded = headers.get("x-forwarded-for", "").split(",", 1)[0].strip()
                client = scope.get("client") or ("unknown", 0)
                client_ip = forwarded or str(client[0])
                allowed, retry_after = rate_limiter.check(
                    f"mcp:{client_ip}", limit=20, window_seconds=60
                )
                if not allowed:
                    payload = json.dumps(
                        {
                            "error": "Çok hızlı MCP isteği gönderiyorsunuz. Lütfen kısa bir süre sonra yeniden deneyin.",
                            "retry_after": retry_after,
                        },
                        ensure_ascii=False,
                    ).encode("utf-8")
                    await send(
                        {
                            "type": "http.response.start",
                            "status": 429,
                            "headers": [
                                (b"content-type", b"application/json; charset=utf-8"),
                                (b"retry-after", str(retry_after).encode("ascii")),
                                (b"content-length", str(len(payload)).encode("ascii")),
                            ],
                        }
                    )
                    await send({"type": "http.response.body", "body": payload})
                    return
            except Exception:
                logger.exception("MCP rate limiter failed open")
        await self.asgi_app(scope, receive, send)


# Create ASGI app directly from FastMCP server and protect the public MCP
# endpoint without buffering its streaming responses.
app = McpRateLimitMiddleware(mcp.http_app())

# Endpoints:
# - / - Web search interface
# - /api/search and /api/document/{id} - Web interface API
# - /mcp/ - MCP server (Streamable HTTP transport)
# - /health - Health check for monitoring
# Run with: uvicorn app:app --host 0.0.0.0 --port 8000

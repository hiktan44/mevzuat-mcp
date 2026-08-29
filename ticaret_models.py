"""Data models for the Ministry of Trade source catalogue."""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class TicaretSource(BaseModel):
    """An official Ministry of Trade catalogue entry point."""

    id: str
    url: str
    content_kind: str
    follow_prefixes: list[str]
    max_pages: int = 250


class TicaretDocument(BaseModel):
    """A page or downloadable document discovered from an official source."""

    id: str
    title: str
    source_id: str
    content_kind: str
    section: str
    subsection: Optional[str] = None
    document_type: Optional[str] = None
    number: Optional[str] = None
    publication_date: Optional[str] = None
    official_gazette: Optional[str] = None
    page_updated_at: Optional[str] = None
    document_url: str
    source_page_url: str
    file_type: str
    is_page: bool = False
    is_repealed: bool = False
    attachment_label: Optional[str] = None
    context: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class TicaretCatalog(BaseModel):
    """A point-in-time snapshot of discovered Ministry content."""

    synced_at: str
    fingerprint: str
    sources: list[TicaretSource]
    pages_scanned: int
    documents: list[TicaretDocument]
    errors: list[str] = Field(default_factory=list)
    added_ids: list[str] = Field(default_factory=list)
    removed_ids: list[str] = Field(default_factory=list)


class TicaretSearchResult(BaseModel):
    """Paginated metadata search response."""

    documents: list[TicaretDocument]
    total_results: int
    offset: int
    limit: int
    catalog_synced_at: str
    catalog_fingerprint: str
    excluded_repealed: int = 0
    note: str


class TicaretDocumentContent(BaseModel):
    """A bounded slice of a document's extracted text."""

    document: TicaretDocument
    content: str
    total_characters: int
    offset: int
    returned_characters: int
    truncated: bool
    resolved_url: str
    fetched_at: str
    warnings: list[str] = Field(default_factory=list)


class TicaretContentMatch(BaseModel):
    """One contextual match inside a Ministry document."""

    document_id: str
    title: str
    section: str
    source_page_url: str
    document_url: str
    occurrence_count: int
    excerpts: list[str]


class TicaretContentSearchResult(BaseModel):
    """Bounded multi-document full-text search response."""

    query: str
    matches: list[TicaretContentMatch]
    scanned_documents: int
    candidate_documents: int
    failed_documents: list[str] = Field(default_factory=list)
    catalog_synced_at: str
    coverage_note: str


class TicaretCatalogStatus(BaseModel):
    """Freshness and coverage information for the live catalogue."""

    ready: bool
    syncing: bool
    last_synced_at: Optional[str] = None
    next_scheduled_sync_at: Optional[str] = None
    sync_interval_seconds: int
    full_sync_interval_seconds: int | None = None
    latest_official_gazette_date: Optional[str] = None
    latest_official_gazette_documents: int = 0
    source_count: int = 0
    pages_scanned: int = 0
    document_count: int = 0
    fingerprint: Optional[str] = None
    added_since_previous_sync: int = 0
    removed_since_previous_sync: int = 0
    errors: list[str] = Field(default_factory=list)

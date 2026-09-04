"""Deterministic origin-document rule table for imports into Türkiye.

The table answers one intake question: which movement/origin document does the
stated origin country normally require? It mirrors the ministry's published
in-force FTA list (scraped 2026-09-04) and the Customs Union arrangement. It is
intake guidance, never a binding origin decision; product-level origin rules and
current validity are always confirmed against the ministry page.
"""
from __future__ import annotations

import unicodedata
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

STA_LIST_URL = "https://ticaret.gov.tr/dis-iliskiler/serbest-ticaret-anlasmalari/yururlukte-bulunan-stalar"
IMPORT_REGIME_URL = (
    "https://ticaret.gov.tr/ithalat/ithalat-mevzuati/ithalat-rejimi-karari-igv-karari-ve-ithalat-tebligleri/"
    "1-ithalat-rejimi-kararikarar-sayisi3350karar-metni-ve-tablolar-konsolide-edilmis-olup-gunceldir"
)
_RULES_CHECKED_AT = "2026-09-04"


def _key(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or "").casefold().replace("ı", "i"))
    return "".join(ch for ch in text if not unicodedata.combining(ch))


# Türkiye – AB Gümrük Birliği: AB üyesi 27 ülke + Türkiye dolaşımında A.TR esastır.
_EU_MEMBERS = {
    "almanya", "avusturya", "belcika", "bulgaristan", "cekya", "cek cumhuriyeti", "danimarka",
    "estonya", "finlandiya", "fransa", "hirvatistan", "hollanda", "irlanda", "ispanya", "isvec",
    "italya", "kibris", "kibris rum kesimi", "letonya", "litvanya", "luksemburg", "macaristan",
    "malta", "polonya", "portekiz", "romanya", "slovakya", "slovenya", "yunanistan",
}

# Ticaret Bakanlığı "Yürürlükte Bulunan STA'lar" sayfasındaki liste (04.09.2026).
_FTA_MEMBERS = {
    # EFTA bloğu ayrıca STA tarafıdır; üyeler tek tek yazılır.
    "isvicre", "norvec", "izlanda", "lihtenstayn", "efta",
    "arnavutluk", "birlesik arap emirlikleri", "bae", "birlesik krallik", "ingiltere",
    "bosna hersek", "faroe adalari", "fas", "filistin", "guney kore", "kore cumhuriyeti",
    "gurcistan", "karadag", "montenegro", "katar", "kosova", "makedonya",
    "kuzey makedonya", "malezya", "misir", "moldova", "morityus", "mauritius",
    "sirbistan", "singapur",
}

# KKTC ile ticaret ayrı bir düzenlemeye tabidir; STA veya GB kapsamında değerlendirilmez.
_KKTC = {"kktc", "kuzey kibris turk cumhuriyeti", "kuzey kibris"}

_GENERAL_DOCUMENTS = [
    "Ticari fatura (orijinal)",
    "Taşıma belgesi (konşimento, CMR, havayolu irsaliyesi)",
    "Ambalaj listesi / içindetay",
    "Sigorta poliçesi (satış teslimi CIF/CIP değilse)",
    "İthalatçı/yetkili temsilci beyan bilgileri",
]


class OriginDocument(BaseModel):
    """One expected movement/origin document with its intake-level applicability."""

    code: Literal["ATR", "EUR1", "GSP_ORIGIN", "CERT_ORIGIN", "SPECIAL"]
    name: str
    applicability: str = Field(
        ..., description="Belgenin ne zaman ve nasıl istendiğine dair giriş düzeyi açıklama."
    )
    note: str = ""


class OriginDocumentRequirements(BaseModel):
    """Rule-table result for one origin country; intake guidance, not a decision."""

    origin_country: str
    regime: Literal["customs_union", "fta", "kktc", "mfn"]
    regime_name: str
    documents: list[OriginDocument] = Field(default_factory=list, max_length=4)
    general_documents: list[str] = Field(default_factory=list, max_length=8)
    caveats: list[str] = Field(default_factory=list, max_length=6)
    sources: list[dict[str, str]] = Field(default_factory=list, max_length=4)
    checked_at: str = _RULES_CHECKED_AT


_ATR = OriginDocument(
    code="ATR",
    name="A.TR Dolaşım Belgesi",
    applicability=(
        "Gümrük Birliği kapsamında serbest dolaşım için gümrük idaresi A.TR ister. "
        "Belge üzerindeki menşe beyanını ihracatçı verir."
    ),
)
_ATR_ORIGIN_NOTE = (
    "Ürün AB/Türkiye menşeli değilse A.TR 'Toplantıda Avrupa Konseyi/AB-Türkiye' satırları "
    "için ayrıca menşe teyidi istenebilir."
)
_EUR1 = OriginDocument(
    code="EUR1",
    name="EUR.1 Hareket Belgesi",
    applicability=(
        "Tercihli menşe talep ediliyorsa EUR.1 düzenlenir; belirli değerin altındaki gönderilerde "
        "ihracatçının fatura/kargo beyanı da tercih beyanı sayılabilir."
    ),
    note="Tercih oranları ve menşe kuralı ürün bazlıdır; anlaşma ek kuralları doğrulanmalıdır.",
)
_MFN_CERT = OriginDocument(
    code="CERT_ORIGIN",
    name="Menşe Şahadetnamesi (tercihsiz)",
    applicability=(
        "Tercihli rejim uygulanmıyor. Menşe şahadetnamesi yalnızca başka bir mevzuat (kota, "
        "gözetim, alıcı talebi) istediğinde düzenlenir; vergi tercihi sağlamaz."
    ),
)
_KKTC_DOC = OriginDocument(
    code="SPECIAL",
    name="KKTC menşe/ticaret belgesi",
    applicability=(
        "KKTC ile ticaret ayrı düzenlemeye tabidir; belge şartları gümrük idaresinden teyit edilmeden "
        "tercih varsayılmamalıdır."
    ),
)


def _caveats(regime_name: str) -> list[str]:
    return [
        "Bu tablo yalnızca belge hazırlığı için giriş düzeyi kılavuzdur; bağlayıcı tarife bilgisi veya menşe kararı değildir.",
        "Menşe kuralları ürün bazlıdır; tercih uygulanabilirliği Gümrük idaresi/Bağlayıcı Bilgi ile teyit edilmeden vergi tercihi varsayılmamalıdır.",
        f"Yürürlük durumu {regime_name} kapsamında değişmiş olabilir; Bakanlık sayfası doğrulanmalıdır.",
    ]


def _sources() -> list[dict[str, str]]:
    return [
        {"title": "Ticaret Bakanlığı – Yürürlükte Bulunan STA'lar", "url": STA_LIST_URL},
        {"title": "İthalat Rejimi Kararı 3350 – konsolide güncel metin", "url": IMPORT_REGIME_URL},
    ]


def origin_document_requirements(origin_country: str) -> Optional[OriginDocumentRequirements]:
    """Match an origin country to its import document regime; empty input returns None."""
    key = _key(origin_country).strip()
    if not key:
        return None

    if key in _EU_MEMBERS:
        return OriginDocumentRequirements(
            origin_country=origin_country.strip(),
            regime="customs_union",
            regime_name="Türkiye – AB Gümrük Birliği",
            documents=[
                _ATR,
                OriginDocument(
                    code="CERT_ORIGIN",
                    name="Menşe Şahadetnamesi (isteğe bağlı)",
                    applicability=(
                        "A.TR'deki menşe beyanı çoğu işlem için yeterlidir; alıcı veya ayrı mevzuat "
                        "istemedikçe ayrı menşe şahadetnamesi gerekmez."
                    ),
                ),
            ],
            general_documents=_GENERAL_DOCUMENTS,
            caveats=_caveats("Gümrük Birliği"),
            sources=_sources(),
        )

    if key in _KKTC:
        return OriginDocumentRequirements(
            origin_country=origin_country.strip(),
            regime="kktc",
            regime_name="Türkiye – KKTC özel düzenlemesi",
            documents=[_KKTC_DOC],
            general_documents=_GENERAL_DOCUMENTS,
            caveats=_caveats("KKTC düzenlemesi"),
            sources=_sources(),
        )

    if key in _FTA_MEMBERS:
        regime_name = "Türkiye – EFTA Serbest Ticaret Anlaşması" if key in {
            "isvicre", "norvec", "izlanda", "lihtenstayn", "efta",
        } else "Türkiye – Serbest Ticaret Anlaşması"
        return OriginDocumentRequirements(
            origin_country=origin_country.strip(),
            regime="fta",
            regime_name=regime_name,
            documents=[_EUR1, _MFN_CERT],
            general_documents=_GENERAL_DOCUMENTS,
            caveats=_caveats(regime_name),
            sources=_sources(),
        )

    return OriginDocumentRequirements(
        origin_country=origin_country.strip(),
        regime="mfn",
        regime_name="Tercihli rejim yok (MFN / diğer ülkeler)",
        documents=[_MFN_CERT],
        general_documents=_GENERAL_DOCUMENTS,
        caveats=[
            *_caveats("tercihsiz ithalat"),
            "Ülke GTS/GSP kapsamındaysa İthalat Rejimi Kararı'ndaki sütun ve menşe beyanı ayrıca değerlendirilir.",
        ],
        sources=_sources(),
    )

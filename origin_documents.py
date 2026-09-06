"""Deterministic origin-document rule table for imports into Türkiye.

The table answers one intake question: which movement/origin document does the
stated origin (and, when different, the dispatch country) normally require for
this tariff chapter?  Country facts come from ``countries.py``; the chapter rules
mirror the Customs Union decisions (1/95 for industrial and processed agricultural
goods, 1/98 for basic agricultural goods) and the Türkiye–ECSC free-trade
agreement.  It is intake guidance, never a binding origin decision; product-level
origin rules and current validity are always confirmed against the ministry page.
"""
from __future__ import annotations

import re
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

from countries import PENDING_AGREEMENTS, REGISTRY_CHECKED_AT, Country, find_country

STA_LIST_URL = "https://ticaret.gov.tr/dis-iliskiler/serbest-ticaret-anlasmalari/yururlukte-bulunan-stalar"
IMPORT_REGIME_URL = (
    "https://ticaret.gov.tr/ithalat/ithalat-mevzuati/ithalat-rejimi-karari-igv-karari-ve-ithalat-tebligleri/"
    "1-ithalat-rejimi-kararikarar-sayisi3350karar-metni-ve-tablolar-konsolide-edilmis-olup-gunceldir"
)
_RULES_CHECKED_AT = REGISTRY_CHECKED_AT

# 1/95 sayılı OKK Ek-1: Gümrük Birliği kapsamındaki işlenmiş tarım ürünleri (sanayi payı A.TR ile).
# Headings are 4 or 6 digits; a product whose code starts with one of them is treated as processed.
_PROCESSED_AGRICULTURAL_PREFIXES = (
    "0403", "0405", "071040", "071190", "1517", "1518", "170250", "1704", "1803", "1804", "1805", "1806",
    "1901", "1902", "1903", "1904", "1905", "200190", "200410", "200490", "200520", "200580", "200811",
    "200891", "200899", "2101", "2102", "2103", "2104", "2105", "2106", "2202", "2205", "2207", "2208",
    "2209", "290543", "290544", "330190", "330210", "3501", "3505", "380910", "3823", "382460",
)
# Türkiye–AKÇT STA kapsamı: kömür ve çelik ürünleri (EUR.1 ile; A.TR düzenlenmez).
_ECSC_PREFIXES = (
    "2601", "2619", "2701", "2702", "2704", "7201", "720211", "720219", "7203", "7204", "7205", "7206",
    "7207", "7208", "7209", "7210", "7211", "7212", "7213", "7214", "7215", "7216", "7217", "7218",
    "7219", "7220", "7221", "7222", "7223", "7224", "7225", "7226", "7227", "7228", "7229", "7301", "7302",
)

CustomsUnionRoute = Literal["atr", "eur1_agricultural", "eur1_ecsc"]


def _digits(value: Any) -> str:
    return re.sub(r"\D", "", str(value or ""))


def customs_union_route(gtip: Any) -> Optional[CustomsUnionRoute]:
    """Which document proves preference for EU trade in this tariff line.

    ``None`` means the code is unknown/too short to decide; callers then fall back
    to the generic A.TR answer with a caveat.
    """
    code = _digits(gtip)
    if len(code) < 4:
        return None
    if code.startswith(_ECSC_PREFIXES):
        return "eur1_ecsc"
    chapter = int(code[:2])
    if 1 <= chapter <= 24:
        return "atr" if code.startswith(_PROCESSED_AGRICULTURAL_PREFIXES) else "eur1_agricultural"
    return "atr"


def atr_eligible(gtip: Any) -> bool:
    """True when goods in free circulation in the EU may move with an A.TR."""
    return customs_union_route(gtip) == "atr"


_GENERAL_DOCUMENTS = [
    "Ticari fatura (orijinal)",
    "Taşıma belgesi (konşimento, CMR, havayolu irsaliyesi)",
    "Ambalaj listesi / çeki listesi",
    "Sigorta poliçesi (satış teslimi CIF/CIP değilse)",
    "İthalatçı/yetkili temsilci beyan bilgileri",
]

DocumentCode = Literal[
    "ATR", "EUR1", "EUR_MED", "ORIGIN_DECLARATION", "AGREEMENT_CERT", "SUPPLIER_DECLARATION",
    "GSP_ORIGIN", "CERT_ORIGIN", "SPECIAL",
]


class OriginDocument(BaseModel):
    """One expected movement/origin document with its intake-level applicability."""

    code: DocumentCode
    name: str
    applicability: str = Field(
        ..., description="Belgenin ne zaman ve nasıl istendiğine dair giriş düzeyi açıklama."
    )
    note: str = ""


class OriginDocumentRequirements(BaseModel):
    """Rule-table result for one origin country; intake guidance, not a decision."""

    origin_country: str
    dispatch_country: str | None = None
    gtip: str | None = None
    chapter: int | None = None
    regime: Literal["customs_union", "efta", "fta", "pta", "kktc", "mfn"]
    regime_name: str
    route: CustomsUnionRoute | None = None
    origin_recognised: bool = True
    documents: list[OriginDocument] = Field(default_factory=list, max_length=6)
    general_documents: list[str] = Field(default_factory=list, max_length=8)
    caveats: list[str] = Field(default_factory=list, max_length=8)
    sources: list[dict[str, str]] = Field(default_factory=list, max_length=4)
    checked_at: str = _RULES_CHECKED_AT


_ATR = OriginDocument(
    code="ATR",
    name="A.TR Dolaşım Belgesi",
    applicability=(
        "Gümrük Birliği kapsamındaki sanayi ürünü ve işlenmiş tarım ürünü için serbest dolaşımı "
        "kanıtlar; gümrük vergisi AB sütunundan alınır."
    ),
    note="A.TR menşe ispatı değildir; İGV/EMY için menşe ayrıca tevsik edilir.",
)
_SUPPLIER_DECLARATION = OriginDocument(
    code="SUPPLIER_DECLARATION",
    name="Tedarikçi beyanı veya menşe şahadetnamesi (İGV/EMY için)",
    applicability=(
        "A.TR ile gelen eşyanın AB/Türkiye menşeli olduğu tedarikçi beyanı (uzun dönem beyanı dâhil) "
        "ya da menşe şahadetnamesiyle tevsik edilmezse ilave gümrük vergisi ve ek mali yükümlülük "
        "eşyanın gerçek menşe sütunundan, menşe bilinmiyorsa 'Diğer Ülkeler' sütunundan alınır."
    ),
)
_EUR1_AGRI = OriginDocument(
    code="EUR1",
    name="EUR.1 / EUR-MED Dolaşım Sertifikası (tarım rejimi)",
    applicability=(
        "1-24. fasıl temel tarım ürünleri Gümrük Birliği'ne dâhil değildir; AB menşeli tarım ürünü için "
        "tercih 1/98 sayılı OKK kapsamında EUR.1/EUR-MED veya onaylanmış ihracatçı fatura beyanıyla istenir. "
        "A.TR düzenlenmez."
    ),
    note="Taviz çoğu üründe tarife kontenjanına bağlıdır; kontenjan bakiyesi ayrıca doğrulanır.",
)
_EUR1_ECSC = OriginDocument(
    code="EUR1",
    name="EUR.1 Dolaşım Sertifikası (Türkiye–AKÇT STA)",
    applicability=(
        "Kömür ve çelik (AKÇT) ürünleri Gümrük Birliği dışındadır; AB menşeli AKÇT ürünü için tercih "
        "Türkiye–AKÇT STA kapsamında EUR.1 veya fatura beyanıyla istenir. A.TR düzenlenmez."
    ),
)
_MFN_CERT = OriginDocument(
    code="CERT_ORIGIN",
    name="Menşe Şahadetnamesi (tercihsiz)",
    applicability=(
        "Tercihli rejim uygulanmıyor. Menşe şahadetnamesi yalnızca başka bir mevzuat (kota, "
        "gözetim, İGV/EMY menşe tevsiki, alıcı talebi) istediğinde düzenlenir; vergi tercihi sağlamaz."
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


def _preference_document(country: Country) -> OriginDocument:
    """The proof-of-origin document the country's agreement actually uses."""
    if country.proof == "origin_declaration":
        return OriginDocument(
            code="ORIGIN_DECLARATION", name="Menşe beyanı (ihracatçı, fatura/ticari belge üzerinde)",
            applicability=country.proof_note or "İhracatçının menşe beyanı ile tercih talep edilir.",
            note=f"{country.agreement}: EUR.1 kullanılmaz; beyan metni ve onaylanmış ihracatçı numarası anlaşma ekine uymalıdır.",
        )
    if country.proof == "agreement_certificate":
        return OriginDocument(
            code="AGREEMENT_CERT", name=f"Menşe ispat belgesi ({country.agreement})",
            applicability=country.proof_note or "Anlaşmaya özgü menşe ispat belgesi ile tercih talep edilir.",
            note="Belge biçimi ve düzenleyen kurum anlaşma ekinden doğrulanmalıdır.",
        )
    return OriginDocument(
        code="EUR1", name="EUR.1 Hareket Belgesi",
        applicability=country.proof_note or "Tercihli menşe talep ediliyorsa EUR.1 düzenlenir.",
        note=f"{country.agreement}: menşe kuralı ürün bazlıdır; anlaşma ek kuralları doğrulanmalıdır.",
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


def _customs_union_documents(route: CustomsUnionRoute | None) -> tuple[list[OriginDocument], list[str]]:
    if route == "eur1_agricultural":
        return [_EUR1_AGRI, _MFN_CERT], ["Tarım ürününde A.TR geçerli değildir; tercih için EUR.1/EUR-MED gerekir."]
    if route == "eur1_ecsc":
        return [_EUR1_ECSC, _MFN_CERT], ["AKÇT ürününde A.TR geçerli değildir; tercih için EUR.1 gerekir."]
    caveats = [] if route == "atr" else ["Tarife kodu verilmediği için sanayi ürünü varsayıldı; tarım (1-24. fasıl) veya AKÇT ürününde belge EUR.1'dir."]
    return [_ATR, _SUPPLIER_DECLARATION], caveats


def origin_document_requirements(
    origin_country: str,
    gtip: str | None = None,
    dispatch_country: str | None = None,
) -> Optional[OriginDocumentRequirements]:
    """Match an origin (and dispatch) country plus tariff chapter to the expected documents."""
    origin_text = str(origin_country or "").strip()
    if not origin_text:
        return None
    origin = find_country(origin_text)
    dispatch = find_country(dispatch_country) if dispatch_country else None
    code = _digits(gtip)
    chapter = int(code[:2]) if len(code) >= 2 else None
    route = customs_union_route(code) if code else None
    common = {
        "origin_country": origin_text,
        "dispatch_country": (dispatch.name if dispatch else (str(dispatch_country).strip() or None)) if dispatch_country else None,
        "gtip": code or None,
        "chapter": chapter,
        "route": route,
        "general_documents": _GENERAL_DOCUMENTS,
        "sources": _sources(),
    }

    if origin is None:
        return OriginDocumentRequirements(
            regime="mfn", regime_name="Menşe ülke tanınmadı", origin_recognised=False,
            documents=[_MFN_CERT],
            caveats=[
                f"'{origin_text}' bilinen ülke listesinde bulunamadı; adı Türkçe yazın (ör. Almanya, Çin, Güney Kore). "
                "Tercihli rejim varsayılmadı.",
                *_caveats("tercihsiz ithalat"),
            ],
            **common,
        )

    if origin.regime == "eu":
        documents, extra = _customs_union_documents(route)
        if dispatch and dispatch.regime != "eu":
            extra.append(
                f"Eşya {dispatch.name} üzerinden sevk ediliyor: A.TR yalnız AB/Türkiye gümrük idarelerince düzenlenir; "
                "AB dışından sevkte A.TR ve tercih uygulanabilirliği gümrük idaresiyle teyit edilmelidir."
            )
        return OriginDocumentRequirements(
            regime="customs_union", regime_name="Türkiye – AB Gümrük Birliği",
            documents=documents, caveats=[*extra, *_caveats("Gümrük Birliği")], **common,
        )

    if origin.regime == "kktc":
        return OriginDocumentRequirements(
            regime="kktc", regime_name="Türkiye – KKTC özel düzenlemesi",
            documents=[_KKTC_DOC], caveats=_caveats("KKTC düzenlemesi"), **common,
        )

    documents: list[OriginDocument] = []
    caveats: list[str] = []
    # Third-country goods in free circulation in the EU: A.TR removes customs duty,
    # but İGV/EMY still follow the real origin unless EU/TR origin is proven.
    if dispatch and dispatch.regime == "eu" and origin.regime != "eu":
        if route == "atr" or route is None:
            documents.append(
                OriginDocument(
                    code="ATR", name="A.TR Dolaşım Belgesi (serbest dolaşım, gümrük vergisi için)",
                    applicability=(
                        f"{origin.name} menşeli eşya AB'de serbest dolaşımdaysa A.TR ile gümrük vergisi AB sütunundan "
                        "alınır; ilave gümrük vergisi ve ek mali yükümlülük ise menşe ülkesi sütunundan tahsil edilir."
                    ),
                    note="A.TR menşe ispatı değildir; tercihli menşe için ayrıca anlaşma belgesi gerekir.",
                )
            )
            caveats.append(
                f"Sevk ülkesi {dispatch.name} (AB), menşe {origin.name}: A.TR gümrük vergisini kaldırır, İGV/EMY'yi kaldırmaz."
            )
        else:
            caveats.append(
                f"Sevk ülkesi {dispatch.name} (AB) olsa da bu tarife satırı için A.TR düzenlenmez (tarım/AKÇT); "
                "gümrük vergisi menşe ülkesine göre uygulanır."
            )

    if origin.regime in {"efta", "fta", "pta"}:
        regime_name = {
            "efta": "Türkiye – EFTA Serbest Ticaret Anlaşması",
            "fta": origin.agreement or "Türkiye – Serbest Ticaret Anlaşması",
            "pta": origin.agreement or "Türkiye – Tercihli Ticaret Anlaşması",
        }[origin.regime]
        documents.extend([_preference_document(origin), _MFN_CERT])
        if origin.regime == "pta":
            caveats.append("Tercihli ticaret anlaşması yalnız anlaşma listesindeki ürünleri kapsar; ürün listede değilse tercih yoktur.")
        return OriginDocumentRequirements(
            regime=origin.regime, regime_name=regime_name,
            documents=documents, caveats=[*caveats, *_caveats(regime_name)], **common,
        )

    pending = PENDING_AGREEMENTS.get(origin.key)
    documents.append(_MFN_CERT)
    return OriginDocumentRequirements(
        regime="mfn", regime_name="Tercihli rejim yok (MFN / diğer ülkeler)",
        documents=documents,
        caveats=[
            *([pending] if pending else []),
            *caveats,
            *_caveats("tercihsiz ithalat"),
            "Ülke GTS/GSP kapsamındaysa İthalat Rejimi Kararı'ndaki sütun ve menşe beyanı ayrıca değerlendirilir.",
        ],
        **common,
    )

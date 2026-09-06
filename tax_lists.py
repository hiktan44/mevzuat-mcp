"""GTİP bazlı ÖTV kapsam sorgusu (4760 sayılı Kanun ekli (I)-(IV) sayılı listeler).

Veri kaynağı ``data/official/excise_tax_lists.json``; 4760 sayılı Özel Tüketim Vergisi
Kanununun Resmî Gazete'de yayımlanan güncel metninin ekli listelerinden çıkarılmıştır.

Listelerde iki oran sütunu vardır: kanun metnindeki oran/tutar ve Cumhurbaşkanı
kararlarıyla yeniden tespit edilen "uygulanacak" oran/tutar. İkinci sütun boşsa
kanuni değer uygulanır. (III) sayılı listede bazı hücreler resmî PDF'te tek parça
basıldığı için sütun eşlemesi doğrulanamamıştır; bu bölümlerde yalnız kapsam bilgisi
verilir, oran gösterilmez.

KDV tarafı bu modülde yer almaz: 2007/13033 sayılı Kararın ekli listeleri GTİP tablosu
değil, fasıl ve pozisyonlara atıf yapan anlatı biçimindedir ve güncel konsolide metni
bu ortamdan doğrulanabilir bir resmî kaynaktan alınamamıştır (bkz. PROJECT_NOTES).
"""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any

from trade_measures import code_matches, normalise_code

logger = logging.getLogger(__name__)

DATA_FILE = "excise_tax_lists.json"
LEGAL_BASIS = "4760 sayılı Özel Tüketim Vergisi Kanunu ekli (I)-(IV) sayılı listeler"

# Listeye göre matrah/uygulama notu – beyanname hazırlarken müşavirin bilmesi gerekenler.
LIST_NOTES = {
    "I": "Petrol ürünleri; vergi maktu tutar olarak (birim başına TL) alınır, ithalatta gümrük idaresince tahsil edilir.",
    "II": "Motorlu taşıtlar; vergi ilk iktisapta oransal olarak alınır, matrah ÖTV hariç satış bedelidir.",
    "III": "Alkollü içecekler, tütün mamulleri ve kolalı gazozlar; oransal vergi ile asgari maktu vergi birlikte uygulanır.",
    "IV": "Lüks tüketim ve dayanıklı tüketim malları; vergi ithalatta oransal olarak alınır.",
}

_VALUE_LABELS = {
    "tax_rate": "Kanuni vergi oranı (%)",
    "applied_tax_rate": "Uygulanacak vergi oranı (%)",
    "tax_amount": "Kanuni vergi tutarı (TL)",
    "applied_tax_amount": "Uygulanacak vergi tutarı (TL)",
    "minimum_specific_tax": "Asgari maktu vergi tutarı (TL)",
    "applied_minimum_specific_tax": "Uygulanacak asgari maktu vergi tutarı (TL)",
    "specific_tax": "Maktu vergi tutarı (TL)",
    "applied_specific_tax": "Uygulanacak maktu vergi tutarı (TL)",
    "unit": "Birim",
}


def _default_data_dir() -> Path:
    override = os.environ.get("OFFICIAL_DATA_DIR")
    if override:
        return Path(override)
    return Path(__file__).resolve().parent / "data" / "official"


def list_label(list_name: str, cetvel: str | None) -> str:
    return f"({list_name}) sayılı liste" + (f" ({cetvel}) cetveli" if cetvel else "")


# Resmî listede eşya tanımı kod satırının hem üstüne hem altına sarar; ayrıştırma sırasında
# bir önceki satırın kuyruğu başa eklenebiliyor. Cümle başı büyük harften önceki parçayı atarız.
_SENTENCE_START_RE = re.compile(r"(?:^|\s)(\(?[A-ZÇĞİÖŞÜ0-9])")


def clean_description(text: str) -> str:
    """Açıklamanın başındaki, önceki satırdan sarkan küçük harfli parçayı ayıklar."""
    value = (text or "").strip()
    if not value or value[:1].isupper() or value[:1].isdigit():
        return value
    match = _SENTENCE_START_RE.search(value)
    return value[match.start(1):].strip() if match else value


class ExciseTaxIndex:
    """GTİP -> ÖTV listesi eşlemesi; salt okunur, tohum dosyasından yüklenir."""

    def __init__(self, data_dir: str | Path | None = None) -> None:
        self._path = Path(data_dir or _default_data_dir()) / DATA_FILE
        self._payload: dict[str, Any] = {}
        self._entries: list[dict[str, Any]] = []
        self._load()

    def _load(self) -> None:
        try:
            self._payload = json.loads(self._path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            logger.warning("ÖTV liste dosyası bulunamadı: %s", self._path)
            return
        except (OSError, ValueError):
            logger.exception("ÖTV liste dosyası okunamadı: %s", self._path)
            return
        for section in self._payload.get("sections", []):
            columns = list(section.get("value_columns") or [])
            for row in section.get("rows", []):
                code = normalise_code(row.get("code", ""))
                if not code:
                    continue
                self._entries.append({
                    "code": code,
                    "raw_code": row.get("code", ""),
                    "description": clean_description(row.get("description")),
                    "list": section.get("list"),
                    "cetvel": section.get("cetvel"),
                    "rates_verified": bool(section.get("rates_verified")),
                    "values": {key: row[key] for key in columns if row.get(key)},
                })

    @property
    def ready(self) -> bool:
        return bool(self._entries)

    def status(self) -> dict[str, Any]:
        return {
            "ready": self.ready,
            "entry_count": len(self._entries),
            "legal_basis": LEGAL_BASIS,
            "source_url": self._payload.get("source_url"),
            "sections": [
                {
                    "list": section.get("list"),
                    "cetvel": section.get("cetvel"),
                    "row_count": section.get("row_count"),
                    "rates_verified": section.get("rates_verified"),
                }
                for section in self._payload.get("sections", [])
            ],
        }

    def lookup(self, gtip: str) -> dict[str, Any]:
        """Sorgulanan GTİP'in ÖTV kapsamını döndürür.

        En uzun (en özel) kod eşleşmesi öncelikli sıralanır; kısa pozisyon satırları
        (ör. 87.03) daha uzun sorgular için de kapsam bildirir.
        """
        code = normalise_code(gtip)
        if not code:
            return {"gtip": gtip, "in_scope": False, "matches": [], "warnings": [], "legal_basis": LEGAL_BASIS}
        matches = [entry for entry in self._entries if code_matches(entry["code"], code)]
        matches.sort(key=lambda entry: len(entry["code"]), reverse=True)

        results: list[dict[str, Any]] = []
        warnings: list[str] = []
        for entry in matches:
            label = list_label(entry["list"], entry["cetvel"])
            values = {
                _VALUE_LABELS.get(key, key): value
                for key, value in entry["values"].items()
                if entry["rates_verified"] or key == "unit"
            }
            results.append({
                "matched_code": entry["raw_code"],
                "list": entry["list"],
                "cetvel": entry["cetvel"],
                "list_label": label,
                "description": entry["description"],
                "rates_verified": entry["rates_verified"],
                "values": values,
                "note": LIST_NOTES.get(entry["list"], ""),
            })

        neighbours: list[dict[str, str]] = []
        if not results and len(code) >= 4:
            # Kanun metnindeki kodlar Armonize Sistem revizyonlarıyla yeniden numaralandırılmış
            # olabilir (ör. cep telefonu 8517.12 -> 8517.13). Aynı pozisyondaki satırları uyarı
            # olarak bildiririz; sessizce "kapsam dışı" demek beyanname hatasına yol açar.
            for entry in self._entries:
                if entry["code"][:4] == code[:4]:
                    neighbours.append({
                        "matched_code": entry["raw_code"],
                        "list_label": list_label(entry["list"], entry["cetvel"]),
                        "description": entry["description"][:120],
                    })
            if neighbours:
                warnings.append(
                    f"Bu GTİP listelerde yok, ancak aynı pozisyonda ({code[:4]}) "
                    f"{len(neighbours)} ÖTV satırı var. Kanun metnindeki kodlar Armonize Sistem "
                    "revizyonlarıyla yeniden numaralandırılmış olabilir; eşyanızın karşılığını doğrulayın."
                )

        if results:
            first = results[0]
            warnings.append(
                f"Eşya ÖTV kapsamındadır: {first['list_label']}, {first['matched_code']}. {first['note']}"
            )
            if not first["rates_verified"]:
                warnings.append(
                    "Bu listede oran sütunları resmî metinde birleşik basıldığı için otomatik okunmadı; "
                    "oran ve asgari maktu vergi tutarını Kanun ekinden doğrulayın."
                )
            else:
                warnings.append(
                    "Kanundaki oran/tutarlar Cumhurbaşkanı kararlarıyla değiştirilebilir; "
                    "beyanname öncesi yürürlükteki değeri doğrulayın."
                )
        return {
            "gtip": code,
            "in_scope": bool(results),
            "matches": results[:10],
            "match_count": len(results),
            "related_positions": neighbours[:10],
            "warnings": warnings,
            "legal_basis": LEGAL_BASIS,
            "source_url": self._payload.get("source_url"),
        }


def summary_lines(report: dict[str, Any]) -> list[str]:
    """MCP araç çıktısı için insan okunur özet."""
    if not report.get("in_scope"):
        lines = ["ÖTV: Bu GTİP 4760 sayılı Kanunun ekli listelerinde bulunamadı (ÖTV'ye tabi görünmüyor)."]
        for related in report.get("related_positions", [])[:5]:
            lines.append(f"  ? Aynı pozisyonda: {related['matched_code']} · {related['list_label']}")
        lines.extend(f"  ! {warning}" for warning in report.get("warnings", []))
        return lines
    lines = [f"ÖTV kapsamı [{report['legal_basis']}]:"]
    for match in report["matches"][:5]:
        parts = [f"  - {match['matched_code']} · {match['list_label']}"]
        if match["description"]:
            parts.append(f" · {match['description'][:80]}")
        if match["values"]:
            rendered = ", ".join(f"{key}: {value}" for key, value in match["values"].items())
            parts.append(f" · {rendered}")
        lines.append("".join(parts))
    lines.extend(f"  ! {warning}" for warning in report.get("warnings", []))
    return lines

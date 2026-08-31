"""Reproducible metrics for the source-anchored customs classification benchmark."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

_OFFICIAL_HOSTS = {"taxation-customs.ec.europa.eu", "eur-lex.europa.eu"}


def _code(value: Any) -> str:
    return re.sub(r"\D", "", str(value or ""))


def load_cases(path: str | Path) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for line_number, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        case = json.loads(line)
        required = {"id", "description", "expected_cn8", "accepted_hs6", "source_page", "source_url", "source_sha256"}
        missing = required - set(case)
        if missing:
            raise ValueError(f"Benchmark satırı {line_number} eksik alanlar içeriyor: {sorted(missing)}")
        if (urlsplit(case["source_url"]).hostname or "").lower() not in _OFFICIAL_HOSTS:
            raise ValueError(f"Benchmark satırı {line_number} resmî olmayan kaynak içeriyor.")
        if not re.fullmatch(r"[0-9a-f]{64}", str(case["source_sha256"])):
            raise ValueError(f"Benchmark satırı {line_number} geçersiz SHA-256 içeriyor.")
        case["expected_cn8"] = [_code(item) for item in case["expected_cn8"]]
        case["accepted_hs6"] = [_code(item) for item in case["accepted_hs6"]]
        if not all(len(item) == 8 for item in case["expected_cn8"]):
            raise ValueError(f"Benchmark satırı {line_number} CN8 dışı hedef içeriyor.")
        if not all(len(item) == 6 for item in case["accepted_hs6"]):
            raise ValueError(f"Benchmark satırı {line_number} HS6 dışı hedef içeriyor.")
        cases.append(case)
    if not cases:
        raise ValueError("Benchmark veri seti boş.")
    return cases


def evaluate_predictions(cases: list[dict[str, Any]], predictions: list[dict[str, Any]]) -> dict[str, Any]:
    by_id = {str(item.get("id")): item for item in predictions}
    totals = {"top1_hs6": 0, "top3_hs6": 0, "top1_cn8": 0, "top3_cn8": 0, "abstained": 0}
    details: list[dict[str, Any]] = []
    for case in cases:
        prediction = by_id.get(case["id"], {})
        codes = [_code(item) for item in prediction.get("candidates", []) if _code(item)][:3]
        expected_cn8 = set(case["expected_cn8"])
        accepted_hs6 = set(case["accepted_hs6"])
        top1_hs6 = bool(codes and codes[0][:6] in accepted_hs6)
        top3_hs6 = any(code[:6] in accepted_hs6 for code in codes)
        top1_cn8 = bool(codes and len(codes[0]) >= 8 and codes[0][:8] in expected_cn8)
        top3_cn8 = any(len(code) >= 8 and code[:8] in expected_cn8 for code in codes)
        totals["top1_hs6"] += int(top1_hs6)
        totals["top3_hs6"] += int(top3_hs6)
        totals["top1_cn8"] += int(top1_cn8)
        totals["top3_cn8"] += int(top3_cn8)
        totals["abstained"] += int(not codes)
        details.append(
            {
                "id": case["id"],
                "candidates": codes,
                "top1_hs6": top1_hs6,
                "top3_hs6": top3_hs6,
                "top1_cn8": top1_cn8,
                "top3_cn8": top3_cn8,
            }
        )
    count = len(cases)
    return {
        "case_count": count,
        "metrics": {key: round(value / count, 4) for key, value in totals.items()},
        "counts": totals,
        "details": details,
        "warning": "Bu ölçüm AB CN8 karar örnekleridir; Türk GTİP12 doğruluğu veya hukuki bağlayıcılık ölçümü değildir.",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("predictions", help="id ve candidates alanlarını içeren JSON dosyası")
    parser.add_argument(
        "--cases",
        default=str(Path(__file__).with_name("benchmarks") / "customs_classification_v1.jsonl"),
    )
    args = parser.parse_args()
    cases = load_cases(args.cases)
    predictions = json.loads(Path(args.predictions).read_text(encoding="utf-8"))
    print(json.dumps(evaluate_predictions(cases, predictions), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

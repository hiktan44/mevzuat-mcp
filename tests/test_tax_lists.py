from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tax_lists import ExciseTaxIndex, clean_description, list_label, summary_lines


def _write_fixture(directory: Path) -> None:
    payload = {
        "source_url": "https://www.mevzuat.gov.tr/MevzuatMetin/1.5.4760.pdf",
        "sections": [
            {
                "list": "II",
                "cetvel": None,
                "value_columns": ["tax_rate", "applied_tax_rate"],
                "rates_verified": True,
                "row_count": 1,
                "rows": [{"code": "87.03", "description": "Binek otomobilleri", "tax_rate": "45", "applied_tax_rate": "80"}],
            },
            {
                "list": "III",
                "cetvel": "A",
                "value_columns": ["tax_rate", "minimum_specific_tax"],
                "rates_verified": False,
                "row_count": 1,
                "rows": [{"code": "2202.10.00.00.13", "description": "Kolalı gazozlar", "tax_rate": "25"}],
            },
            {
                "list": "IV",
                "cetvel": None,
                "value_columns": ["tax_rate", "applied_tax_rate"],
                "rates_verified": True,
                "row_count": 2,
                "rows": [
                    {"code": "8517.12.00.00.11", "description": "Telsiz telefon cihazları", "tax_rate": "40"},
                    {"code": "1604.31.00.00.00", "description": "Havyar", "tax_rate": "20"},
                ],
            },
        ],
    }
    (directory / "excise_tax_lists.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


class ExciseTaxIndexTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = Path(self._tmp.name)
        _write_fixture(self.dir)
        self.index = ExciseTaxIndex(self.dir)

    def test_index_loads_every_row(self) -> None:
        self.assertTrue(self.index.ready)
        self.assertEqual(self.index.status()["entry_count"], 4)

    def test_position_row_covers_longer_gtip(self) -> None:
        report = self.index.lookup("870323100011")
        self.assertTrue(report["in_scope"])
        self.assertEqual(report["matches"][0]["matched_code"], "87.03")
        self.assertEqual(report["matches"][0]["values"]["Kanuni vergi oranı (%)"], "45")
        self.assertEqual(report["matches"][0]["values"]["Uygulanacak vergi oranı (%)"], "80")

    def test_unverified_section_hides_rates_and_says_so(self) -> None:
        report = self.index.lookup("2202100000 13".replace(" ", ""))
        match = report["matches"][0]
        self.assertFalse(match["rates_verified"])
        self.assertNotIn("Kanuni vergi oranı (%)", match["values"])
        self.assertTrue(any("doğrulayın" in warning for warning in report["warnings"]))

    def test_renumbered_position_is_reported_instead_of_silent_miss(self) -> None:
        # 8517.13 (akıllı telefon) Kanun metninde yok; aynı pozisyondaki 8517.12 satırı uyarılmalı.
        report = self.index.lookup("851713000000")
        self.assertFalse(report["in_scope"])
        self.assertTrue(report["related_positions"])
        self.assertEqual(report["related_positions"][0]["matched_code"], "8517.12.00.00.11")
        self.assertTrue(any("yeniden numaralandırılmış" in warning for warning in report["warnings"]))

    def test_out_of_scope_gtip_reports_nothing(self) -> None:
        report = self.index.lookup("940360000000")
        self.assertFalse(report["in_scope"])
        self.assertEqual(report["related_positions"], [])
        self.assertEqual(summary_lines(report)[0][:4], "ÖTV:")

    def test_longest_code_wins_over_position_row(self) -> None:
        index = ExciseTaxIndex(self.dir)
        report = index.lookup("220210000013")
        self.assertEqual(report["matches"][0]["matched_code"], "2202.10.00.00.13")

    def test_empty_and_invalid_input(self) -> None:
        for value in ("", "   ", "abc"):
            report = self.index.lookup(value)
            self.assertFalse(report["in_scope"])
            self.assertEqual(report["matches"], [])

    def test_missing_data_file_degrades_quietly(self) -> None:
        with tempfile.TemporaryDirectory() as empty:
            index = ExciseTaxIndex(empty)
            self.assertFalse(index.ready)
            self.assertFalse(index.lookup("870300")["in_scope"])

    def test_list_label_renders_cetvel(self) -> None:
        self.assertEqual(list_label("III", "A"), "(III) sayılı liste (A) cetveli")
        self.assertEqual(list_label("IV", None), "(IV) sayılı liste")

    def test_clean_description_drops_leading_continuation(self) -> None:
        self.assertEqual(clean_description("cihazları ve el kurutma Kordonsuz ahizeli"), "Kordonsuz ahizeli")
        self.assertEqual(clean_description("Havyar"), "Havyar")
        self.assertEqual(clean_description(""), "")


class ShippedExciseDataTests(unittest.TestCase):
    """Depoyla birlikte gelen resmî tohum dosyasının bütünlüğü."""

    def setUp(self) -> None:
        self.index = ExciseTaxIndex()
        if not self.index.ready:
            self.skipTest("resmî ÖTV tohum dosyası bulunamadı")

    def test_all_four_lists_are_present(self) -> None:
        lists = {section["list"] for section in self.index.status()["sections"]}
        self.assertEqual(lists, {"I", "II", "III", "IV"})

    def test_known_products_resolve_to_their_official_list(self) -> None:
        self.assertEqual(self.index.lookup("870323100011")["matches"][0]["list"], "II")
        self.assertEqual(self.index.lookup("160431000000")["matches"][0]["list"], "IV")
        self.assertEqual(self.index.lookup("271012410000")["matches"][0]["list"], "I")

    def test_ordinary_industrial_goods_stay_out_of_scope(self) -> None:
        for gtip in ("730640209000", "847130000000", "940360000000"):
            self.assertFalse(self.index.lookup(gtip)["in_scope"], gtip)


class TariffEngineAttachmentTests(unittest.TestCase):
    """Tarife sorgusuna ÖTV kapsamının iliştirilmesi."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        _write_fixture(Path(self._tmp.name))

    def _result(self, gtip: str):
        from tariff_engine import TariffLookupResult

        return TariffLookupResult(status="matched", gtip=gtip, as_of="2026-01-01T00:00:00Z")

    def test_lookup_result_carries_excise_scope_and_warning(self) -> None:
        from tariff_engine import TariffEngine

        engine = TariffEngine.__new__(TariffEngine)
        engine.excise_tax = ExciseTaxIndex(self._tmp.name)
        result = self._result("870323100011")
        engine._attach_excise_tax(result)
        self.assertIsNotNone(result.excise_tax)
        self.assertTrue(result.excise_tax["in_scope"])
        self.assertTrue(any("ÖTV kapsamındadır" in warning for warning in result.warnings))

    def test_engine_without_excise_index_stays_silent(self) -> None:
        from tariff_engine import TariffEngine

        engine = TariffEngine.__new__(TariffEngine)
        engine.excise_tax = None
        result = self._result("870323100011")
        engine._attach_excise_tax(result)
        self.assertIsNone(result.excise_tax)
        self.assertEqual(result.warnings, [])

    def test_broken_index_does_not_break_the_lookup(self) -> None:
        from tariff_engine import TariffEngine

        class Exploding:
            def lookup(self, _gtip: str) -> dict:
                raise RuntimeError("veri bozuk")

        engine = TariffEngine.__new__(TariffEngine)
        engine.excise_tax = Exploding()
        result = self._result("870323100011")
        with self.assertLogs("tariff_engine", level="ERROR"):
            engine._attach_excise_tax(result)
        self.assertIsNone(result.excise_tax)


if __name__ == "__main__":
    unittest.main()

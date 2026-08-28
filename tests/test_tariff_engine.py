from __future__ import annotations

import io
import unittest
import zipfile

from openpyxl import Workbook

from tariff_engine import (
    LandedCostInput,
    TariffEngine,
    _number,
    _zip_name,
    calculate_landed_cost,
)


def _xlsx(rows: list[list[object]], title: str = "84") -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = title
    for row in rows:
        sheet.append(row)
    output = io.BytesIO()
    workbook.save(output)
    return output.getvalue()


class TariffParsingTests(unittest.TestCase):
    def test_numeric_zero_is_a_real_rate(self) -> None:
        self.assertEqual(_number(0), (0.0, "0"))

    def test_turkish_dos_zip_name_is_decoded(self) -> None:
        info = zipfile.ZipInfo("ÿGV/EK-1.xlsx")
        self.assertEqual(_zip_name(info), "İGV/EK-1.xlsx")

    def test_official_industry_columns_are_parsed_with_provenance(self) -> None:
        workbook = _xlsx(
            [
                ["84. FASIL"],
                ["GTİP", "DİPNOT", "1", "2", "3", "4", "5", "6", "7"],
                ["840120001011", None, 0, 3.7, 0, 0, 0, 0, 3.7],
            ]
        )
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, "w") as output:
            output.writestr("II Sayılı Liste (84-85-90-97. Fasıllar).xlsx", workbook)
        parsed = TariffEngine._parse_archive(
            archive.getvalue(),
            {
                "id": "import_regime",
                "title": "İthalat Rejimi",
                "landing_url": "https://ticaret.gov.tr/test",
                "measure_family": "customs_duty",
                "valid_from": "2026-01-01",
            },
            "https://ticaret.gov.tr/data/test.zip",
            "a" * 64,
            "2026-08-28T00:00:00+03:00",
        )
        rows = [item for item in parsed.measures if item["gtip"] == "840120001011"]
        self.assertEqual(len(rows), 7)
        self.assertEqual(rows[0]["rate"], 0.0)
        self.assertEqual(rows[-1]["country_group"], "7")
        self.assertEqual(rows[-1]["source_row"], 3)

    def test_country_column_resolution_is_deterministic(self) -> None:
        labels = {"1", "2", "3", "4", "5", "6", "7"}
        self.assertEqual(TariffEngine._matching_group("Almanya", labels, {}, "840120001011")[0], "1")
        self.assertEqual(TariffEngine._matching_group("Çin", labels, {}, "840120001011")[0], "7")
        self.assertEqual(TariffEngine._matching_group("Katar", labels, {}, "840120001011")[0], "2")


class LandedCostTests(unittest.TestCase):
    def test_missing_rates_block_the_total(self) -> None:
        result = calculate_landed_cost(LandedCostInput(invoice_value=1000, vat_rate=20))
        self.assertEqual(result.status, "partial")
        self.assertIsNone(result.landed_total)
        self.assertIn("Gümrük vergisi oranı", result.missing_rates)

    def test_full_formula_is_reproducible(self) -> None:
        result = calculate_landed_cost(
            LandedCostInput(
                invoice_value=1000,
                freight=100,
                insurance=10,
                other_costs=20,
                quantity=10,
                customs_duty_rate=10,
                additional_duty_rate=5,
                vat_rate=20,
            )
        )
        self.assertEqual(result.status, "complete")
        self.assertEqual(result.customs_value, 1110)
        self.assertEqual(result.landed_total, 1555.8)
        self.assertEqual(result.unit_landed_cost, 155.58)

    def test_surveillance_uplift_requires_declared_certificate_state(self) -> None:
        result = calculate_landed_cost(
            LandedCostInput(
                invoice_value=1000,
                quantity=100,
                surveillance_unit_value=20,
                has_surveillance_certificate=False,
                customs_duty_rate=0,
                additional_duty_rate=0,
                vat_rate=20,
            )
        )
        self.assertEqual(result.customs_value, 2000)
        self.assertTrue(result.warnings)


if __name__ == "__main__":
    unittest.main()

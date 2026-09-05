from __future__ import annotations

import asyncio
from datetime import date

import httpx
import pytest

import exchange_rates as xr

FIXTURE = """<?xml version="1.0" encoding="UTF-8"?>
<Tarih_Date Tarih="04.09.2026" Date="09/04/2026" Bulten_No="2026/170">
  <Currency CrossOrder="0" Kod="USD" CurrencyCode="USD">
    <Unit>1</Unit><Isim>ABD DOLARI</Isim><CurrencyName>US DOLLAR</CurrencyName>
    <ForexBuying>41.9012</ForexBuying><ForexSelling>41.9767</ForexSelling>
    <BanknoteBuying>41.8719</BanknoteBuying><BanknoteSelling>42.0397</BanknoteSelling>
  </Currency>
  <Currency CrossOrder="9" Kod="EUR" CurrencyCode="EUR">
    <Unit>1</Unit><Isim>EURO</Isim><CurrencyName>EURO</CurrencyName>
    <ForexBuying>48.9012</ForexBuying><ForexSelling>48.9893</ForexSelling>
    <BanknoteBuying>48.8670</BanknoteBuying><BanknoteSelling>49.0628</BanknoteSelling>
  </Currency>
  <Currency CrossOrder="3" Kod="JPY" CurrencyCode="JPY">
    <Unit>100</Unit><Isim>JAPON YENI</Isim><CurrencyName>JAPENESE YEN</CurrencyName>
    <ForexBuying>28.2451</ForexBuying><ForexSelling>28.4323</ForexSelling>
    <BanknoteBuying></BanknoteBuying><BanknoteSelling></BanknoteSelling>
  </Currency>
</Tarih_Date>
"""


def test_parse_bulletin_reads_rates_and_units():
    bulletin = xr.parse_bulletin(FIXTURE, "https://example.test/today.xml")
    assert bulletin.bulletin_date == date(2026, 9, 4)
    assert bulletin.bulletin_no == "2026/170"
    assert bulletin.quote("usd").forex_selling == 41.9767
    jpy = bulletin.quote("JPY")
    assert jpy.unit == 100
    assert round(jpy.customs_rate, 6) == round(28.4323 / 100, 6)
    assert bulletin.quote("TL").customs_rate == 1.0
    with pytest.raises(xr.ExchangeRateError):
        bulletin.quote("XAU")


def test_candidate_days_skip_weekends_and_start_the_day_before():
    days = xr.candidate_bulletin_days(date(2026, 9, 7))  # Pazartesi
    assert days[0] == date(2026, 9, 4)  # Cuma
    assert all(day.weekday() < 5 for day in days)
    assert xr.candidate_bulletin_days(date(2026, 9, 4))[0] == date(2026, 9, 3)


def _service(available: dict[str, str]) -> tuple[xr.ExchangeRateService, list[str]]:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        body = available.get(str(request.url))
        if body is None:
            return httpx.Response(404)
        return httpx.Response(200, text=body)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return xr.ExchangeRateService(client), seen


def test_customs_quote_uses_previous_business_day_bulletin():
    friday = xr.archive_url(date(2026, 9, 4))
    service, seen = _service({friday: FIXTURE})
    result = asyncio.run(service.customs_quote("USD", date(2026, 9, 7)))
    assert result["bulletin_date"] == "2026-09-04"
    assert result["rate"] == 41.9767
    assert result["basis"] == "forex_selling"
    assert "Gümrük Kanunu md. 30" in result["legal_basis"]
    assert seen == [friday]


def test_customs_quote_walks_back_over_holidays_and_caches():
    fixture = FIXTURE.replace('Tarih="04.09.2026"', 'Tarih="27.08.2026"')
    thursday = xr.archive_url(date(2026, 8, 27))
    service, seen = _service({thursday: fixture})
    # 31 Ağustos Pazartesi: 28 Ağustos (Cuma) bülteni yok, 27 Ağustos bulunmalı
    result = asyncio.run(service.customs_quote("EUR", date(2026, 8, 31)))
    assert result["bulletin_date"] == "2026-08-27"
    assert seen == [xr.archive_url(date(2026, 8, 28)), thursday]
    asyncio.run(service.customs_quote("EUR", date(2026, 8, 31)))
    assert len(seen) == 2  # both hit and miss cached


def test_customs_quote_fails_clearly_when_no_bulletin():
    service, _ = _service({})
    with pytest.raises(xr.ExchangeRateError):
        asyncio.run(service.customs_quote("USD", date(2026, 9, 7)))


def test_parse_registration_date_accepts_turkish_format():
    assert xr.parse_registration_date("05.09.2026") == date(2026, 9, 5)
    assert xr.parse_registration_date("2026-09-05") == date(2026, 9, 5)
    assert xr.parse_registration_date("") is None
    with pytest.raises(xr.ExchangeRateError):
        xr.parse_registration_date("bugün")

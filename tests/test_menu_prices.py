"""가격·통화의 모호성 및 환율 캐시를 네트워크 없이 확인한다."""
from datetime import date
from email.utils import formatdate

import httpx
import pytest

from core import menu_prices as prices


RATE = {"base": "EUR", "quote": "KRW", "date": "2026-11-04", "rate": 1501.84}


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    monkeypatch.setattr(prices, "_today", lambda: date(2026, 11, 4))
    prices._CACHE.clear()
    monkeypatch.setattr(prices, "_BLOCKED_UNTIL", 0)
    def no_network(*args, **kwargs):
        raise AssertionError("Unexpected real FX request")
    monkeypatch.setattr(prices.httpx, "get", no_network)


@pytest.mark.parametrize("raw, amount", [("14,90 €", "14.90"), ("EUR 1.234,50", "1234.50"),
                                        ("1,234.50 EUR", "1234.50"), ("€1 234,50", "1234.50"),
                                        ("€1\u00a0234,50", "1234.50"), ("EUR 1.234", "1234"),
                                        ("EUR 0", "0"), ("eur 14.9", "14.9")])
def test_single_price_decimal_formats(raw, amount):
    result = prices.price_info(raw, fx_data={**RATE, "rate": 100})
    assert result["display"] == raw
    assert result["currency"] == "EUR"
    assert result["krw"] == f"약 {prices.Decimal(amount) * 100:,.0f}원"
    assert result["date"] == RATE["date"]


@pytest.mark.parametrize("raw", ["€12–15", "€12/15", "€12 + €3", "from €12", "12,34.50 EUR", "1.2.3 EUR",
                                 "0.123 EUR", "€ 12 34", "EUR -1", "EUR 1e4", "EUR 12 USD"])
def test_compound_or_invalid_price_preserves_raw_without_conversion(raw):
    result = prices.price_info(raw)
    assert result["display"] == raw and result["krw"] == ""


@pytest.mark.parametrize("raw", ["14,90", "$14.90", "¥1400", "￥1400"])
def test_ambiguous_currency_never_guessed(raw):
    result = prices.price_info(raw)
    assert result["currency"] == "" and result["krw"] == ""
    assert result["status"] == "currency_required"


def test_explicit_context_bare_number_and_ambiguous_symbol():
    assert prices.price_info("14,90", "EUR", fx_data=RATE)["display"] == "14,90 EUR"
    dollar = prices.price_info("$14.90", "USD", fx_data={**RATE, "base": "USD", "rate": 1300})
    assert dollar["display"] == "$14.90 USD" and dollar["krw"] == "약 19,370원"
    assert prices.price_info("¥100", "JPY", fx_data={**RATE, "base": "JPY", "rate": 9})["krw"] == "약 900원"
    assert prices.price_info("$14", "EUR", fx_data=RATE)["currency"] == ""
    assert prices.price_info("€14", "USD", fx_data=RATE)["currency"] == "EUR"
    assert prices.price_info("$14 USD", fx_data={**RATE, "base": "USD"})["currency"] == "USD"


def test_existing_krw_and_empty_prices_need_no_fx():
    for raw in ("₩12,000", "12000원", "KRW 12000"):
        result = prices.price_info(raw)
        assert result["status"] == "krw" and result["display"] == raw and result["krw"] == ""
    assert prices.price_info("")["display"] == ""
    assert prices.price_info(None)["krw"] == ""


@pytest.mark.parametrize("patch", [{"base": "USD"}, {"quote": "USD"}, {"rate": 0}, {"rate": -1},
                                    {"rate": float("inf")}, {"rate": float("nan")}, {"rate": True},
                                    {"date": "2026-99-01"}, {"date": "2027-01-01"}, {"date": "20261104"}])
def test_invalid_override_never_converts_or_falls_through_to_network(patch):
    result = prices.price_info("€14", fx_data={**RATE, **patch})
    assert result["krw"] == "" and result["status"] == "unavailable"


def test_none_override_is_offline_unavailable():
    assert prices.price_info("€14", fx_data=None)["status"] == "unavailable"


def test_hour_cache_daily_refresh_and_request_timeout(monkeypatch):
    calls, clock = [], [0]
    monkeypatch.setattr(prices.time, "monotonic", lambda: clock[0])
    def get(url, **kwargs):
        calls.append(url)
        assert kwargs == {"timeout": 3.0, "follow_redirects": False}
        return httpx.Response(200, json=RATE)
    monkeypatch.setattr(prices.httpx, "get", get)
    assert prices.price_info("14,90 €")["krw"] == "약 22,377원"
    prices.price_info("€20")
    assert len(calls) == 1
    clock[0] = 3601
    prices.price_info("€20")
    assert len(calls) == 2
    monkeypatch.setattr(prices, "_today", lambda: date(2026, 11, 5))
    prices.price_info("€20")
    assert len(calls) == 3
    assert calls[0] == "https://api.frankfurter.dev/v2/rate/EUR/KRW"


@pytest.mark.parametrize("retry", ["120", formatdate(1120, usegmt=True)])
def test_429_honors_retry_after_across_currencies(monkeypatch, retry):
    clock, calls = [0], []
    monkeypatch.setattr(prices.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(prices.time, "time", lambda: 1000 + clock[0])
    def get(url, **kwargs):
        calls.append(url)
        return httpx.Response(429, headers={"Retry-After": retry})
    monkeypatch.setattr(prices.httpx, "get", get)
    assert prices.price_info("€14")["status"] == "unavailable"
    clock[0] = 119
    prices.price_info("GBP 14")
    assert len(calls) == 1
    clock[0] = 121
    prices.price_info("GBP 14")
    assert len(calls) == 2


def test_transport_failure_is_cached_and_keeps_price(monkeypatch):
    calls = []
    def get(*args, **kwargs):
        calls.append(1)
        raise httpx.ReadTimeout("offline")
    monkeypatch.setattr(prices.httpx, "get", get)
    result = prices.price_info("€14")
    assert result["display"] == "€14" and result["status"] == "unavailable"
    prices.price_info("€16")
    assert len(calls) == 1


def test_cache_size_is_bounded(monkeypatch):
    monkeypatch.setattr(prices, "CACHE_LIMIT", 2)
    def get(url, **kwargs):
        return httpx.Response(200, json={**RATE, "base": url.split("/")[-2]})
    monkeypatch.setattr(prices.httpx, "get", get)
    for currency in ("EUR", "GBP", "USD"):
        assert prices.price_info("14", currency)["krw"]
    assert len(prices._CACHE) == 2


@pytest.mark.parametrize("currency", ["INR", "SEK", "NZD"])
@pytest.mark.parametrize("explicit", [True, False])
def test_currency_outside_label_options_converts(currency, explicit):
    raw = f"{currency} 14.90" if explicit else "14.90"
    result = prices.price_info(raw, currency=currency.lower(), fx_data={**RATE, "base": currency, "rate": 100})
    assert result["currency"] == currency
    assert result["krw"] == "약 1,490원"
    assert result["display"] == (raw if explicit else f"14.90 {currency}")


def test_currency_nzd_disambiguates_dollar_symbol():
    result = prices.price_info("$14.90", "NZD", fx_data={**RATE, "base": "NZD", "rate": 100})
    assert result["currency"] == "NZD" and result["krw"] == "약 1,490원"
    assert prices.price_info("$14.90", "SEK", fx_data={**RATE, "base": "SEK"})["currency"] == ""


@pytest.mark.parametrize("currency", ["IN", "EURO", "US1", "US/D", "../USD", "ＵＳＤ"])
def test_currency_malformed_context_is_not_requested(currency):
    result = prices.price_info("14.90", currency)
    assert result["currency"] == "" and result["status"] == "currency_required"


def test_currency_unsupported_by_provider_stays_known_but_unavailable(monkeypatch):
    calls = []
    def get(url, **kwargs):
        calls.append(url)
        return httpx.Response(422, json={"message": "Unsupported currency"})
    monkeypatch.setattr(prices.httpx, "get", get)
    result = prices.price_info("XYZ 14.90")
    assert result["currency"] == "XYZ" and result["display"] == "XYZ 14.90"
    assert result["status"] == "unavailable" and result["krw"] == ""
    assert calls == ["https://api.frankfurter.dev/v2/rate/XYZ/KRW"]


def test_extraction_currency_recovers_explicit_iso_in_real_model_evidence():
    extraction = {"currency_code": "", "currency_source": "inferred",
                  "currency_evidence": "가격 형식과 독일어 메뉴로 인해 유로화(EUR)로 추정됨, 명확한 통화 기호는 없음."}
    before = dict(extraction)
    assert prices.currency_code(extraction) == "EUR"
    assert extraction == before


@pytest.mark.parametrize("extraction, expected", [
    ({"currency_code": "EUR", "currency_source": "printed"}, "EUR"),
    ({"currency_code": "sek", "currency_source": "inferred"}, "SEK"),
    ({"currency_code": "EUR", "currency_source": "unknown", "currency_evidence": "(EUR)"}, ""),
    ({"currency_code": "", "currency_source": "inferred", "currency_evidence": "EUR 또는 USD"}, ""),
    ({"currency_code": "", "currency_source": "inferred", "currency_evidence": "EUR, (EUR)"}, "EUR"),
    ({"currency_code": "", "currency_source": "printed", "currency_evidence": "(EUR)"}, ""),
    ({"currency_code": "", "currency_source": "inferred", "currency_evidence": "독일어 메뉴, 유로화 추정"}, ""),
    ({"currency_code": "", "currency_source": "inferred", "currency_evidence": "(eur)"}, ""),
    ({"currency_code": "", "currency_source": "inferred", "currency_evidence": "XEUR EUR1 _EUR 유로EUR"}, ""),
    ({"currency_code": "EURO", "currency_source": "inferred", "currency_evidence": "(EUR)"}, ""),
    ({"currency_source": "inferred", "currency_evidence": "(NZD)"}, "NZD"),
    ({"currency_source": "inferred", "currency_evidence": None}, ""),
    ({"currency_source": []}, ""),
    ({}, ""), (None, ""),
])
def test_extraction_currency_requires_explicit_unambiguous_model_code(extraction, expected):
    assert prices.currency_code(extraction) == expected

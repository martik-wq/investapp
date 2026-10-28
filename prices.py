"""Cena akcie a profil firmy z Yahoo Finance (neoficiálne verejné endpointy).

Yahoo nemá oficiálne API, takže sa to môže bez upozornenia pokaziť.
Vtedy aplikácia nespadne, len údaje chýbajú a cenu si zadáš ručne.
"""
import json
import os
import time

import requests

CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache")
PRICE_TTL = 15 * 60
PROFILE_TTL = 24 * 3600
CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{sym}?range=5d&interval=1d"
CRUMB_URL = "https://query1.finance.yahoo.com/v1/test/getcrumb"
SUMMARY_URL = ("https://query1.finance.yahoo.com/v10/finance/quoteSummary/{sym}"
               "?modules=assetProfile,summaryDetail,price&crumb={crumb}")
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                         "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"}


def _sym(ticker):
    return ticker.upper().replace(".", "-")


def _cached(name, ttl):
    path = os.path.join(CACHE_DIR, name)
    if os.path.exists(path) and time.time() - os.path.getmtime(path) < ttl:
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return None
    return None


def _store(name, data):
    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(os.path.join(CACHE_DIR, name), "w", encoding="utf-8") as f:
        json.dump(data, f)


def get_price(ticker):
    """Vráti dict {price, currency, time, name, prev_close, change, change_pct,
    high52, low52, exchange} alebo None."""
    sym = _sym(ticker)
    hit = _cached(f"price_{sym}.json", PRICE_TTL)
    if hit:
        return hit
    try:
        r = requests.get(CHART_URL.format(sym=sym), headers=HEADERS, timeout=10)
        r.raise_for_status()
        res = r.json()["chart"]["result"][0]
        meta = res["meta"]
        price = float(meta["regularMarketPrice"])
        closes = []
        try:
            closes = [c for c in res["indicators"]["quote"][0]["close"] if c is not None]
        except (KeyError, IndexError, TypeError):
            pass
        prev = closes[-2] if len(closes) >= 2 else meta.get("chartPreviousClose")
        out = {"price": price,
               "currency": meta.get("currency", "USD"),
               "time": time.strftime("%d.%m.%Y %H:%M", time.localtime(
                   meta.get("regularMarketTime", time.time()))),
               "name": meta.get("longName") or meta.get("shortName") or sym,
               "exchange": meta.get("fullExchangeName") or meta.get("exchangeName"),
               "high52": meta.get("fiftyTwoWeekHigh"),
               "low52": meta.get("fiftyTwoWeekLow"),
               "prev_close": prev,
               "change": (price - prev) if prev else None,
               "change_pct": ((price - prev) / prev) if prev else None}
    except (requests.RequestException, KeyError, IndexError, TypeError, ValueError):
        return None
    _store(f"price_{sym}.json", out)
    return out


def _raw(d, key):
    v = d.get(key)
    if isinstance(v, dict):
        return v.get("raw")
    return v


def get_profile(ticker):
    """Popis firmy, vedenie, sektor... z Yahoo (quoteSummary). None ak sa nepodarí."""
    sym = _sym(ticker)
    hit = _cached(f"profile_{sym}.json", PROFILE_TTL)
    if hit:
        return hit
    try:
        s = requests.Session()
        s.headers.update(HEADERS)
        s.get("https://fc.yahoo.com", timeout=10)  # nastaví cookie (odpoveď môže byť 404)
        crumb = s.get(CRUMB_URL, timeout=10)
        crumb.raise_for_status()
        r = s.get(SUMMARY_URL.format(sym=sym, crumb=crumb.text.strip()), timeout=10)
        r.raise_for_status()
        res = r.json()["quoteSummary"]["result"][0]
    except (requests.RequestException, KeyError, IndexError, TypeError, ValueError):
        return None
    ap = res.get("assetProfile") or {}
    sd = res.get("summaryDetail") or {}
    pr = res.get("price") or {}
    officers = []
    for o in (ap.get("companyOfficers") or [])[:8]:
        if o.get("name"):
            officers.append({"name": o.get("name"), "title": o.get("title"),
                             "age": o.get("age")})
    out = {
        "summary": ap.get("longBusinessSummary"),
        "sector": ap.get("sector"),
        "industry": ap.get("industry"),
        "website": ap.get("website"),
        "employees": ap.get("fullTimeEmployees"),
        "country": ap.get("country"),
        "city": ap.get("city"),
        "officers": officers,
        "market_cap": _raw(pr, "marketCap") or _raw(sd, "marketCap"),
        "dividend_yield": _raw(sd, "dividendYield"),
        "beta": _raw(sd, "beta"),
        "pe_trailing": _raw(sd, "trailingPE"),
        "volume": _raw(sd, "volume"),
        "avg_volume": _raw(sd, "averageVolume"),
        "long_name": pr.get("longName"),
    }
    _store(f"profile_{sym}.json", out)
    return out

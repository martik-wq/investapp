"""Cena akcie a profil firmy z Yahoo Finance (neoficiálne verejné endpointy).

Yahoo nemá oficiálne API, takže sa to môže bez upozornenia pokaziť.
Vtedy aplikácia nespadne, len údaje chýbajú a cenu si zadáš ručne.
"""
import json
import os
import re
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
    """Yahoo symbol. Triedy akcií (BRK.B) majú pomlčku, burzové prípony (VUSA.L) bodku."""
    t = ticker.upper().strip()
    if re.fullmatch(r"[A-Z0-9]+\.[AB]", t):
        return t.replace(".", "-")
    return t


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


SEARCH_URL = ("https://query1.finance.yahoo.com/v1/finance/search?q={q}&quotesCount=8"
              "&newsCount=0&listsCount=0")


def search_symbol(query):
    """Yahoo symbol podľa ISIN (alebo názvu). None, ak sa nenájde."""
    key = re.sub(r"[^A-Za-z0-9]", "_", query)
    hit = _cached(f"search_{key}.json", 7 * 24 * 3600)
    if hit is not None:
        return hit.get("symbol")
    try:
        r = requests.get(SEARCH_URL.format(q=requests.utils.quote(query)), headers=HEADERS,
                         timeout=10)
        r.raise_for_status()
        quotes = r.json().get("quotes") or []
    except (requests.RequestException, ValueError, AttributeError):
        return None
    sym = None
    for q in quotes:
        if q.get("quoteType") in ("EQUITY", "ETF", "MUTUALFUND") and q.get("symbol"):
            sym = q["symbol"]
            break
    _store(f"search_{key}.json", {"symbol": sym})
    return sym


HIST_URL = ("https://query1.finance.yahoo.com/v8/finance/chart/{sym}?period1={p1}&period2={p2}"
            "&interval=1d&events=div%2Csplits")


def get_history(symbol, start):
    """Denné ceny od dátumu `start` (date): {'dates','close','adj','currency'} alebo None.
    adj = cena upravená o dividendy (celkový výnos), ak ju Yahoo uvádza."""
    from datetime import datetime, timedelta, timezone
    sym = _sym(symbol)
    p1 = int(datetime(start.year, start.month, start.day, tzinfo=timezone.utc).timestamp())
    p2 = int((datetime.now(timezone.utc) + timedelta(days=2)).timestamp())
    name = f"hist2_{re.sub(r'[^A-Za-z0-9]', '_', sym)}_{start.isoformat()}.json"
    hit = _cached(name, 6 * 3600)
    if hit:
        return hit
    try:
        url = HIST_URL.format(sym=requests.utils.quote(sym), p1=p1, p2=p2)
        r = requests.get(url, headers=HEADERS, timeout=20)
        if r.status_code == 429:                      # Yahoo občas obmedzí počet požiadaviek
            time.sleep(1.5)
            r = requests.get(url, headers=HEADERS, timeout=20)
        r.raise_for_status()
        res = r.json()["chart"]["result"][0]
        ts = res["timestamp"]
        close = res["indicators"]["quote"][0]["close"]
        adj = None
        try:
            adj = res["indicators"]["adjclose"][0]["adjclose"]
        except (KeyError, IndexError, TypeError):
            pass
        ccy = res["meta"].get("currency")
        splits = []
        for ev in ((res.get("events") or {}).get("splits") or {}).values():
            try:
                ratio = float(ev["numerator"]) / float(ev["denominator"])
                splits.append([datetime.fromtimestamp(ev["date"], timezone.utc).date().isoformat(), ratio])
            except (KeyError, TypeError, ValueError, ZeroDivisionError):
                continue
        splits.sort()
    except (requests.RequestException, KeyError, IndexError, TypeError, ValueError):
        return None
    dates, c, a = [], [], []
    for i, t in enumerate(ts):
        if close[i] is None:
            continue
        dates.append(datetime.fromtimestamp(t, timezone.utc).date().isoformat())
        c.append(close[i])
        a.append(adj[i] if adj and adj[i] is not None else close[i])
    if not dates:
        return None
    out = {"dates": dates, "close": c, "adj": a, "currency": ccy, "splits": splits}
    _store(name, out)
    return out


# ------------------------------------------------------------ biografia člena vedenia
_TITLE_RE = re.compile(r"^(mr|ms|mrs|miss|dr|prof|sir|dame|hon)\.?\s+", re.I)
_SUFFIX_RE = re.compile(r",?\s+(j\.?d\.?|ph\.?d\.?|cpa|mba|esq\.?|m\.?d\.?|jr\.?|sr\.?|ii|iii|iv)\.?$", re.I)
_CORP_WORDS = {"inc", "corp", "corporation", "co", "company", "ltd", "plc", "holdings", "group", "the",
               "limited", "sa", "nv", "ag", "llc", "lp", "de", "com", "technologies", "technology"}


def clean_person_name(name):
    """„Mr. Jeffrey P. Bezos“ -> „Jeffrey P. Bezos“ (bez titulov a prípon)."""
    n = re.sub(r"\s+", " ", (name or "")).strip()
    for _ in range(3):
        n = _TITLE_RE.sub("", n)
        n = _SUFFIX_RE.sub("", n)
    return n.strip(" ,")


def _company_tokens(company):
    toks = [w for w in re.findall(r"[A-Za-z0-9]+", company or "") if w.lower() not in _CORP_WORDS and len(w) > 2]
    return [t.lower() for t in toks[:2]]


def _trim_sentences(text, limit=900):
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    cut = text[:limit]
    end = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "))
    return (cut[:end + 1] if end > 200 else cut.rstrip() + "…")


WIKI_API = ("https://en.wikipedia.org/w/api.php?action=query&list=search&srlimit=5&format=json"
            "&srsearch={q}")
WIKI_SUMMARY = "https://en.wikipedia.org/api/rest_v1/page/summary/{title}"


def get_officer_bio(name, company, ticker=""):
    """Krátka biografia z anglickej Wikipédie, len ak sa v nej spomína firma (overenie, že ide o toho
    istého človeka). {'title','description','extract','url','image'} alebo None."""
    clean = clean_person_name(name)
    if not clean:
        return None
    key = re.sub(r"[^a-z0-9]+", "_", f"{clean}_{company}".lower())[:90]
    hit = _cached(f"bio_{key}.json", 30 * 24 * 3600)
    if hit is not None:
        return hit.get("bio")
    parts = clean.split()
    last = parts[-1].lower()
    first = parts[0].lower()
    toks = _company_tokens(company) + ([ticker.lower()] if ticker and len(ticker) > 3 else [])
    bio = None
    try:
        q = requests.utils.quote(f"{parts[0]} {parts[-1]} {toks[0] if toks else ''}".strip())
        r = requests.get(WIKI_API.format(q=q), headers=HEADERS, timeout=10)
        r.raise_for_status()
        results = r.json().get("query", {}).get("search", [])
        for res in results[:4]:
            title = res.get("title", "")
            if last not in title.lower():
                continue
            s = requests.get(WIKI_SUMMARY.format(title=requests.utils.quote(title.replace(" ", "_"), safe="")),
                             headers=HEADERS, timeout=10)
            if s.status_code != 200:
                continue
            d = s.json()
            ext = d.get("extract") or ""
            if d.get("type") != "standard" or not ext:
                continue
            low = ext.lower()
            if not any(t in low for t in toks):
                continue
            img = (d.get("thumbnail") or {}).get("source")
            bio = {"title": d.get("title"), "description": d.get("description"),
                   "extract": _trim_sentences(ext), "image": img,
                   "url": ((d.get("content_urls") or {}).get("desktop") or {}).get("page")
                   or "https://en.wikipedia.org/wiki/" + title.replace(" ", "_")}
            break
    except (requests.RequestException, ValueError, KeyError, IndexError, AttributeError):
        return None   # chyba siete sa neukladá, aby sa to skúsilo znova
    _store(f"bio_{key}.json", {"bio": bio})
    return bio

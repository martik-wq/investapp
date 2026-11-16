"""Našepkávanie firiem podľa názvu alebo tickeru (vyhľadávanie, watchlist, porovnanie).

Zdroje: zoznam firiem appky (directory), zoznam firiem SEC (company_tickers.json, v pamäti) a vyhľadávanie
Yahoo Finance (európske a ázijské akcie, ETF). Výsledky sa zlúčia a zoradia podľa zhody."""
import re
import threading
import time

import requests

import directory
import edgar

YAHOO_URL = ("https://query2.finance.yahoo.com/v1/finance/search?q={q}&quotesCount=10&newsCount=0"
             "&listsCount=0&enableFuzzyQuery=true")
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                         "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"}
_sec = {"rows": None, "t": 0.0}
_ycache = {}
_lock = threading.Lock()
SUFFIX_RE = re.compile(r"\b(inc|incorporated|corp|corporation|co|company|ltd|limited|plc|holdings?|group|sa|se|ag|nv|"
                       r"the|class [a-c]|/[a-z]{2})\b\.?", re.I)


def _norm(s):
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", (s or "").lower())).strip()


def _sec_rows():
    """[(ticker, názov, normalizovaný názov)] zo SEC, držané v pamäti (súbor sa cachuje 24 h)."""
    with _lock:
        if _sec["rows"] is not None and time.time() - _sec["t"] < 6 * 3600:
            return _sec["rows"]
    try:
        raw = edgar._get_json(edgar.TICKERS_URL, "company_tickers.json")
        # poradie v súbore SEC je približne podľa trhovej kapitalizácie: index = popularita
        rows = [(v["ticker"].upper(), v["title"], _norm(v["title"]), i)
                for i, v in enumerate(raw.values() if isinstance(raw, dict) else raw)]
    except Exception:  # noqa: BLE001 - bez SEC zoznamu ostanú ostatné zdroje
        rows = []
    with _lock:
        _sec.update(rows=rows, t=time.time())
    return rows


def _yahoo(q):
    key = _norm(q)
    hit = _ycache.get(key)
    if hit and time.time() - hit[0] < 24 * 3600:
        return hit[1]
    out = []
    try:
        r = requests.get(YAHOO_URL.format(q=requests.utils.quote(q)), headers=HEADERS, timeout=6)
        r.raise_for_status()
        for x in r.json().get("quotes") or []:
            sym = str(x.get("symbol") or "").upper()
            typ = x.get("quoteType")
            if not sym or typ not in ("EQUITY", "ETF"):
                continue
            out.append({"symbol": sym, "name": x.get("longname") or x.get("shortname") or sym,
                        "ex": x.get("exchDisp") or x.get("exchange") or "", "kind": "ETF" if typ == "ETF" else "",
                        "src": "yahoo"})
    except (requests.RequestException, ValueError, AttributeError):
        return []
    _ycache[key] = (time.time(), out)
    return out


def _score(q, sym, name):
    """Stupeň zhody (nižší = lepší): 0 presný ticker, 1 začiatok názvu alebo tickeru, 2 začiatok slova, 3 obsahuje."""
    qs, nn = q.upper(), _norm(name)
    ql = _norm(q)
    if sym == qs or sym.split(".")[0] == qs:
        return 0
    core = _norm(SUFFIX_RE.sub(" ", name))
    if nn.startswith(ql) or core.startswith(ql) or sym.startswith(qs):
        return 1
    if re.search(r"\b" + re.escape(ql), nn):
        return 2
    if ql in nn:
        return 3
    return None


def suggest(q, limit=10, use_yahoo=True):
    q = (q or "").strip()
    if len(q) < 2:
        return []
    found = {}

    def add(item, score):
        s = item["symbol"]
        if s not in found or score < found[s][0]:
            found[s] = (score, item)
    # kľúč triedenia: (stupeň zhody, popularita); moje firmy majú prednosť, Yahoo za veľkými firmami zo SEC

    for e in directory.entries():
        names = [e["name"]] + e["aliases"]
        sc = min([x for x in (_score(q, e["symbol"], n) for n in names) if x is not None] or [None]) \
            if any(_score(q, e["symbol"], n) is not None for n in names) else None
        if sc is not None:
            add({"symbol": e["symbol"], "name": e["name"], "ex": e["country"], "kind": "",
                 "src": "sec" if e["src"] == "sec" else "yahoo"}, (sc, -1))
    ql = _norm(q)
    sec_hits, per_title = [], {}
    for t, title, nt, rank in _sec_rows():
        if ql not in nt and not t.startswith(q.upper()):
            continue
        if re.search(r"-P[A-Z]?$|-W[ST]?$|-U[N]?$|-R[T]?$", t):      # prioritné akcie, warranty, jednotky, práva
            continue
        sc = _score(q, t, title)
        if sc is None:
            continue
        sec_hits.append(((sc, rank), t, title))
    syms = {t for _k, t, _ in sec_hits}
    for key, t, title in sorted(sec_hits):
        if len(t) >= 4 and t[-1] in "WUR" and t[:-1] in syms:          # GRABW = warrant k GRAB
            continue
        n = per_title.get(title, 0)
        if n >= 2:                                                     # najviac 2 triedy akcií jednej firmy
            continue
        per_title[title] = n + 1
        add({"symbol": t, "name": title, "ex": "SEC · USA", "kind": "", "src": "sec"}, key)
        if len(per_title) >= limit:
            break
    if use_yahoo:
        sec_syms = {t for _k, t, _ in sec_hits}
        for i, y in enumerate(_yahoo(q)):
            if y["symbol"] in found or y["symbol"].replace("-", ".") in sec_syms:
                continue
            sc = _score(q, y["symbol"], y["name"])
            add(y, (sc if sc is not None else 2, 400 + i * 40))
    items = sorted(found.values(), key=lambda x: x[0])
    return [it for _s, it in items[:limit]]

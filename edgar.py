"""Sťahovanie a spracovanie dát zo SEC EDGAR (XBRL companyfacts API)."""
import json
import os
import re
import time
from datetime import datetime, timedelta

import requests

from taxonomy import ALL_ITEMS, SHARES_OUT_TAGS

BASE = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(BASE, "cache")
DEMO_DIR = os.path.join(BASE, "demo_data")
CACHE_TTL = 24 * 3600  # dáta z SEC sa cachujú 24 hodín

TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"
SUBS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"

DEMO_TICKERS = {
    "DEMOCO": ("Demo Software Inc. (fiktívna firma)", 9000001),
    "DEMOBANK": ("Demo Bank Corp. (fiktívna banka)", 9000002),
}


class EdgarError(Exception):
    """Chyba so zrozumiteľnou správou pre používateľa."""


# ------------------------------------------------------------------ HTTP + cache
def _user_agent():
    ua = os.environ.get("SEC_USER_AGENT", "").strip()
    cfg = os.path.join(BASE, "config.txt")
    if not ua and os.path.exists(cfg):
        with open(cfg, encoding="utf-8-sig") as f:
            ua = f.readline().strip()
    if not ua or "@" not in ua:
        raise EdgarError(
            "Chýba nastavenie SEC_USER_AGENT. SEC vyžaduje, aby si v požiadavkách "
            "uviedol svoje meno a e-mail, napr. SEC_USER_AGENT=\"Meno Priezvisko "
            "meno@example.com\". Pozri README.md.")
    return ua


def _get_json(url, cache_name):
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = os.path.join(CACHE_DIR, cache_name)
    if os.path.exists(path) and time.time() - os.path.getmtime(path) < CACHE_TTL:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    try:
        r = requests.get(url, headers={"User-Agent": _user_agent(),
                                       "Accept-Encoding": "gzip, deflate"}, timeout=40)
    except requests.RequestException as e:
        # ak máme starú cache, radšej ju použijeme
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        raise EdgarError(f"Nepodarilo sa spojiť so SEC ({e.__class__.__name__}). "
                         "Skontroluj internetové pripojenie.")
    if r.status_code == 404:
        raise EdgarError("Pre túto firmu SEC nemá dostupné XBRL dáta (404).")
    if r.status_code in (403, 429):
        raise EdgarError(f"SEC odmietla požiadavku (HTTP {r.status_code}). Skontroluj "
                         "SEC_USER_AGENT alebo skús o chvíľu (limit je 10 požiadaviek/s).")
    r.raise_for_status()
    data = r.json()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)
    return data


def _load_demo(ticker, kind):
    p = os.path.join(DEMO_DIR, f"{ticker}_{kind}.json")
    if not os.path.exists(p):
        raise EdgarError("Ukážkové dáta neexistujú. Spusti: python tests/make_demo_data.py")
    with open(p, encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------- vyhľadanie firmy
def find_company(query):
    """Vráti (match, candidates). match = (ticker, cik, title) alebo None."""
    q = query.strip().upper()
    if not q:
        raise EdgarError("Zadaj ticker alebo názov firmy.")
    if q in DEMO_TICKERS:
        title, cik = DEMO_TICKERS[q]
        return (q, cik, title), []
    raw = _get_json(TICKERS_URL, "company_tickers.json")
    rows = [(v["ticker"].upper(), int(v["cik_str"]), v["title"]) for v in raw.values()]
    for t, cik, title in rows:
        if t == q or t == q.replace(".", "-"):
            return (t, cik, title), []
    ql = query.strip().lower()
    cands = [r for r in rows if ql in r[2].lower()][:12]
    return None, cands


# ------------------------------------------------------------------ načítanie firmy
def load_company(ticker, cik, title):
    if ticker in DEMO_TICKERS:
        facts = _load_demo(ticker, "facts")
        subs = _load_demo(ticker, "subs")
    else:
        facts = _get_json(FACTS_URL.format(cik=cik), f"facts_{cik}.json")
        try:
            subs = _get_json(SUBS_URL.format(cik=cik), f"subs_{cik}.json")
        except EdgarError:
            subs = {}
    sic = subs.get("sic")
    return {
        "ticker": ticker,
        "cik": cik,
        "name": facts.get("entityName") or title,
        "facts": facts,
        "sic": int(sic) if sic and str(sic).isdigit() else None,
        "sic_desc": subs.get("sicDescription", ""),
        "currency": detect_currency(facts),
        "shares_out": latest_shares_outstanding(facts),
        "is_demo": ticker in DEMO_TICKERS,
    }


def _concept(facts, tag):
    tax, name = tag.split(":", 1) if ":" in tag else ("us-gaap", tag)
    return facts.get("facts", {}).get(tax, {}).get(name)


def detect_currency(facts):
    """Mena, v ktorej firma vykazuje (najčastejšia trojpísmenová jednotka)."""
    counts = {}
    for tag in ("Assets", "Revenues", "NetIncomeLoss", "ifrs:Assets", "ifrs:Revenue",
                "ifrs:ProfitLoss", "StockholdersEquity", "ifrs:Equity"):
        c = _concept(facts, tag)
        if not c:
            continue
        for unit, ents in c.get("units", {}).items():
            if re.fullmatch(r"[A-Z]{3}", unit):
                counts[unit] = counts.get(unit, 0) + len(ents)
    if not counts:
        return "USD"
    return max(counts, key=counts.get)


def latest_shares_outstanding(facts):
    best = None
    for tag in SHARES_OUT_TAGS + ["CommonStockSharesOutstanding"]:
        c = _concept(facts, tag)
        if not c:
            continue
        ents = c.get("units", {}).get("shares", [])
        for e in ents:
            key = (e.get("end", ""), e.get("filed", ""))
            if best is None or key > best[0]:
                best = (key, e["val"])
        if best:
            break
    return best[1] if best else None


# ----------------------------------------------------------------- spracovanie faktov
def _d(s):
    return datetime.strptime(s, "%Y-%m-%d").date()


def _unit_candidates(unit_kind, cur):
    if unit_kind == "cur":
        return [cur]
    if unit_kind == "shares":
        return ["shares"]
    if unit_kind == "eps":
        return [f"{cur}/shares", "USD/shares"]
    return [cur]


def _flow_map(entries):
    """{(start, end): hodnota}; pri duplicitách vyhrá najnovšie podanie."""
    best = {}
    for e in entries:
        if "start" not in e or "end" not in e:
            continue
        k = (_d(e["start"]), _d(e["end"]))
        f = e.get("filed", "")
        if k not in best or f >= best[k][0]:
            best[k] = (f, e["val"])
    return {k: v[1] for k, v in best.items()}


def _instant_map(entries):
    best = {}
    for e in entries:
        if "end" not in e or "start" in e:
            continue
        k = _d(e["end"])
        f = e.get("filed", "")
        if k not in best or f >= best[k][0]:
            best[k] = (f, e["val"])
    return {k: v[1] for k, v in best.items()}


def _annual(m):
    return {e: v for (s, e), v in m.items() if 340 <= (e - s).days <= 390}


def _quarters(m, additive=True):
    """Samostatné kvartály. Ak 10-Q uvádza len kumulatívne (6M, 9M) alebo
    ročné hodnoty, kvartál sa dopočíta odčítaním predchádzajúceho kumulatívu."""
    q = {}
    for (s, e), v in m.items():
        if 80 <= (e - s).days <= 100:
            q[e] = v
    if not additive:
        # vážený priemer akcií sa neodčítava; pre Q4 použijeme ročnú hodnotu
        for (s, e), v in m.items():
            if 340 <= (e - s).days <= 390 and e not in q:
                q[e] = v
        return q
    for (s, e), v in m.items():
        if e in q:
            continue
        d = (e - s).days
        if 170 <= d <= 195 or 260 <= d <= 285 or 340 <= d <= 390:
            for (s2, e2), v2 in m.items():
                if s2 == s and 80 <= (e - e2).days <= 100 and (e2 - s2).days < d:
                    q[e] = v - v2
                    break
    return q


def item_series(facts, item, mode, cur):
    """{end_date: hodnota} pre jeden riadok výkazu (zlúčené cez všetky tagy)."""
    out = {}
    units = _unit_candidates(item["unit"], cur)
    for tag in item["tags"]:
        c = _concept(facts, tag)
        if not c:
            continue
        ents = []
        for u in units:
            if u in c.get("units", {}):
                ents = c["units"][u]
                break
        if not ents:
            continue
        if item["kind"] == "flow":
            m = _flow_map(ents)
            s = _annual(m) if mode == "annual" else _quarters(m, item["additive"])
        else:
            s = _instant_map(ents)
        for k, v in s.items():
            out.setdefault(k, v)
    return out


def align(series, ends, tol=4):
    """Priradí hodnoty k referenčným koncom období (tolerancia pár dní)."""
    out = {}
    keys = list(series.keys())
    for e in ends:
        if e in series:
            out[e] = series[e]
            continue
        best = None
        for k in keys:
            dd = abs((k - e).days)
            if dd <= tol and (best is None or dd < best[0]):
                best = (dd, k)
        if best:
            out[e] = series[best[1]]
    return out


def all_item_series(company, mode):
    facts, cur = company["facts"], company["currency"]
    return {it["key"]: item_series(facts, it, mode, cur) for it in ALL_ITEMS}


def determine_periods(raw, mode, count):
    anchors = ["net_income", "revenue", "cfo", "pretax", "nii", "premiums", "op_income"]
    have = [a for a in anchors if raw.get(a)]
    if not have:
        raise EdgarError("Pre túto firmu sa nenašli žiadne výkazy v XBRL dátach "
                         "(možno ide o novú alebo neamerickú firmu).")
    counts = {}
    for a in have:
        for e in raw[a]:
            counts[e] = counts.get(e, 0) + 1
    need = 2 if len(have) >= 2 else 1
    ends = sorted(e for e, c in counts.items() if c >= need)
    if len(ends) < 2:
        ends = sorted(counts)
    # zahodiť neaktuálne obdobia staršie ako 12 rokov
    return ends[-count:]

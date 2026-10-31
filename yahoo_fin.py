"""Záložný zdroj výkazov pre firmy, ktoré nie sú v SEC (BMW, SK hynix...): neoficiálne ročné výkazy z Yahoo Finance.

Údaje sa prevedú do rovnakého tvaru ako SEC „companyfacts“, takže zvyšok appky (výkazy, grafy, modely, kvalita)
funguje bez zmeny. Yahoo dáva zvyčajne len 4 až 5 ročných období a žiadne kvartály ani podúčty."""
import json
import os
import re
import time
from datetime import date, timedelta

import requests

import taxonomy

CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache")
TTL = 24 * 3600
URL = ("https://query1.finance.yahoo.com/ws/fundamentals-timeseries/v1/finance/timeseries/{sym}"
       "?type={types}&period1=946684800&period2={now}")
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                         "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"}
SYMBOL = re.compile(r"^[A-Z0-9]{1,8}([.\-][A-Z0-9]{1,4})?$")

# kľúč riadku v appke -> (typ Yahoo bez „annual“, znamienko). Znamienko −1 = Yahoo uvádza výdavky so záporným znamienkom.
MAP = {
    "revenue": ("TotalRevenue", 1), "cost_of_revenue": ("CostOfRevenue", 1), "gross_profit": ("GrossProfit", 1),
    "rnd": ("ResearchAndDevelopment", 1), "sga": ("SellingGeneralAndAdministration", 1),
    "op_income": ("OperatingIncome", 1), "interest_expense": ("InterestExpense", 1),
    "pretax": ("PretaxIncome", 1), "tax": ("TaxProvision", 1), "net_income": ("NetIncomeCommonStockholders", 1),
    "eps_diluted": ("DilutedEPS", 1), "shares_diluted": ("DilutedAverageShares", 1),
    "cash": ("CashAndCashEquivalents", 1), "total_assets": ("TotalAssets", 1),
    "current_liabilities": ("CurrentLiabilities", 1), "debt_current": ("CurrentDebt", 1),
    "debt_lt": ("LongTermDebt", 1), "equity": ("StockholdersEquity", 1),
    "total_liabilities": ("TotalLiabilitiesNetMinorityInterest", 1),
    "da": ("DepreciationAndAmortization", 1), "sbc": ("StockBasedCompensation", 1),
    "cfo": ("OperatingCashFlow", 1), "capex": ("CapitalExpenditure", -1),
    "div_paid": ("CashDividendsPaid", -1),
}
EXTRA = ["OrdinarySharesNumber", "CurrentAssets", "ShareIssued"]
INSTANT = {"cash", "total_assets", "current_liabilities", "debt_current", "debt_lt", "equity", "total_liabilities"}


def _cache_path(sym):
    return os.path.join(CACHE_DIR, "yf_" + re.sub(r"[^A-Za-z0-9_.-]", "_", sym) + ".json")


def fetch(sym):
    """Surová odpoveď Yahoo ako {typ: [{asOfDate, currencyCode, raw}]} alebo None. Používa 24-hodinovú cache."""
    sym = sym.upper().strip()
    if not SYMBOL.match(sym):
        return None
    path = _cache_path(sym)
    if os.path.exists(path) and time.time() - os.path.getmtime(path) < TTL:
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            pass
    types = ",".join("annual" + t for t, _s in list(MAP.values()) + [(x, 1) for x in EXTRA])
    try:
        r = requests.get(URL.format(sym=sym, types=types, now=int(time.time())), headers=HEADERS, timeout=15)
        r.raise_for_status()
        results = r.json()["timeseries"]["result"]
    except (requests.RequestException, KeyError, TypeError, ValueError):
        return None
    out = {}
    for res in results or []:
        try:
            typ = res["meta"]["type"][0]
        except (KeyError, IndexError, TypeError):
            continue
        rows = []
        for e in res.get(typ) or []:
            try:
                rows.append({"asOfDate": e["asOfDate"], "currencyCode": e.get("currencyCode"),
                             "raw": float(e["reportedValue"]["raw"])})
            except (KeyError, TypeError, ValueError):
                continue
        if rows:
            out[typ[len("annual"):] if typ.startswith("annual") else typ] = rows
    if not out.get("TotalRevenue") and not out.get("NetIncomeCommonStockholders"):
        return None
    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f)
    return out


def _currency(raw):
    cnt = {}
    for k in ("TotalRevenue", "TotalAssets", "NetIncomeCommonStockholders"):
        for r in raw.get(k, []):
            c = r.get("currencyCode")
            if c and re.fullmatch(r"[A-Z]{3}", c):
                cnt[c] = cnt.get(c, 0) + 1
    return max(cnt, key=cnt.get) if cnt else "USD"


def to_facts(raw, name):
    """Prevod do tvaru SEC companyfacts: {'entityName', 'facts': {'us-gaap': {tag: {'units': {mena: [...]}}}}}."""
    cur = _currency(raw)
    items = {i["key"]: i for i in taxonomy.ALL_ITEMS}
    gaap = {}
    for key, (ytype, sign) in MAP.items():
        rows, it = raw.get(ytype), items.get(key)
        if not rows or not it:
            continue
        tag = next((t for t in it["tags"] if ":" not in t), None)
        if not tag:
            continue
        unit = cur if it["unit"] == "cur" else "shares" if it["unit"] == "shares" else f"{cur}/shares"
        ents = []
        for r in rows:
            try:
                end = date.fromisoformat(r["asOfDate"])
            except ValueError:
                continue
            ent = {"end": end.isoformat(), "val": r["raw"] * sign, "fy": end.year, "fp": "FY", "form": "20-F",
                   "filed": (end + timedelta(days=60)).isoformat()}
            if it["kind"] == "flow":
                ent["start"] = (end - timedelta(days=364)).isoformat()
            ents.append(ent)
        if ents:
            gaap.setdefault(tag, {"units": {}})["units"][unit] = ents
    facts = {"entityName": name, "facts": {"us-gaap": gaap, "dei": {}}}
    sh = raw.get("OrdinarySharesNumber") or raw.get("ShareIssued")
    if sh:
        last = max(sh, key=lambda r: r["asOfDate"])
        facts["facts"]["dei"]["EntityCommonStockSharesOutstanding"] = {"units": {"shares": [
            {"end": last["asOfDate"], "val": last["raw"], "filed": last["asOfDate"]}]}}
    return facts


def lookup(sym):
    """(ticker, 'YF', názov) ak Yahoo pre symbol má ročné výkazy, inak None."""
    raw = fetch(sym)
    if not raw:
        return None
    sym = sym.upper().strip()
    name = sym
    try:
        import prices
        name = (prices.get_price(sym) or {}).get("name") or sym
    except Exception:  # noqa: BLE001 - názov je len kozmetika
        pass
    return (sym, "YF", name)


def load(sym, title):
    raw = fetch(sym)
    if not raw:
        return None
    return to_facts(raw, title), _currency(raw)

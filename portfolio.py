"""Portfólio z exportu Trading 212 (História → Export CSV).

Import sa dá spúšťať opakovane (T212 dovoľuje najviac 12 mesiacov na jeden súbor):
transakcie sa spájajú a duplicity sa zahodia. Údaje zostávajú len na tvojom
počítači, v súbore data/portfolio.json.
"""
import csv
import hashlib
import io
import json
import os
import re
from collections import defaultdict
from datetime import datetime

BASE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE, "data")
STORE = os.path.join(DATA_DIR, "portfolio.json")

TIME_FORMATS = ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S.%fZ",
                "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S", "%d/%m/%Y %H:%M:%S",
                "%d/%m/%Y %H:%M", "%Y-%m-%d %H:%M", "%Y-%m-%d")
EPS = 1e-7


class PortfolioError(Exception):
    """Chyba so zrozumiteľnou správou pre používateľa."""


# ------------------------------------------------------------------- čítanie CSV
def _num(text):
    if text is None:
        return None
    t = str(text).strip().replace("\xa0", "").replace(" ", "")
    if not t or t.lower() in ("not available", "n/a", "na", "-", "—", "null", "none"):
        return None
    if re.fullmatch(r"-?\d{1,3}(,\d{3})+(\.\d+)?", t):   # 1,234.56
        t = t.replace(",", "")
    elif "," in t and "." not in t:                       # 12,5
        t = t.replace(",", ".")
    try:
        return float(t)
    except ValueError:
        return None


def _time(text):
    t = (text or "").strip()
    for fmt in TIME_FORMATS:
        try:
            return datetime.strptime(t, fmt)
        except ValueError:
            continue
    return None


def classify(action):
    a = (action or "").strip().lower()
    if not a:
        return "other"
    if a.startswith("dividend"):
        return "dividend"
    if "interest" in a:
        return "interest"
    if "buy" in a:
        return "buy"
    if "sell" in a:
        return "sell"
    if a.startswith("deposit"):
        return "deposit"
    if a.startswith("withdraw"):
        return "withdrawal"
    if "cashback" in a:
        return "cashback"
    if "split" in a:
        return "split"
    if "currency conversion" in a or a.startswith("card") or "conversion" in a:
        return "ignore"
    return "other"


def _find(headers, *names, prefix=None):
    """Index stĺpca: presný názov (bez ohľadu na veľkosť písmen), inak začiatok názvu."""
    low = [h.strip().lower() for h in headers]
    for n in names:
        if n.lower() in low:
            return low.index(n.lower())
    if prefix:
        for i, h in enumerate(low):
            if h.startswith(prefix.lower() + " (") and not h.startswith("currency"):
                return i
    return None


def parse_csv(text):
    """Vráti {'txns': [...], 'acct_ccy': 'EUR', 'warnings': [...], 'rows': n}."""
    text = text.lstrip("﻿")
    if not text.strip():
        raise PortfolioError("Súbor je prázdny.")
    sample = text[:4000]
    delim = ";" if sample.count(";") > sample.count(",") else ","
    reader = csv.reader(io.StringIO(text), delimiter=delim)
    try:
        headers = next(reader)
    except StopIteration:
        raise PortfolioError("Súbor je prázdny.")
    ci = {
        "action": _find(headers, "Action"), "time": _find(headers, "Time"),
        "isin": _find(headers, "ISIN"), "ticker": _find(headers, "Ticker"),
        "name": _find(headers, "Name"), "shares": _find(headers, "No. of shares"),
        "price": _find(headers, "Price / share"),
        "price_ccy": _find(headers, "Currency (Price / share)", "Currency"),
        "fx": _find(headers, "Exchange rate"),
        "total": _find(headers, "Total", prefix="Total"),
        "result": _find(headers, "Result", prefix="Result"),
        "wht": _find(headers, "Withholding tax"),
        "id": _find(headers, "ID"), "notes": _find(headers, "Notes"),
        "total_ccy": _find(headers, "Currency (Total)"),
    }
    if ci["action"] is None or ci["time"] is None or ci["total"] is None:
        raise PortfolioError(
            "Toto nevyzerá ako export histórie z Trading 212 (chýbajú stĺpce Action, Time alebo "
            "Total). V Trading 212 choď do History, klikni na ikonu exportu a vyber CSV.")
    acct = None
    m = re.search(r"\(([A-Za-z]{3})\)\s*$", headers[ci["total"]])
    if m:
        acct = m.group(1).upper()
    txns, warnings, skipped = [], [], defaultdict(int)
    n = 0
    for row in reader:
        if not row or not any(c.strip() for c in row):
            continue
        n += 1
        g = lambda k: (row[ci[k]].strip() if ci[k] is not None and ci[k] < len(row) else "")  # noqa: E731
        raw_action = g("action")
        kind = classify(raw_action)
        when = _time(g("time"))
        if when is None:
            skipped["bez platného dátumu"] += 1
            continue
        if kind == "ignore":          # konverzie mien a kartové platby sú bežné a nezaujímavé
            continue
        if kind == "other":
            skipped[raw_action or "neznáma akcia"] += 1
            continue
        if acct is None and ci["total_ccy"] is not None and g("total_ccy"):
            acct = g("total_ccy").upper()
        total = _num(g("total"))
        t = {
            "time": when.strftime("%Y-%m-%d %H:%M:%S"), "kind": kind, "action": raw_action,
            "isin": g("isin"), "ticker": g("ticker"), "name": g("name"),
            "shares": _num(g("shares")), "price": _num(g("price")),
            "price_ccy": g("price_ccy").upper() if g("price_ccy") else "",
            "fx": _num(g("fx")), "total": total, "result": _num(g("result")),
            "wht": _num(g("wht")), "notes": g("notes"), "id": g("id"),
        }
        if kind in ("buy", "sell") and (not t["isin"] or not t["shares"] or total is None):
            skipped[f"{raw_action} (chýbajú údaje)"] += 1
            continue
        t["key"] = t["id"] or hashlib.sha1(
            f"{t['time']}|{raw_action}|{t['isin']}|{t['shares']}|{total}".encode()).hexdigest()
        txns.append(t)
    for what, c in skipped.items():
        warnings.append(f"Preskočené: {what} ({c}×)")
    if any(t["kind"] == "split" for t in txns):
        warnings.append("V exporte je akciový split alebo iný korporátny úkon. Počet kusov "
                        "a priemerná cena pri týchto pozíciách môžu byť nepresné.")
    if not txns:
        raise PortfolioError("V súbore sa nenašla žiadna použiteľná transakcia.")
    if acct is None:
        acct = "EUR"
        warnings.append("Menu účtu sa nepodarilo zistiť z hlavičky, predpokladám EUR.")
    return {"txns": txns, "acct_ccy": acct, "warnings": warnings, "rows": n}


# --------------------------------------------------------------------- úložisko
def load_store():
    if not os.path.exists(STORE):
        return {"txns": {}, "acct_ccy": None, "symbols": {}, "files": []}
    try:
        with open(STORE, encoding="utf-8") as f:
            d = json.load(f)
    except (OSError, ValueError):
        return {"txns": {}, "acct_ccy": None, "symbols": {}, "files": []}
    d.setdefault("txns", {})
    d.setdefault("symbols", {})
    d.setdefault("files", [])
    return d


def save_store(d):
    os.makedirs(DATA_DIR, exist_ok=True)
    tmp = STORE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False)
    os.replace(tmp, STORE)


def import_files(files):
    """files = [(názov, text)]. Vráti {'added', 'duplicates', 'warnings', 'files'}."""
    store = load_store()
    added = dup = 0
    warnings = []
    for name, text in files:
        try:
            res = parse_csv(text)
        except PortfolioError as e:
            warnings.append(f"{name}: {e}")
            continue
        if store["acct_ccy"] and res["acct_ccy"] != store["acct_ccy"]:
            warnings.append(f"{name}: mena účtu {res['acct_ccy']} sa líši od už nahratej "
                            f"({store['acct_ccy']}), súbor som preskočil. Každý účet nahrávaj "
                            "zvlášť (zmaž portfólio alebo použi súbory z jedného účtu).")
            continue
        store["acct_ccy"] = res["acct_ccy"]
        n_new = 0
        for t in res["txns"]:
            if t["key"] in store["txns"]:
                dup += 1
            else:
                store["txns"][t["key"]] = t
                n_new += 1
        added += n_new
        warnings += [f"{name}: {w}" for w in res["warnings"]]
        store["files"].append({"name": name, "rows": res["rows"], "new": n_new,
                               "at": datetime.now().strftime("%d.%m.%Y %H:%M")})
    if added:
        save_store(store)
    return {"added": added, "duplicates": dup, "warnings": warnings}


def clear_store():
    if os.path.exists(STORE):
        os.remove(STORE)


def set_symbol(isin, symbol):
    store = load_store()
    if symbol:
        store["symbols"][isin] = symbol.strip().upper()
    else:
        store["symbols"].pop(isin, None)
    save_store(store)


# ------------------------------------------------------------------- výpočty
def build_positions(txns):
    """Priemerná nákupná cena (v mene účtu). Vráti dict s otvorenými a uzavretými
    pozíciami, dividendami a súčtami."""
    items = sorted(txns, key=lambda t: t["time"])
    pos = {}
    totals = defaultdict(float)
    div_year = defaultdict(float)
    warnings = []
    for t in items:
        k, total = t["kind"], t["total"]
        if k in ("buy", "sell", "dividend"):
            p = pos.setdefault(t["isin"], {
                "isin": t["isin"], "ticker": t["ticker"], "name": t["name"], "shares": 0.0,
                "cost": 0.0, "realized": 0.0, "dividends": 0.0, "bought": 0.0, "sold": 0.0,
                "first": t["time"][:10], "last": t["time"][:10], "ccy": t["price_ccy"], "n": 0})
            if t["isin"]:
                p["ticker"] = t["ticker"] or p["ticker"]
                p["name"] = t["name"] or p["name"]
                p["ccy"] = t["price_ccy"] or p["ccy"]
            p["last"] = t["time"][:10]
        if k == "buy":
            amt = abs(total or 0.0)
            p["shares"] += t["shares"]
            p["cost"] += amt
            p["bought"] += amt
            p["n"] += 1
        elif k == "sell":
            proceeds = abs(total or 0.0)
            sh = t["shares"]
            if p["shares"] < sh - 1e-6:
                warnings.append(f"{p['ticker'] or p['isin']}: predaj {sh:g} ks, ale evidujem len "
                                f"{p['shares']:g} ks (chýba časť histórie alebo split).")
            sold = min(sh, p["shares"])
            avg = p["cost"] / p["shares"] if p["shares"] > EPS else 0.0
            cost_sold = avg * sold
            p["realized"] += proceeds - cost_sold
            p["cost"] -= cost_sold
            p["shares"] -= sold
            p["sold"] += proceeds
            p["n"] += 1
            if p["shares"] < 1e-6:
                p["shares"], p["cost"] = 0.0, 0.0
        elif k == "dividend":
            amt = abs(total or 0.0)
            p["dividends"] += amt
            div_year[t["time"][:4]] += amt
            totals["dividends"] += amt
        elif k == "interest":
            totals["interest"] += abs(total or 0.0)
        elif k == "deposit":
            totals["deposits"] += abs(total or 0.0)
        elif k == "withdrawal":
            totals["withdrawals"] += abs(total or 0.0)
        elif k == "cashback":
            totals["cashback"] += abs(total or 0.0)
    open_pos = [p for p in pos.values() if p["shares"] > 1e-6]
    closed = [p for p in pos.values() if p["shares"] <= 1e-6 and (p["bought"] or p["sold"])]
    for p in open_pos:
        p["avg_cost"] = p["cost"] / p["shares"] if p["shares"] else 0.0
    totals["realized"] = sum(p["realized"] for p in pos.values())
    return {"open": sorted(open_pos, key=lambda p: -p["cost"]), "closed": closed,
            "dividends_by_year": dict(sorted(div_year.items())), "totals": dict(totals),
            "warnings": warnings, "dividend_only": [
                p for p in pos.values() if not p["bought"] and not p["sold"] and p["dividends"]]}


def _to_quote_currency(price, ccy):
    """Yahoo uvádza londýnske ceny v penciach (GBp/GBX)."""
    if ccy in ("GBp", "GBX"):
        return price / 100.0, "GBP"
    return price, ccy


def value_positions(pos, acct_ccy, symbol_fn, quote_fn, fx_fn):
    """Doplní aktuálnu cenu, hodnotu a nerealizovaný zisk. Funkcie:
    symbol_fn(isin, ticker) -> symbol, quote_fn(symbol) -> {'price','currency'} | None,
    fx_fn(from, to) -> kurz | None."""
    from concurrent.futures import ThreadPoolExecutor

    def one(p):
        sym = symbol_fn(p["isin"], p["ticker"])
        p["symbol"] = sym
        q = quote_fn(sym) if sym else None
        if not q:
            return
        price, qc = _to_quote_currency(q["price"], q.get("currency") or p["ccy"] or acct_ccy)
        rate = 1.0 if qc == acct_ccy else fx_fn(qc, acct_ccy)
        if rate is None:
            return
        p["price"], p["price_ccy"] = q["price"], q.get("currency")
        p["price_acct"] = price * rate
        p["value"] = p["price_acct"] * p["shares"]
        p["unrealized"] = p["value"] - p["cost"]
        p["unrealized_pct"] = (p["value"] / p["cost"] - 1) if p["cost"] > 0 else None
        p["day_change_pct"] = q.get("change_pct")

    with ThreadPoolExecutor(max_workers=6) as ex:
        list(ex.map(one, pos))
    return pos


def summarize(data, valued):
    """Súhrn: trhová hodnota, vložené, zisky... (len z pozícií, ktoré majú cenu)."""
    t = data["totals"]
    priced = [p for p in valued if p.get("value") is not None]
    value = sum(p["value"] for p in priced)
    cost_priced = sum(p["cost"] for p in priced)
    cost_all = sum(p["cost"] for p in valued)
    unreal = value - cost_priced
    out = {
        "value": value, "cost": cost_all, "cost_priced": cost_priced,
        "unrealized": unreal, "unrealized_pct": (unreal / cost_priced) if cost_priced > 0 else None,
        "realized": t.get("realized", 0.0), "dividends": t.get("dividends", 0.0),
        "interest": t.get("interest", 0.0), "deposits": t.get("deposits", 0.0),
        "withdrawals": t.get("withdrawals", 0.0),
        "unpriced": [p for p in valued if p.get("value") is None],
    }
    out["total_return"] = out["unrealized"] + out["realized"] + out["dividends"] + out["interest"]
    for p in priced:
        p["weight"] = p["value"] / value if value else 0.0
    return out

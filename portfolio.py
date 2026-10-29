"""Portfólio z exportu Trading 212 (História → Export CSV).

Podporuje starší formát (jedna mena účtu, stĺpec „Total (EUR)“) aj nový formát
s viacerými peňaženkami (stĺpce „Time (UTC)“, „Currency (Total)“ v každom riadku).
Export sa dá nahrávať po častiach (T212 dovoľuje najviac 12 mesiacov na súbor):
transakcie sa spájajú a duplicity sa zahodia. Údaje zostávajú len na tvojom
počítači, v súbore data/portfolio.json.
"""
import csv
import hashlib
import io
import json
import os
import re
import threading
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

BASE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE, "data")
STORE = os.path.join(DATA_DIR, "portfolio.json")

TIME_FORMATS = ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%d/%m/%Y %H:%M:%S",
                "%d/%m/%Y %H:%M", "%Y-%m-%d %H:%M", "%Y-%m-%d")
EPS = 1e-7
# vklad/výber s týmito poznámkami je skutočný pohyb peňazí z/do banky
EXTERNAL_NOTE = re.compile(r"bank|card|sent to|sepa|iban|wire|apple pay|google pay|paypal", re.I)


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
    if not t:
        return None
    try:
        d = datetime.fromisoformat(t.replace("Z", "+00:00"))
        if d.tzinfo is not None:                 # „2025-10-30 02:05:37+00:00“
            d = d.astimezone(timezone.utc).replace(tzinfo=None)
        return d
    except ValueError:
        pass
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
    if "spin" in a and "off" in a:
        return "spinoff"
    if "split" in a:
        return "split"
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
    if "conversion" in a or a.startswith("card"):
        return "ignore"
    return "other"


def _find(headers, *names, prefix=None):
    """Index stĺpca: presný názov (bez ohľadu na veľkosť písmen), inak „Názov (…)“."""
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
    """Vráti {'txns': [...], 'acct_ccy': 'EUR'|None, 'warnings': [...], 'rows': n}."""
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
        "action": _find(headers, "Action"), "time": _find(headers, "Time", prefix="Time"),
        "isin": _find(headers, "ISIN"), "ticker": _find(headers, "Ticker"),
        "name": _find(headers, "Name"), "shares": _find(headers, "No. of shares"),
        "price": _find(headers, "Price / share"),
        "price_ccy": _find(headers, "Currency (Price / share)", "Currency"),
        "fx": _find(headers, "Exchange rate"),
        "total": _find(headers, "Total", prefix="Total"),
        "result": _find(headers, "Result", prefix="Result"),
        "result_ccy": _find(headers, "Currency (Result)"),
        "wht": _find(headers, "Withholding tax"),
        "wht_ccy": _find(headers, "Currency (Withholding tax)"),
        "id": _find(headers, "ID"), "notes": _find(headers, "Notes"),
        "total_ccy": _find(headers, "Currency (Total)"),
    }
    if ci["action"] is None or ci["time"] is None or ci["total"] is None:
        raise PortfolioError(
            "Toto nevyzerá ako export histórie z Trading 212 (chýbajú stĺpce Action, Time alebo "
            "Total). V Trading 212 choď do History, klikni na ikonu exportu a vyber CSV.")
    header_ccy = None
    m = re.search(r"\(([A-Za-z]{3})\)\s*$", headers[ci["total"]])
    if m:
        header_ccy = m.group(1).upper()
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
        ccy = (g("total_ccy") or header_ccy or "").upper()
        total = _num(g("total"))
        t = {
            "time": when.strftime("%Y-%m-%d %H:%M:%S"), "kind": kind, "action": raw_action,
            "isin": g("isin"), "ticker": g("ticker"), "name": g("name"),
            "shares": _num(g("shares")), "price": _num(g("price")),
            "price_ccy": g("price_ccy").upper() if g("price_ccy") else "",
            "fx": _num(g("fx")), "total": total, "ccy": ccy, "result": _num(g("result")),
            "result_ccy": (g("result_ccy") or ccy).upper(), "wht": _num(g("wht")),
            "wht_ccy": (g("wht_ccy") or "").upper(), "notes": g("notes"), "id": g("id"),
        }
        if kind in ("buy", "sell") and (not t["isin"] or not t["shares"]
                                        or (total is None and t["price"] is None)):
            skipped[f"{raw_action} (chýbajú údaje)"] += 1
            continue
        if not t["ccy"]:
            t["ccy"] = t["price_ccy"]
        t["key"] = t["id"] or hashlib.sha1(
            f"{t['time']}|{raw_action}|{t['isin']}|{t['shares']}|{total}".encode()).hexdigest()
        txns.append(t)
    for what, c in skipped.items():
        warnings.append(f"Preskočené: {what} ({c}×)")
    if any(t["kind"] == "split" for t in txns):
        warnings.append("V exporte je akciový split. Počet kusov a priemerná cena pri týchto "
                        "pozíciách môžu byť nepresné.")
    if not txns:
        raise PortfolioError("V súbore sa nenašla žiadna použiteľná transakcia.")
    return {"txns": txns, "acct_ccy": header_ccy, "warnings": warnings, "rows": n}


# --------------------------------------------------------------------- úložisko
def _empty():
    return {"txns": {}, "acct_ccy": None, "symbols": {}, "files": [], "hidden_periods": []}


def load_store():
    if not os.path.exists(STORE):
        return _empty()
    try:
        with open(STORE, encoding="utf-8") as f:
            d = json.load(f)
    except (OSError, ValueError):
        return _empty()
    for k, v in _empty().items():
        d.setdefault(k, v)
    return d


def save_store(d):
    os.makedirs(DATA_DIR, exist_ok=True)
    tmp = STORE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False)
    os.replace(tmp, STORE)


def import_files(files):
    """files = [(názov, text)]. Vráti {'added', 'duplicates', 'warnings'}."""
    store = load_store()
    added = dup = 0
    warnings = []
    for name, text in files:
        try:
            res = parse_csv(text)
        except PortfolioError as e:
            warnings.append(f"{name}: {e}")
            continue
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


def set_hidden(key, hide=True):
    """Skryje (alebo znova zobrazí) riadok v tabuľke výnosov, napr. 'y2024'."""
    store = load_store()
    hid = [k for k in store.get("hidden_periods", []) if k != key]
    if hide:
        hid.append(key)
    store["hidden_periods"] = hid
    save_store(store)


def set_symbol(isin, symbol):
    store = load_store()
    if symbol:
        store["symbols"][isin] = symbol.strip().upper()
    else:
        store["symbols"].pop(isin, None)
    save_store(store)


# ------------------------------------------------------------------- výpočty
def _mark_transfers(items):
    """Vklad v jednej mene a výber v druhej mene v priebehu pár sekúnd (bez poznámky o banke
    alebo karte) je len presun medzi peňaženkami, nie skutočný pohyb peňazí."""
    cand = [t for t in items if t["kind"] in ("deposit", "withdrawal")
            and not EXTERNAL_NOTE.search(t.get("notes") or "")]
    ts = [datetime.strptime(t["time"], "%Y-%m-%d %H:%M:%S") for t in cand]
    used = set()
    for i, a in enumerate(cand):
        if i in used:
            continue
        for j in range(i + 1, len(cand)):
            if j in used:
                continue
            if (ts[j] - ts[i]).total_seconds() > 300:
                break
            b = cand[j]
            if a["kind"] != b["kind"] and a["ccy"] != b["ccy"]:
                a["kind"] = b["kind"] = "transfer"
                used.update((i, j))
                break


def _amount(t, pccy, mism):
    """Suma obchodu v mene pozície."""
    if t["ccy"] == pccy and t["total"] is not None:
        return abs(t["total"])
    if t["price_ccy"] == pccy and t["price"] is not None and t["shares"]:
        return t["shares"] * t["price"]
    mism.add(t.get("ticker") or t["isin"])
    return abs(t["total"] or 0.0)


def _add(d, ccy, v):
    d[ccy or "?"] = d.get(ccy or "?", 0.0) + v


def build_positions(txns):
    """Priemerná nákupná cena v mene pozície (mena, v ktorej Trading 212 obchod zúčtoval;
    ak sa menila, mena akcie). Vráti pozície, dividendy, vklady a upozornenia."""
    items = sorted((dict(t) for t in txns), key=lambda t: t["time"])
    _mark_transfers(items)
    ccys, price_ccys = defaultdict(set), defaultdict(Counter)
    for t in items:
        if t["kind"] in ("buy", "sell"):
            ccys[t["isin"]].add(t["ccy"])
            price_ccys[t["isin"]][t["price_ccy"]] += 1

    def pos_ccy(isin, fallback):
        s = ccys.get(isin)
        if s and len(s) == 1:
            return next(iter(s))
        c = price_ccys.get(isin)
        if c:
            return c.most_common(1)[0][0]
        return fallback

    pos = {}
    totals = defaultdict(dict)
    div_year = defaultdict(dict)
    warnings, missing, mism, spin = [], set(), set(), []
    for t in items:
        k = t["kind"]
        p = None
        if k in ("buy", "sell", "dividend", "spinoff"):
            p = pos.get(t["isin"])
            if p is None:
                p = pos[t["isin"]] = {
                    "isin": t["isin"], "ticker": t["ticker"], "name": t["name"],
                    "ccy": pos_ccy(t["isin"], t["ccy"] or t["price_ccy"]), "shares": 0.0,
                    "cost": 0.0, "realized": {}, "div": {}, "bought": 0.0, "sold": 0.0,
                    "first": t["time"][:10], "last": t["time"][:10], "n": 0,
                    "missing_history": False, "spinoff": False}
            p["ticker"] = t["ticker"] or p["ticker"]
            p["name"] = t["name"] or p["name"]
            p["last"] = t["time"][:10]
        if k == "buy":
            amt = _amount(t, p["ccy"], mism)
            p["shares"] += t["shares"]
            p["cost"] += amt
            p["bought"] += amt
            p["n"] += 1
        elif k == "spinoff":
            p["shares"] += t["shares"] or 0.0
            p["spinoff"] = True
            spin.append(p["ticker"] or p["isin"])
        elif k == "sell":
            proceeds = _amount(t, p["ccy"], mism)
            sh = t["shares"]
            tracked = min(sh, p["shares"])
            if p["shares"] < sh - 1e-6:
                p["missing_history"] = True
                missing.add(p["ticker"] or p["isin"])
            avg = p["cost"] / p["shares"] if p["shares"] > EPS else 0.0
            cost_sold = avg * tracked
            if t["result"] is not None:             # Trading 212 pozná aj staršiu históriu
                _add(p["realized"], t["result_ccy"] or p["ccy"], t["result"])
            else:
                _add(p["realized"], p["ccy"], proceeds * (tracked / sh) - cost_sold)
            p["cost"] -= cost_sold
            p["shares"] -= tracked
            p["sold"] += proceeds
            p["n"] += 1
            if p["shares"] < 1e-6:
                p["shares"], p["cost"] = 0.0, 0.0
        elif k == "dividend":
            amt = abs(t["total"] or 0.0)
            _add(p["div"], t["ccy"], amt)
            _add(div_year[t["time"][:4]], t["ccy"], amt)
            _add(totals["dividends"], t["ccy"], amt)
        elif k in ("interest", "deposit", "withdrawal", "cashback", "transfer"):
            key = {"interest": "interest", "deposit": "deposits", "withdrawal": "withdrawals",
                   "cashback": "cashback", "transfer": "transfers"}[k]
            _add(totals[key], t["ccy"], abs(t["total"] or 0.0))
    if missing:
        warnings.append(
            "Chýba staršia história: pri " + ", ".join(sorted(missing)) +
            " sú v exporte predaje väčšie než nákupy. Zisk z týchto predajov beriem z Trading 212, "
            "ale pozície kúpené pred začiatkom exportu (a ešte držané) sa v tabuľke nezobrazia. "
            "Nahraj aj staršie súbory (každý najviac 12 mesiacov).")
    if mism:
        warnings.append("Pri " + ", ".join(sorted(mism)) + " sa mena obchodu nezhoduje s menou "
                        "pozície, suma môže byť nepresná.")
    # spin-off, ktorý sa hneď predal, je len zisk z predaja (hodnota akcií = výnos); varuj len pri držaných
    spin = [x for x in spin if any((q["ticker"] or q["isin"]) == x and q["shares"] > 1e-6 for q in pos.values())]
    if spin:
        warnings.append("Spin-off (" + ", ".join(sorted(set(spin))) + "): nová pozícia má nulovú "
                        "nákupnú cenu, jej zisk je preto nadhodnotený. Pôvodná cena patrí čiastočne "
                        "k materskej akcii.")
    open_pos = [p for p in pos.values() if p["shares"] > 1e-6]
    closed = [p for p in pos.values() if p["shares"] <= 1e-6 and (p["bought"] or p["sold"] or p["realized"])]
    for p in open_pos:
        p["avg_cost"] = p["cost"] / p["shares"] if p["shares"] else 0.0
    times = [t["time"] for t in items]
    return {"open": sorted(open_pos, key=lambda p: -p["cost"]), "closed": closed,
            "all": list(pos.values()), "totals": {k: dict(v) for k, v in totals.items()},
            "dividends_by_year": {y: dict(v) for y, v in sorted(div_year.items())},
            "warnings": warnings, "first": times[0][:10] if times else None,
            "last": times[-1][:10] if times else None,
            "currencies": sorted({t["ccy"] for t in items if t["ccy"]})}


class Converter:
    """Kurzy mien s pamäťou (volania môžu bežať paralelne)."""

    def __init__(self, fx_fn):
        self.fx_fn, self.cache, self.lock = fx_fn, {}, threading.Lock()
        self.missing = set()

    def rate(self, a, b):
        if not a or not b or a == b:
            return 1.0
        key = (a, b)
        with self.lock:
            if key in self.cache:
                return self.cache[key]
        r = self.fx_fn(a, b)
        with self.lock:
            self.cache[key] = r
            if r is None:
                self.missing.add(f"{a}→{b}")
        return r

    def convert(self, d, base):
        """Súčet slovníka {mena: suma} v základnej mene."""
        tot = 0.0
        for c, v in d.items():
            r = self.rate(c, base)
            if r is not None:
                tot += v * r
        return tot


def _pence(price, ccy):
    """Yahoo uvádza londýnske ceny v penciach (GBp/GBX)."""
    if ccy in ("GBp", "GBX"):
        return price / 100.0, "GBP"
    return price, ccy


def value_positions(pos, base, symbol_fn, quote_fn, conv):
    """Doplní aktuálnu cenu, hodnotu a nerealizovaný zisk (v mene pozície aj v základnej mene).
    symbol_fn(isin, ticker) -> symbol, quote_fn(symbol) -> {'price','currency'} | None."""
    def one(p):
        for k in ("price", "price_quote_ccy", "price_pc", "value", "unrealized", "unrealized_pct",
                  "value_b", "unrealized_b", "day_change_pct", "weight"):
            p[k] = None          # kým nemáme cenu, zostane prázdne (nie chýbajúce)
        sym = symbol_fn(p["isin"], p["ticker"])
        p["symbol"] = sym
        p["to_base"] = conv.rate(p["ccy"], base)
        q = quote_fn(sym) if sym else None
        if not q:
            return
        price, qc = _pence(q["price"], q.get("currency") or p["ccy"])
        rate = conv.rate(qc, p["ccy"])
        if rate is None:
            return
        p["price"], p["price_quote_ccy"] = q["price"], q.get("currency")
        p["price_pc"] = price * rate
        p["value"] = p["price_pc"] * p["shares"]
        p["unrealized"] = p["value"] - p["cost"]
        p["unrealized_pct"] = (p["value"] / p["cost"] - 1) if p["cost"] > 0 else None
        if p["to_base"] is not None:
            p["value_b"] = p["value"] * p["to_base"]
            p["unrealized_b"] = p["unrealized"] * p["to_base"]
        p["day_change_pct"] = q.get("change_pct")

    with ThreadPoolExecutor(max_workers=6) as ex:
        list(ex.map(one, pos))
    for p in pos:
        p["cost_b"] = p["cost"] * p["to_base"] if p.get("to_base") is not None else None
        p["div_b"] = conv.convert(p["div"], base)
    return pos


def summarize(data, valued, base, conv):
    """Súhrn v základnej mene (prepočet aktuálnym kurzom, preto približný)."""
    t = data["totals"]
    priced = [p for p in valued if p.get("value_b") is not None]
    value = sum(p["value_b"] for p in priced)
    cost_priced = sum(p["cost_b"] for p in priced if p["cost_b"] is not None)
    cost_all = sum(p["cost_b"] for p in valued if p["cost_b"] is not None)
    unreal = value - cost_priced
    realized = 0.0
    for p in data["all"]:
        p["realized_b"] = conv.convert(p["realized"], base)
        realized += p["realized_b"]
    out = {
        "value": value, "cost": cost_all, "cost_priced": cost_priced, "unrealized": unreal,
        "unrealized_pct": (unreal / cost_priced) if cost_priced > 0 else None,
        "realized": realized,
        "dividends": conv.convert(t.get("dividends", {}), base),
        "interest": conv.convert(t.get("interest", {}), base),
        "deposits": conv.convert(t.get("deposits", {}), base),
        "withdrawals": conv.convert(t.get("withdrawals", {}), base),
        "unpriced": [p for p in valued if p.get("value_b") is None],
        "div_year": {y: conv.convert(v, base) for y, v in data["dividends_by_year"].items()},
        "fx_missing": sorted(conv.missing),
    }
    out["total_return"] = out["unrealized"] + out["realized"] + out["dividends"] + out["interest"]
    for p in priced:
        p["weight"] = p["value_b"] / value if value else 0.0
    return out


def default_base(txns):
    """Základná mena: mena, v ktorej vkladáš peniaze z banky (inak najčastejšia mena)."""
    c = Counter(t["ccy"] for t in txns if t["kind"] == "deposit" and t["ccy"]
                and EXTERNAL_NOTE.search(t.get("notes") or ""))
    if not c:
        c = Counter(t["ccy"] for t in txns if t["ccy"])
    return c.most_common(1)[0][0] if c else "EUR"

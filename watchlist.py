"""Watchlist: zoznam sledovaných akcií (ticker, cena pri pridaní, voliteľná cieľová cena).
Ukladá sa len na tvojom počítači do data/watchlist.json."""
import json
import os
import re
import time

import portfolio

PATH = os.path.join(portfolio.DATA_DIR, "watchlist.json")
TICKER = re.compile(r"^[A-Z0-9][A-Z0-9.\-=^]{0,14}$")
MAX_ITEMS = 100


def load():
    try:
        with open(PATH, encoding="utf-8") as f:
            d = json.load(f)
        items = d.get("items", []) if isinstance(d, dict) else []
    except (OSError, ValueError):
        items = []
    return [i for i in items if isinstance(i, dict) and TICKER.match(str(i.get("ticker", "")))]


def save(items):
    os.makedirs(portfolio.DATA_DIR, exist_ok=True)
    tmp = PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"items": items}, f, ensure_ascii=False, indent=1)
    os.replace(tmp, PATH)


def _num(v):
    try:
        x = float(str(v).replace(",", ".").replace(" ", ""))
        return x if x > 0 else None
    except (TypeError, ValueError):
        return None


def add(ticker, price, name="", target=None):
    """Vráti (ok, správa). price = aktuálna cena v čase pridania (pre „od pridania“)."""
    t = (ticker or "").upper().strip()
    if not TICKER.match(t):
        return False, "Neplatný ticker."
    items = load()
    if any(i["ticker"] == t for i in items):
        return False, f"{t} už v zozname je."
    if len(items) >= MAX_ITEMS:
        return False, f"Zoznam môže mať najviac {MAX_ITEMS} položiek."
    items.append({"ticker": t, "name": name or t, "added": time.strftime("%Y-%m-%d"),
                  "price_at_add": price, "target": _num(target)})
    save(items)
    return True, f"{t} pridaný do watchlistu."


def remove(ticker):
    t = (ticker or "").upper().strip()
    items = load()
    new = [i for i in items if i["ticker"] != t]
    if len(new) != len(items):
        save(new)
        return True
    return False


def set_target(ticker, target):
    t = (ticker or "").upper().strip()
    items = load()
    for i in items:
        if i["ticker"] == t:
            i["target"] = _num(target)
            save(items)
            return True
    return False


def enrich(items, quote_fn):
    """Doplní cenu, zmenu za deň, polohu v 52-týždňovom rozsahu, zmenu od pridania a vzdialenosť k cieľu."""
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=6) as ex:
        quotes = list(ex.map(lambda i: _safe(quote_fn, i["ticker"]), items))
    rows = []
    for i, q in zip(items, quotes):
        r = dict(i)
        r["quote"] = q
        p = q.get("price") if q else None
        r["price"] = p
        r["ccy"] = q.get("currency") if q else None
        r["day_pct"] = q.get("change_pct") if q else None
        lo, hi = (q.get("low52"), q.get("high52")) if q else (None, None)
        r["range_pos"] = ((p - lo) / (hi - lo)) if p is not None and lo is not None and hi and hi > lo else None
        r["from_high"] = (p / hi - 1) if p is not None and hi else None
        pa = i.get("price_at_add")
        r["since_add"] = (p / pa - 1) if p is not None and pa else None
        tg = i.get("target")
        r["to_target"] = (tg / p - 1) if p and tg else None
        r["hit"] = bool(p and tg and p >= tg)
        rows.append(r)
    return rows


def _safe(fn, t):
    try:
        return fn(t)
    except Exception:  # noqa: BLE001 - jedna zlá položka nesmie zhodiť stránku
        return None

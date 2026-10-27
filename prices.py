"""Aktuálna cena akcie z Yahoo Finance (neoficiálny verejný endpoint).

Yahoo nemá oficiálne API, takže sa to môže bez upozornenia pokaziť.
Vtedy aplikácia nespadne, len si cenu zadáš ručne.
"""
import json
import os
import time

import requests

CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache")
TTL = 15 * 60
URL = "https://query1.finance.yahoo.com/v8/finance/chart/{sym}?range=5d&interval=1d"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                         "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"}


def get_price(ticker):
    """Vráti dict {price, currency, time, name} alebo None."""
    sym = ticker.upper().replace(".", "-")
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = os.path.join(CACHE_DIR, f"price_{sym}.json")
    if os.path.exists(path) and time.time() - os.path.getmtime(path) < TTL:
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            pass
    try:
        r = requests.get(URL.format(sym=sym), headers=HEADERS, timeout=10)
        r.raise_for_status()
        meta = r.json()["chart"]["result"][0]["meta"]
        out = {"price": float(meta["regularMarketPrice"]),
               "currency": meta.get("currency", "USD"),
               "time": time.strftime("%d.%m.%Y %H:%M", time.localtime(
                   meta.get("regularMarketTime", time.time()))),
               "name": meta.get("longName") or meta.get("shortName") or sym}
    except (requests.RequestException, KeyError, IndexError, TypeError, ValueError):
        return None
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f)
    return out

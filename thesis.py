"""Investičná téza ku každej firme: prečo ju držíš, kedy by si predal, čo sledovať, a krátky denník poznámok.
Ukladá sa len na tvojom počítači do data/thesis.json."""
import json
import os
import re
from datetime import date

import portfolio

PATH = os.path.join(portfolio.DATA_DIR, "thesis.json")
TICKER = re.compile(r"^[A-Z0-9][A-Z0-9.\-=^]{0,14}$")
MAX_TEXT = 3000
MAX_LOG = 60
FIELDS = ("why", "sell_if", "watch")


def _load_all():
    try:
        with open(PATH, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_all(d):
    os.makedirs(portfolio.DATA_DIR, exist_ok=True)
    tmp = PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=1)
    os.replace(tmp, PATH)


def get(ticker):
    """Téza firmy alebo None."""
    t = _load_all().get((ticker or "").upper())
    return t if isinstance(t, dict) else None


def save(ticker, why="", sell_if="", watch="", note="", price=None, today=None):
    """Uloží tézu. Prázdne všetky polia a bez poznámky = téza sa zmaže. Vráti (ok, správa)."""
    t = (ticker or "").upper().strip()
    if not TICKER.match(t):
        return False, "Neplatný ticker."
    today = (today or date.today()).isoformat()
    d = _load_all()
    cur = d.get(t) if isinstance(d.get(t), dict) else {}
    new = {k: (locals()[k] or "").strip()[:MAX_TEXT] for k in FIELDS}
    note = (note or "").strip()[:600]
    log = list(cur.get("log") or [])
    if note:
        log.insert(0, {"d": today, "t": note})
    if not any(new.values()) and not log:
        d.pop(t, None)
        _save_all(d)
        return True, "Téza zmazaná."
    changed = any(new[k] != cur.get(k, "") for k in FIELDS)
    rec = {**new, "log": log[:MAX_LOG], "created": cur.get("created") or today,
           "updated": today if (changed or not cur) else cur.get("updated", today),
           "price": cur.get("price") if cur.get("price") is not None else price}
    d[t] = rec
    _save_all(d)
    return True, "Téza uložená."


def stale(th, last_release_date):
    """True, ak výsledky vyšli po poslednej úprave tézy (dátumy ISO)."""
    if not th or not last_release_date:
        return False
    return str(last_release_date) > str(th.get("updated") or "")

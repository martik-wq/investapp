"""Insider transakcie z formulárov 4 zo SEC (vedenie, členovia predstavenstva, veľkí akcionári).

Berú sa len podania typu 4 z posledných mesiacov. Za signál sa považujú nákupy a predaje na voľnom trhu (kód P a S);
udelené akcie, uplatnenie opcií a zrážky dane (A, M, F, G) sa zobrazia, ale do súčtu sa nerátajú.
Inštitucionálne držby (13F) sa tu nedajú zobraziť: podávajú sa za fond, nie za emitenta."""
import re
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

import filings

CODES = {"P": "nákup na trhu", "S": "predaj na trhu", "A": "udelené akcie", "M": "uplatnenie opcie",
         "F": "zrážka dane", "G": "dar", "C": "konverzia", "D": "predaj firme", "X": "uplatnenie opcie",
         "J": "iné", "W": "dedičstvo", "I": "diskrétna transakcia"}
MAX_FILINGS = 40


def _t(node, path):
    el = node.find(path) if node is not None else None
    return (el.text or "").strip() if el is not None and el.text else ""


def _f(s):
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def parse_form4(xml_text, acc="", filed=""):
    """Zoznam transakcií z jedného formulára 4: dict(date, who, title, code, shares, price, side, after, plan)."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []
    owner = root.find("reportingOwner")
    who = _t(owner, "reportingOwnerId/rptOwnerName")
    rel = owner.find("reportingOwnerRelationship") if owner is not None else None
    title = _t(rel, "officerTitle")
    if not title and rel is not None:
        if _t(rel, "isDirector") in ("1", "true"):
            title = "člen predstavenstva"
        elif _t(rel, "isTenPercentOwner") in ("1", "true"):
            title = "akcionár nad 10 %"
    plan = _t(root, "aff10b5One") in ("1", "true")
    out = []
    for tx in root.findall("nonDerivativeTable/nonDerivativeTransaction"):
        code = _t(tx, "transactionCoding/transactionCode")
        shares = _f(_t(tx, "transactionAmounts/transactionShares/value"))
        price = _f(_t(tx, "transactionAmounts/transactionPricePerShare/value"))
        side = _t(tx, "transactionAmounts/transactionAcquiredDisposedCode/value")
        if shares is None or not code:
            continue
        out.append({"date": _t(tx, "transactionDate/value"), "who": who, "title": title, "code": code,
                    "kind": CODES.get(code, code), "shares": shares, "price": price, "side": side,
                    "after": _f(_t(tx, "postTransactionAmounts/sharesOwnedFollowingTransaction/value")),
                    "plan": plan, "acc": acc, "filed": filed})
    return out


def summarize(txs, today=None, days=180):
    """Súčet nákupov a predajov na trhu za posledných `days` dní."""
    today = today or date.today()
    lim = (today - timedelta(days=days)).isoformat()
    buys = [t for t in txs if t["code"] == "P" and t["date"] >= lim]
    sells = [t for t in txs if t["code"] == "S" and t["date"] >= lim]
    val = lambda xs: sum(t["shares"] * (t["price"] or 0) for t in xs)  # noqa: E731
    return {"days": days, "n_buy": len(buys), "n_sell": len(sells),
            "buy_value": val(buys), "sell_value": val(sells),
            "buyers": sorted({t["who"] for t in buys}), "sellers": sorted({t["who"] for t in sells}),
            "net": val(buys) - val(sells)}


def _raw_doc(doc):
    """primaryDocument ukazuje na XSL zobrazenie (xslF345X05/x.xml); surové XML je rovnaký názov bez prefixu."""
    return re.sub(r"^xsl[^/]*/", "", doc or "")


def get_insider(company, today=None):
    """{'txs': [...], 'summary': {...}, 'n_filings': n} alebo {'error': text}."""
    r = company.get("filings") or {}
    forms = r.get("form") or []
    rows = [(r["accessionNumber"][i], (r.get("filingDate") or [""] * len(forms))[i],
             (r.get("primaryDocument") or [""] * len(forms))[i])
            for i, f in enumerate(forms) if f == "4"]
    if company.get("source") == "yahoo" or not company.get("cik") or company.get("cik") == "YF":
        return {"error": "Insider transakcie sú len pri firmách podávajúcich SEC formuláre (USA)."}
    if not rows:
        return {"error": "V posledných podaniach firmy nie sú žiadne formuláre 4 (zahraniční emitenti ich nepodávajú)."}
    rows = rows[:MAX_FILINGS]

    def one(x):
        acc, filed, doc = x
        try:
            txt = filings.fetch_text(company, acc, _raw_doc(doc))
        except Exception:  # noqa: BLE001 - jedno podanie nesmie zhodiť zvyšok
            txt = None
        return parse_form4(txt, acc, filed) if txt else []

    with ThreadPoolExecutor(max_workers=4) as ex:
        txs = [t for part in ex.map(one, rows) for t in part]
    txs.sort(key=lambda t: (t["date"], t["acc"]), reverse=True)
    return {"txs": txs, "summary": summarize(txs, today), "n_filings": len(rows), "error": None}

"""Zoznam dôležitých firiem, aby sa dali nájsť podľa názvu aj tickeru, aj keď nie sú v SEC.

Symboly sú podľa Yahoo Finance (prípona = burza: .T Tokio, .KS Soul, .DE Xetra, .AS Amsterdam, .L Londýn, .TW Taiwan).
Firmy zo SEC (src = 'sec') sa tu len pripomínajú na úvodnej stránke, údaje pre ne ide priamo zo SEC.
Chceš pridať ďalšiu? Pridaj riadok do FIRMS, formát: (symbol, názov, krajina, src, typ, aliasy)."""
import re

# typ: None = automaticky, inak kľúč z BUSINESS_TYPES (general, tech, bank, insurance, reit)
FIRMS = [
    ("GRAB", "Grab Holdings", "Singapur", "sec", None, ["grab"]),
    ("NU", "Nu Holdings", "Brazília", "sec", "bank", ["nubank", "nu holdings"]),
    ("SOFI", "SoFi Technologies", "USA", "sec", "bank", ["sofi"]),
    ("SE", "Sea Limited", "Singapur", "sec", None, ["sea ltd", "shopee"]),
    ("CPNG", "Coupang", "Južná Kórea", "sec", None, ["coupang"]),
    ("MELI", "MercadoLibre", "Argentína", "sec", None, ["mercadolibre", "mercado libre"]),
    ("ASML", "ASML Holding", "Holandsko", "sec", "tech", ["asml"]),
    ("TSM", "TSMC (ADR)", "Taiwan", "sec", "tech", ["tsmc", "taiwan semiconductor"]),
    ("6146.T", "Disco Corporation", "Japonsko", "yahoo", "tech", ["disco", "disco corp", "disco corporation"]),
    ("323410.KS", "KakaoBank", "Južná Kórea", "yahoo", "bank", ["kakaobank", "kakao bank", "kakao"]),
    ("000660.KS", "SK hynix", "Južná Kórea", "yahoo", "tech", ["sk hynix", "hynix", "skhynix"]),
    ("005930.KS", "Samsung Electronics", "Južná Kórea", "yahoo", "tech", ["samsung", "samsung electronics"]),
    ("035420.KS", "Naver", "Južná Kórea", "yahoo", "tech", ["naver"]),
    ("035720.KS", "Kakao Corp", "Južná Kórea", "yahoo", "tech", ["kakao corp"]),
    ("8035.T", "Tokyo Electron", "Japonsko", "yahoo", "tech", ["tokyo electron"]),
    ("6857.T", "Advantest", "Japonsko", "yahoo", "tech", ["advantest"]),
    ("6920.T", "Lasertec", "Japonsko", "yahoo", "tech", ["lasertec"]),
    ("6758.T", "Sony Group", "Japonsko", "yahoo", None, ["sony"]),
    ("7203.T", "Toyota Motor", "Japonsko", "yahoo", None, ["toyota"]),
    ("BMW.DE", "BMW", "Nemecko", "yahoo", None, ["bmw", "bayerische motoren werke"]),
    ("SAP.DE", "SAP", "Nemecko", "yahoo", "tech", ["sap"]),
    ("ADYEN.AS", "Adyen", "Holandsko", "yahoo", "tech", ["adyen"]),
    ("WISE.L", "Wise", "Veľká Británia", "yahoo", "tech", ["wise", "transferwise"]),
]


def _norm(s):
    return re.sub(r"[^a-z0-9.]+", " ", s.lower()).strip()


def entries():
    return [dict(symbol=s, name=n, country=c, src=src, type=t, aliases=a) for s, n, c, src, t, a in FIRMS]


def by_symbol(symbol):
    s = (symbol or "").upper().strip()
    return next((e for e in entries() if e["symbol"] == s), None)


def find(query):
    """(presná_zhoda alebo None, [čiastočné zhody]) len medzi firmami, ktoré nie sú v SEC."""
    q = _norm(query)
    if not q:
        return None, []
    exact, part = None, []
    for e in entries():
        if e["src"] != "yahoo":
            continue
        names = {_norm(e["symbol"]), _norm(e["name"])} | {_norm(a) for a in e["aliases"]}
        if q in names:
            exact = exact or e
        elif len(q) >= 3 and any(q in n for n in names):
            part.append(e)
    return exact, part


def as_candidate(e):
    return (e["symbol"], "YF", f"{e['name']} · {e['country']}")

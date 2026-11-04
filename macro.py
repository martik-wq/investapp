"""Makro dáta z FRED (Federal Reserve Bank of St. Louis): sadzby, výnosová krivka, inflácia, nezamestnanosť.
Používa sa verejný CSV export bez kľúča. FRED sa môže bez upozornenia zmeniť, vtedy údaje chýbajú, appka nespadne."""
import re
from datetime import date

import requests

import prices

URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={id}"
TTL = 12 * 3600
# (id, názov, jednotka, popis, yoy = prepočítať index na medziročnú zmenu)
SERIES = [
    ("FEDFUNDS", "Sadzba Fed (federal funds)", "%", "Základná sadzba americkej centrálnej banky, mesačný priemer.", False),
    ("DGS10", "Výnos 10-ročných štátnych dlhopisov USA", "%", "Dlhodobá sadzba; ovplyvňuje hypotéky a ocenenie akcií.", False),
    ("DGS2", "Výnos 2-ročných štátnych dlhopisov USA", "%", "Trh sa tu stavia k budúcim sadzbám Fedu.", False),
    ("T10Y2Y", "Výnosová krivka: 10 rokov mínus 2 roky", "p. b.", "Pod nulou (inverzia) bola v minulosti častým predzvesťou recesie.", False),
    ("CPIAUCSL", "Inflácia v USA (CPI, medziročne)", "%", "Medziročná zmena indexu spotrebiteľských cien.", True),
    ("UNRATE", "Nezamestnanosť v USA", "%", "Podiel nezamestnaných na pracovnej sile.", False),
    ("MORTGAGE30US", "Hypotéka v USA na 30 rokov", "%", "Priemerná sadzba; dôležitá pre banky a stavebníctvo.", False),
    ("ECBDFR", "Depozitná sadzba ECB (eurozóna)", "%", "Hlavná sadzba ECB pre eurozónu.", False),
]
SERIES_BY_ID = {s[0]: s for s in SERIES}


def parse_fred_csv(text):
    """[(ISO dátum, hodnota)] z CSV so stĺpcami dátum,hodnota. Chýbajúce hodnoty ('.', prázdne) sa vynechajú."""
    out = []
    for line in (text or "").splitlines()[1:]:
        parts = line.strip().split(",")
        if len(parts) < 2 or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", parts[0]):
            continue
        try:
            out.append((parts[0], float(parts[1])))
        except ValueError:
            continue
    return out


def yoy(points):
    """Medziročná zmena v % z mesačného indexu."""
    by = {d[:7]: v for d, v in points}
    out = []
    for d, v in points:
        y, m = int(d[:4]), d[5:7]
        prev = by.get(f"{y - 1}-{m}")
        if prev:
            out.append((d, (v / prev - 1) * 100))
    return out


def _thin(points, max_n=900):
    """Zredčí husté (denné) rady, aby graf nebol zbytočne ťažký; posledný bod zostane."""
    if len(points) <= max_n:
        return points
    step = -(-len(points) // max_n)
    out = points[::step]
    if out[-1] != points[-1]:
        out.append(points[-1])
    return out


def get_points(sid):
    """Surová rada [(dátum, hodnota)] alebo None. Cachuje na 12 hodín."""
    name = f"fred_{re.sub(r'[^A-Za-z0-9]', '_', sid)}.json"
    hit = prices._cached(name, TTL)
    if hit:
        return [tuple(x) for x in hit]
    try:
        r = requests.get(URL.format(id=sid), headers=prices.HEADERS, timeout=20)
        r.raise_for_status()
        pts = parse_fred_csv(r.text)
    except requests.RequestException:
        return None
    if not pts:
        return None
    prices._store(name, [list(p) for p in pts])
    return pts


def page_data(years=10, today=None):
    """Zoznam kariet: {'id','name','unit','desc','last','last_date','chg_1y','points'|None}."""
    today = today or date.today()
    lim = date(today.year - years, today.month, 1).isoformat()
    cards = []
    for sid, name, unit, desc, as_yoy in SERIES:
        pts = get_points(sid)
        card = {"id": sid, "name": name, "unit": unit, "desc": desc, "points": None, "last": None,
                "last_date": None, "chg_1y": None}
        if pts:
            if as_yoy:
                pts = yoy(pts)
            shown = [p for p in pts if p[0] >= lim]
            if shown:
                card["last"], card["last_date"] = shown[-1][1], shown[-1][0]
                ago = next((v for d, v in reversed(pts) if d <= f"{int(shown[-1][0][:4]) - 1}{shown[-1][0][4:]}"), None)
                card["chg_1y"] = None if ago is None else shown[-1][1] - ago
                card["points"] = [[d, round(v, 3)] for d, v in _thin(shown)]
        cards.append(card)
    return cards


def annual_avg(points, year):
    """Priemer hodnôt rady za kalendárny rok alebo None."""
    vals = [v for d, v in points if d.startswith(str(year))]
    return sum(vals) / len(vals) if vals else None

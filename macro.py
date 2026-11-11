"""Makro dáta z FRED (Federal Reserve Bank of St. Louis): sadzby, výnosová krivka, inflácia, nezamestnanosť.
Používa sa verejný CSV export bez kľúča. FRED sa môže bez upozornenia zmeniť, vtedy údaje chýbajú, appka nespadne."""
import os
import re
import time
from datetime import date

import requests

import prices

URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={id}&cosd={start}"
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


API_URL = ("https://api.stlouisfed.org/fred/series/observations?series_id={id}&api_key={key}"
           "&file_type=json&observation_start={start}")
KEY_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "fred_key.txt")
_FAILED = {"until": 0.0, "error": None}       # po zlyhaní sa FRED 30 minút neskúša (stránky sa nespomaľujú)
LAST_ERROR = {"text": None}


def api_key():
    k = os.environ.get("FRED_API_KEY", "").strip()
    if not k and os.path.exists(KEY_PATH):
        with open(KEY_PATH, encoding="utf-8") as f:
            k = f.read().strip()
    return k if re.fullmatch(r"[a-z0-9]{32}", k or "") else None


def save_key(k):
    k = (k or "").strip().lower()
    if not re.fullmatch(r"[a-z0-9]{32}", k):
        return False
    os.makedirs(os.path.dirname(KEY_PATH), exist_ok=True)
    with open(KEY_PATH, "w", encoding="utf-8") as f:
        f.write(k)
    _FAILED["until"] = 0.0
    return True


def parse_api_json(data):
    out = []
    for o in (data or {}).get("observations") or []:
        try:
            out.append((o["date"], float(o["value"])))
        except (KeyError, TypeError, ValueError):
            continue
    return out


def _download(sid, start):
    key = api_key()
    if key:                                   # oficiálne API s bezplatným kľúčom (funguje aj tam, kde CSV blokujú)
        r = requests.get(API_URL.format(id=sid, key=key, start=start), timeout=(5, 12))
        r.raise_for_status()
        return parse_api_json(r.json())
    last = None
    for hdr in ({"User-Agent": "investapp/1.0 (personal research)", "Accept": "text/csv,*/*"}, prices.HEADERS):
        try:
            r = requests.get(URL.format(id=sid, start=start), headers=hdr, timeout=(5, 10))
            r.raise_for_status()
            pts = parse_fred_csv(r.text)
            if pts:
                return pts
        except requests.RequestException as e:
            last = e
    if last:
        raise last
    return []


def get_points(sid):
    """Surová rada [(dátum, hodnota)] alebo None. Cachuje na 12 hodín."""
    name = f"fred_{re.sub(r'[^A-Za-z0-9]', '_', sid)}.json"
    hit = prices._cached(name, TTL)
    if hit:
        return [tuple(x) for x in hit]
    if time.time() < _FAILED["until"]:
        return None
    try:
        pts = _download(sid, date(date.today().year - 12, 1, 1).isoformat())
    except (requests.RequestException, ValueError) as e:
        _FAILED["until"] = time.time() + 1800
        LAST_ERROR["text"] = f"{type(e).__name__}: {str(e)[:160]}"
        return None
    if not pts:
        return None
    LAST_ERROR["text"] = None
    prices._store(name, [list(p) for p in pts])
    return pts


def page_data(years=10, today=None):
    """Zoznam kariet: {'id','name','unit','desc','last','last_date','chg_1y','points'|None}."""
    today = today or date.today()
    lim = date(today.year - years, today.month, 1).isoformat()
    from concurrent.futures import ThreadPoolExecutor
    ids = [s[0] for s in SERIES]
    first = get_points(ids[0])                                  # ak FRED nejde, ostatné netreba skúšať
    got = {ids[0]: first}
    if first is not None:
        with ThreadPoolExecutor(max_workers=4) as ex:          # zvyšok paralelne
            got.update(zip(ids[1:], ex.map(get_points, ids[1:])))
    cards = []
    for sid, name, unit, desc, as_yoy in SERIES:
        pts = got.get(sid)
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

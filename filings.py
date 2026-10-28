"""Podrobné výkazy „ako ich firma uvádza“.

Štandardizované údaje (companyfacts API) obsahujú len súčty, bez členenia
(napr. tržby za tovar a za služby). Podrobné riadky sú v samotných podaniach
SEC. Každé podanie má vygenerované stránky R2.htm, R4.htm... (výkazy) a súbor
FilingSummary.xml s ich zoznamom. Tu ich sťahujeme, čítame z nich tabuľky,
zlučujeme viac podaní do jedného časového radu a pre kvartálny pohľad
dopočítavame samostatné kvartály (Q4 = rok − 9M, cash flow = rozdiely
kumulatívnych hodnôt).
"""
import os
import re
import threading
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from html.parser import HTMLParser

import requests

import edgar
from edgar import EdgarError

ARCHIVE = "https://www.sec.gov/Archives/edgar/data/{cik}/{acc}/{name}"
ANNUAL_FORMS = {"10-K", "10-KT", "10-K405", "20-F", "40-F"}
QUARTERLY_FORMS = {"10-Q", "10-QT"}
MAX_ANNUAL_YEARS = 12
MAX_QUARTERLY_YEARS = 5
KINDS = ("income", "balance", "cashflow")

_lock = threading.Lock()
_last = [0.0]
MONTHS = {m: i + 1 for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}


# ---------------------------------------------------------------- sťahovanie
def _throttle():
    """SEC dovoľuje najviac 10 požiadaviek za sekundu."""
    with _lock:
        d = time.time() - _last[0]
        if d < 0.12:
            time.sleep(0.12 - d)
        _last[0] = time.time()


def _cache_path(company, acc, name):
    return os.path.join(edgar.CACHE_DIR, "filings", str(company["cik"]), acc, name)


def fetch_text(company, acc, name):
    """Text súboru z podania alebo None, ak neexistuje. Podania sa nemenia,
    preto sa cachujú natrvalo."""
    acc_nd = acc.replace("-", "")
    if company["is_demo"]:
        p = os.path.join(edgar.DEMO_DIR, "filings", company["ticker"], acc_nd, name)
        if not os.path.exists(p):
            return None
        with open(p, encoding="utf-8") as f:
            return f.read()
    cp = _cache_path(company, acc_nd, name)
    if os.path.exists(cp):
        with open(cp, encoding="utf-8") as f:
            txt = f.read()
        return txt or None
    url = ARCHIVE.format(cik=company["cik"], acc=acc_nd, name=name)
    last_err = None
    for attempt in range(3):
        _throttle()
        try:
            r = requests.get(url, headers={"User-Agent": edgar._user_agent()}, timeout=40)
        except requests.RequestException as e:
            last_err = e
            time.sleep(1 + attempt)
            continue
        if r.status_code == 404:
            txt = ""
        elif r.status_code in (403, 429, 503):
            last_err = EdgarError(f"SEC dočasne odmietla požiadavku (HTTP {r.status_code}).")
            time.sleep(2 + 2 * attempt)
            continue
        else:
            r.raise_for_status()
            txt = r.text
        os.makedirs(os.path.dirname(cp), exist_ok=True)
        with open(cp, "w", encoding="utf-8") as f:
            f.write(txt)
        return txt or None
    raise EdgarError("Nepodarilo sa stiahnuť podanie zo SEC "
                     f"({last_err.__class__.__name__ if last_err else 'chyba'}).")


# ------------------------------------------------------------- zoznam podaní
def list_filings(recent, forms):
    """recent = subs['filings']['recent'] (paralelné polia). Najnovšie prvé."""
    out = []
    n = len(recent.get("accessionNumber", []))
    for i in range(n):
        form = recent["form"][i]
        if form in forms:
            out.append({"form": form, "acc": recent["accessionNumber"][i],
                        "report_date": recent.get("reportDate", [""] * n)[i] or
                        recent.get("filingDate", [""] * n)[i]})
    out.sort(key=lambda f: f["report_date"], reverse=True)
    return out


def classify(short_name):
    s = short_name.upper()
    if any(k in s for k in ("PARENTHETICAL", "(DETAILS", "TABLES", "POLICIES", "NARRATIVE")):
        return None
    if "CASH FLOW" in s:
        return "cashflow"
    if any(k in s for k in ("BALANCE SHEET", "FINANCIAL POSITION", "FINANCIAL CONDITION",
                            "ASSETS AND LIABILITIES")):
        return "balance"
    if "COMPREHENSIVE" in s and not any(k in s for k in ("OPERATIONS", "INCOME AND", "EARNINGS")):
        return None
    if any(k in s for k in ("OPERATIONS", "INCOME", "EARNINGS", "PROFIT OR LOSS",
                            "PROFIT AND LOSS")):
        return "income"
    return None


def parse_filing_summary(xml_text):
    """{'income': 'R4.htm', 'balance': 'R2.htm', 'cashflow': 'R8.htm'}"""
    out = {}
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return out
    reports = []
    for rep in root.iter("Report"):
        g = lambda tag: (rep.findtext(tag) or "").strip()  # noqa: E731
        reports.append((int(g("Position") or 9999), g("ShortName"), g("HtmlFileName"),
                        g("MenuCategory")))
    reports.sort()
    for _, short, fname, cat in reports:
        if cat and cat.lower() != "statements":
            continue
        kind = classify(short)
        if kind and kind not in out and fname:
            out[kind] = fname
    return out


# ------------------------------------------------------------- parser tabuľky
class _Cell:
    def __init__(self, tag, attrs):
        a = dict(attrs)
        self.tag = tag
        self.cls = a.get("class") or ""
        self.colspan = int(re.sub(r"\D", "", a.get("colspan") or "1") or 1)
        self.text = ""
        self.concept = None


class _TableParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows = []
        self._row = None
        self._cell = None
        self._depth = 0
        self._done = False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "table":
            if self._done:
                return
            cls = a.get("class") or ""
            if self._depth == 0 and "report" not in cls:
                return
            self._depth += 1
        elif self._depth == 1 and tag == "tr":
            self._row = []
        elif self._depth == 1 and tag in ("td", "th") and self._row is not None:
            self._cell = _Cell(tag, attrs)
        elif self._cell is not None and tag == "a":
            m = re.search(r"defref_([A-Za-z0-9\-]+_[A-Za-z0-9_\-\.]+)", a.get("onclick") or "")
            if m:
                self._cell.concept = m.group(1)
        elif self._cell is not None and tag == "br":
            self._cell.text += " "

    def handle_endtag(self, tag):
        if tag == "table" and self._depth:
            self._depth -= 1
            if self._depth == 0:
                self._done = True
        elif self._depth == 1 and tag in ("td", "th") and self._cell is not None:
            self._cell.text = re.sub(r"\s+", " ", self._cell.text).strip()
            self._row.append(self._cell)
            self._cell = None
        elif self._depth == 1 and tag == "tr" and self._row is not None:
            if self._row:
                self.rows.append(self._row)
            self._row = None

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.text += data


def parse_date(text):
    m = re.search(r"([A-Za-z]{3,9})\.?\s+(\d{1,2}),?\s+(\d{4})", text)
    if not m:
        return None
    mon = MONTHS.get(m.group(1)[:3].lower())
    if not mon:
        return None
    try:
        return date(int(m.group(3)), mon, int(m.group(2)))
    except ValueError:
        return None


def parse_months(text):
    m = re.search(r"(\d+)\s*(Months?|Weeks?)\s+Ended", text, re.I)
    if not m:
        return None
    n = int(m.group(1))
    if m.group(2).lower().startswith("week"):
        return max(1, round(n / 4.345))
    return n


def parse_number(text):
    """'$ (1,234)' -> -1234.0;  '—' -> None."""
    t = re.sub(r"\[\d+\]", "", text.replace("\xa0", " ")).strip()  # poznámky pod čiarou [1]
    if not t:
        return None
    neg = "(" in t and ")" in t
    t = re.sub(r"[^\d.,\-]", "", t)
    if not t or not re.search(r"\d", t):
        return None
    t = t.replace(",", "")
    try:
        v = float(t)
    except ValueError:
        return None
    return -abs(v) if neg else v


SCALE = {"millions": 1e6, "thousands": 1e3, "billions": 1e9}


def _scales(title):
    money, shares = 1.0, None
    for pre, word in re.findall(r"(?:(\S+)\s+)?in\s+(Millions|Thousands|Billions)", title, re.I):
        sc = SCALE[word.lower()]
        if pre.lower() == "shares":
            shares = sc
        else:
            money = sc
    return money, (shares if shares is not None else money)


EPS_RE = re.compile(r"per (common |ordinary )?(share|adr)|earnings per|\beps\b", re.I)
SHARES_RE = re.compile(r"\bshares\b|number of (common )?shares", re.I)
TOTAL_RE = re.compile(r"^(total|net (cash|income|loss|increase|decrease|earnings|change)|"
                      r"gross (profit|margin)|operating (income|loss|profit)|"
                      r"income \(loss\) before|income before|profit before|loss before)", re.I)


SHARES_FIRST_RE = re.compile(r"weighted|shares (used|outstanding|issued)|number of "
                             r"(common |ordinary )?shares", re.I)


def row_kind(label):
    low = label.lower().strip()
    if SHARES_FIRST_RE.search(low) and not low.startswith(("basic", "diluted", "net", "earnings",
                                                           "income", "loss")):
        return "shares"
    if EPS_RE.search(label):
        return "eps"
    if SHARES_RE.search(label):
        return "shares"
    return "money"


def parse_report(html):
    """Vráti {'title','currency','cols':[{'end','months'}],'rows':[...]} alebo None."""
    p = _TableParser()
    p.feed(html)
    rows = p.rows
    if not rows:
        return None
    hdr = [r for r in rows if all(c.tag == "th" for c in r)]
    body = [r for r in rows if not all(c.tag == "th" for c in r)]
    if not hdr:
        return None
    title = next((c.text for r in hdr for c in r if "tl" in c.cls.split()), hdr[0][0].text)
    cur = re.search(r"\b([A-Z]{3})\s*\(", title)
    money, shares = _scales(title)

    def value_cells(row):
        return [c for c in row if "tl" not in c.cls.split()]

    date_idx = None
    for i, r in enumerate(hdr):
        ds = [parse_date(c.text) for c in value_cells(r)]
        if ds and all(d is not None for d in ds):
            date_idx = i
    if date_idx is None:
        return None
    dates = [parse_date(c.text) for c in value_cells(hdr[date_idx])]
    months = [None] * len(dates)
    if date_idx > 0:
        exp = []
        for c in value_cells(hdr[date_idx - 1]):
            exp += [parse_months(c.text)] * c.colspan
        if len(exp) == len(dates):
            months = exp
    cols = [{"end": d, "months": m} for d, m in zip(dates, months)]

    out_rows, in_group, group_kind = [], False, "money"
    for r in body:
        label_cell = r[0]
        label = re.sub(r"\s*\[\d+\]", "", label_cell.text).strip()
        if not label:
            continue
        raw_vals = [parse_number(c.text) for c in r[1:1 + len(cols)]]
        raw_vals += [None] * (len(cols) - len(raw_vals))
        has_vals = any(v is not None for v in raw_vals)
        kind = row_kind(label)
        if kind == "money" and in_group and group_kind != "money":
            kind = group_kind  # „Basic“/„Diluted“ pod hlavičkou o akciách alebo EPS
        mult = {"money": money, "shares": shares, "eps": 1.0}[kind]
        vals = [None if v is None else v * mult for v in raw_vals]
        bold = False
        if not has_vals:
            in_group = True
            group_kind = kind
            out_rows.append({"label": label, "concept": label_cell.concept, "kind": kind,
                             "vals": vals, "header": True, "indent": 0, "bold": True})
            continue
        indent = 1 if in_group else 0
        if TOTAL_RE.match(label):
            bold, indent, in_group = True, 0, False
        out_rows.append({"label": label, "concept": label_cell.concept, "kind": kind,
                         "vals": vals, "header": False, "indent": indent, "bold": bold})
    if not any(not r["header"] for r in out_rows):
        return None
    return {"title": title, "currency": cur.group(1) if cur else None,
            "cols": cols, "rows": out_rows}


# ---------------------------------------------------------- načítanie podania
def load_filing(company, filing):
    """{'income': parsed|None, 'balance': ..., 'cashflow': ...} pre jedno podanie."""
    out = {k: None for k in KINDS}
    summary = fetch_text(company, filing["acc"], "FilingSummary.xml")
    if not summary:
        return out
    pages = parse_filing_summary(summary)
    for kind, fname in pages.items():
        html = fetch_text(company, filing["acc"], fname)
        if html:
            try:
                out[kind] = parse_report(html)
            except Exception:  # noqa: BLE001 - poškodená stránka nesmie zhodiť aplikáciu
                out[kind] = None
    return out


# ------------------------------------------------------------------ zlučovanie
def _norm(label):
    return re.sub(r"[^a-z0-9]+", " ", label.lower()).strip()


def _merge_rows(reports):
    """reports: spracované výkazy od najnovšieho. Vráti (order, meta, raw)."""
    order, meta, raw = [], {}, {}
    for rep in reports:
        seen, prev = {}, None
        for row in rep["rows"]:
            nk = _norm(row["label"])
            seen[nk] = seen.get(nk, 0) + 1
            key = (nk, seen[nk])
            if key not in meta:
                meta[key] = {k: row[k] for k in ("label", "kind", "indent", "bold", "header")}
                pos = order.index(prev) + 1 if prev in order else 0
                order.insert(pos, key)
            prev = key
            for col, v in zip(rep["cols"], row["vals"]):
                if v is not None:
                    raw.setdefault(key, {}).setdefault((col["end"], col["months"]), v)
    return order, meta, raw


def _near(target, candidates, tol):
    best = None
    for c in candidates:
        d = abs((c - target).days)
        if d <= tol and (best is None or d < best[0]):
            best = (d, c)
    return best[1] if best else None


def _shift_back(end, ends, months=3):
    """Koniec predchádzajúceho kvartálu (približne `months` mesiacov pred `end`)."""
    return _near(end - timedelta(days=round(months * 30.4)), ends, 9)


def _quarter_value(vals, end, ends, additive=True):
    """Samostatný kvartál končiaci `end` z hodnôt {(end, mesiace): v}."""
    if (end, 3) in vals:
        return vals[(end, 3)]
    if not additive:  # vážený priemer akcií sa neodčítava
        return None
    for m in (6, 9, 12):
        if (end, m) in vals:
            prev = _shift_back(end, ends)
            if prev is None:
                return None
            pv = vals.get((prev, m - 3))
            if pv is None:
                return None
            return vals[(end, m)] - pv
    return None


def merge_statement(reports, kind, mode, n):
    """Zlúči výkazy jedného druhu z viacerých podaní do časového radu."""
    if not reports:
        return None
    order, meta, raw = _merge_rows(reports)
    if kind == "balance":
        ends = sorted({e for v in raw.values() for (e, _m) in v})
        series = {k: {e: val for (e, m), val in v.items()} for k, v in raw.items()}
        return order, meta, series, ends
    # toky: ročné alebo kvartálne
    if mode == "annual":
        series = {k: {e: val for (e, m), val in v.items() if m == 12} for k, v in raw.items()}
        ends = sorted({e for s in series.values() for e in s})
        return order, meta, series, ends
    all_ends = sorted({e for v in raw.values() for (e, m) in v if m in (3, 6, 9, 12)})
    series = {}
    for k, v in raw.items():
        s = {}
        for e in all_ends:
            q = _quarter_value(v, e, all_ends, meta[k]["kind"] != "shares")
            if q is not None:
                s[e] = q
        series[k] = s
    ends = sorted({e for s in series.values() for e in s})
    return order, meta, series, ends


def _build_statement(kind, reports, mode, display_ends):
    res = merge_statement(reports, kind, mode, len(display_ends))
    if res is None:
        return None
    order, meta, series, ends = res
    rows = []
    for key in order:
        s = series.get(key, {})
        vals = {}
        for e in display_ends:
            v = s.get(e)
            if v is None:
                near = _near(e, s.keys(), 6)
                v = s.get(near) if near else None
            vals[e] = v
        m = meta[key]
        if not m["header"] and all(v is None for v in vals.values()):
            continue
        rows.append(dict(m, vals=vals))
    # prázdne hlavičky skupín (bez riadkov pod nimi) vyhodiť
    clean = []
    for i, r in enumerate(rows):
        if r["header"] and (i + 1 >= len(rows) or rows[i + 1]["header"]):
            continue
        clean.append(r)
    return clean


def get_detailed(company, mode, years):
    """Podrobné výkazy {'income': [...], 'balance': [...], 'cashflow': [...],
    'ends': [...], 'filings': n, 'capped': bool} alebo EdgarError."""
    recent = (company.get("filings") or {})
    if not recent:
        raise EdgarError("Zoznam podaní tejto firmy nie je dostupný.")
    if mode == "annual":
        yrs = min(years, MAX_ANNUAL_YEARS)
        ann = list_filings(recent, ANNUAL_FORMS)
        chosen = ann[::2][:(yrs + 1) // 2]  # každé 10-K pokrýva 2 súvahy a 3 roky výsledkov
        n_cols = yrs
    else:
        yrs = min(years, MAX_QUARTERLY_YEARS)
        allf = list_filings(recent, ANNUAL_FORMS | QUARTERLY_FORMS)
        chosen = allf[:yrs * 4 + 1]
        n_cols = yrs * 4
    if not chosen:
        raise EdgarError("Pre túto firmu sa nenašli výročné ani štvrťročné podania.")
    with ThreadPoolExecutor(max_workers=4) as ex:
        loaded = list(ex.map(lambda f: load_filing(company, f), chosen))
    by_kind = {k: [ld[k] for ld in loaded if ld[k]] for k in KINDS}
    if not by_kind["income"]:
        raise EdgarError("Z podaní sa nepodarilo prečítať výkaz ziskov a strát "
                         "(firma nemusí mať výkazy v XBRL formáte).")
    inc = merge_statement(by_kind["income"], "income", mode, n_cols)
    all_ends = inc[3]
    if not all_ends:
        raise EdgarError("V podaniach sa nenašli žiadne obdobia výkazu ziskov a strát.")
    display = all_ends[-n_cols:]
    out = {"ends": display, "filings": len(chosen), "years": yrs,
           "capped": (years > yrs)}
    for k in KINDS:
        out[k] = _build_statement(k, by_kind[k], mode, display) or []
    return out

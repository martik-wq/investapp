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


def _reports(xml_text):
    """Zoznam stránok podania: [(poloha, názov, súbor, kategória)] podľa polohy."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []
    out = []
    for rep in root.iter("Report"):
        g = lambda tag: (rep.findtext(tag) or "").strip()  # noqa: E731
        try:
            pos = int(g("Position") or 9999)
        except ValueError:
            pos = 9999
        out.append((pos, g("ShortName"), g("HtmlFileName"), g("MenuCategory")))
    out.sort()
    return out


def parse_filing_summary(xml_text):
    """{'income': 'R4.htm', 'balance': 'R2.htm', 'cashflow': 'R8.htm'}"""
    out = {}
    for _, short, fname, cat in _reports(xml_text):
        if cat and cat.lower() != "statements":
            continue
        kind = classify(short)
        if kind and kind not in out and fname:
            out[kind] = fname
    return out


DETAIL_GOOD = (("disaggregat", 3), ("revenue by", 3), ("by product", 2), ("product", 2),
               ("service", 2), ("type", 2), ("revenue", 1), ("net sales", 1), ("sales", 1),
               ("segment", 1))
DETAIL_BAD = ("concentration", "allowance", "contract balance", "remaining performance",
              "deferred revenue", "unbilled", "receivable", "lease", "tax", "per share",
              "stock", "debt", "fair value", "goodwill", "intangible", "acquisition")
GEO_RE = re.compile(r"geograph|region|countr|international|domestic|united states|by location",
                    re.I)


def detail_pages(xml_text, limit=8):
    """Stránky „(Details)“ o tržbách, od najpravdepodobnejších: [(súbor, názov, geo)]."""
    scored = []
    for _, short, fname, cat in _reports(xml_text):
        if not fname or cat.lower() not in ("details", "tables"):
            continue
        low = short.lower()
        if "detail" not in low or any(b in low for b in DETAIL_BAD):
            continue
        sc = sum(w for k, w in DETAIL_GOOD if k in low)
        if sc <= 0:
            continue
        geo = bool(GEO_RE.search(low))
        scored.append((sc - (3 if geo else 0), fname, short, geo))
    scored.sort(key=lambda x: -x[0])
    return [(f, s, g) for _, f, s, g in scored[:limit]]


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
    out["subs"] = False
    if mode == "annual":
        try:
            with ThreadPoolExecutor(max_workers=2) as ex:
                futs = {k: ex.submit(attach_subaccounts, company, chosen, out[k], display)
                        for k in ("balance", "cashflow")}
                for k, fu in futs.items():
                    new = fu.result()
                    if len(new) != len(out[k]):
                        out["subs"] = True
                    out[k] = new
        except Exception:  # noqa: BLE001 - podúčty sú len bonus, výkazy musia ostať
            pass
    return out


# ------------------------------------------------- členenie tržieb (streams)
MEMBER_RE = re.compile(r"\s*\[(Member|Axis|Domain|Line Items|Abstract|Table)\]\s*$", re.I)


def _clean_label(label):
    return MEMBER_RE.sub("", label).strip()


REV_LABEL_RE = re.compile(r"revenue|sales|\bnet sales\b|turnover", re.I)
COST_LABEL_RE = re.compile(r"cost|expense|deferred|unearned", re.I)


def _col_index(rep, end, months, tol=5):
    best = None
    for i, c in enumerate(rep["cols"]):
        if c["months"] != months:
            continue
        d = abs((c["end"] - end).days)
        if d <= tol and (best is None or d < best[0]):
            best = (d, i)
    return best[1] if best else None


def _expand(rows, idx, depth=0):
    """Ak je riadok `idx` súčtom riadkov nad ním, nahradí ho jeho zložkami."""
    label, v, pv = rows[idx]
    if depth < 3 and v and v > 0:
        acc, parts = 0.0, []
        for j in range(idx - 1, -1, -1):
            acc += rows[j][1]
            parts.append(j)
            if len(parts) >= 2 and abs(acc - v) <= 0.003 * abs(v):
                out = []
                for k in sorted(parts):
                    out += _expand(rows, k, depth + 1)
                return out
            if len(parts) > 12:
                break
    return [(label, v, pv)]


def extract_breakdown(rep, end, months, expected_total=None, tol=0.012):
    """Členenie tržieb zo stránky výkazu/poznámky: riadky, ktorých súčet sedí s
    riadkom „Total“. Vráti {'items':[{'label','value','prev'}], 'total'} alebo None."""
    ci = _col_index(rep, end, months)
    if ci is None:
        return None
    pi = _col_index(rep, date(end.year - 1, end.month, min(end.day, 28)), months, tol=12)
    rows = []
    for r in rep["rows"]:
        if r["header"] or r["kind"] != "money" or r["vals"][ci] is None:
            continue
        rows.append((_clean_label(r["label"]), r["vals"][ci],
                     r["vals"][pi] if pi is not None else None))
    best = None
    for t, (lab, v, pv) in enumerate(rows):
        if v <= 0 or t < 2:
            continue
        if expected_total:
            if abs(v - expected_total) > tol * abs(expected_total):
                continue
        elif not REV_LABEL_RE.search(lab) or COST_LABEL_RE.search(lab):
            continue  # bez očakávaných tržieb musí „súčet“ vyzerať ako tržby
        acc, parts = 0.0, []
        for j in range(t - 1, -1, -1):
            acc += rows[j][1]
            parts.append(j)
            if len(parts) >= 2 and abs(acc - v) <= 0.003 * abs(v):
                items = []
                for k in sorted(parts):
                    items += _expand(rows, k)
                if len(items) >= 2 and (best is None or len(items) > len(best["items"])):
                    best = {"items": [{"label": a, "value": b, "prev": c}
                                      for a, b, c in items],
                            "total": v, "total_prev": pv, "total_label": lab}
                break
            if len(parts) > 14:
                break
    return best


def _window_from_rows(rows, target, tol=0.004):
    """rows = [(label, hodnota, predošlá)]. Súvislý úsek, ktorého súčet sedí s `target`."""
    cands = []
    for i in range(len(rows)):
        acc = 0.0
        for j in range(i, len(rows)):
            if rows[j][1] <= 0:
                break
            acc += rows[j][1]
            if j > i and abs(acc - target) <= tol * target:
                cands.append((i, j))
                break
            if acc > target * 1.01:
                break
    cands.sort(key=lambda c: -(c[1] - c[0]))
    for i, j in cands:
        items = []
        for k in range(i, j + 1):
            items += _expand(rows, k)
        keys = [_norm(a) for a, _b, _c in items]
        if len(items) >= 2 and len(set(keys)) == len(keys):  # bez zdvojených (súčet + zložky)
            return {"items": [{"label": a, "value": b, "prev": c} for a, b, c in items]}
    return None


def extract_window(rep, end, months, target, tol=0.004):
    """Súvislý úsek riadkov výkazu, ktorých súčet sedí s `target` (napr. prevádzkové
    náklady). Podsúčty sa rozpadnú na zložky. Vráti {'items': [...]} alebo None."""
    ci = _col_index(rep, end, months)
    if ci is None or not target or target <= 0:
        return None
    pi = _col_index(rep, date(end.year - 1, end.month, min(end.day, 28)), months, tol=12)
    rows = []
    for r in rep["rows"]:
        if r["header"] or r["kind"] != "money" or r["vals"][ci] is None:
            continue
        rows.append((_clean_label(r["label"]), r["vals"][ci],
                     r["vals"][pi] if pi is not None else None))
    return _window_from_rows(rows, target, tol)


# ------------------------------------------- podúčty k riadkom súvahy a cash flow
SUB_STOP = {"and", "the", "of", "in", "on", "to", "for", "net", "other", "total", "details", "detail",
            "additional", "information", "components", "component", "schedule", "summary", "table",
            "tables", "current", "non", "noncurrent", "balance", "sheet", "sheets", "narrative",
            "parenthetical", "policies", "accounting", "disclosures", "supplemental", "description",
            "business", "from", "with", "by", "at", "or", "a", "an", "less", "plus"}
SUB_SKIP_LABEL = re.compile(r"beginning|ending|balance at|balances at|end of|start of|"
                            r"accumulated|\bnet of\b|^total\b", re.I)


def _tokens(text):
    out = set()
    for w in re.findall(r"[a-z]+", text.lower()):
        if w in SUB_STOP or len(w) < 3:
            continue
        out.add(w[:-1] if w.endswith("s") and len(w) > 4 else w)
    return out


def _detail_page_list(summary_xml):
    """[(súbor, názov časti za poslednou pomlčkou)] pre stránky „(Details)“."""
    out = []
    for _, short, fname, cat in _reports(summary_xml):
        if not fname or (cat or "").lower() != "details":
            continue
        low = short.lower()
        if "parenthetical" in low or "(details" not in low:
            continue
        title = short.split(" - ")[-1]
        out.append((fname, title))
    return out


def _col_by_date(rep, end, tol=5):
    best = None
    for i, c in enumerate(rep["cols"]):
        d = abs((c["end"] - end).days)
        if d <= tol and (best is None or d < best[0]):
            best = (d, i)
    return best[1] if best else None


def attach_subaccounts(company, filings_list, rows, display_ends, fetch=None, max_pages_per_row=4):
    """Ku riadkom súvahy / cash flow doplní podúčty z poznámok („Details“ stránok podania).
    Podúčet sa pridá len vtedy, keď súčet zložiek na stránke sedí s hodnotou riadku (±0,4 %),
    takže sa nič nedomýšľa. Vráti nový zoznam riadkov."""
    fetch = fetch or fetch_text
    if not rows or not filings_list:
        return rows
    page_cache = {}

    def page(acc, fname):
        k = (acc, fname)
        if k not in page_cache:
            html = fetch(company, acc, fname)
            try:
                page_cache[k] = parse_report(html) if html else None
            except Exception:  # noqa: BLE001
                page_cache[k] = None
        return page_cache[k]

    lists = {}
    for f in filings_list:
        summary = fetch(company, f["acc"], "FilingSummary.xml")
        lists[f["acc"]] = _detail_page_list(summary) if summary else []
    used_pages = set()
    children = {}   # index riadku -> {norm: {'label', 'vals'}} + poradie
    for idx, row in enumerate(rows):
        if row.get("header") or row.get("kind") != "money" or row.get("sub"):
            continue
        if TOTAL_RE.match(row["label"]):
            continue
        rt = _tokens(row["label"])
        if not rt:
            continue
        targets = {e: v for e, v in row["vals"].items() if v not in (None, 0) and e in display_ends}
        if not targets:
            continue
        found = {}
        order = []
        for f in filings_list:
            cands = []
            for fname, title in lists[f["acc"]]:
                pt = _tokens(title)
                ov = len(rt & pt)
                if ov and (f["acc"], fname) not in used_pages:
                    cands.append((ov / len(rt | pt), fname))
            cands.sort(reverse=True)
            for _score, fname in cands[:max_pages_per_row]:
                rep = page(f["acc"], fname)
                if not rep:
                    continue
                matched = False
                for e, tv in targets.items():
                    ci = _col_by_date(rep, e)
                    if ci is None:
                        continue
                    pi = None
                    rws = []
                    for r in rep["rows"]:
                        if r["header"] or r["kind"] != "money" or r["vals"][ci] is None:
                            continue
                        rws.append((_clean_label(r["label"]), r["vals"][ci], None))
                    w = _window_from_rows(rws, abs(tv))
                    if not w or len(w["items"]) > 25:
                        continue
                    if any(SUB_SKIP_LABEL.search(it["label"]) for it in w["items"]):
                        continue
                    sign = 1.0 if tv > 0 else -1.0
                    for it in w["items"]:
                        key = _norm(it["label"])
                        if key not in found:
                            found[key] = {"label": it["label"], "vals": {}}
                            order.append(key)
                        found[key]["vals"][e] = sign * it["value"]
                    matched = True
                if matched:
                    used_pages.add((f["acc"], fname))
                    break
        if found and len(order) >= 2:
            children[idx] = [found[k] for k in order]
    out = []
    for idx, row in enumerate(rows):
        out.append(row)
        for ch in children.get(idx, ()):
            vals = {e: ch["vals"].get(e) for e in display_ends}
            out.append({"label": ch["label"], "kind": "money", "indent": 2, "bold": False,
                        "header": False, "sub": True, "vals": vals})
    return out


def _income_window_candidates(company, filing, end, months, target):
    """Kandidáti na rozpis nákladov z výkazu ziskov a strát jedného podania."""
    summary = fetch_text(company, filing["acc"], "FilingSummary.xml")
    if not summary:
        return []
    fname = parse_filing_summary(summary).get("income")
    if not fname:
        return []
    html = fetch_text(company, filing["acc"], fname)
    if not html:
        return []
    try:
        rep = parse_report(html)
    except Exception:  # noqa: BLE001
        return []
    if not rep:
        return []
    bd = extract_window(rep, end, months, target)
    if not bd:
        return []
    bd["geo"], bd["page"] = False, "výkaz"
    return [bd]


def _filing_candidates(company, filing, end, months, expected_total):
    """Všetky nájdené členenia tržieb v jednom podaní (výkaz + poznámky)."""
    summary = fetch_text(company, filing["acc"], "FilingSummary.xml")
    if not summary:
        return []
    pages = []
    stm = parse_filing_summary(summary)
    if stm.get("income"):
        pages.append((stm["income"], "výkaz", False))
    pages += [(f, s, g) for f, s, g in detail_pages(summary)]
    out = []
    for fname, short, geo in pages:
        html = fetch_text(company, filing["acc"], fname)
        if not html:
            continue
        try:
            rep = parse_report(html)
        except Exception:  # noqa: BLE001
            continue
        if not rep:
            continue
        bd = extract_breakdown(rep, end, months, expected_total)
        if bd:
            bd["geo"], bd["page"] = geo, short
            out.append(bd)
    return out


def _best(cands):
    if not cands:
        return None
    return sorted(cands, key=lambda c: (c["geo"], -min(len(c["items"]), 9)))[0]


def _near_date(f, d, tol=8):
    try:
        y, m, dd = (int(x) for x in f["report_date"].split("-"))
    except (ValueError, AttributeError):
        return False
    return abs((date(y, m, dd) - d).days) <= tol


def revenue_breakdown(company, end, months, expected_total, expected_fy=None, expected_9m=None):
    """Členenie tržieb za obdobie končiace `end` (months = 3 alebo 12).
    Vráti [{'label','value','prev'}] alebo None. Q4 sa dopočíta ako rok − 9M."""
    return _period_items(company, end, months, expected_total, expected_fy, expected_9m,
                         _filing_candidates)


def cost_components(company, end, months, target, expected_fy=None, expected_9m=None):
    """Položky nákladov z výkazu ziskov a strát, ktorých súčet sedí s `target`."""
    return _period_items(company, end, months, target, expected_fy, expected_9m,
                         _income_window_candidates)


def _period_items(company, end, months, expected_total, expected_fy, expected_9m, gather):
    recent = company.get("filings") or {}
    if not recent:
        return None
    allf = list_filings(recent, ANNUAL_FORMS | QUARTERLY_FORMS)
    direct = [f for f in allf if _near_date(f, end)]
    if months == 12:
        k = [f for f in direct if f["form"] in ANNUAL_FORMS]
        best = _best(gather(company, k[0], end, 12, expected_total)) if k else None
        return best["items"] if best else None
    q = [f for f in direct if f["form"] in QUARTERLY_FORMS]
    if q:
        best = _best(gather(company, q[0], end, 3, expected_total))
        return best["items"] if best else None
    k = [f for f in direct if f["form"] in ANNUAL_FORMS]
    if not k:
        return None
    q3_end = end - timedelta(days=91)
    q3 = [f for f in allf if f["form"] in QUARTERLY_FORMS and _near_date(f, q3_end, 12)]
    if not q3 or (gather is not _filing_candidates and not (expected_fy and expected_9m)):
        return None
    q3_date = date(*(int(x) for x in q3[0]["report_date"].split("-")))
    fy = gather(company, k[0], end, 12, expected_fy)
    nine = gather(company, q3[0], q3_date, 9, expected_9m)
    best = None
    for a in fy:
        for b in nine:
            ma = {_norm(i["label"]): i for i in a["items"]}
            mb = {_norm(i["label"]): i for i in b["items"]}
            if set(ma) != set(mb) or len(ma) < 2:
                continue
            items = []
            for key, ia in ma.items():
                ib = mb[key]
                prev = (ia["prev"] - ib["prev"]) if ia["prev"] is not None and ib["prev"] is not None \
                    else None
                items.append({"label": ia["label"], "value": ia["value"] - ib["value"], "prev": prev})
            total = sum(i["value"] for i in items)
            if expected_total and abs(total - expected_total) > 0.015 * abs(expected_total):
                continue
            cand = {"items": items, "geo": a["geo"]}
            if best is None or (cand["geo"], -len(items)) < (best["geo"], -len(best["items"])):
                best = cand
    return best["items"] if best else None

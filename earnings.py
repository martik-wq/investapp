"""Výsledky a earnings call.

Automaticky: oficiálna tlačová správa k výsledkom (8-K, položka 2.02, príloha EX-99.x) zo SEC. Niektoré firmy v prílohe
podajú aj prepis callu, vtedy sa použije. Úplné prepisy z platených stránok sa nesťahujú (autorské práva), preto je
možné prepis vložiť ručne; ukladá sa len u teba v data/transcripts.

Kľúčové body sú jednoduchý výber viet podľa kľúčových slov a čísel (bez AI), preto sú hrubšie než ľudské zhrnutie."""
import json
import os
import re
from html.parser import HTMLParser

import filings
import portfolio
from edgar import EdgarError

TRANSCRIPT_DIR = os.path.join(portfolio.DATA_DIR, "transcripts")
MAX_PASTE = 600_000   # znakov, ~ 2-hodinový call

CATEGORIES = [
    ("guidance", "Výhľad a guidance", r"\b(guidance|outlook|expect(?:s|ed|ation)?|anticipate|forecast|project(?:s|ed|ion)?|target|full[- ]year|next quarter|fiscal 20\d\d)\b"),
    ("results", "Výsledky", r"\b(record|revenue|net sales|net income|earnings per share|eps|operating (?:income|margin)|gross margin|free cash flow|grew|growth|increase[ds]?|up \d+|year[- ]over[- ]year|compared (?:to|with))\b"),
    ("risks", "Riziká a protivietor", r"\b(headwinds?|pressure|decline[ds]?|decrease[ds]?|weak(?:ness|er)?|tariffs?|uncertain(?:ty)?|challeng\w+|inflation|slowdown|impair\w*|restructuring|lower than|below)\b"),
    ("capital", "Kapitál a návrat akcionárom", r"\b(buybacks?|repurchase[ds]?|dividends?|capex|capital expenditures?|investments? in|share count|debt|liquidity|cash and cash equivalents)\b"),
    ("strategy", "Stratégia a produkty", r"\b(launch(?:ed|es)?|new product|\bAI\b|artificial intelligence|customers?|market share|partnership|acquisition|expand(?:ed|ing)?|demand|pipeline|backlog)\b"),
]
_NUM = re.compile(r"(\$\s?\d|\d+(?:[.,]\d+)?\s?(?:%|percent|billion|million|bps|basis points|x\b))", re.I)


class _Text(HTMLParser):
    """HTML -> text. Tabuľky sa preskakujú pri výbere viet (sú v nich čísla bez súvislostí), ale ostávajú v `tables`."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out, self.skip, self.table = [], 0, 0
        self.tables = []
        self._row = []

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.skip += 1
        elif tag == "table":
            self.table += 1
        elif tag in ("p", "div", "br", "li", "h1", "h2", "h3", "tr") and not self.table:
            self.out.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self.skip = max(0, self.skip - 1)
        elif tag == "table":
            self.table = max(0, self.table - 1)
        elif tag == "tr" and self._row:
            self.tables.append(" | ".join(self._row))
            self._row = []

    def handle_data(self, data):
        if self.skip:
            return
        t = re.sub(r"\s+", " ", data.replace("\xa0", " ")).strip()
        if not t:
            return
        if self.table:
            self._row.append(t)
        else:
            self.out.append(t + " ")


def html_to_text(html):
    p = _Text()
    try:
        p.feed(html)
    except Exception:  # noqa: BLE001 - poškodené HTML nesmie zhodiť stránku
        pass
    text = "".join(p.out)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text).strip()
    return text


# ------------------------------------------------------------------ zoznam a stiahnutie
def list_releases(company, n=12):
    """Podania 8-K s položkou 2.02 (výsledky), najnovšie prvé: [{'acc','date','doc'}]."""
    r = (company.get("filings") or {})
    out = []
    for i, form in enumerate(r.get("form", [])):
        items = (r.get("items") or [""] * len(r["form"]))[i] or ""
        if form in ("8-K", "6-K") and ("2.02" in items.split(",") or form == "6-K" and not items):
            out.append({"acc": r["accessionNumber"][i], "date": r.get("filingDate", [""] * len(r["form"]))[i],
                        "doc": r.get("primaryDocument", [""] * len(r["form"]))[i]})
    out.sort(key=lambda x: x["date"], reverse=True)
    return out[:n]


def _exhibits(company, acc):
    """Názvy príloh EX-99.x z indexu podania (najprv EX-99.1)."""
    txt = filings.fetch_text(company, acc, "index.json")
    if not txt:
        return []
    try:
        items = json.loads(txt)["directory"]["item"]
    except (ValueError, KeyError, TypeError):
        return []
    names = [i["name"] for i in items if re.search(r"(ex|exhibit)[-_]?99", i["name"], re.I)
             and i["name"].lower().endswith((".htm", ".html", ".txt"))]
    return sorted(names, key=lambda n: (not re.search(r"99[-_.]?0?1", n), n))


def get_release(company, acc):
    """{'text', 'files', 'transcript_file'} alebo None. Text tlačovej správy (EX-99.1) a prípadne prepis z inej prílohy."""
    names = _exhibits(company, acc)
    if not names:
        return None
    release, transcript = None, None
    for nm in names[:4]:
        raw = filings.fetch_text(company, acc, nm)
        if not raw:
            continue
        txt = html_to_text(raw)
        if re.search(r"\b(transcript|operator|question-and-answer|q&a session)\b", txt[:6000], re.I) and len(txt) > 15000:
            transcript = transcript or (nm, txt)
        elif release is None:
            release = (nm, txt, release_tables(raw))
    if not release and not transcript:
        return None
    return {"files": names, "release": release[1] if release else None, "release_file": release[0] if release else None,
            "tables": numbers_table(release[2]) if release else [],
            "transcript": transcript[1] if transcript else None, "transcript_file": transcript[0] if transcript else None}


# ------------------------------------------------------------------ kľúčové body
def sentences(text):
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z\"“$0-9])|\n+", text)
    out = []
    for s in parts:
        s = re.sub(r"\s+", " ", s).strip()
        if 40 <= len(s) <= 320 and not s.isupper() and "|" not in s and not re.search(r"forward[- ]looking|safe harbor|undue reliance", s, re.I):
            out.append(s)
    return out


def key_points(text, per_cat=4):
    """{'kľúč': [vety]} – každá veta len v jednej kategórii (tej, kde má najviac zásahov), zoradené podľa skóre."""
    sents = sentences(text)
    best = {}
    forward = re.compile(r"\b(guidance|outlook|expects?|expected|anticipates?|forecasts?|next quarter|full[- ]year)\b", re.I)
    for s in sents:
        nums = len(_NUM.findall(s))
        for key, _label, rx in CATEGORIES:
            hits = len(re.findall(rx, s, re.I))
            if not hits:
                continue
            score = hits * 2 + min(nums, 3) * 2 + (2 if re.search(r"\b(record|guidance|outlook|expect)\b", s, re.I) else 0)
            if s not in best or score > best[s][0]:
                best[s] = (score, key)
        if s in best and forward.search(s):   # výhľad má prednosť pred bežnými výsledkami
            best[s] = (best[s][0] + 2, "guidance")
    out = {k: [] for k, _l, _r in CATEGORIES}
    for s, (score, key) in sorted(best.items(), key=lambda kv: -kv[1][0]):
        if len(out[key]) < per_cat and score >= 5:
            out[key].append(s)
    return {k: v for k, v in out.items() if v}


def numbers_table(tables, limit=14):
    """Prvé riadky tabuliek, ktoré začínajú kľúčovou položkou (tržby, zisk, EPS...) – rýchly prehľad čísel."""
    want = re.compile(r"^(total )?(net )?(revenues?|sales|net income|operating income|diluted|earnings per share|gross (profit|margin)|free cash flow)", re.I)
    out = []
    for row in tables:
        if want.match(row) and re.search(r"\d", row) and row not in out:
            out.append(row[:200])
        if len(out) >= limit:
            break
    return out


def release_tables(html):
    p = _Text()
    try:
        p.feed(html)
    except Exception:  # noqa: BLE001
        pass
    return p.tables


# ------------------------------------------------------------------ vlastný prepis
def _path(ticker, key):
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", f"{ticker}_{key}")
    return os.path.join(TRANSCRIPT_DIR, safe + ".txt")


def load_transcript(ticker, key):
    try:
        with open(_path(ticker, key), encoding="utf-8") as f:
            return f.read()
    except OSError:
        return None


def save_transcript(ticker, key, text):
    text = (text or "").replace("\r\n", "\n").strip()
    if len(text) < 500:
        return False, "Prepis je príliš krátky (aspoň pár odsekov)."
    if len(text) > MAX_PASTE:
        return False, f"Prepis je príliš dlhý (najviac {MAX_PASTE // 1000} tisíc znakov)."
    os.makedirs(TRANSCRIPT_DIR, exist_ok=True)
    with open(_path(ticker, key), "w", encoding="utf-8") as f:
        f.write(text)
    return True, "Prepis uložený."


def delete_transcript(ticker, key):
    try:
        os.remove(_path(ticker, key))
        return True
    except OSError:
        return False


# ------------------------------------------------------------------ hľadanie na stránke pre investorov (IR)
import ipaddress  # noqa: E402
import socket  # noqa: E402
from urllib.parse import urljoin, urlparse  # noqa: E402

import requests  # noqa: E402

_UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"}
IR_PATHS = ("", "/investors", "/investor-relations", "/investor", "/ir", "/investors/earnings", "/earnings")
_NEXT = re.compile(r"(earnings|quarterly[- ]results|financial[- ]results|results|events|webcast|presentations)", re.I)


class _Links(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links, self._href, self._txt = [], None, []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self._href = dict(attrs).get("href")
            self._txt = []

    def handle_data(self, data):
        if self._href is not None:
            self._txt.append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self._href is not None:
            self.links.append((re.sub(r"\s+", " ", "".join(self._txt)).strip(), self._href))
            self._href = None


def safe_url(url):
    """Len http(s) adresy na verejný internet (ochrana pred zneužitím formulára na prístup do vnútornej siete)."""
    try:
        u = urlparse(url)
        if u.scheme not in ("http", "https") or not u.hostname:
            return False
        for info in socket.getaddrinfo(u.hostname, None):
            ip = ipaddress.ip_address(info[4][0])
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                return False
        return True
    except (OSError, ValueError):
        return False


def _get(url, timeout=8):
    if not safe_url(url):
        return None
    try:
        r = requests.get(url, headers=_UA, timeout=timeout, allow_redirects=True)
        if r.status_code != 200 or not safe_url(r.url):
            return None
        return r
    except requests.RequestException:
        return None


def ir_start_urls(website):
    """Možné adresy stránky pre investorov z webu firmy (napr. https://www.apple.com -> investor.apple.com...)."""
    if not website:
        return []
    if not re.match(r"https?://", website):
        website = "https://" + website
    host = urlparse(website).hostname or ""
    base = re.sub(r"^(www|www2|corporate|about)\.", "", host)
    roots = [f"https://investor.{base}", f"https://investors.{base}", f"https://ir.{base}", f"https://{host}"]
    out = []
    for r in roots:
        for p in IR_PATHS:
            if (r.startswith(f"https://{host}") or p == "") and r + p not in out:
                out.append(r + p)
    return out[:10]


def _scan(url, html):
    p = _Links()
    try:
        p.feed(html)
    except Exception:  # noqa: BLE001
        pass
    found, nxt = [], []
    for txt, href in p.links:
        if not href or href.startswith(("#", "javascript:", "mailto:")):
            continue
        full = urljoin(url, href)
        if re.search(r"transcript", txt + " " + href, re.I):
            found.append({"title": (txt or full)[:140], "url": full})
        elif _NEXT.search(txt) and urlparse(full).hostname == urlparse(url).hostname:
            nxt.append(full)
    return found, nxt


def find_ir_transcripts(website, max_fetch=8):
    """Preskúma stránku pre investorov a nájde odkazy so slovom „transcript“. Vráti (odkazy, použité stránky)."""
    seen, found, used, queue, fetched = set(), [], [], ir_start_urls(website), 0
    while queue and fetched < max_fetch:
        url = queue.pop(0)
        if url in seen:
            continue
        seen.add(url)
        r = _get(url)
        fetched += 1
        if not r or "html" not in r.headers.get("content-type", ""):
            continue
        used.append(r.url)
        f, nxt = _scan(r.url, r.text)
        found += [x for x in f if x["url"] not in {y["url"] for y in found}]
        if not found:
            queue = [u for u in nxt[:3] if u not in seen] + queue
        elif len(found) >= 6:
            break
    return found[:15], used


def fetch_transcript_url(url):
    """Stiahne prepis z odkazu (HTML alebo PDF). Vráti (text, chyba)."""
    r = _get(url, timeout=20)
    if not r:
        return None, "Odkaz sa nepodarilo otvoriť (stránka nie je dostupná alebo adresa nie je verejná)."
    ctype = r.headers.get("content-type", "")
    if "pdf" in ctype or url.lower().split("?")[0].endswith(".pdf"):
        try:
            import io

            from pypdf import PdfReader
            text = "\n".join((pg.extract_text() or "") for pg in PdfReader(io.BytesIO(r.content)).pages)
        except ImportError:
            return None, "Na čítanie PDF chýba knižnica pypdf (spusti: pip install pypdf), alebo vlož text ručne."
        except Exception as e:  # noqa: BLE001
            return None, f"PDF sa nepodarilo prečítať ({e.__class__.__name__})."
    else:
        text = html_to_text(r.text)
    if len(text) < 3000:
        return None, "Stránka neobsahuje dostatočne dlhý text (možno sa načítava cez JavaScript). Skús vložiť prepis ručne."
    return text, None

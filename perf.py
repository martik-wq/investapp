"""Výkonnosť portfólia: denná hodnota cenných papierov, časovo vážený výnos (TWR) a
zisk/strata po obdobiach. Porovnanie s indexmi vo vybranej mene.

Metóda (rovnaká ako pri fondoch): výnos dňa = (hodnota na konci dňa + dividendy − nákupy
+ predaje) / hodnota včera − 1. Nákupy a predaje (vklady do/výbery z cenných papierov)
preto výnos neovplyvňujú, kým by pri jednoduchom porovnaní hodnôt vyzerali ako zisk
alebo strata. Hotovosť na účte sa nepočíta, rovnako ako pri indexoch.
"""
from bisect import bisect_right
from collections import defaultdict
from datetime import date, datetime, timedelta

MIN_VALUE = 1e-6


class Series:
    """Denné hodnoty s dopĺňaním posledného známeho (cez víkendy a sviatky)."""

    def __init__(self, dates, values):
        pairs = sorted((d.toordinal(), v) for d, v in zip(dates, values) if v is not None)
        self.o = [p[0] for p in pairs]
        self.v = [p[1] for p in pairs]

    def at(self, day):
        i = bisect_right(self.o, day.toordinal()) - 1
        return self.v[i] if i >= 0 else None

    @property
    def first(self):
        return date.fromordinal(self.o[0]) if self.o else None

    @property
    def last(self):
        return date.fromordinal(self.o[-1]) if self.o else None

    def __bool__(self):
        return bool(self.o)


def to_series(hist, field="close"):
    """hist = {'dates': [iso], 'close': [...], 'adj': [...], 'currency': 'USD'} -> (Series, mena).
    Londýnske ceny v penciach (GBp/GBX) sa prepočítajú na libry."""
    if not hist or not hist.get("dates"):
        return None, None
    vals = hist.get(field) or hist.get("close")
    ccy = hist.get("currency") or ""
    k = 1.0
    if ccy in ("GBp", "GBX"):
        k, ccy = 0.01, "GBP"
    ds = [date.fromisoformat(d) for d in hist["dates"]]
    return Series(ds, [None if v is None else v * k for v in vals]), ccy


class Rates:
    """Kurzy mien v čase. fx[(a, b)] = Series kurzu a→b (voliteľné)."""

    def __init__(self, fx):
        self.fx = fx or {}
        self.missing = set()

    def rate(self, a, b, day):
        if not a or not b or a == b:
            return 1.0
        s = self.fx.get((a, b))
        if s:
            r = s.at(day)
            if r is None:
                r = s.v[0]
            return r
        inv = self.fx.get((b, a))
        if inv:
            r = inv.at(day)
            if r is None:
                r = inv.v[0]
            return 1.0 / r if r else None
        self.missing.add(f"{a}→{b}")
        return None


def _trade_amount(t):
    if t.get("total") is not None:
        return abs(t["total"]), t.get("ccy") or t.get("price_ccy")
    if t.get("price") is not None and t.get("shares"):
        return abs(t["price"] * t["shares"]), t.get("price_ccy") or t.get("ccy")
    return 0.0, t.get("ccy")


def compute(txns, base, price_hist, rates, end):
    """Denné hodnoty a TWR.

    price_hist: {isin: (Series|None, mena ceny)} (Series v mene ceny, libry nie pence)
    rates: Rates; end: posledný deň výpočtu.
    Vráti dict: days (zoznam riadkov), warnings."""
    warnings = []
    items = sorted((t for t in txns if t["kind"] in ("buy", "sell", "spinoff", "dividend")),
                   key=lambda t: t["time"])
    if not items:
        return {"days": [], "warnings": ["Žiadne obchody na výpočet."]}
    first_day = datetime.strptime(items[0]["time"][:10], "%Y-%m-%d").date()
    end = max(end, first_day)

    ev = defaultdict(list)
    last_trade_price = {}
    for t in items:
        d = datetime.strptime(t["time"][:10], "%Y-%m-%d").date()
        ev[d].append(t)

    shares = defaultdict(float)
    ticker = {}
    days, prev_v, idx = [], 0.0, None
    jumps = []
    fb_price = {}                                   # posledná cena z obchodu (náhradná)
    day = first_day
    no_hist = set()
    while day <= end:
        buys = sells = div = 0.0
        for t in ev.get(day, ()):
            k = t["kind"]
            ticker[t["isin"]] = t.get("ticker") or t["isin"]
            if k in ("buy", "sell", "spinoff"):
                sh = t.get("shares") or 0.0
                amt, ccy = _trade_amount(t)
                r = rates.rate(ccy, base, day)
                if t.get("price") is not None:
                    fb_price[t["isin"]] = (t["price"], t.get("price_ccy") or ccy)
                if k == "buy":
                    shares[t["isin"]] += sh
                    buys += amt * r if r is not None else 0.0
                elif k == "sell":
                    tracked = min(sh, shares[t["isin"]])      # staršia história chýba -> len evidovaná časť
                    shares[t["isin"]] -= tracked
                    frac = tracked / sh if sh else 0.0
                    sells += amt * frac * r if r is not None else 0.0
                else:
                    shares[t["isin"]] += sh
            elif k == "dividend":
                amt = abs(t.get("total") or 0.0)
                r = rates.rate(t.get("ccy"), base, day)
                div += amt * r if r is not None else 0.0
        v = 0.0
        for isin, sh in shares.items():
            if sh <= 1e-9:
                continue
            s, pccy = price_hist.get(isin, (None, None))
            px = s.at(day) if s else None
            if px is None:                            # bez histórie cien: posledná cena z obchodu
                fb = fb_price.get(isin)
                if fb is None:
                    continue
                px, pccy = fb
                no_hist.add(ticker.get(isin, isin))
            r = rates.rate(pccy, base, day)
            if r is None:
                continue
            v += sh * px * r
        flow = buys - sells
        if idx is None:
            if v > MIN_VALUE:
                idx = 100.0
        elif prev_v + buys > MIN_VALUE:
            # nákupy sa berú ako kapitál od začiatku dňa, predaje sa započítajú do konca dňa:
            # výnos nikdy nemôže byť menší ako −100 % (čitateľ ani menovateľ nie sú záporné)
            f = (v + div + sells) / (prev_v + buys)
            if f > 1.6 or f < 0.4:
                jumps.append((day, f - 1.0))
            idx *= f
        days.append({"d": day, "v": v, "flow": flow, "div": div, "idx": idx})
        prev_v = v
        day += timedelta(days=1)
    if jumps:
        ex = ", ".join(f"{d.strftime('%d.%m.%Y')} ({r * 100:+.0f} %)" for d, r in jumps[:3])
        warnings.append(f"Podozrivý denný pohyb portfólia ({len(jumps)}×, napr. {ex}). Býva to chyba "
                        "v cenách (zlý symbol, akciový split) alebo neúplná história, výnosy v tom "
                        "období môžu byť nepresné.")
    if no_hist:
        warnings.append("Bez histórie cien z Yahoo: " + ", ".join(sorted(no_hist)) +
                        ". Hodnota týchto pozícií je odhadnutá z poslednej ceny z obchodu, výnos "
                        "môže byť nepresný.")
    if rates.missing:
        warnings.append("Chýbajú historické kurzy: " + ", ".join(sorted(rates.missing)) +
                        ". Obchody v týchto menách nie sú vo výpočte.")
    return {"days": days, "warnings": warnings}


# ------------------------------------------------------------------ obdobia
class Timeline:
    """Rýchle súčty a hodnoty z denných riadkov."""

    def __init__(self, days):
        self.days = days
        self.o = [d["d"].toordinal() for d in days]
        self.cf, self.cd = [0.0], [0.0]
        for d in days:
            self.cf.append(self.cf[-1] + d["flow"])
            self.cd.append(self.cd[-1] + d["div"])

    def _i(self, day):
        return bisect_right(self.o, day.toordinal()) - 1

    def row(self, day):
        i = self._i(day)
        return self.days[i] if i >= 0 else None

    def sum_after(self, arr, start, end):
        """Súčet za dni (start, end]."""
        a, b = self._i(start), self._i(end)
        a = max(a, -1)
        return arr[b + 1] - arr[a + 1] if b >= 0 else 0.0

    @property
    def first(self):
        for d in self.days:
            if d["idx"] is not None:
                return d["d"]
        return None

    @property
    def last(self):
        return self.days[-1]["d"] if self.days else None


def window(tl, start, end, from_scratch=False):
    """Výkonnosť za (start, end]. start = deň, ku ktorého zatvoreniu merame (napr. 31. 12.).
    from_scratch: portfólio začína v tomto okne (začiatočná hodnota 0)."""
    r_end, r_start = tl.row(end), tl.row(start)
    if r_end is None or r_end["idx"] is None:
        return None
    v_end = r_end["v"]
    if from_scratch or r_start is None or r_start["idx"] is None:
        first = tl.first
        v_start, idx_start = 0.0, 100.0
        base_day = first
        flows = tl.sum_after(tl.cf, (first - timedelta(days=1)), end) if first else 0.0
        divs = tl.sum_after(tl.cd, (first - timedelta(days=1)), end) if first else 0.0
        idx_ref = tl.row(first)["idx"] if first else 100.0
    else:
        v_start, idx_ref = r_start["v"], r_start["idx"]
        base_day = r_start["d"]
        flows = tl.sum_after(tl.cf, start, end)
        divs = tl.sum_after(tl.cd, start, end)
    pnl = v_end - v_start - flows + divs
    twr = r_end["idx"] / idx_ref - 1.0 if idx_ref else None
    return {"start": base_day, "end": r_end["d"], "pnl": pnl, "twr": twr, "v_start": v_start,
            "v_end": v_end, "flows": flows, "dividends": divs}


def standard_windows(tl, today):
    """Zoznam (kľúč, popis, začiatok, koniec, od_nuly) pre YTD, kalendárne roky, 12 mesiacov a celé obdobie."""
    first, last = tl.first, tl.last
    if first is None:
        return []
    end = min(today, last)
    out = []
    y0 = first.year
    for y in range(end.year, y0 - 1, -1):
        start = date(y - 1, 12, 31)
        e = min(date(y, 12, 31), end)
        label = f"YTD {y}" if y == end.year else str(y)
        if y == y0:
            label += f" (od {first.day}. {first.month}. {first.year})"
        out.append((f"y{y}", label, start, e, start < first))
    twelve = end - timedelta(days=365)
    if twelve >= first:
        out.append(("12m", "Posledných 12 mesiacov", twelve, end, False))
    out.append(("all", "Od začiatku", first - timedelta(days=1), end, True))
    return out


def benchmark_return(series, start, end, from_day=None):
    """Výnos indexu za (start, end]; ak začiatok predchádza dátam, od prvého dňa."""
    if not series:
        return None
    a = series.at(start) if from_day is None else series.at(from_day)
    if a is None:
        a = series.v[0]
    b = series.at(end)
    if b is None or not a:
        return None
    return b / a - 1.0


def period_rows(tl, windows, benches):
    """benches = {id: Series v základnej mene}. Riadky pre tabuľku výnosov."""
    rows = []
    for key, label, start, end, scratch in windows:
        w = window(tl, start, end, from_scratch=scratch)
        if not w:
            continue
        # indexy merať od rovnakého dňa ako portfólio
        b_start = w["start"] if scratch else start
        row = {"key": key, "label": label, "start": w["start"], "end": w["end"], "pnl": w["pnl"],
               "twr": w["twr"], "dividends": w["dividends"], "bench": {},
               "bad": w["twr"] is None or w["twr"] <= -1.0 or w["twr"] > 50}
        for bid, s in benches.items():
            row["bench"][bid] = benchmark_return(s, b_start, w["end"])
        rows.append(row)
    return rows

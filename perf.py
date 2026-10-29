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


def _session_fraction(time_str):
    """Podiel obchodného dňa (07:00–21:00 UTC), ktorý v čase obchodu už uplynul (0 až 1)."""
    try:
        h, m = int(time_str[11:13]), int(time_str[14:16])
    except (ValueError, IndexError):
        return 0.0
    return min(1.0, max(0.0, (h + m / 60.0 - 7.0) / 14.0))


def compute(txns, base, price_hist, rates, end):
    """Denné hodnoty a TWR.

    price_hist: {isin: (Series|None, mena ceny)} (Series v mene ceny, libry nie pence)
    rates: Rates; end: posledný deň výpočtu.
    Deň sa rozdelí obchodmi na úseky. Pred každým obchodom sa portfólio ocení (obchodovaný
    titul cenou obchodu, ostatné interpoláciou medzi včerajším a dnešným zatvorením podľa času),
    takže výnos úseku nezávisí od veľkosti obchodu. Výnos dňa je súčin výnosov úsekov.
    Vráti dict: days (zoznam riadkov), warnings."""
    warnings = []
    items = sorted((t for t in txns if t["kind"] in ("buy", "sell", "spinoff", "dividend")),
                   key=lambda t: t["time"])
    if not items:
        return {"days": [], "warnings": ["Žiadne obchody na výpočet."]}
    first_day = datetime.strptime(items[0]["time"][:10], "%Y-%m-%d").date()
    end = max(end, first_day)
    ev = defaultdict(list)
    for t in items:
        ev[datetime.strptime(t["time"][:10], "%Y-%m-%d").date()].append(t)

    shares = defaultdict(float)
    ticker, fb_price, no_hist = {}, {}, set()

    def price_base(isin, day):
        """Cena akcie v základnej mene ku koncu dňa (alebo None)."""
        s, pccy = price_hist.get(isin, (None, None))
        px = s.at(day) if s else None
        if px is None:                                  # bez histórie: posledná cena z obchodu
            fb = fb_price.get(isin)
            if fb is None:
                return None
            px, pccy = fb
            no_hist.add(ticker.get(isin, isin))
        r = rates.rate(pccy, base, day)
        return None if r is None else px * r

    def value(day, at=None, traded=None, tprice=None, w=0.0):
        """Hodnota portfólia: na konci dňa (at=None) alebo v čase obchodu."""
        v = 0.0
        for isin, sh in shares.items():
            if sh <= 1e-9:
                continue
            c = price_base(isin, day)
            if at is not None:
                if isin == traded and tprice is not None:
                    c = tprice
                else:
                    c0 = price_base(isin, day - timedelta(days=1))
                    if c is not None and c0 is not None:
                        c = c0 + w * (c - c0)
            if c is not None:
                v += sh * c
        return v

    days, prev_v, idx, jumps = [], 0.0, None, []
    day = first_day
    while day <= end:
        buys = sells = div = 0.0
        factor, chk = 1.0, prev_v
        trades = []
        for t in ev.get(day, ()):
            if t["kind"] == "dividend":
                amt = abs(t.get("total") or 0.0)
                r = rates.rate(t.get("ccy"), base, day)
                div += amt * r if r is not None else 0.0
            else:
                trades.append(t)
        for t in trades:
            k, isin = t["kind"], t["isin"]
            ticker[isin] = t.get("ticker") or isin
            sh = t.get("shares") or 0.0
            amt, ccy = _trade_amount(t)
            r = rates.rate(ccy, base, day)
            if t.get("price") is not None:
                fb_price[isin] = (t["price"], t.get("price_ccy") or ccy)
            tp = None                                   # cena obchodu v základnej mene
            if t.get("price") is not None:
                rp = rates.rate(t.get("price_ccy") or ccy, base, day)
                tp = t["price"] * rp if rp is not None else None
            if tp is None and sh and r is not None:
                tp = amt * r / sh
            vb = value(day, at=True, traded=isin, tprice=tp, w=_session_fraction(t["time"]))
            if chk > MIN_VALUE:
                factor *= vb / chk
            if k == "buy":
                f_cash = amt * r if r is not None else 0.0
                shares[isin] += sh
                buys += f_cash
                chk = vb + f_cash
            elif k == "sell":
                tracked = min(sh, shares[isin])        # staršia história chýba -> len evidovaná časť
                frac = tracked / sh if sh else 0.0
                f_cash = amt * frac * r if r is not None else 0.0
                shares[isin] -= tracked
                sells += f_cash
                chk = vb - f_cash
            else:                                       # spin-off: nová akcia bez peňažného toku
                shares[isin] += sh
                chk = vb
        v = value(day)
        if idx is None:
            if v > MIN_VALUE:
                idx = 100.0
        elif chk > MIN_VALUE:
            factor *= (v + div) / chk
            if factor > 1.6 or factor < 0.4:
                jumps.append((day, factor - 1.0))
            idx *= factor
        days.append({"d": day, "v": v, "flow": buys - sells, "div": div, "idx": idx})
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

"""Technická analýza: indikátory a signály z denných cien (OHLCV).

Čisté funkcie bez závislostí. Zoznamy majú rovnakú dĺžku ako vstup, kde sa indikátor ešte nedá spočítať, je None.
Nejde o investičné odporúčanie: signály z minulých cien nepredpovedajú budúcnosť, slúžia na orientáciu."""
import math
import random
from datetime import date, timedelta


def sma(v, n):
    out, s = [None] * len(v), 0.0
    for i, x in enumerate(v):
        s += x
        if i >= n:
            s -= v[i - n]
        if i >= n - 1:
            out[i] = s / n
    return out


def ema(v, n, start=0):
    """EMA so začiatkom v indexe `start`: prvá hodnota = jednoduchý priemer prvých n hodnôt od `start`."""
    out = [None] * len(v)
    if len(v) - start < n:
        return out
    k = 2.0 / (n + 1)
    prev = sum(v[start:start + n]) / n
    out[start + n - 1] = prev
    for i in range(start + n, len(v)):
        prev = v[i] * k + prev * (1 - k)
        out[i] = prev
    return out


def rsi(close, n=14):
    """Wilderovo RSI."""
    out = [None] * len(close)
    if len(close) <= n:
        return out
    gains = [max(close[i] - close[i - 1], 0) for i in range(1, len(close))]
    losses = [max(close[i - 1] - close[i], 0) for i in range(1, len(close))]
    ag, al = sum(gains[:n]) / n, sum(losses[:n]) / n

    def val(g, l_):
        if l_ == 0:
            return 100.0 if g > 0 else 50.0
        return 100 - 100 / (1 + g / l_)

    out[n] = val(ag, al)
    for i in range(n, len(gains)):
        ag = (ag * (n - 1) + gains[i]) / n
        al = (al * (n - 1) + losses[i]) / n
        out[i + 1] = val(ag, al)
    return out


def macd(close, fast=12, slow=26, sig=9):
    ef, es = ema(close, fast), ema(close, slow)
    line = [a - b if a is not None and b is not None else None for a, b in zip(ef, es)]
    first = next((i for i, x in enumerate(line) if x is not None), None)
    signal = [None] * len(close)
    if first is not None:
        vals = line[first:]
        sg = ema(vals, sig)
        for i, x in enumerate(sg):
            signal[first + i] = x
    hist = [a - b if a is not None and b is not None else None for a, b in zip(line, signal)]
    return line, signal, hist


def bollinger(close, n=20, k=2.0):
    mid = sma(close, n)
    up, lo = [None] * len(close), [None] * len(close)
    for i in range(n - 1, len(close)):
        w = close[i - n + 1:i + 1]
        m = mid[i]
        sd = math.sqrt(sum((x - m) ** 2 for x in w) / n)    # populačná smerodajná odchýlka
        up[i], lo[i] = m + k * sd, m - k * sd
    return mid, up, lo


def atr(high, low, close, n=14):
    tr = [high[0] - low[0]] + [max(high[i] - low[i], abs(high[i] - close[i - 1]), abs(low[i] - close[i - 1]))
                               for i in range(1, len(close))]
    out = [None] * len(close)
    if len(tr) < n:
        return out
    prev = sum(tr[:n]) / n
    out[n - 1] = prev
    for i in range(n, len(tr)):
        prev = (prev * (n - 1) + tr[i]) / n
        out[i] = prev
    return out


def stochastic(high, low, close, n=14, d=3):
    k = [None] * len(close)
    for i in range(n - 1, len(close)):
        hh, ll = max(high[i - n + 1:i + 1]), min(low[i - n + 1:i + 1])
        k[i] = 50.0 if hh == ll else (close[i] - ll) / (hh - ll) * 100
    first = next((i for i, x in enumerate(k) if x is not None), None)
    dd = [None] * len(close)
    if first is not None:
        for i, x in enumerate(sma(k[first:], d)):
            dd[first + i] = x
    return k, dd


def obv(close, volume):
    out, s = [0.0], 0.0
    for i in range(1, len(close)):
        if close[i] > close[i - 1]:
            s += volume[i]
        elif close[i] < close[i - 1]:
            s -= volume[i]
        out.append(s)
    return out


# ------------------------------------------------------------------ úrovne a štatistiky
def swing_levels(high, low, window=8, lookback=260, tol=0.02):
    """Lokálne maximá a minimá (okno ±window dní) za posledných `lookback` dní, zlúčené, ak sú do `tol` od seba."""
    n = len(high)
    start = max(window, n - lookback)
    pts = []
    for i in range(start, n - window):
        if high[i] == max(high[i - window:i + window + 1]):
            pts.append(high[i])
        if low[i] == min(low[i - window:i + window + 1]):
            pts.append(low[i])
    pts.sort()
    groups = []
    for p in pts:
        if groups and p <= groups[-1][-1] * (1 + tol):
            groups[-1].append(p)
        else:
            groups.append([p])
    return [(sum(g) / len(g), len(g)) for g in groups]


def nearest_levels(levels, price, k=3):
    above = sorted((l for l, _c in levels if l > price * 1.003))[:k]
    below = sorted((l for l, _c in levels if l < price * 0.997), reverse=True)[:k]
    return above, below


def _ret(close, n):
    return close[-1] / close[-1 - n] - 1 if len(close) > n else None


def stats(dates, close, high, low, atr14):
    last = len(close) - 1
    y = date.fromisoformat(dates[-1]).year
    ytd_i = next((i for i, d in enumerate(dates) if d.startswith(str(y))), None)
    ytd = close[-1] / close[ytd_i - 1] - 1 if ytd_i and ytd_i > 0 else None
    yr = close[-252:]
    rets = [math.log(yr[i] / yr[i - 1]) for i in range(1, len(yr)) if yr[i - 1] > 0 and yr[i] > 0]
    vol = None
    if len(rets) > 20:
        m = sum(rets) / len(rets)
        vol = math.sqrt(sum((r - m) ** 2 for r in rets) / (len(rets) - 1)) * math.sqrt(252)
    peak, mdd = yr[0], 0.0
    for p in yr:
        peak = max(peak, p)
        mdd = min(mdd, p / peak - 1)
    hi52, lo52 = max(high[-252:]), min(low[-252:])
    return {"ret_1m": _ret(close, 21), "ret_3m": _ret(close, 63), "ret_6m": _ret(close, 126), "ret_1y": _ret(close, 252),
            "ret_ytd": ytd, "vol_1y": vol, "mdd_1y": mdd, "hi52": hi52, "lo52": lo52,
            "from_hi": close[-1] / hi52 - 1, "from_lo": close[-1] / lo52 - 1,
            "atr_pct": (atr14[last] / close[-1]) if atr14[last] is not None else None}


# ------------------------------------------------------------------ signály
BULL, NEUT, BEAR = 1, 0, -1


def _recent_cross(a, b, days=10):
    """+1, ak a pretla b zdola nahor v poslednom týždni-dvoch, −1 opačne, 0 inak."""
    n = len(a)
    for i in range(n - 1, max(n - 1 - days, 0), -1):
        if None in (a[i], b[i], a[i - 1], b[i - 1]):
            continue
        if a[i - 1] <= b[i - 1] and a[i] > b[i]:
            return 1
        if a[i - 1] >= b[i - 1] and a[i] < b[i]:
            return -1
    return 0


def signals(d):
    """d = výstup analyze(). Zoznam {'group','name','value','reading','signal','why'}."""
    c = d["close"]
    last = len(c) - 1
    g = lambda s: s[last]  # noqa: E731
    out = []

    def add(group, name, value, reading, sig, why):
        out.append({"group": group, "name": name, "value": value, "reading": reading, "signal": sig, "why": why})

    s50, s200, s20 = g(d["sma50"]), g(d["sma200"]), g(d["sma20"])
    if s50 is not None:
        add("Trend", "Cena vs SMA 50", f"{c[last] / s50 - 1:+.1%}".replace(".", ","),
            "nad priemerom" if c[last] > s50 else "pod priemerom", BULL if c[last] > s50 else BEAR,
            "Cena nad 50-dňovým priemerom znamená krátkodobý až strednodobý rastúci trend.")
    if s200 is not None:
        add("Trend", "Cena vs SMA 200", f"{c[last] / s200 - 1:+.1%}".replace(".", ","),
            "nad priemerom" if c[last] > s200 else "pod priemerom", BULL if c[last] > s200 else BEAR,
            "200-dňový priemer je bežná hranica medzi dlhodobým rastúcim a klesajúcim trendom.")
    if s50 is not None and s200 is not None:
        x = _recent_cross(d["sma50"], d["sma200"], 20)
        rd = ("zlatý kríž (nedávno)" if x > 0 else "smrtiaci kríž (nedávno)" if x < 0
              else "SMA 50 nad SMA 200" if s50 > s200 else "SMA 50 pod SMA 200")
        add("Trend", "SMA 50 vs SMA 200", f"{s50 / s200 - 1:+.1%}".replace(".", ","), rd,
            BULL if s50 > s200 else BEAR,
            "Zlatý kríž = 50-dňový priemer prerazí 200-dňový nahor (býčí signál), smrtiaci kríž opačne. Oneskorený indikátor.")
    r = g(d["rsi"])
    if r is not None:
        if r >= 70:
            rd, sg = "prekúpené", NEUT
        elif r <= 30:
            rd, sg = "prepredané", NEUT
        elif r >= 55:
            rd, sg = "býčia momentum zóna", BULL
        elif r <= 45:
            rd, sg = "medvedia momentum zóna", BEAR
        else:
            rd, sg = "neutrálne", NEUT
        add("Momentum", "RSI (14)", f"{r:.0f}", rd, sg,
            "RSI meria silu posledných pohybov (0 až 100). Nad 70 sa cena často považuje za prekúpenú, pod 30 za prepredanú; "
            "extrémy nie sú signálom na predaj či nákup, len upozornením.")
    m, sg_, h = g(d["macd"]), g(d["macd_sig"]), g(d["macd_hist"])
    if None not in (m, sg_):
        x = _recent_cross(d["macd"], d["macd_sig"], 10)
        rd = ("býčí prienik (nedávno)" if x > 0 else "medvedí prienik (nedávno)" if x < 0
              else "MACD nad signálom" if m > sg_ else "MACD pod signálom")
        add("Momentum", "MACD (12, 26, 9)", f"{m:.2f}", rd, BULL if m > sg_ else BEAR,
            "MACD = rozdiel dvoch exponenciálnych priemerov. Keď je nad signálnou čiarou, momentum rastie.")
    k, dd = g(d["stoch_k"]), g(d["stoch_d"])
    if None not in (k, dd):
        if k >= 80:
            rd, sg = "prekúpené", NEUT
        elif k <= 20:
            rd, sg = "prepredané", NEUT
        else:
            rd, sg = ("%K nad %D" if k > dd else "%K pod %D"), (BULL if k > dd else BEAR)
        add("Momentum", "Stochastic (14, 3)", f"{k:.0f}", rd, sg,
            "Ukazuje polohu zatváracej ceny v rozpätí posledných 14 dní. Nad 80 prekúpené, pod 20 prepredané.")
    u, lo_, mid = g(d["bb_up"]), g(d["bb_lo"]), g(d["bb_mid"])
    if None not in (u, lo_, mid) and u > lo_:
        pb = (c[last] - lo_) / (u - lo_)
        if pb > 1:
            rd, sg = "nad hornou pásmou", NEUT
        elif pb < 0:
            rd, sg = "pod dolným pásmom", NEUT
        else:
            rd, sg = ("v hornej polovici pásma" if pb >= 0.5 else "v dolnej polovici pásma"), (BULL if pb >= 0.5 else BEAR)
        add("Volatilita", "Bollingerove pásma (%B)", f"{pb:.2f}".replace(".", ","), rd, sg,
            "%B ukazuje polohu ceny v pásme (0 = dolná hranica, 1 = horná). Mimo pásma je cena štatisticky neobvykle ďaleko od priemeru.")
    ob, obs = d["obv"], sma(d["obv"], 50)
    if obs[last] is not None:
        add("Objem", "OBV vs jeho priemer 50", "", "objem potvrdzuje rast" if ob[last] > obs[last] else "objem potvrdzuje pokles",
            BULL if ob[last] > obs[last] else BEAR,
            "OBV sčítava objem v dňoch rastu a odčítava v dňoch poklesu. Ak rastie spolu s cenou, trend podporujú aj obchody.")
    st = d["stats"]
    if st["ret_3m"] is not None:
        add("Momentum", "Výnos za 3 mesiace", f"{st['ret_3m']:+.1%}".replace(".", ","), "kladný" if st["ret_3m"] > 0 else "záporný",
            BULL if st["ret_3m"] > 0 else BEAR, "Akcie s kladným strednodobým výnosom majú tendenciu v tom pokračovať (momentum efekt).")
    if st["ret_1y"] is not None:
        add("Momentum", "Výnos za 12 mesiacov", f"{st['ret_1y']:+.1%}".replace(".", ","), "kladný" if st["ret_1y"] > 0 else "záporný",
            BULL if st["ret_1y"] > 0 else BEAR, "Ročný výnos je najčastejšie používaná miera momenta.")
    fh = st["from_hi"]
    add("Trend", "Vzdialenosť od 52-týždňového maxima", f"{fh:+.1%}".replace(".", ","),
        "blízko maxima" if fh > -0.05 else "výrazne pod maximom" if fh < -0.30 else "stredné",
        BULL if fh > -0.05 else BEAR if fh < -0.30 else NEUT,
        "Akcie blízko ročných maxím sú v silnom trende, hlboko pod maximom v slabom.")
    return out


def verdict(sigs):
    bull = sum(1 for s in sigs if s["signal"] == BULL)
    bear = sum(1 for s in sigs if s["signal"] == BEAR)
    neut = len(sigs) - bull - bear
    net = bull - bear
    n = max(len(sigs), 1)
    if net >= n * 0.4:
        label = "prevažujú býčie signály"
    elif net <= -n * 0.4:
        label = "prevažujú medvedie signály"
    else:
        label = "zmiešané signály"
    return {"bull": bull, "bear": bear, "neutral": neut, "net": net, "label": label}


def analyze(o):
    """o = {'dates','open','high','low','close','volume'}. Vráti série indikátorov, štatistiky, úrovne a signály."""
    c, h, l_, v = o["close"], o["high"], o["low"], o["volume"]
    if len(c) < 60:
        return None
    d = {"dates": o["dates"], "open": o["open"], "high": h, "low": l_, "close": c, "volume": v,
         "sma20": sma(c, 20), "sma50": sma(c, 50), "sma200": sma(c, 200), "rsi": rsi(c)}
    d["macd"], d["macd_sig"], d["macd_hist"] = macd(c)
    d["bb_mid"], d["bb_up"], d["bb_lo"] = bollinger(c)
    d["atr"] = atr(h, l_, c)
    d["stoch_k"], d["stoch_d"] = stochastic(h, l_, c)
    d["obv"] = obv(c, v)
    d["stats"] = stats(o["dates"], c, h, l_, d["atr"])
    lv = swing_levels(h, l_)
    d["resistance"], d["support"] = nearest_levels(lv, c[-1])
    d["signals"] = signals(d)
    d["verdict"] = verdict(d["signals"])
    return d


def synthetic(n=900, seed=7, start_price=50.0):
    """Vymyslené ceny na ukážku a testy bez internetu (náhodná prechádzka s miernym driftom)."""
    rnd = random.Random(seed)
    dates, op, hi, lo, cl, vol = [], [], [], [], [], []
    p, d0 = start_price, date(2023, 1, 2)
    day = 0
    while len(dates) < n:
        dt = d0 + timedelta(days=day)
        day += 1
        if dt.weekday() >= 5:
            continue
        o_ = p
        p = max(1.0, p * math.exp(rnd.gauss(0.0004, 0.014)))
        dates.append(dt.isoformat())
        op.append(o_)
        cl.append(p)
        hi.append(max(o_, p) * (1 + abs(rnd.gauss(0, 0.005))))
        lo.append(min(o_, p) * (1 - abs(rnd.gauss(0, 0.005))))
        vol.append(int(rnd.uniform(0.6, 1.6) * 2_000_000))
    return {"dates": dates, "open": op, "high": hi, "low": lo, "close": cl, "volume": vol, "currency": "USD"}

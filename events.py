"""Kalendár: odhad dátumu ďalších výsledkov (z histórie podaní 8-K) a dividend (z histórie výplat).

Žiadny z dátumov nie je oficiálny. Výsledky sa odhadujú podľa toho, kedy firma zverejnila rovnaký kvartál vlani;
dividendy podľa rozstupu posledných výplat. Firmy zverejnia presný termín väčšinou len 2 až 4 týždne vopred."""
from datetime import date, timedelta
from statistics import median


def _d(s):
    return date.fromisoformat(s[:10])


def estimate_next_earnings(release_dates, today=None):
    """Odhad ďalšieho dátumu výsledkov z ISO dátumov minulých vydaní (v ľubovoľnom poradí).
    Vráti dict(date, basis) alebo None. Preferuje rovnaký kvartál vlani, inak medián rozstupu."""
    today = today or date.today()
    ds = sorted({_d(x) for x in release_dates if x}, reverse=True)
    if not ds:
        return None
    est, basis = None, ""
    if len(ds) >= 4 and (ds[0] - ds[3]).days < 330:
        est, basis = ds[3] + timedelta(days=364), "rovnaký kvartál vlani"
    elif len(ds) >= 3:
        gaps = [(ds[i] - ds[i + 1]).days for i in range(min(4, len(ds) - 1))]
        est, basis = ds[0] + timedelta(days=int(median(gaps))), "typický rozstup medzi výsledkami"
    else:
        est, basis = ds[0] + timedelta(days=91), "približne štvrťrok po poslednom"
    guard = 0
    while est < today and guard < 8:      # odhad už uplynul: posuň o kvartál
        est += timedelta(days=91)
        guard += 1
    return {"date": est.isoformat(), "basis": basis, "last": ds[0].isoformat()}


def dividend_info(divs, today=None):
    """divs = [(ISO dátum ex-dividendy, suma)]. Vráti dict alebo None, ak firma dividendu neplatí."""
    today = today or date.today()
    pts = sorted({(_d(d), float(a)) for d, a in divs if a})
    if not pts:
        return None
    last_d, last_a = pts[-1]
    if (today - last_d).days > 540:        # dividenda sa dlho nevyplatila: už ju neplatí
        return None
    gaps = [(pts[i + 1][0] - pts[i][0]).days for i in range(len(pts) - 1)][-4:]
    gap = int(median(gaps)) if gaps else None
    if gap is None:
        freq, nxt = "neznáma", None
    else:
        freq = ("mesačne" if gap <= 40 else "štvrťročne" if gap <= 110 else "polročne" if gap <= 210 else "ročne")
        n = last_d + timedelta(days=gap)
        guard = 0
        while n < today and guard < 30:
            n += timedelta(days=gap)
            guard += 1
        nxt = n.isoformat()
    year = sum(a for d, a in pts if (today - d).days <= 365)
    return {"last_date": last_d.isoformat(), "last_amount": last_a, "freq": freq, "next_date": nxt,
            "year_sum": year}


def upcoming(rows, today=None, horizon=120):
    """Z riadkov po firmách poskladá časovú os najbližších udalostí (zoradenú podľa dátumu)."""
    today = today or date.today()
    lim = (today + timedelta(days=horizon)).isoformat()
    out = []
    for r in rows:
        e = r.get("earnings")
        if e and today.isoformat() <= e["date"] <= lim:
            out.append({"date": e["date"], "ticker": r["ticker"], "name": r.get("name") or r["ticker"],
                        "kind": "Výsledky (odhad)", "note": e["basis"]})
        dv = r.get("dividend")
        if dv and dv.get("next_date") and today.isoformat() <= dv["next_date"] <= lim:
            amt = dv["last_amount"]
            note = f"naposledy {amt:.4g} {r.get('div_ccy') or ''}".strip()
            if r.get("shares"):
                note += f" × {r['shares']:.6g} ks = {amt * r['shares']:.2f} {r.get('div_ccy') or ''}".rstrip()
            out.append({"date": dv["next_date"], "ticker": r["ticker"], "name": r.get("name") or r["ticker"],
                        "kind": "Ex-dividenda (odhad)", "note": note})
    out.sort(key=lambda x: (x["date"], x["ticker"]))
    return out

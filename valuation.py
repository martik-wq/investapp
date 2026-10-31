"""Oceňovacie modely (DCF, férové P/B, násobky) s odporúčanými vstupmi z histórie a odhadov analytikov.

Všetky výpočty sú čisté funkcie bez siete, aby sa dali testovať. Percentá sú v desatinách (0.12 = 12 %).
Peňažné hodnoty v jednotkách meny (nie v miliónoch)."""
import math

MAX_G = 0.5


def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


def net_revenue(built, end):
    """Tržby firmy. U bánk a fintech firiem je „revenue“ často len čiastkový riadok, preto sa berie
    čistý výnos (čistý úrokový výnos + neúrokové výnosy), ak je zjavne väčší."""
    d = built["data"]
    r = d.get("revenue", {}).get(end)
    nii, ni = d.get("nii", {}).get(end), d.get("nonint_income", {}).get(end)
    if nii is not None and ni is not None:
        nr = nii + ni
        if r is None or nr > r * 1.05:
            return nr
    return r


def revenue_series(built):
    out = []
    for e in built["display"]:
        v = net_revenue(built, e)
        if v is not None:
            out.append((e, v))
    return out


def _series(built, key):
    """[(koniec obdobia, hodnota)] vzostupne pre zobrazené ročné obdobia."""
    d = built["data"].get(key, {})
    return [(e, d.get(e)) for e in built["display"] if d.get(e) is not None]


def cagr(first, last, years):
    if first is None or last is None or first <= 0 or last <= 0 or years <= 0:
        return None
    return (last / first) ** (1.0 / years) - 1.0


def _cagr_n(series, n):
    """CAGR za n rokov z ročných dát (posledná hodnota voči hodnote pred n rokmi)."""
    if len(series) <= n:
        return None
    return cagr(series[-1 - n][1], series[-1][1], n)


def _avg(vals):
    vals = [v for v in vals if v is not None]
    return sum(vals) / len(vals) if vals else None


def history_facts(built, ttm=None):
    """Údaje z výkazov, z ktorých sa odvodzujú odporúčania. built = ročné výkazy; ttm = {'revenue','fcf',
    'net_income','eps'} z posledných 4 kvartálov (voliteľné)."""
    rev = revenue_series(built)
    fcf = _series(built, "fcf")
    ni = _series(built, "net_income")
    eq = _series(built, "equity")
    sh = _series(built, "shares_diluted")
    eps = _series(built, "eps_diluted")
    margins = []
    for (e, f) in fcf:
        r = net_revenue(built, e)
        if r:
            margins.append((e, f / r))
    roe = []
    for i, (e, n) in enumerate(ni):
        eqs = [v for (ee, v) in eq if ee == e]
        prev = [v for (ee, v) in eq if i > 0 and ee == ni[i - 1][0]]
        if eqs:
            base = (eqs[0] + prev[0]) / 2 if prev else eqs[0]
            if base and base > 0:
                roe.append((e, n / base))
    last = built["display"][-1]
    g = lambda k: built["data"].get(k, {}).get(last)  # noqa: E731
    cash = (g("cash") or 0) + (g("st_investments") or 0)
    lt_inv = g("lt_investments") or 0
    debt = g("total_debt")
    if debt is None:
        debt = (g("debt_current") or 0) + (g("debt_lt") or 0)
    divs = _series(built, "div_paid")
    dps = []
    for (e, dv) in divs:
        shd = built["data"].get("shares_diluted", {}).get(e)
        if shd:
            dps.append((e, abs(dv) / shd))
    ebitda = []
    for e in built["display"]:
        oi, da = built["data"].get("op_income", {}).get(e), built["data"].get("da", {}).get(e)
        if oi is not None and da is not None:
            ebitda.append((e, oi + da))
    out = {
        "last_end": last,
        "dps": dps[-1][1] if dps else None,
        "dps_cagr3": _cagr_n(dps, 3), "dps_cagr5": _cagr_n(dps, 5),
        "ebitda": ebitda[-1][1] if ebitda else None, "ebitda_cagr3": _cagr_n(ebitda, 3),
        "fcf_fy": fcf[-1][1] if fcf else None, "fcf_ttm": (ttm or {}).get("fcf"),
        "rev_fy": rev[-1][1] if rev else None,
        "rev_ttm": (ttm or {}).get("revenue"),
        "fcf_margin_fy": margins[-1][1] if margins else None,
        "fcf_margin_ttm": (ttm["fcf"] / ttm["revenue"]) if ttm and ttm.get("revenue") and ttm.get("fcf") is not None else None,
        "fcf_margin_avg3": _avg([m for _, m in margins[-3:]]),
        "fcf_margin_avg5": _avg([m for _, m in margins[-5:]]),
        "fcf_margin_max": max([m for _, m in margins], default=None),
        "rev_cagr3": _cagr_n(rev, 3), "rev_cagr5": _cagr_n(rev, 5),
        "rev_cagr_all": cagr(rev[0][1], rev[-1][1], len(rev) - 1) if len(rev) >= 3 else None,
        "rev_years": len(rev) - 1 if rev else 0,
        "shares_dil": sh[-1][1] if sh else None,
        "shares_cagr3": _cagr_n(sh, 3), "shares_cagr5": _cagr_n(sh, 5),
        "eps_ttm": (ttm or {}).get("eps") or (eps[-1][1] if eps else None),
        "eps_cagr3": _cagr_n(eps, 3), "eps_cagr5": _cagr_n(eps, 5),
        "ni": (ttm or {}).get("net_income") if ttm and ttm.get("net_income") is not None else (ni[-1][1] if ni else None),
        "equity": eq[-1][1] if eq else None,
        "roe_last": roe[-1][1] if roe else None,
        "roe_avg3": _avg([r for _, r in roe[-3:]]), "roe_avg5": _avg([r for _, r in roe[-5:]]),
        "cash": cash, "lt_inv": lt_inv, "debt": debt, "net_debt": (debt or 0) - cash - lt_inv,
        "op_margin_fy": (g("op_income") / g("revenue")) if g("op_income") is not None and g("revenue") else None,
        "interest_expense": g("interest_expense"),
    }
    out["rev_base"] = out["rev_ttm"] or out["rev_fy"]
    out["rev_base_label"] = "posledných 12 mesiacov (TTM)" if out["rev_ttm"] else "posledný fiškálny rok"
    out["fcf_margin_now"] = out["fcf_margin_ttm"] if out["fcf_margin_ttm"] is not None else out["fcf_margin_fy"]
    return out


# ------------------------------------------------------------ odporúčané vstupy
def capm(beta, rf=None, erp=0.05):
    """Požadovaná návratnosť vlastného imania: rf + beta × prémia za riziko akcií."""
    rf = 0.042 if rf is None else rf
    b = 1.0 if beta is None else _clamp(beta, 0.5, 2.5)
    return rf + b * erp, rf, b


def wacc_estimate(ke, debt, mcap, interest_expense=None, tax=0.21):
    """Vážený priemer ceny vlastného imania a dlhu. Bez údajov o dlhu = ke."""
    if not mcap or mcap <= 0 or not debt or debt <= 0:
        return ke, 0.0, None
    kd = _clamp(interest_expense / debt, 0.02, 0.12) if interest_expense and interest_expense > 0 else 0.05
    w_d = debt / (debt + mcap)
    return (1 - w_d) * ke + w_d * kd * (1 - tax), w_d, kd


def recommend_growth(facts, analyst):
    """Odporúčaný rast tržieb: priemer odhadu analytikov na budúci rok a 5-ročného CAGR (ak sú obe)."""
    a = None
    if analyst:
        rg = analyst.get("rev_growth") or {}
        a = rg.get("+1y") if rg.get("+1y") is not None else rg.get("0y")
    h = facts.get("rev_cagr5") if facts.get("rev_cagr5") is not None else facts.get("rev_cagr3")
    if a is not None and h is not None:
        v, why = (a + h) / 2, "priemer odhadu analytikov a historického CAGR"
    elif a is not None:
        v, why = a, "odhad analytikov"
    elif h is not None:
        v, why = h, "historický CAGR tržieb"
    else:
        v, why = 0.08, "všeobecný predpoklad (chýbajú údaje)"
    return _clamp(v, -0.10, MAX_G), why


def recommend_margin(facts):
    cands = [facts.get("fcf_margin_avg3"), facts.get("fcf_margin_now")]
    v = _avg(cands)
    return _clamp(v if v is not None else 0.10, -0.10, 0.50)


def recommend_dilution(facts):
    v = facts.get("shares_cagr3")
    if v is None:
        v = facts.get("shares_cagr5")
    return _clamp(v if v is not None else 0.0, -0.04, 0.06)


# ------------------------------------------------------------------- modely
def dcf(rev0, g1, margin0, margin5, wacc, g_term, net_debt, shares, dilution=0.0, years=10):
    """DCF z voľného cash flow. Rast g1 platí 5 rokov, potom sa lineárne znižuje na g_term (do roku 10).
    FCF marža sa lineárne mení z margin0 na margin5 (rok 5) a ďalej ostáva. Vráti dict alebo {'error'}."""
    if wacc <= g_term + 0.005:
        return {"error": "Diskontná sadzba musí byť aspoň o 0,5 p. b. vyššia ako terminálny rast."}
    if not rev0 or rev0 <= 0 or not shares or shares <= 0:
        return {"error": "Chýba základ (tržby alebo počet akcií)."}
    rev, pv, rows = rev0, 0.0, []
    for t in range(1, years + 1):
        g = g1 if t <= 5 else g1 + (g_term - g1) * (t - 5) / (years - 5)
        rev *= 1 + g
        m = margin0 + (margin5 - margin0) * min(t, 5) / 5
        fcf = rev * m
        df = (1 + wacc) ** t
        pv += fcf / df
        rows.append({"t": t, "growth": g, "revenue": rev, "margin": m, "fcf": fcf, "pv": fcf / df})
    tv = rows[-1]["fcf"] * (1 + g_term) / (wacc - g_term)
    pv_tv = tv / (1 + wacc) ** years
    ev = pv + pv_tv
    equity = ev - net_debt
    sh = shares * (1 + dilution) ** 5
    return {"rows": rows, "pv_fcf": pv, "pv_tv": pv_tv, "tv_share": pv_tv / ev if ev > 0 else None, "ev": ev,
            "equity": equity, "shares_future": sh, "per_share": equity / sh}


def dcf_scenarios(p, price=None):
    """Pesimistický / základný / optimistický variant (rast ±5 p. b., marža ±3 p. b., sadzba ∓1 p. b.)."""
    out = []
    for name, dg, dm, dw in (("Pesimistický", -0.05, -0.03, 0.01), ("Základný", 0, 0, 0),
                             ("Optimistický", 0.05, 0.03, -0.01)):
        r = dcf(p["rev0"], p["g1"] + dg, p["margin0"], p["margin5"] + dm, p["wacc"] + dw, p["g_term"],
                p["net_debt"], p["shares"], p["dilution"])
        v = None if "error" in r else r["per_share"]
        out.append({"name": name, "g1": p["g1"] + dg, "margin5": p["margin5"] + dm, "wacc": p["wacc"] + dw,
                    "value": v, "upside": (v / price - 1) if v is not None and price else None})
    return out


def dcf_sensitivity(p, waccs=None, gts=None):
    waccs = waccs or [p["wacc"] + d for d in (-0.02, -0.01, 0, 0.01, 0.02)]
    gts = gts or [p["g_term"] + d for d in (-0.01, -0.005, 0, 0.005, 0.01)]
    grid = []
    for w in waccs:
        row = []
        for g in gts:
            r = dcf(p["rev0"], p["g1"], p["margin0"], p["margin5"], w, g, p["net_debt"], p["shares"], p["dilution"])
            row.append(None if "error" in r else r["per_share"])
        grid.append(row)
    return {"waccs": waccs, "gts": gts, "grid": grid}


def fair_pb(roe, ke, g):
    """Férové P/B = (ROE − g) / (ke − g) (model trvalo udržateľného rastu)."""
    if ke <= g + 0.005:
        return None
    return (roe - g) / (ke - g)


def pb_model(roe, ke, g, bvps, price=None):
    f = fair_pb(roe, ke, g)
    if f is None or not bvps or bvps <= 0:
        return {"error": "Cost of equity musí byť aspoň o 0,5 p. b. vyššia ako rast a BVPS kladné."}
    v = f * bvps
    return {"fair_pb": f, "value": v, "upside": (v / price - 1) if price else None}


def pb_scenarios(p, price=None):
    out = []
    for name, dr, dk in (("Pesimistický", -0.03, 0.01), ("Základný", 0, 0), ("Optimistický", 0.03, -0.01)):
        r = pb_model(p["roe"] + dr, p["ke"] + dk, p["g"], p["bvps"], price)
        out.append({"name": name, "roe": p["roe"] + dr, "ke": p["ke"] + dk,
                    "fair_pb": r.get("fair_pb"), "value": r.get("value"), "upside": r.get("upside")})
    return out


def pb_sensitivity(p):
    roes = [p["roe"] + d for d in (-0.04, -0.02, 0, 0.02, 0.04)]
    kes = [p["ke"] + d for d in (-0.02, -0.01, 0, 0.01, 0.02)]
    grid = []
    for r_ in roes:
        row = []
        for k in kes:
            res = pb_model(r_, k, p["g"], p["bvps"])
            row.append(res.get("value"))
        grid.append(row)
    return {"roes": roes, "kes": kes, "grid": grid}


def multiple_model(eps0, g_eps, target_pe, r, price=None):
    """Hodnota = EPS o rok × cieľové P/E; diskontovaná späť sadzbou r na dnešok."""
    if not eps0 or eps0 <= 0 or target_pe <= 0:
        return {"error": "EPS musí byť kladné (pri strate sa P/E model nedá použiť)."}
    eps1 = eps0 * (1 + g_eps)
    in_year = eps1 * target_pe
    today = in_year / (1 + r)
    return {"eps1": eps1, "in_year": in_year, "value": today, "upside": (today / price - 1) if price else None}


def multiple_scenarios(p, price=None):
    out = []
    for name, dg, dpe in (("Pesimistický", -0.05, -0.20), ("Základný", 0, 0), ("Optimistický", 0.05, 0.20)):
        r = multiple_model(p["eps0"], p["g_eps"] + dg, p["target_pe"] * (1 + dpe), p["r"], price)
        out.append({"name": name, "g_eps": p["g_eps"] + dg, "pe": p["target_pe"] * (1 + dpe),
                    "value": r.get("value"), "upside": r.get("upside")})
    return out


# ------------------------------------------------------------------ ďalšie modely
def ddm(dps0, g_high, g_term, ke, years_high=5):
    """Dvojstupňový dividendový model: dividenda rastie g_high prvých 5 rokov, potom g_term navždy."""
    if ke <= g_term + 0.005:
        return {"error": "Požadovaná návratnosť musí byť aspoň o 0,5 p. b. vyššia ako terminálny rast."}
    if not dps0 or dps0 <= 0:
        return {"error": "Firma neplatí dividendu, dividendový model sa nedá použiť."}
    pv, d, rows = 0.0, dps0, []
    for t in range(1, years_high + 1):
        d *= 1 + g_high
        pv += d / (1 + ke) ** t
        rows.append({"t": t, "dps": d})
    tv = d * (1 + g_term) / (ke - g_term)
    pv_tv = tv / (1 + ke) ** years_high
    return {"rows": rows, "pv_div": pv, "pv_tv": pv_tv, "value": pv + pv_tv, "dps1": rows[0]["dps"]}


def ddm_scenarios(p, price=None):
    out = []
    for name, dg, dk in (("Pesimistický", -0.03, 0.01), ("Základný", 0, 0), ("Optimistický", 0.03, -0.01)):
        r = ddm(p["dps0"], p["g_high"] + dg, p["g_term"], p["ke"] + dk)
        v = r.get("value")
        out.append({"name": name, "cols": [("Rast dividendy", p["g_high"] + dg, "pct"), ("Požad. návratnosť", p["ke"] + dk, "pct")],
                    "value": v, "upside": (v / price - 1) if v and price else None})
    return out


def ev_ebitda_model(ebitda0, g, target_mult, net_debt, shares, r):
    """Hodnota firmy o rok = EBITDA × (1 + g) × cieľový násobok; mínus čistý dlh, delené akciami, diskontované."""
    if not ebitda0 or ebitda0 <= 0 or not shares or target_mult <= 0:
        return {"error": "EBITDA musí byť kladná (pri strate sa tento model nedá použiť)."}
    ev1 = ebitda0 * (1 + g) * target_mult
    eq = ev1 - net_debt
    return {"ev1": ev1, "value": eq / shares / (1 + r), "value_in_year": eq / shares}


def ev_ebitda_scenarios(p, price=None):
    out = []
    for name, dg, dm in (("Pesimistický", -0.05, -0.20), ("Základný", 0, 0), ("Optimistický", 0.05, 0.20)):
        r = ev_ebitda_model(p["ebitda0"], p["g"] + dg, p["mult"] * (1 + dm), p["net_debt"], p["shares"], p["r"])
        v = r.get("value")
        out.append({"name": name, "cols": [("Rast EBITDA", p["g"] + dg, "pct"), ("Cieľový násobok", p["mult"] * (1 + dm), "x")],
                    "value": v, "upside": (v / price - 1) if v and price else None})
    return out


def fcf_yield_model(fcf0, g, target_yield, shares, r):
    """Hodnota = FCF na akciu o rok ÷ cieľový FCF výnos, diskontovaná na dnes."""
    if not fcf0 or fcf0 <= 0 or not shares or target_yield <= 0:
        return {"error": "Voľný cash flow musí byť kladný (pri zápornom sa tento model nedá použiť)."}
    fps1 = fcf0 * (1 + g) / shares
    return {"fps1": fps1, "value": fps1 / target_yield / (1 + r)}


def fcf_yield_scenarios(p, price=None):
    out = []
    for name, dg, dy in (("Pesimistický", -0.05, 0.01), ("Základný", 0, 0), ("Optimistický", 0.05, -0.01)):
        r = fcf_yield_model(p["fcf0"], p["g"] + dg, p["yield"] + dy, p["shares"], p["r"])
        v = r.get("value")
        out.append({"name": name, "cols": [("Rast FCF", p["g"] + dg, "pct"), ("Cieľový FCF výnos", p["yield"] + dy, "pct")],
                    "value": v, "upside": (v / price - 1) if v and price else None})
    return out


def ps_model(rev0, g, target_ps, shares, r):
    if not rev0 or rev0 <= 0 or not shares or target_ps <= 0:
        return {"error": "Chýbajú tržby alebo počet akcií."}
    rps1 = rev0 * (1 + g) / shares
    return {"rps1": rps1, "value": rps1 * target_ps / (1 + r)}


def ps_scenarios(p, price=None):
    out = []
    for name, dg, dm in (("Pesimistický", -0.05, -0.25), ("Základný", 0, 0), ("Optimistický", 0.05, 0.25)):
        r = ps_model(p["rev0"], p["g"] + dg, p["target_ps"] * (1 + dm), p["shares"], p["r"])
        v = r.get("value")
        out.append({"name": name, "cols": [("Rast tržieb", p["g"] + dg, "pct"), ("Cieľové P/S", p["target_ps"] * (1 + dm), "x")],
                    "value": v, "upside": (v / price - 1) if v and price else None})
    return out


def graham(eps, bvps, g_pct, yield_aaa):
    """Grahamovo číslo √(22,5 × EPS × BVPS) a Grahamov vzorec EPS × (8,5 + 2g) × 4,4 / Y (g a Y v %)."""
    if not eps or eps <= 0 or not bvps or bvps <= 0:
        return {"error": "Grahamove vzorce potrebujú kladný zisk aj kladnú účtovnú hodnotu na akciu."}
    num = (22.5 * eps * bvps) ** 0.5
    formula = eps * (8.5 + 2 * g_pct) * 4.4 / yield_aaa if yield_aaa > 0 else None
    return {"number": num, "formula": formula}


def graham_scenarios(p, price=None):
    out = []
    for name, dg in (("Pesimistický", -3.0), ("Základný", 0.0), ("Optimistický", 3.0)):
        r = graham(p["eps"], p["bvps"], max(0.0, p["g"] + dg), p["y"])
        v = r.get("formula")
        out.append({"name": name, "cols": [("Rast zisku (% ročne)", (p["g"] + dg) / 100, "pct"), ("Grahamovo číslo", r.get("number"), "money")],
                    "value": v, "upside": (v / price - 1) if v and price else None})
    return out


def implied_growth(price, p, lo=-0.20, hi=0.60):
    """Reverzný DCF: aký rast tržieb v rokoch 1 až 5 trh očakáva pri daných ostatných vstupoch? (bisekcia)."""
    def val(g):
        r = dcf(p["rev0"], g, p["margin0"], p["margin5"], p["wacc"], p["g_term"], p["net_debt"], p["shares"], p["dilution"])
        return None if "error" in r else r["per_share"]
    a, b = val(lo), val(hi)
    if a is None or b is None or not price:
        return None
    if price <= a:
        return {"g": lo, "edge": "low"}
    if price >= b:
        return {"g": hi, "edge": "high"}
    for _ in range(60):
        mid = (lo + hi) / 2
        if val(mid) < price:
            lo = mid
        else:
            hi = mid
    return {"g": (lo + hi) / 2, "edge": None}

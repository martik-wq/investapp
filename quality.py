"""Kvalita podniku: Piotroski F-score, Altman Z'', DuPont, ROIC a súhrnné hodnotenia (slabé / priemerné / silné).

Čisté funkcie nad ročnými výkazmi (statements.build). Percentá sú v desatinách. Pravidlá hodnotenia sú
zámerne jednoduché a vypísané v šablóne, aby bolo vidno, prečo vyšiel daný výsledok."""
import valuation as V

LABELS = {0: "slabé", 1: "priemerné", 2: "silné"}


def _g(built, key, end):
    return built["data"].get(key, {}).get(end)


def _div(a, b):
    return None if a is None or b in (None, 0) else a / b


def _years(built):
    return list(built["display"])


def piotroski(built):
    """9 kritérií (0 alebo 1). Vráti {'score', 'items': [(názov, splnené|None, vysvetlenie)], 'n'} alebo None."""
    ys = _years(built)
    if len(ys) < 2:
        return None
    t, p = ys[-1], ys[-2]
    g = lambda k, e: _g(built, k, e)  # noqa: E731
    ta_t, ta_p = g("total_assets", t), g("total_assets", p)
    ta_pp = g("total_assets", ys[-3]) if len(ys) >= 3 else None
    ni_t, ni_p = g("net_income", t), g("net_income", p)
    cfo_t = g("cfo", t)
    roa_t = _div(ni_t, ta_p)
    roa_p = _div(ni_p, ta_pp)
    lev_t = _div(g("debt_lt", t) or 0, ta_t)
    lev_p = _div(g("debt_lt", p) or 0, ta_p)
    cr_t = _div(g("current_assets", t), g("current_liabilities", t))
    cr_p = _div(g("current_assets", p), g("current_liabilities", p))
    sh_t, sh_p = g("shares_diluted", t), g("shares_diluted", p)
    gm_t = _div(g("gross_profit", t), g("revenue", t))
    gm_p = _div(g("gross_profit", p), g("revenue", p))
    at_t = _div(g("revenue", t), ta_p)
    at_p = _div(g("revenue", p), ta_pp)
    def chk(c):
        return None if c is None else bool(c)
    items = [
        ("Zisk je kladný (ROA > 0)", chk(roa_t > 0 if roa_t is not None else None), "čistý zisk lomený aktívami z minulého roka"),
        ("Prevádzkový cash flow je kladný", chk(cfo_t > 0 if cfo_t is not None else None), "firma zo samotného podnikania peniaze generuje"),
        ("ROA sa zlepšilo", chk(roa_t > roa_p if roa_t is not None and roa_p is not None else None), "oproti minulému roku"),
        ("Cash flow je väčší ako zisk", chk(cfo_t > ni_t if cfo_t is not None and ni_t is not None else None), "zisk je podložený peniazmi, nie len účtovníctvom"),
        ("Dlhodobý dlh voči aktívam klesol", chk(lev_t < lev_p if lev_t is not None and lev_p is not None else None), "firma sa nezadlžuje"),
        ("Bežná likvidita sa zlepšila", chk(cr_t > cr_p if cr_t is not None and cr_p is not None else None), "obežné aktíva / krátkodobé záväzky"),
        ("Počet akcií nerástol", chk(sh_t <= sh_p * 1.005 if sh_t is not None and sh_p is not None else None), "firma neriedi akcionárov"),
        ("Hrubá marža sa zlepšila", chk(gm_t > gm_p if gm_t is not None and gm_p is not None else None), "oproti minulému roku"),
        ("Obrat aktív sa zlepšil", chk(at_t > at_p if at_t is not None and at_p is not None else None), "tržby / aktíva"),
    ]
    known = [i for i in items if i[1] is not None]
    if len(known) < 5:
        return None
    return {"score": sum(1 for i in known if i[1]), "n": len(known), "items": items, "year": t}


def altman(built):
    """Altman Z'' (verzia pre nevýrobné firmy a bez trhovej hodnoty). Zóny: > 2,6 bezpečná, 1,1 až 2,6 šedá, < 1,1 riziková."""
    t = _years(built)[-1]
    g = lambda k: _g(built, k, t)  # noqa: E731
    ta = g("total_assets")
    if not ta:
        return None
    wc = (g("current_assets") - g("current_liabilities")) if g("current_assets") is not None and g("current_liabilities") is not None else None
    re_ = g("retained")
    ebit = g("op_income")
    eq = g("equity")
    tl = g("total_liabilities")
    if None in (wc, re_, ebit, eq) or not tl:
        return None
    x1, x2, x3, x4 = wc / ta, re_ / ta, ebit / ta, eq / tl
    z = 6.56 * x1 + 3.26 * x2 + 6.72 * x3 + 1.05 * x4
    zone = "bezpečná" if z > 2.6 else ("šedá" if z >= 1.1 else "riziková")
    return {"z": z, "zone": zone, "parts": [("Pracovný kapitál / aktíva", x1), ("Nerozdelený zisk / aktíva", x2),
                                           ("EBIT / aktíva", x3), ("Vlastné imanie / záväzky", x4)], "year": t}


def dupont(built, n=5):
    """Rozklad ROE = čistá marža × obrat aktív × finančná páka (koncoroční zostatky)."""
    rows = []
    for e in _years(built)[-n:]:
        g = lambda k: _g(built, k, e)  # noqa: E731
        ni, rev, ta, eq = g("net_income"), V.net_revenue(built, e), g("total_assets"), g("equity")
        if None in (ni, rev, ta, eq) or not rev or not ta or not eq or eq <= 0:
            continue
        rows.append({"end": e, "margin": ni / rev, "turnover": rev / ta, "leverage": ta / eq, "roe": ni / eq})
    return rows


def roic(built, tax_default=0.21):
    """NOPAT / investovaný kapitál (dlh + vlastné imanie − hotovosť)."""
    t = _years(built)[-1]
    g = lambda k: _g(built, k, t)  # noqa: E731
    ebit, eq = g("op_income"), g("equity")
    if ebit is None or eq is None:
        return None
    debt = g("total_debt")
    if debt is None:
        debt = (g("debt_current") or 0) + (g("debt_lt") or 0)
    cash = (g("cash") or 0) + (g("st_investments") or 0)
    ic = debt + eq - cash
    if ic <= 0:
        return None
    pretax, tax = g("pretax"), g("tax")
    rate = tax_default
    if pretax and tax is not None and pretax > 0:
        rate = max(0.0, min(0.35, tax / pretax))
    return {"roic": ebit * (1 - rate) / ic, "tax": rate, "invested": ic}


def _score(v, strong, ok, higher_better=True):
    """2 = silné, 1 = priemerné, 0 = slabé; None, ak hodnota chýba."""
    if v is None:
        return None
    if higher_better:
        return 2 if v >= strong else (1 if v >= ok else 0)
    return 2 if v <= strong else (1 if v <= ok else 0)


# Referenčné hranice podľa typu biznisu: kľúč -> {typ: (silné, priemerné)}, vyšší/nižší je lepší, jednotka.
# Hodnota je „silná“, ak dosiahne prvé číslo, „priemerná“, ak dosiahne druhé, inak „slabá“.
TH = {
    "rev_cagr": ("Rast tržieb (CAGR)", True, "pct", {"general": (0.06, 0.02), "tech": (0.15, 0.06), "reit": (0.05, 0.02),
                                                   "bank": (0.08, 0.03), "insurance": (0.06, 0.02)}),
    "eps_cagr": ("Rast zisku na akciu (CAGR)", True, "pct", {"general": (0.08, 0.02), "tech": (0.15, 0.05), "reit": (0.05, 0.0),
                                                           "bank": (0.10, 0.03), "insurance": (0.08, 0.02)}),
    "op_margin": ("Prevádzková marža", True, "pct", {"general": (0.15, 0.07), "tech": (0.25, 0.12), "reit": (0.30, 0.15)}),
    "roic": ("ROIC", True, "pct", {"general": (0.12, 0.07), "tech": (0.20, 0.10), "reit": (0.06, 0.03)}),
    "fcf_margin": ("FCF marža (priemer 3 roky)", True, "pct", {"general": (0.10, 0.04), "tech": (0.20, 0.08), "reit": (0.25, 0.10)}),
    "nd_ebitda": ("Čistý dlh / EBITDA", False, "x", {"general": (1.5, 3.0), "tech": (0.5, 2.0), "reit": (5.0, 7.0)}),
    "coverage": ("Krytie úrokov (EBIT / úroky)", True, "x", {"general": (8, 3), "tech": (15, 5), "reit": (3, 1.5)}),
    "cfo_ni": ("Cash flow / čistý zisk", True, "x", {"general": (1.0, 0.7), "tech": (1.0, 0.7), "reit": (1.2, 0.9)}),
    "sbc": ("Akciové odmeny / tržby", False, "pct", {"general": (0.01, 0.03), "tech": (0.06, 0.12), "reit": (0.01, 0.03)}),
    "roe": ("ROE", True, "pct", {"bank": (0.12, 0.08), "insurance": (0.12, 0.08)}),
    "roa": ("ROA (zisk / aktíva)", True, "pct", {"bank": (0.010, 0.005), "insurance": (0.020, 0.008)}),
    "efficiency": ("Efficiency ratio (náklady / výnosy)", False, "pct", {"bank": (0.55, 0.65)}),
    "eq_assets": ("Vlastné imanie / aktíva", True, "pct", {"bank": (0.10, 0.06), "insurance": (0.15, 0.08)}),
    "ltd": ("Úvery / vklady", False, "pct", {"bank": (0.85, 1.00)}),
    "net_margin": ("Čistá marža", True, "pct", {"bank": (0.25, 0.12), "insurance": (0.10, 0.04)}),
}
TYPE_NAMES = {"general": "Všeobecné firmy", "tech": "Technológie", "reit": "REIT", "bank": "Banky", "insurance": "Poisťovne"}


def _fmt_th(v, kind):
    if kind == "pct":
        return f"{v * 100:.1f} %".replace(".", ",").replace(",0 %", " %")
    return f"{v:g}×".replace(".", ",")


def _ref(key, btype):
    """Text referencie pre ukazovateľ a typ biznisu: „silné ≥ 15 %, priemerné ≥ 7 %, slabé pod 7 %“."""
    name, hi, kind, per = TH[key]
    th = per.get(btype) or per.get("general")
    if not th:
        return None
    s_, o_ = th
    if hi:
        return f"silné ≥ {_fmt_th(s_, kind)}, priemerné ≥ {_fmt_th(o_, kind)}, slabé pod {_fmt_th(o_, kind)}"
    return f"silné ≤ {_fmt_th(s_, kind)}, priemerné ≤ {_fmt_th(o_, kind)}, slabé nad {_fmt_th(o_, kind)}"


def _sc(key, btype, v):
    name, hi, kind, per = TH[key]
    th = per.get(btype) or per.get("general")
    return None if not th else _score(v, th[0], th[1], hi)


def reference_table():
    """Všetky referenčné hranice pre všetky typy biznisu (riadky: ukazovateľ, stĺpce: typ)."""
    rows = []
    for key, (name, hi, kind, per) in TH.items():
        cells = []
        for t in ("general", "tech", "reit", "bank", "insurance"):
            th = per.get(t)
            cells.append(None if not th else (f"≥ {_fmt_th(th[0], kind)} / ≥ {_fmt_th(th[1], kind)}" if hi
                                              else f"≤ {_fmt_th(th[0], kind)} / ≤ {_fmt_th(th[1], kind)}"))
        rows.append({"name": name, "cells": cells})
    return {"types": [TYPE_NAMES[t] for t in ("general", "tech", "reit", "bank", "insurance")], "rows": rows}


def ratings(built, facts, pio, alt, ro, btype="general"):
    """Hodnotenia s ukazovateľmi: [{'name','label','level','parts':[(názov, hodnota, skóre, referencia)]}]."""
    t = _years(built)[-1]
    g = lambda k: _g(built, k, t)  # noqa: E731
    pct = lambda v: "–" if v is None else f"{v * 100:.1f} %".replace(".", ",")  # noqa: E731
    x = lambda v: "–" if v is None else f"{v:.1f}×".replace(".", ",")  # noqa: E731
    ebitda = None
    if g("op_income") is not None and g("da") is not None:
        ebitda = g("op_income") + g("da")
    nd_e = _div(facts.get("net_debt"), ebitda) if ebitda and ebitda > 0 else None
    cov = _div(g("op_income"), abs(g("interest_expense"))) if g("interest_expense") else None
    om = _div(g("op_income"), g("revenue"))
    cfo_ni = _div(g("cfo"), g("net_income")) if (g("net_income") or 0) > 0 else None
    sbc = _div(g("sbc"), g("revenue"))
    groups = []

    def grp(name, parts):
        sc = [s for _, _, s, _ in parts if s is not None]
        lvl = round(sum(sc) / len(sc)) if sc else None
        groups.append({"name": name, "level": lvl, "label": LABELS.get(lvl, "bez údajov"), "parts": parts})

    def part(label, key, value, text):
        return (label, text, _sc(key, btype, value), _ref(key, btype))

    no_nd = (facts.get("net_debt") or 0) <= 0
    grp("Rast", [part("Rast tržieb 3 roky (CAGR)", "rev_cagr", facts.get("rev_cagr3"), pct(facts.get("rev_cagr3"))),
                 part("Rast tržieb 5 rokov (CAGR)", "rev_cagr", facts.get("rev_cagr5"), pct(facts.get("rev_cagr5"))),
                 part("Rast zisku na akciu 3 roky", "eps_cagr", facts.get("eps_cagr3"), pct(facts.get("eps_cagr3")))])
    grp("Ziskovosť", [part("Prevádzková marža", "op_margin", om, pct(om)),
                      part("ROIC", "roic", ro["roic"] if ro else None, pct(ro["roic"] if ro else None)),
                      part("FCF marža (priemer 3 roky)", "fcf_margin", facts.get("fcf_margin_avg3"), pct(facts.get("fcf_margin_avg3")))])
    nd_part = ("Čistý dlh / EBITDA", x(nd_e) if nd_e is not None else ("bez čistého dlhu" if no_nd else "–"),
               2 if no_nd else _sc("nd_ebitda", btype, nd_e), _ref("nd_ebitda", btype))
    grp("Finančné zdravie", [nd_part, part("Krytie úrokov (EBIT / úroky)", "coverage", cov, x(cov)),
                             ("Altman Z'' zóna", alt["zone"] if alt else "–",
                              None if not alt else (2 if alt["zone"] == "bezpečná" else (1 if alt["zone"] == "šedá" else 0)),
                              "silné: bezpečná zóna (Z'' > 2,6), priemerné: šedá (1,1 až 2,6), slabé: riziková (< 1,1)")])
    grp("Kvalita ziskov", [part("Cash flow / čistý zisk", "cfo_ni", cfo_ni, x(cfo_ni)),
                           part("Akciové odmeny / tržby", "sbc", sbc, pct(sbc)),
                           ("Piotroski F-score", f"{pio['score']} z {pio['n']}" if pio else "–",
                            None if not pio else (2 if pio["score"] >= 7 else (1 if pio["score"] >= 4 else 0)),
                            "silné: 7 až 9, priemerné: 4 až 6, slabé: 0 až 3")])
    return groups


def financial_ratings(built, facts, btype):
    """Hodnotenia pre banky a poisťovne z ich vlastných ukazovateľov."""
    ys = _years(built)
    t = ys[-1]
    g = lambda k: _g(built, k, t)  # noqa: E731
    pct = lambda v: "–" if v is None else f"{v * 100:.1f} %".replace(".", ",")  # noqa: E731
    ni, eq, ta = g("net_income"), g("equity"), g("total_assets")
    eq_prev = _g(built, "equity", ys[-2]) if len(ys) >= 2 else None
    eq_avg = (eq + eq_prev) / 2 if eq is not None and eq_prev else eq
    net_rev = (g("nii") or 0) + (g("nonint_income") or 0) if g("nii") is not None else g("revenue")
    roe = _div(ni, eq_avg) if eq_avg and eq_avg > 0 else None
    roa = _div(ni, ta)
    eff = _div(g("nonint_expense"), net_rev) if g("nonint_expense") is not None and net_rev else None
    eqa = _div(eq, ta)
    ltd = _div(g("loans"), g("deposits"))
    nm = _div(ni, net_rev)
    groups = []

    def part(label, key, value):
        return (label, pct(value), _sc(key, btype, value), _ref(key, btype))

    def grp(name, parts):
        sc = [s for _, _, s, _ in parts if s is not None]
        lvl = round(sum(sc) / len(sc)) if sc else None
        groups.append({"name": name, "level": lvl, "label": LABELS.get(lvl, "bez údajov"), "parts": parts})

    grp("Rast", [part("Rast tržieb 3 roky (CAGR)", "rev_cagr", facts.get("rev_cagr3")),
                 part("Rast tržieb 5 rokov (CAGR)", "rev_cagr", facts.get("rev_cagr5")),
                 part("Rast zisku na akciu 3 roky", "eps_cagr", facts.get("eps_cagr3"))])
    prof = [part("ROE", "roe", roe), part("ROA (zisk / aktíva)", "roa", roa)]
    if btype == "bank":
        prof.append(part("Efficiency ratio (náklady / výnosy)", "efficiency", eff))
    else:
        prof.append(part("Čistá marža", "net_margin", nm))
    grp("Ziskovosť", prof)
    health = [part("Vlastné imanie / aktíva", "eq_assets", eqa)]
    if btype == "bank":
        health.append(part("Úvery / vklady", "ltd", ltd))
    grp("Finančné zdravie", health)
    return groups


def build(built, facts, btype):
    """Karta kvality. Pri bankách a poisťovniach sa Piotroski, Altman a ROIC nepoužívajú; majú vlastné ukazovatele."""
    ref = reference_table()
    if btype in ("bank", "insurance"):
        try:
            return {"skip": False, "financial": True, "pio": None, "alt": None, "roic": None, "dupont": dupont(built),
                    "ratings": financial_ratings(built, facts, btype), "reference": ref, "btype": btype}
        except (TypeError, ZeroDivisionError):
            return {"skip": True}
    try:
        pio, alt, ro = piotroski(built), altman(built), roic(built)
        rat = ratings(built, facts, pio, alt, ro, btype)
    except (TypeError, ZeroDivisionError):
        return {"skip": True}
    return {"skip": False, "financial": False, "pio": pio, "alt": alt, "roic": ro, "dupont": dupont(built),
            "ratings": rat, "reference": ref, "btype": btype}

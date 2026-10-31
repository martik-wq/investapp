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
        ni, rev, ta, eq = g("net_income"), g("revenue"), g("total_assets"), g("equity")
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
    pretax, tax = g("pretax"), g("income_tax")
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


def ratings(built, facts, pio, alt, ro):
    """Štyri hodnotenia s vypísanými ukazovateľmi: [{'name','label','level','parts':[(názov,hodnota text,skóre)]}]."""
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
        sc = [s for _, _, s in parts if s is not None]
        lvl = round(sum(sc) / len(sc)) if sc else None
        groups.append({"name": name, "level": lvl, "label": LABELS.get(lvl, "bez údajov"), "parts": parts})

    grp("Rast", [("Rast tržieb 3 roky (CAGR)", pct(facts.get("rev_cagr3")), _score(facts.get("rev_cagr3"), 0.10, 0.03)),
                 ("Rast tržieb 5 rokov (CAGR)", pct(facts.get("rev_cagr5")), _score(facts.get("rev_cagr5"), 0.10, 0.03)),
                 ("Rast zisku na akciu 3 roky", pct(facts.get("eps_cagr3")), _score(facts.get("eps_cagr3"), 0.10, 0.03))])
    grp("Ziskovosť", [("Prevádzková marža", pct(om), _score(om, 0.20, 0.08)),
                      ("ROIC", pct(ro["roic"] if ro else None), _score(ro["roic"] if ro else None, 0.15, 0.08)),
                      ("FCF marža (priemer 3 roky)", pct(facts.get("fcf_margin_avg3")), _score(facts.get("fcf_margin_avg3"), 0.15, 0.05))])
    grp("Finančné zdravie", [("Čistý dlh / EBITDA", x(nd_e) if nd_e is not None else ("bez čistého dlhu" if (facts.get("net_debt") or 0) <= 0 else "–"),
                              2 if (facts.get("net_debt") or 0) <= 0 else _score(nd_e, 1.0, 3.0, False)),
                             ("Krytie úrokov (EBIT / úroky)", x(cov), _score(cov, 8, 3)),
                             ("Altman Z'' zóna", alt["zone"] if alt else "–", None if not alt else (2 if alt["zone"] == "bezpečná" else (1 if alt["zone"] == "šedá" else 0)))])
    grp("Kvalita ziskov", [("Cash flow / čistý zisk", x(cfo_ni), _score(cfo_ni, 1.0, 0.7)),
                           ("Akciové odmeny / tržby", pct(sbc), _score(sbc, 0.03, 0.08, False)),
                           ("Piotroski F-score", f"{pio['score']} z {pio['n']}" if pio else "–",
                            None if not pio else (2 if pio["score"] >= 7 else (1 if pio["score"] >= 4 else 0)))])
    return groups


def build(built, facts, btype):
    """Celá karta kvality. Pri bankách a poisťovniach sa tieto modely nepoužívajú (vráti {'skip': True})."""
    if btype in ("bank", "insurance"):
        return {"skip": True}
    try:
        pio, alt, ro = piotroski(built), altman(built), roic(built)
    except (TypeError, ZeroDivisionError):
        return {"skip": True}
    return {"skip": False, "pio": pio, "alt": alt, "roic": ro, "dupont": dupont(built),
            "ratings": ratings(built, facts, pio, alt, ro)}

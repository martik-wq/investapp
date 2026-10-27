"""Finančné metriky podľa typu biznisu.

V ročnom režime sa metriky počítajú z ročných údajov. V kvartálnom režime sa
všetky toky (tržby, zisk, cash flow...) sčítajú za posledných 12 mesiacov (TTM),
takže ratio ako ROE či marže sú porovnateľné s ročnými.
"""
from datetime import timedelta

from taxonomy import (BANK_SIC, BUSINESS_TYPES, FLOW_KEYS, INSURANCE_SIC, REIT_SIC,
                      TECH_SIC)


# ------------------------------------------------------------------ pomocné funkcie
def div(a, b):
    if a is None or b is None or b == 0:
        return None
    return a / b


def sub(a, b):
    return None if a is None or b is None else a - b


def add(*xs):
    return None if any(x is None for x in xs) else sum(xs)


def addn(*xs):
    vals = [x for x in xs if x is not None]
    return sum(vals) if vals else None


def mul(a, b):
    return None if a is None or b is None else a * b


def ttm_data(built):
    """Z kvartálnych údajov vyrobí TTM (súčet posledných 4 kvartálov)."""
    ends, data = built["ends"], built["data"]
    out = {}
    for k, s in data.items():
        if k in FLOW_KEYS or k == "fcf":
            t = {}
            for i, e in enumerate(ends):
                if i >= 3 and 250 <= (e - ends[i - 3]).days <= 290:
                    vals = [s.get(x) for x in ends[i - 3:i + 1]]
                    if all(v is not None for v in vals):
                        t[e] = sum(vals)
            out[k] = t
        else:
            out[k] = s
    return out


class Ctx:
    def __init__(self, data, ends):
        self.d, self.ends = data, ends

    def v(self, k, e):
        return self.d.get(k, {}).get(e)

    def prev(self, e):
        target = e - timedelta(days=365)
        best = None
        for x in self.ends:
            dd = abs((x - target).days)
            if dd <= 25 and (best is None or dd < best[0]):
                best = (dd, x)
        return best[1] if best else None

    def pv(self, k, e):
        p = self.prev(e)
        return self.v(k, p) if p else None

    def avg(self, k, e):
        a, b = self.v(k, e), self.pv(k, e)
        return (a + b) / 2 if a is not None and b is not None else None

    def growth(self, k, e):
        a, b = self.v(k, e), self.pv(k, e)
        if a is None or b is None or b <= 0:
            return None
        return a / b - 1

    def tax_rate(self, e):
        t, p = self.v("tax", e), self.v("pretax", e)
        if t is not None and p is not None and p > 0:
            return min(max(t / p, 0.0), 0.35)
        return 0.21

    # odvodené veličiny
    def revenue_like(self, e):
        r = self.v("revenue", e)
        if r is not None:
            return r
        return add(self.nii(e), self.v("nonint_income", e)) \
            if self.nii(e) is not None and self.v("nonint_income", e) is not None else None

    def nii(self, e):
        return self.v("nii", e)

    def ebitda(self, e):
        return add(self.v("op_income", e), self.v("da", e))

    def net_debt(self, e):
        td = self.v("total_debt", e)
        cash = self.v("cash", e)
        if td is None or cash is None:
            return None
        return td - cash - (self.v("st_investments", e) or 0)

    def tangible_equity(self, e):
        eq = self.v("equity", e)
        if eq is None:
            return None
        return eq - (self.v("goodwill", e) or 0) - (self.v("intangibles", e) or 0)

    def shares(self, e):
        return self.v("shares_diluted", e)

    def ffo(self, e):
        ni, da = self.v("net_income", e), self.v("da", e)
        if ni is None or da is None:
            return None
        return ni + da - (self.v("gain_on_sale", e) or 0)


def M(id_, label, fn, fmt, note=None):
    return dict(id=id_, label=label, fn=fn, fmt=fmt, note=note)


# -------------------------------------------------------------- definície metrík
def _common_returns(c):
    return [
        M("roe", "ROE (čistý zisk / priem. vlastné imanie)",
          lambda e: div(c.v("net_income", e), c.avg("equity", e)), "pct"),
        M("roa", "ROA (čistý zisk / priem. aktíva)",
          lambda e: div(c.v("net_income", e), c.avg("total_assets", e)), "pct"),
    ]


def _per_share(c, tangible=False):
    rows = [
        M("eps", "EPS (zriedený)", lambda e: c.v("eps_diluted", e), "eps"),
        M("eps_g", "Rast EPS (r/r)", lambda e: c.growth("eps_diluted", e), "pct"),
        M("bvps", "Účtovná hodnota na akciu (BVPS)",
          lambda e: div(c.v("equity", e), c.shares(e)), "eps"),
    ]
    if tangible:
        rows.append(M("tbvps", "Tangible BVPS (bez goodwillu a nehm. majetku)",
                      lambda e: div(c.tangible_equity(e), c.shares(e)), "eps"))
    rows += [
        M("dps", "Dividenda na akciu (vyplatené / akcie)",
          lambda e: div(c.v("div_paid", e), c.shares(e)), "eps"),
        M("payout", "Výplatný pomer (dividendy / čistý zisk)",
          lambda e: div(c.v("div_paid", e), c.v("net_income", e)), "pct"),
    ]
    return rows


def groups_general(c, tech=False):
    g = []
    g.append(("Rast", [
        M("rev_g", "Rast tržieb (r/r)", lambda e: c.growth("revenue", e), "pct"),
        M("opi_g", "Rast prevádzkového zisku (r/r)",
          lambda e: c.growth("op_income", e), "pct"),
        M("ni_g", "Rast čistého zisku (r/r)", lambda e: c.growth("net_income", e), "pct"),
    ]))
    g.append(("Ziskovosť", [
        M("gm", "Hrubá marža", lambda e: div(c.v("gross_profit", e), c.v("revenue", e)),
          "pct"),
        M("om", "Prevádzková marža", lambda e: div(c.v("op_income", e), c.v("revenue", e)),
          "pct"),
        M("ebitda", "EBITDA (prev. zisk + odpisy)", c.ebitda, "money"),
        M("ebitda_m", "EBITDA marža", lambda e: div(c.ebitda(e), c.v("revenue", e)),
          "pct"),
        M("nm", "Čistá marža", lambda e: div(c.v("net_income", e), c.v("revenue", e)),
          "pct"),
    ] + _common_returns(c) + [
        M("roic", "ROIC (NOPAT / (dlh + imanie − hotovosť))",
          lambda e: div(
              mul(c.v("op_income", e), 1 - c.tax_rate(e)),
              (lambda a, b: None if a is None or b is None else (a + b) / 2)(
                  _ic(c, e), _ic(c, c.prev(e)) if c.prev(e) else None)),
          "pct", "Daňová sadzba = efektívna (0–35 %), inak 21 %."),
    ]))
    if tech:
        g.append(("Technologické ukazovatele", [
            M("rnd_pct", "R&D / tržby", lambda e: div(c.v("rnd", e), c.v("revenue", e)),
              "pct"),
            M("sga_pct", "SG&A / tržby", lambda e: div(c.v("sga", e), c.v("revenue", e)),
              "pct"),
            M("sbc_pct", "Akciová kompenzácia / tržby",
              lambda e: div(c.v("sbc", e), c.v("revenue", e)), "pct"),
            M("r40", "Rule of 40 (rast tržieb + FCF marža)",
              lambda e: add(c.growth("revenue", e), div(c.v("fcf", e), c.v("revenue", e)))
              if c.growth("revenue", e) is not None
              and div(c.v("fcf", e), c.v("revenue", e)) is not None else None,
              "pct", "Hodnota nad 40 % sa považuje za silnú."),
        ]))
    g.append(("Cash flow", [
        M("fcf", "Voľný cash flow (FCF)", lambda e: c.v("fcf", e), "money"),
        M("fcf_m", "FCF marža", lambda e: div(c.v("fcf", e), c.v("revenue", e)), "pct"),
        M("fcf_conv", "FCF / čistý zisk",
          lambda e: div(c.v("fcf", e), c.v("net_income", e)), "pct"),
        M("capex_pct", "CapEx / tržby",
          lambda e: div(abs(c.v("capex", e)) if c.v("capex", e) is not None else None,
                        c.v("revenue", e)), "pct"),
    ]))
    g.append(("Zadlženosť a likvidita", [
        M("cur_ratio", "Pomer bežnej likvidity",
          lambda e: div(c.v("current_assets", e), c.v("current_liabilities", e)), "x"),
        M("quick", "Rýchla likvidita ((hotovosť + inv. + pohľadávky) / kr. záväzky)",
          lambda e: div(addn(c.v("cash", e), c.v("st_investments", e),
                             c.v("receivables", e)), c.v("current_liabilities", e)), "x"),
        M("de", "Dlh / vlastné imanie",
          lambda e: div(c.v("total_debt", e), c.v("equity", e)), "x"),
        M("net_debt", "Čistý dlh", c.net_debt, "money"),
        M("nd_ebitda", "Čistý dlh / EBITDA",
          lambda e: div(c.net_debt(e), c.ebitda(e)), "x"),
        M("icov", "Úrokové krytie (prev. zisk / úrokové náklady)",
          lambda e: div(c.v("op_income", e), abs(c.v("interest_expense", e))
                        if c.v("interest_expense", e) else None), "x"),
        M("liab_assets", "Záväzky / aktíva",
          lambda e: div(c.v("total_liabilities", e), c.v("total_assets", e)), "pct"),
    ]))
    g.append(("Efektivita", [
        M("asset_turn", "Obrat aktív (tržby / priem. aktíva)",
          lambda e: div(c.v("revenue", e), c.avg("total_assets", e)), "x"),
        M("dso", "DSO – dni inkasa pohľadávok",
          lambda e: mul(div(c.v("receivables", e), c.v("revenue", e)), 365), "days"),
        M("dio", "DIO – dni zásob",
          lambda e: mul(div(c.v("inventory", e), c.v("cost_of_revenue", e)), 365), "days"),
    ]))
    g.append(("Na akciu a dividendy", _per_share(c)))
    return g


def _ic(c, e):
    if e is None:
        return None
    td, eq, cash = c.v("total_debt", e), c.v("equity", e), c.v("cash", e)
    if eq is None:
        return None
    return (td or 0) + eq - (cash or 0)


def groups_bank(c):
    def nii(e):
        return c.nii(e)

    def net_rev(e):
        n, ni = nii(e), c.v("nonint_income", e)
        return add(n, ni) if n is not None and ni is not None else None

    def gross_loans(e):
        l, a = c.v("loans", e), c.v("allowance", e)
        return l + abs(a) if l is not None and a is not None else l

    g = []
    g.append(("Rast", [
        M("nii_g", "Rast čistého úrokového výnosu (r/r)",
          lambda e: _g(c, nii, e), "pct"),
        M("rev_g", "Rast výnosov (r/r)", lambda e: _g(c, c.revenue_like, e), "pct"),
        M("ni_g", "Rast čistého zisku (r/r)", lambda e: c.growth("net_income", e), "pct"),
        M("loan_g", "Rast úverov (r/r)", lambda e: c.growth("loans", e), "pct"),
        M("dep_g", "Rast vkladov (r/r)", lambda e: c.growth("deposits", e), "pct"),
    ]))
    g.append(("Ziskovosť", [
        M("nii", "Čistý úrokový výnos (NII)", nii, "money"),
        M("net_rev", "Výnosy spolu (NII + neúrokové výnosy)", net_rev, "money"),
        M("nim", "NII / priemerné aktíva (približné NIM)",
          lambda e: div(nii(e), c.avg("total_assets", e)), "pct",
          "Skutočné NIM sa počíta z úročených aktív, tu je to zjednodušenie."),
        M("nonint_share", "Podiel neúrokových výnosov",
          lambda e: div(c.v("nonint_income", e), net_rev(e)), "pct"),
        M("eff", "Efficiency ratio (neúrokové náklady / výnosy)",
          lambda e: div(c.v("nonint_expense", e), net_rev(e)), "pct",
          "Nižšie = lepšie."),
        M("nm", "Čistá marža (čistý zisk / výnosy)",
          lambda e: div(c.v("net_income", e), c.revenue_like(e)), "pct"),
    ] + _common_returns(c) + [
        M("rotce", "ROTCE (čistý zisk / priem. tangible equity)",
          lambda e: div(c.v("net_income", e),
                        _avg_fn(c, c.tangible_equity, e)), "pct"),
    ]))
    g.append(("Kvalita úverov a bilancia", [
        M("cor", "Náklady na riziko (provízie / priem. úvery)",
          lambda e: div(c.v("provision", e), c.avg("loans", e)), "pct"),
        M("allow", "Opravné položky / hrubé úvery",
          lambda e: div(abs(c.v("allowance", e)) if c.v("allowance", e) is not None
                        else None, gross_loans(e)), "pct"),
        M("ltd", "Úvery / vklady",
          lambda e: div(c.v("loans", e), c.v("deposits", e)), "pct"),
        M("eq_assets", "Vlastné imanie / aktíva",
          lambda e: div(c.v("equity", e), c.v("total_assets", e)), "pct"),
        M("tce_assets", "Tangible equity / aktíva",
          lambda e: div(c.tangible_equity(e), c.v("total_assets", e)), "pct"),
    ]))
    g.append(("Cash flow", [
        M("cfo", "Cash flow z prevádzkovej činnosti", lambda e: c.v("cfo", e), "money",
          "U bánk je CFO ovplyvnené zmenami úverov, takže FCF sa nezobrazuje."),
    ]))
    g.append(("Na akciu a dividendy", _per_share(c, tangible=True)))
    return g


def _g(c, fn, e):
    p = c.prev(e)
    a, b = fn(e), fn(p) if p else None
    if a is None or b is None or b <= 0:
        return None
    return a / b - 1


def _avg_fn(c, fn, e):
    p = c.prev(e)
    a, b = fn(e), fn(p) if p else None
    return (a + b) / 2 if a is not None and b is not None else None


def groups_insurance(c):
    g = []
    g.append(("Rast", [
        M("rev_g", "Rast výnosov (r/r)", lambda e: c.growth("revenue", e), "pct"),
        M("prem_g", "Rast zaslúženého poistného (r/r)",
          lambda e: c.growth("premiums", e), "pct"),
        M("ni_g", "Rast čistého zisku (r/r)", lambda e: c.growth("net_income", e), "pct"),
    ]))
    g.append(("Underwriting", [
        M("premiums", "Zaslúžené poistné", lambda e: c.v("premiums", e), "money"),
        M("loss_ratio", "Loss ratio (plnenia / zaslúžené poistné)",
          lambda e: div(c.v("claims", e), c.v("premiums", e)), "pct", "Nižšie = lepšie."),
        M("combined", "Približný combined ratio (všetky náklady / zaslúžené poistné)",
          lambda e: div(c.v("total_benefits_expenses", e), c.v("premiums", e)), "pct",
          "Zjednodušenie z konsolidovaných údajov. Pod 100 % = underwriting zisk."),
        M("inv_share", "Podiel výnosov z investícií na výnosoch",
          lambda e: div(c.v("inv_income", e), c.v("revenue", e)), "pct"),
    ]))
    g.append(("Ziskovosť", [
        M("nm", "Čistá marža", lambda e: div(c.v("net_income", e), c.v("revenue", e)),
          "pct"),
    ] + _common_returns(c)))
    g.append(("Bilancia", [
        M("eq_assets", "Vlastné imanie / aktíva",
          lambda e: div(c.v("equity", e), c.v("total_assets", e)), "pct"),
        M("de", "Dlh / vlastné imanie",
          lambda e: div(c.v("total_debt", e), c.v("equity", e)), "x"),
    ]))
    g.append(("Cash flow", [
        M("cfo", "Cash flow z prevádzkovej činnosti", lambda e: c.v("cfo", e), "money"),
    ]))
    g.append(("Na akciu a dividendy", _per_share(c)))
    return g


def groups_reit(c):
    g = []
    g.append(("Rast", [
        M("rev_g", "Rast tržieb (r/r)", lambda e: c.growth("revenue", e), "pct"),
        M("ffo_g", "Rast FFO (r/r)", lambda e: _g(c, c.ffo, e), "pct"),
    ]))
    g.append(("FFO a dividendy", [
        M("ffo", "FFO (čistý zisk + odpisy − zisk z predaja)", c.ffo, "money",
          "Zjednodušené FFO. Presné FFO podľa NAREIT upravuje aj o znehodnotenia."),
        M("ffo_ps", "FFO na akciu",
          lambda e: div(c.ffo(e), c.shares(e)), "eps"),
        M("ffo_payout", "Výplatný pomer z FFO (dividendy / FFO)",
          lambda e: div(c.v("div_paid", e), c.ffo(e)), "pct"),
        M("dps", "Dividenda na akciu",
          lambda e: div(c.v("div_paid", e), c.shares(e)), "eps"),
        M("eps", "EPS (zriedený)", lambda e: c.v("eps_diluted", e), "eps"),
    ]))
    g.append(("Ziskovosť", [
        M("om", "Prevádzková marža", lambda e: div(c.v("op_income", e), c.v("revenue", e)),
          "pct"),
        M("ebitda", "EBITDA", c.ebitda, "money"),
        M("ebitda_m", "EBITDA marža", lambda e: div(c.ebitda(e), c.v("revenue", e)),
          "pct"),
        M("ga_pct", "G&A / tržby", lambda e: div(c.v("ga", e), c.v("revenue", e)), "pct"),
    ] + _common_returns(c)))
    g.append(("Zadlženosť", [
        M("net_debt", "Čistý dlh", c.net_debt, "money"),
        M("nd_ebitda", "Čistý dlh / EBITDA", lambda e: div(c.net_debt(e), c.ebitda(e)),
          "x", "Pre REIT sa považuje za zdravé zhruba 5–7×."),
        M("debt_assets", "Dlh / aktíva",
          lambda e: div(c.v("total_debt", e), c.v("total_assets", e)), "pct"),
        M("icov", "Úrokové krytie (EBITDA / úrokové náklady)",
          lambda e: div(c.ebitda(e), abs(c.v("interest_expense", e))
                        if c.v("interest_expense", e) else None), "x"),
    ]))
    g.append(("Cash flow", [
        M("cfo", "Cash flow z prevádzkovej činnosti", lambda e: c.v("cfo", e), "money"),
        M("bvps", "Účtovná hodnota na akciu",
          lambda e: div(c.v("equity", e), c.shares(e)), "eps"),
    ]))
    return g


# ------------------------------------------------------------- detekcia typu biznisu
def detect_type(company, built):
    sic = company.get("sic")
    d = built["data"]
    if sic in REIT_SIC:
        return "reit"
    if sic in INSURANCE_SIC:
        return "insurance"
    if sic in BANK_SIC:
        return "bank"
    if d.get("deposits") and d.get("loans"):
        return "bank"
    if d.get("premiums") and d.get("claims"):
        return "insurance"
    if sic in TECH_SIC:
        return "tech"
    rev, rnd = d.get("revenue", {}), d.get("rnd", {})
    for e in sorted(rev, reverse=True)[:1]:
        if rev[e] and rnd.get(e) and rnd[e] / rev[e] > 0.15:
            return "tech"
    return "general"


HEADLINES = {
    "general": ["rev_g", "om", "nm", "roe", "roic", "fcf_m", "nd_ebitda", "eps"],
    "tech": ["rev_g", "gm", "om", "fcf_m", "r40", "roe", "sbc_pct", "eps"],
    "bank": ["rev_g", "nim", "eff", "roe", "rotce", "cor", "eq_assets", "eps"],
    "insurance": ["prem_g", "loss_ratio", "combined", "roe", "roa", "eq_assets", "eps",
                  "bvps"],
    "reit": ["rev_g", "ffo_ps", "ffo_payout", "nd_ebitda", "icov", "om", "dps", "bvps"],
}


def compute(company, built, btype):
    """Vráti dict: groups, headline, chart, valuation_fn, ctx info."""
    data = ttm_data(built) if built["mode"] == "quarterly" else built["data"]
    c = Ctx(data, built["ends"])
    disp = built["display"]

    if btype == "bank":
        raw_groups = groups_bank(c)
    elif btype == "insurance":
        raw_groups = groups_insurance(c)
    elif btype == "reit":
        raw_groups = groups_reit(c)
    else:
        raw_groups = groups_general(c, tech=(btype == "tech"))

    groups, by_id = [], {}
    for title, metrics in raw_groups:
        rows = []
        for m in metrics:
            vals = {}
            for e in disp:
                try:
                    vals[e] = m["fn"](e)
                except (ZeroDivisionError, TypeError):
                    vals[e] = None
            if all(v is None for v in vals.values()):
                continue
            row = dict(id=m["id"], label=m["label"], vals=vals, fmt=m["fmt"],
                       note=m["note"])
            rows.append(row)
            by_id[m["id"]] = row
        if rows:
            groups.append({"title": title, "rows": rows})

    headline = [by_id[i] for i in HEADLINES[btype] if i in by_id][:8]

    chart = {
        "labels": [e.isoformat() for e in disp],
        "revenue": [c.revenue_like(e) for e in disp],
        "net_income": [c.v("net_income", e) for e in disp],
        "fcf": [c.v("fcf", e) for e in disp] if btype in ("general", "tech", "reit")
        else [None for _ in disp],
    }
    return {"groups": groups, "headline": headline, "chart": chart, "ctx": c,
            "type": btype, "type_label": BUSINESS_TYPES[btype],
            "ttm": built["mode"] == "quarterly"}


def valuation(company, built, result, price):
    """Valuačné násobky z ceny zadanej používateľom (EDGAR cenu neposkytuje)."""
    if not price or price <= 0:
        return None
    c, btype = result["ctx"], result["type"]
    e = built["display"][-1]
    shares = company.get("shares_out") or c.shares(e)
    if not shares:
        return None
    mcap = price * shares
    items = [("Trhová kapitalizácia (mil.)", mcap, "money"),
             ("Počet akcií (posledná známa hodnota)", shares, "num")]
    eps = c.v("eps_diluted", e)
    ni = c.v("net_income", e)
    pe = price / eps if eps and eps > 0 else (div(mcap, ni) if ni and ni > 0 else None)
    equity = c.v("equity", e)
    divs = c.v("div_paid", e)
    dy = div(divs, mcap)
    if btype in ("bank", "insurance"):
        items += [("P/E", pe, "x"),
                  ("P/B (cena / účtovná hodnota)", div(mcap, equity), "x")]
        if btype == "bank":
            items.append(("P/TBV (cena / tangible book)", div(mcap, c.tangible_equity(e)),
                          "x"))
        items.append(("Dividendový výnos", dy, "pct"))
    elif btype == "reit":
        ev = None
        nd = c.net_debt(e)
        if nd is not None:
            ev = mcap + nd
        ffo = c.ffo(e)
        items += [("P/FFO", div(mcap, ffo), "x"),
                  ("P/B", div(mcap, equity), "x"),
                  ("EV/EBITDA", div(ev, c.ebitda(e)), "x"),
                  ("Dividendový výnos", dy, "pct")]
    else:
        nd = c.net_debt(e)
        ev = mcap + nd if nd is not None else None
        items += [("P/E", pe, "x"),
                  ("P/S (kapitalizácia / tržby)", div(mcap, c.v("revenue", e)), "x"),
                  ("P/B", div(mcap, equity), "x"),
                  ("EV/EBITDA", div(ev, c.ebitda(e)), "x"),
                  ("FCF výnos", div(c.v("fcf", e), mcap), "pct"),
                  ("Dividendový výnos", dy, "pct")]
    items = [(l, v, f) for l, v, f in items if v is not None]
    return {"period": e, "items": items}

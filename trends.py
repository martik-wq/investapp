"""Časové rady (ročné aj kvartálne) pre grafy a tabuľku „Vývoj v čase“."""
from edgar import EdgarError
import statements
from taxonomy import ITEM_BY_KEY


def _div(a, b):
    return None if a is None or b is None or b == 0 else a / b


def _add(a, b):
    return None if a is None or b is None else a + b


def _rev(g, e):
    r = g("revenue", e)
    if r is not None:
        return r
    return _add(g("nii", e), g("nonint_income", e))


def _capex(g, e):
    a, b = g("capex", e), g("capex_sw", e)
    if a is None and b is None:
        return None
    return abs(a or 0) + abs(b or 0)


def _abs(k):
    return lambda g, e: None if g(k, e) is None else abs(g(k, e))


def _common_invest():
    return [
        ("capex_total", "CapEx (investície do majetku a softvéru)", "invest", _capex),
        ("da_inv", "Odpisy a amortizácia", "invest", lambda g, e: g("da", e)),
        ("div_inv", "Vyplatené dividendy", "invest", _abs("div_paid")),
        ("buy_inv", "Spätné odkupy akcií", "invest", _abs("buybacks")),
    ]


def _common_pct():
    return [
        ("capex_pct", "CapEx / tržby", "pct", lambda g, e: _div(_capex(g, e), _rev(g, e))),
    ]


def _defs(btype):
    """(id, popis, skupina, funkcia(g, e)). g(key, e) vráti hodnotu alebo None."""
    ebitda = lambda g, e: _add(g("op_income", e), g("da", e))  # noqa: E731
    ffo = lambda g, e: (None if g("net_income", e) is None or g("da", e) is None
                        else g("net_income", e) + g("da", e) - (g("gain_on_sale", e) or 0))  # noqa: E731
    net_rev = lambda g, e: _add(g("nii", e), g("nonint_income", e))  # noqa: E731
    eps = ("eps_diluted", "EPS (zriedený)", "eps", lambda g, e: g("eps_diluted", e))
    if btype == "bank":
        return [
            ("net_rev", "Výnosy spolu (NII + neúrokové)", "money", net_rev),
            ("nii", "Čistý úrokový výnos", "money", lambda g, e: g("nii", e)),
            ("nonint_income", "Neúrokové výnosy", "money", lambda g, e: g("nonint_income", e)),
            ("nonint_expense", "Neúrokové náklady", "money", lambda g, e: g("nonint_expense", e)),
            ("provision", "Náklady na úverové straty", "money", lambda g, e: g("provision", e)),
            ("net_income", "Čistý zisk", "money", lambda g, e: g("net_income", e)),
            ("loans", "Úvery (netto)", "money", lambda g, e: g("loans", e)),
            ("deposits", "Vklady", "money", lambda g, e: g("deposits", e)),
            ("pretax", "Zisk pred zdanením", "money", lambda g, e: g("pretax", e)),
            ("gm", "Hrubá marža", "pct", lambda g, e: _div(g("gross_profit", e), _rev(g, e))),
            ("om", "Prevádzková marža", "pct", lambda g, e: _div(g("op_income", e), _rev(g, e))),
            ("pm", "Marža pred zdanením", "pct", lambda g, e: _div(g("pretax", e), _rev(g, e))),
            ("nm", "Čistá marža", "pct", lambda g, e: _div(g("net_income", e), _rev(g, e))),
            ("eff", "Efficiency ratio", "pct",
             lambda g, e: _div(g("nonint_expense", e), net_rev(g, e))),
            ("ltd", "Úvery / vklady", "pct", lambda g, e: _div(g("loans", e), g("deposits", e))),
            ("eq_assets", "Vlastné imanie / aktíva", "pct",
             lambda g, e: _div(g("equity", e), g("total_assets", e))),
        ] + _common_pct() + _common_invest() + [eps]
    if btype == "insurance":
        return [
            ("revenue", "Výnosy", "money", lambda g, e: g("revenue", e)),
            ("premiums", "Zaslúžené poistné", "money", lambda g, e: g("premiums", e)),
            ("claims", "Poistné plnenia", "money", lambda g, e: g("claims", e)),
            ("net_income", "Čistý zisk", "money", lambda g, e: g("net_income", e)),
            ("cfo", "Cash flow z prevádzky", "money", lambda g, e: g("cfo", e)),
            ("loss_ratio", "Loss ratio", "pct", lambda g, e: _div(g("claims", e), g("premiums", e))),
            ("combined", "Približný combined ratio", "pct",
             lambda g, e: _div(g("total_benefits_expenses", e), g("premiums", e))),
            ("om", "Prevádzková marža", "pct", lambda g, e: _div(g("op_income", e), g("revenue", e))),
            ("nm", "Čistá marža", "pct", lambda g, e: _div(g("net_income", e), g("revenue", e))),
        ] + _common_pct() + _common_invest() + [eps]
    if btype == "reit":
        return [
            ("revenue", "Tržby", "money", lambda g, e: g("revenue", e)),
            ("op_income", "Prevádzkový zisk", "money", lambda g, e: g("op_income", e)),
            ("ebitda", "EBITDA", "money", ebitda),
            ("ffo", "FFO (zjednodušené)", "money", ffo),
            ("net_income", "Čistý zisk", "money", lambda g, e: g("net_income", e)),
            ("cfo", "Cash flow z prevádzky", "money", lambda g, e: g("cfo", e)),
            ("om", "Prevádzková marža", "pct", lambda g, e: _div(g("op_income", e), g("revenue", e))),
            ("ebitda_m", "EBITDA marža", "pct", lambda g, e: _div(ebitda(g, e), g("revenue", e))),
            ("nm", "Čistá marža", "pct", lambda g, e: _div(g("net_income", e), g("revenue", e))),
        ] + _common_pct() + _common_invest() + [eps]
    return [
        ("revenue", "Tržby", "money", lambda g, e: g("revenue", e)),
        ("gross_profit", "Hrubý zisk", "money", lambda g, e: g("gross_profit", e)),
        ("op_income", "Prevádzkový zisk", "money", lambda g, e: g("op_income", e)),
        ("ebitda", "EBITDA", "money", ebitda),
        ("net_income", "Čistý zisk", "money", lambda g, e: g("net_income", e)),
        ("cfo", "Cash flow z prevádzky", "money", lambda g, e: g("cfo", e)),
        ("fcf", "Voľný cash flow", "money", lambda g, e: g("fcf", e)),
        ("gm", "Hrubá marža", "pct", lambda g, e: _div(g("gross_profit", e), g("revenue", e))),
        ("om", "Prevádzková marža", "pct", lambda g, e: _div(g("op_income", e), g("revenue", e))),
        ("nm", "Čistá marža", "pct", lambda g, e: _div(g("net_income", e), g("revenue", e))),
        ("fcf_m", "FCF marža", "pct", lambda g, e: _div(g("fcf", e), g("revenue", e))),
    ] + _common_pct() + _common_invest() + [eps]


DEFAULTS = {
    "general": {"money": ["revenue", "gross_profit", "net_income"], "pct": ["gm", "om", "nm"],
                "invest": ["capex_total", "da_inv", "buy_inv"]},
    "bank": {"money": ["net_rev", "nii", "net_income"], "pct": ["om", "pm", "nm"],
             "invest": ["capex_total", "da_inv", "buy_inv"]},
    "insurance": {"money": ["revenue", "claims", "net_income"], "pct": ["loss_ratio", "nm"],
                  "invest": ["capex_total", "div_inv", "buy_inv"]},
    "reit": {"money": ["revenue", "ffo", "net_income"], "pct": ["om", "nm"],
             "invest": ["capex_total", "da_inv", "div_inv"]},
}


def _ttm_data(b, n):
    """Z kvartálnych dát urobí TTM (súčet posledných 4 kvartálov) pre tokové položky;
    zostatkové položky (súvaha) a nesčítateľné (počet akcií) berie z posledného kvartálu.
    Vráti (display, data) alebo None, ak nie je dosť nadväzujúcich kvartálov."""
    ends = b["ends"]
    if len(ends) < 5:
        return None
    flow_keys = {k for k, it in ITEM_BY_KEY.items() if it.get("kind") == "flow" and it.get("additive", True)}
    flow_keys |= {"fcf"}
    data = {}
    out_ends = []
    for i in range(3, len(ends)):
        win = ends[i - 3:i + 1]
        gaps = [(win[j + 1] - win[j]).days for j in range(3)]
        if all(60 <= g <= 125 for g in gaps):
            out_ends.append(ends[i])
    for k, series in b["data"].items():
        d = {}
        for i in range(3, len(ends)):
            e = ends[i]
            if e not in out_ends:
                continue
            if k in flow_keys:
                vals = [series.get(x) for x in ends[i - 3:i + 1]]
                d[e] = None if any(v is None for v in vals) else sum(vals)
            else:
                d[e] = series.get(e)
        data[k] = d
    display = out_ends[-n:]
    return display, data


def _label(e, mode):
    if mode == "annual":
        return str(e.year) if e.month == 12 else e.strftime("%m/%Y")
    return f"Q{(e.month - 1) // 3 + 1} {e.year % 100:02d}"  # kvartálne aj TTM


def build_trends(company, btype, start_mode="annual", years=8):
    out = {"currency": company["currency"], "start": start_mode,
           "defaults": DEFAULTS.get(btype, DEFAULTS["general"]) | {"eps": ["eps_diluted"]}}
    if btype == "tech":
        out["defaults"] = DEFAULTS["general"] | {"eps": ["eps_diluted"]}
    for mode, n in (("annual", years), ("quarterly", years * 4), ("ttm", years * 4)):
        try:
            if mode == "ttm":
                b = statements.build(company, "quarterly", n + 3)
                tt = _ttm_data(b, n)
                if tt is None:
                    out[mode] = None
                    continue
                disp, data = tt
            else:
                b = statements.build(company, mode, n)
                disp, data = b["display"], b["data"]
        except EdgarError:
            out[mode] = None
            continue
        g = lambda k, e, d=data: d.get(k, {}).get(e)  # noqa: E731
        series = []
        for sid, label, group, fn in _defs(btype):
            vals = []
            for e in disp:
                try:
                    vals.append(fn(g, e))
                except (TypeError, ZeroDivisionError):
                    vals.append(None)
            if any(v is not None for v in vals):
                series.append({"id": sid, "label": label, "group": group, "values": vals})
        out[mode] = {"labels": [_label(e, mode) for e in disp],
                     "dates": [e.strftime("%d.%m.%Y") for e in disp],
                     "lag": 1 if mode == "annual" else 4, "series": series}
    if not out.get("annual") and not out.get("quarterly"):
        return None
    if not out.get(start_mode):
        out["start"] = "annual" if out.get("annual") else "quarterly"
    return out

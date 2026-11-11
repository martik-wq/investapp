"""Zostavenie výkazov (súvaha, výkaz ziskov a strát, cash flow) z EDGAR dát."""
from edgar import all_item_series, align, determine_periods
from taxonomy import (BALANCE, CASHFLOW, INCOME, ITEM_BY_KEY, DERIVED_LABELS)


def _sub(a, b):
    return None if a is None or b is None else a - b


def _sum_any(*xs):
    vals = [x for x in xs if x is not None]
    return sum(vals) if vals else None


def _total_debt(data, e):
    """Celkový finančný dlh (bez lízingov). Komerčné papiere a krátkodobé pôžičky firmy často vykazujú mimo
    „krátkodobej časti dlhodobého dlhu“ (Apple, Microsoft), preto sa skladá z jednotlivých častí."""
    g = lambda k: data[k].get(e)  # noqa: E731
    short_extra = max(g("cp") or 0, g("stb") or 0)            # CP býva súčasťou krátkodobých pôžičiek: neduplikovať
    if g("ltd_nc") is not None:
        short = g("debt_cur_total") if g("debt_cur_total") is not None else _sum_any(g("ltd_cur"), short_extra or None)
        return g("ltd_nc") + (short or 0)
    if g("ltd_total") is not None:                            # LongTermDebt už obsahuje krátkodobú časť
        return g("ltd_total") + short_extra
    return _sum_any(g("debt_current"), g("debt_lt"))


def build(company, mode="annual", n=8):
    """Vráti dict: ends (vzostupne, vrátane extra období pre priemery),
    display (posledných n), data {kľúč: {end: hodnota}}."""
    extra = 1 if mode == "annual" else 4
    raw = all_item_series(company, mode)
    ends = determine_periods(raw, mode, n + extra)
    data = {k: align(v, ends) for k, v in raw.items()}

    for e in ends:
        g = lambda k: data[k].get(e)  # noqa: E731

        # banky a brokeri: tržby po úrokových nákladoch sú skutočný „top line“, riadok Revenues býva len časť (poplatky)
        rn = g("rev_net_int")
        net_rev = rn is not None and (g("revenue") is None or rn > g("revenue") * 1.05)
        if net_rev:
            data["revenue"][e] = rn
        if g("da") is None and g("dep_only") is not None:      # napr. Microsoft: odpisy a amortizácia zvlášť
            data["da"][e] = g("dep_only") + (g("amort_intang") or 0)
        if g("gross_profit") is None and g("revenue") is not None and not net_rev \
                and g("cost_of_revenue") is not None:
            data["gross_profit"][e] = g("revenue") - g("cost_of_revenue")
        if g("nii") is None and g("int_income") is not None \
                and g("interest_expense") is not None:
            data["nii"][e] = g("int_income") - g("interest_expense")
        if g("total_liabilities") is None and g("total_liab_equity") is not None \
                and g("equity") is not None:
            data["total_liabilities"][e] = g("total_liab_equity") - g("equity")
        if g("net_income") is None and g("cf_net_income") is not None:
            data["net_income"][e] = g("cf_net_income")

    # odvodené riadky
    data["total_debt"] = {}
    data["fcf"] = {}
    for e in ends:
        td = _total_debt(data, e)
        if td is not None:
            data["total_debt"][e] = td
        cfo, capex = data["cfo"].get(e), data["capex"].get(e)
        sw = data["capex_sw"].get(e)
        if cfo is not None and (capex is not None or sw is not None):
            data["fcf"][e] = cfo - abs(capex or 0) - abs(sw or 0)

    display = ends[-n:]
    return {"ends": ends, "display": display, "data": data, "mode": mode,
            "currency": company["currency"]}


def statement_rows(built, items, extra_derived=()):
    """Riadky pre zobrazenie; prázdne riadky (bez hodnôt) sa vynechajú."""
    disp = built["display"]
    rows = []
    for it in items:
        vals = {e: built["data"][it["key"]].get(e) for e in disp}
        if all(v is None for v in vals.values()):
            continue
        rows.append({"key": it["key"], "label": it["label"], "vals": vals,
                     "unit": it["unit"], "bold": it["bold"], "indent": it["indent"]})
    for key in extra_derived:
        vals = {e: built["data"][key].get(e) for e in disp}
        if all(v is None for v in vals.values()):
            continue
        label, bold = DERIVED_LABELS[key]
        rows.append({"key": key, "label": label, "vals": vals, "unit": "cur",
                     "bold": bold, "indent": 0})
    return rows


def all_statements(built):
    return {
        "income": statement_rows(built, INCOME),
        "balance": statement_rows(built, BALANCE, extra_derived=("total_debt",)),
        "cashflow": statement_rows(built, CASHFLOW, extra_derived=("fcf",)),
    }

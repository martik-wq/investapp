"""Tok „od tržieb k zisku“ (Sankey diagram): uzly a prepojenia z výkazov firmy.

Každý uzol má typ: rev (tržby, modrá), profit (zisk, zelená), cost (náklady,
červená). Hodnoty sú v mene výkazov (nie v miliónoch), JS ich pekne naformátuje.
"""
from datetime import timedelta

OTHER_MIN_SHARE = 0.01     # menšie „ostatné“ položky sa nezobrazujú
MAX_STREAMS = 7


def _prev_end(ends, e):
    best = None
    for x in ends:
        d = abs((x - (e - timedelta(days=365))).days)
        if d <= 25 and (best is None or d < best[0]):
            best = (d, x)
    return best[1] if best else None


def _vals(data, e):
    """Základné hodnoty výkazu k dátumu e (alebo None, ak chýba)."""
    if e is None:
        return {}
    g = lambda k: data.get(k, {}).get(e)  # noqa: E731
    abs_ = lambda v: None if v is None else abs(v)  # noqa: E731
    v = {
        "revenue": g("revenue"), "cogs": abs_(g("cost_of_revenue")), "gp": g("gross_profit"),
        "rnd": abs_(g("rnd")), "sga": abs_(g("sga")), "ga": abs_(g("ga")),
        "opex_rep": abs_(g("opex_total")), "oi": g("op_income"), "pretax": g("pretax"),
        "tax": g("tax"), "ni": g("net_income"),
        "int_income": g("int_income"), "int_exp": abs_(g("interest_expense")),
        "nii": g("nii"), "nonint_income": g("nonint_income"),
        "nonint_exp": abs_(g("nonint_expense")), "prov": g("provision"),
    }
    if v["gp"] is None and v["revenue"] is not None and v["cogs"] is not None:
        v["gp"] = v["revenue"] - v["cogs"]
    if v["cogs"] is None and v["revenue"] is not None and v["gp"] is not None:
        v["cogs"] = v["revenue"] - v["gp"]
    return v


def _growth(cur, prev):
    if cur is None or prev is None or prev == 0:
        return None
    if prev < 0:
        return None  # zmena voči zápornej báze nemá zmysel
    return cur / prev - 1


class _Flow:
    def __init__(self):
        self.nodes, self.links, self._ids = [], [], set()

    def node(self, nid, label, col, typ, value, prev=None, sub=None, ord=None):
        if value is None or nid in self._ids:
            return
        self._ids.add(nid)
        self.nodes.append({"id": nid, "label": label, "col": col, "type": typ,
                           "value": value, "prev": prev, "sub": sub,
                           "ord": {"profit": 0, "rev": 1, "cost": 2}[typ] if ord is None else ord})

    def link(self, s, t, v):
        if v is None or v <= 0 or s not in self._ids or t not in self._ids:
            return
        self.links.append({"s": s, "t": t, "v": v})


def _streams(f, streams, revenue, prev_rev):
    """Zdroje tržieb (stĺpec 0). Vráti True, ak sa pridali."""
    if not streams or len(streams) < 2 or not revenue:
        return False
    items = sorted([s for s in streams if s["value"] and s["value"] > 0],
                   key=lambda s: -s["value"])
    if len(items) < 2:
        return False
    total = sum(s["value"] for s in items)
    if abs(total - revenue) > 0.02 * abs(revenue):
        return False
    if len(items) > MAX_STREAMS:
        rest = items[MAX_STREAMS - 1:]
        items = items[:MAX_STREAMS - 1] + [{
            "label": "Ostatné", "value": sum(s["value"] for s in rest),
            "prev": (sum(s["prev"] for s in rest) if all(s.get("prev") for s in rest) else None)}]
    total = sum(s["value"] for s in items)
    if total < revenue * 0.997:           # chýbajúci zvyšok ako „Ostatné“
        items.append({"label": "Ostatné", "value": revenue - total, "prev": None})
        total = revenue
    scale = revenue / total  # drobné rozdiely (zaokrúhľovanie) sa vyrovnajú
    for i, s in enumerate(items):
        nid = f"stream{i}"
        f.node(nid, s["label"], 0, "rev", s["value"] * scale, s.get("prev"))
        f.link(nid, "revenue", s["value"] * scale)
    return True


def _general(cur, prev, streams, labels):
    f = _Flow()
    R = cur["revenue"]
    if R is None or R <= 0:
        return None
    has_streams = bool(streams)
    c0 = 1 if has_streams else 0
    # tržby
    f.node("revenue", "Tržby", c0, "rev", R, prev.get("revenue"))
    if has_streams and not _streams(f, streams, R, prev.get("revenue")):
        # streams nesedia -> prečíslovať bez nich
        f = _Flow()
        has_streams, c0 = False, 0
        f.node("revenue", "Tržby", 0, "rev", R, prev.get("revenue"))
    OI, NI, TAX = cur["oi"], cur["ni"], cur["tax"]
    GP, COGS = cur["gp"], cur["cogs"]
    col = c0 + 1
    opex_src, opex_val = "revenue", None
    if GP is not None and COGS is not None and COGS > 0 and GP > -1e-9:
        f.node("gp", "Hrubý zisk", col, "profit", GP, prev.get("gp"),
               sub=f"marža {GP / R * 100:.0f} %")
        f.node("cogs", "Náklady na tržby", col, "cost", COGS, prev.get("cogs"))
        f.link("revenue", "gp", GP)
        f.link("revenue", "cogs", COGS)
        opex_src = "gp"
        col += 1
        base = GP
    else:
        base = R
    if OI is None:
        return f if len(f.nodes) > 2 else None
    opex = base - OI
    prev_base = (prev.get("gp") if opex_src == "gp" else prev.get("revenue"))
    prev_opex = (prev_base - prev["oi"]) if prev_base is not None and prev.get("oi") is not None \
        else None
    if OI > 0:
        f.node("oi", "Prevádzkový zisk", col, "profit", OI, prev.get("oi"),
               sub=f"marža {OI / R * 100:.0f} %")
    else:
        f.node("loss", "Prevádzková strata", col - 1, "cost", -OI,
               (-prev["oi"] if prev.get("oi") is not None and prev["oi"] < 0 else None),
               sub="kryje sa z iných zdrojov", ord=1)
    if opex > 0:
        f.node("opex", "Prevádzkové náklady", col, "cost", opex, prev_opex)
    if OI > 0:
        f.link(opex_src, "oi", OI)
        f.link(opex_src, "opex", opex)
    else:
        f.link(opex_src, "opex", base)
        f.link("loss", "opex", -OI)
    col += 1
    # členenie prevádzkových nákladov
    comps = [("rnd", "Výskum a vývoj")]
    comps.append(("sga", "Predaj a administratíva") if cur["sga"] else
                 ("ga", "Správna réžia"))
    used = 0
    comp_nodes = []
    for key, label in comps:
        v = cur[key]
        if v and v > 0:
            comp_nodes.append((key, label, v))
            used += v
    if opex > 0 and comp_nodes:
        rest = opex - used
        if rest > OTHER_MIN_SHARE * opex:
            comp_nodes.append(("opex_other", "Ostatné prevádzkové náklady", rest))
        elif rest < -0.02 * opex:
            comp_nodes = []  # nedáva zmysel
    # čo sa deje s prevádzkovým ziskom
    tax = TAX if TAX is not None else 0.0
    ni_flow = max(NI, 0) if NI is not None else None
    if OI > 0 and ni_flow is not None:
        other_income = 0.0
        if tax < 0:
            other_income += -tax
            tax = 0.0
        other_net = OI - tax - ni_flow          # > 0 náklady, < 0 výnosy
        if other_net < 0:
            other_income += -other_net
            other_net = 0.0
        f.node("ni", "Čistý zisk", col, "profit", ni_flow if ni_flow > 0 else None,
               prev.get("ni"), sub=(f"marža {ni_flow / R * 100:.0f} %" if ni_flow > 0 else None))
        if other_net > OTHER_MIN_SHARE * OI:
            f.node("other_cost", "Ostatné náklady (netto)", col, "cost", other_net)
        else:
            tax += other_net  # drobnosť pripočítať k daniam, aby tok sedel
            other_net = 0.0
        if tax > 0:
            f.node("tax", "Dane", col, "cost", tax, prev.get("tax"))
        t1 = min(tax, OI)
        f.link("oi", "ni", OI - t1 - other_net if ni_flow else 0)
        f.link("oi", "other_cost", other_net)
        f.link("oi", "tax", t1)
        if other_income > 0:
            f.node("other_inc", "Ostatné výnosy (netto)", col - 1, "profit", other_income, ord=1)
            f.link("other_inc", "tax", tax - t1)
            f.link("other_inc", "ni", other_income - (tax - t1))
        # prepočítať: ak oi->ni vyšlo záporné, link sa neprida (v <= 0)
    # členenie prevádzkových nákladov
    for key, label, v in comp_nodes:
        f.node(key, label, col, "cost", v, prev.get(key) if key in prev else None,
               sub=f"{v / R * 100:.0f} % tržieb")
        f.link("opex", key, v)
    return f


def _bank(cur, prev):
    f = _Flow()
    ii, ie = cur["int_income"], cur["int_exp"]
    ni_inc = cur["nonint_income"] or 0.0
    if ii is None or ie is None:
        return None
    rev = ii + ni_inc
    if rev <= 0:
        return None
    f.node("int_income", "Úrokové výnosy", 0, "rev", ii, prev.get("int_income"))
    if ni_inc > 0:
        f.node("nonint_income", "Neúrokové výnosy", 0, "rev", ni_inc, prev.get("nonint_income"))
    f.node("revenue", "Výnosy spolu", 1, "rev", rev,
           (prev["int_income"] + (prev.get("nonint_income") or 0)) if prev.get("int_income") else None)
    f.link("int_income", "revenue", ii)
    f.link("nonint_income", "revenue", ni_inc)
    net_rev = rev - ie
    f.node("net_rev", "Čisté výnosy", 2, "profit", net_rev,
           ((prev["int_income"] + (prev.get("nonint_income") or 0) - prev["int_exp"])
            if prev.get("int_income") and prev.get("int_exp") else None),
           sub=f"{net_rev / rev * 100:.0f} % výnosov")
    f.node("int_exp", "Úrokové náklady", 2, "cost", ie, prev.get("int_exp"))
    f.link("revenue", "net_rev", net_rev)
    f.link("revenue", "int_exp", ie)
    prov, nonexp, pretax = cur["prov"], cur["nonint_exp"], cur["pretax"]
    prov = max(prov, 0) if prov is not None else 0.0
    if pretax is None:
        pretax = net_rev - prov - (nonexp or 0)
    f.node("pretax", "Zisk pred zdanením", 3, "profit", pretax if pretax > 0 else None,
           prev.get("pretax"), sub=(f"marža {pretax / rev * 100:.0f} %" if pretax > 0 else None))
    if prov > 0:
        f.node("prov", "Rezervy na úverové straty", 3, "cost", prov, prev.get("prov"))
    if nonexp:
        f.node("nonexp", "Neúrokové náklady", 3, "cost", nonexp, prev.get("nonint_exp"))
    other = net_rev - prov - (nonexp or 0) - max(pretax, 0)
    if other > OTHER_MIN_SHARE * net_rev:
        f.node("other_cost", "Ostatné náklady (netto)", 3, "cost", other)
    f.link("net_rev", "pretax", max(pretax, 0))
    f.link("net_rev", "prov", prov)
    f.link("net_rev", "nonexp", nonexp)
    f.link("net_rev", "other_cost", other if other > OTHER_MIN_SHARE * net_rev else 0)
    tax, ni = cur["tax"], cur["ni"]
    if pretax > 0 and ni is not None:
        tax = max(tax if tax is not None else pretax - ni, 0)
        nif = max(ni, 0)
        f.node("ni", "Čistý zisk", 4, "profit", nif if nif > 0 else None, prev.get("ni"),
               sub=(f"marža {nif / rev * 100:.0f} %" if nif > 0 else None))
        if tax > 0:
            f.node("tax", "Dane", 4, "cost", tax, prev.get("tax"))
        f.link("pretax", "ni", min(nif, pretax))
        f.link("pretax", "tax", min(tax, pretax))
    return f


def _tiles(cur, prev):
    tiles = []

    def add(label, g, tone_good=True):
        if g is None:
            return
        tiles.append({"label": label, "value": g, "good": g >= 0 if tone_good else g <= 0})

    add("Rast tržieb", _growth(cur["revenue"], prev.get("revenue")))
    add("Rast čistého zisku", _growth(cur["ni"], prev.get("ni")))
    oi_g = _growth(cur["oi"], prev.get("oi"))
    if oi_g is not None:
        add("Zmena prevádzkového zisku", oi_g)
    else:
        add("Zmena zisku pred zdanením", _growth(cur["pretax"], prev.get("pretax")))
    return tiles[:3]


def build_flow(built, end, btype, streams=None):
    """Údaje pre Sankey diagram za obdobie končiace `end`. streams = zoznam
    {'label','value','prev'} s členením tržieb (voliteľné)."""
    data = built["data"]
    ends = built["ends"]
    cur = _vals(data, end)
    pe = _prev_end(ends, end)
    prev = _vals(data, pe)
    if btype == "bank" and cur.get("int_income") is not None:
        cur_b = dict(cur)
        cur_b["revenue"] = (cur["int_income"] or 0) + (cur["nonint_income"] or 0)
        prev_b = dict(prev)
        if prev.get("int_income") is not None:
            prev_b["revenue"] = (prev["int_income"] or 0) + (prev.get("nonint_income") or 0)
        f = _bank(cur, prev)
        cur, prev = cur_b, prev_b
    else:
        if cur.get("revenue") is None:
            return None
        f = _general(cur, prev, streams, None)
    if f is None or len(f.nodes) < 3 or not f.links:
        return None
    # medziročná zmena pre uzly bez uloženej predchádzajúcej hodnoty
    for n in f.nodes:
        n["yoy"] = _growth(n["value"], n.get("prev"))
    note = []
    if cur["ni"] is not None and cur["ni"] <= 0:
        note.append("Čistý zisk je záporný (strata), v diagrame preto nie je uzol Čistý zisk.")
    if cur["oi"] is not None and cur["oi"] <= 0:
        note.append("Prevádzkový výsledok je strata.")
    return {"nodes": f.nodes, "links": f.links, "tiles": _tiles(cur, prev),
            "end": end.strftime("%d.%m.%Y"), "currency": built["currency"],
            "has_prev": pe is not None, "note": " ".join(note),
            "net_income": cur["ni"]}

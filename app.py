"""Investičná aplikácia – výkazy a metriky verejne obchodovaných firiem zo SEC EDGAR.

Spustenie:  python app.py   a potom otvor http://127.0.0.1:5000
"""
import csv
import io
from datetime import date

from flask import Flask, Response, abort, redirect, render_template, request, url_for

import edgar
import filings
import flow
import metrics
import prices
import trends
import statements
from taxonomy import BUSINESS_TYPES

app = Flask(__name__)


# ----------------------------------------------------------------- formátovanie
def fmt_value(v, fmt, scale_note=None):
    if v is None:
        return "–"
    if fmt == "money":
        m = v / 1e6
        return f"{m:,.0f}" if abs(m) >= 1000 else f"{m:,.1f}"
    if fmt == "num":
        return f"{v / 1e6:,.1f} mil."
    if fmt == "pct":
        return f"{v * 100:.1f} %"
    if fmt == "x":
        return f"{v:.2f}×"
    if fmt == "days":
        return f"{v:.0f} dní"
    if fmt == "eps":
        return f"{v:,.2f}"
    if fmt == "big":
        a = abs(v)
        if a >= 1e9:
            return f"{v / 1e9:,.1f} mld."
        if a >= 1e6:
            return f"{v / 1e6:,.0f} mil."
        return f"{v:,.0f}"
    return f"{v}"


def unit_to_fmt(unit):
    return {"cur": "money", "shares": "num", "eps": "eps"}.get(unit, "money")


app.jinja_env.filters["fmt"] = fmt_value
app.jinja_env.globals["unit_to_fmt"] = unit_to_fmt


def parse_price(s):
    try:
        return float(str(s).replace(",", ".")) if s else None
    except ValueError:
        return None


# --------------------------------------------------------------------- stránky
SECTIONS = [
    ("overview", "Úvod", "🏠"),
    ("statements", "Výkazy", "📑"),
    ("charts", "Grafy", "📈"),
    ("fundamental", "Fundamentálna analýza", "🔎"),
    ("technical", "Technická analýza", "📉"),
]
SECTION_KEYS = {k for k, _, _ in SECTIONS}
YEARS_OPTIONS = (5, 8, 10, 15, 20, 30)  # 30 = všetko dostupné

DEMO_PROFILES = {
    "DEMOCO": {
        "summary": "Fiktívna softvérová firma slúžiaca na testovanie aplikácie. Predáva predplatné "
                   "na cloudový softvér pre firmy, väčšinu tržieb tvoria opakované platby. "
                   "Údaje sú vymyslené a nepredstavujú skutočnú spoločnosť.",
        "sector": "Technology", "industry": "Software", "website": None, "employees": 4200,
        "country": "Fiktívny štát", "city": "Demo City",
        "officers": [{"name": "Jana Ukážková", "title": "CEO", "age": 51},
                     {"name": "Peter Testovací", "title": "CFO", "age": 47}],
        "market_cap": None, "dividend_yield": None, "beta": None, "pe_trailing": None},
    "DEMOBANK": {
        "summary": "Fiktívna regionálna banka na testovanie aplikácie. Poskytuje úvery a "
                   "prijíma vklady od obyvateľov a firiem. Údaje sú vymyslené.",
        "sector": "Financial Services", "industry": "Banks - Regional", "website": None,
        "employees": 9800, "country": "Fiktívny štát", "city": "Demo City",
        "officers": [{"name": "Marta Vzorová", "title": "CEO", "age": 58}],
        "market_cap": None, "dividend_yield": None, "beta": None, "pe_trailing": None},
}
DEMO_QUOTE = {"price": 50.0, "currency": "USD", "time": "fiktívna cena", "name": "Demo",
              "exchange": "DEMO", "high52": 58.0, "low52": 38.0, "prev_close": 49.4,
              "change": 0.6, "change_pct": 0.6 / 49.4}


def parse_price(s):
    try:
        return float(str(s).replace(",", ".")) if s else None
    except ValueError:
        return None


def parse_years(v):
    try:
        y = int(v)
    except (TypeError, ValueError):
        return 8
    return y if y in YEARS_OPTIONS else 8


def _params():
    mode = request.args.get("mode", "annual")
    mode = mode if mode in ("annual", "quarterly") else "annual"
    typ = request.args.get("type", "auto")
    typ = typ if typ in BUSINESS_TYPES else "auto"
    return {"mode": mode, "typ": typ, "price_raw": request.args.get("price", ""),
            "years": parse_years(request.args.get("years")),
            "detail": request.args.get("detail") == "1"}


def _qs(p):
    """Parametre, ktoré sa prenášajú medzi záložkami."""
    q = {}
    if p["mode"] != "annual":
        q["mode"] = p["mode"]
    if p["years"] != 8:
        q["years"] = p["years"]
    if p["typ"] != "auto":
        q["type"] = p["typ"]
    if p["price_raw"]:
        q["price"] = p["price_raw"]
    if p["detail"]:
        q["detail"] = "1"
    return q


def _flow_streams(comp, built, end, btype, mode):
    """Členenie tržieb z podaní (alebo None). Chyby nikdy nezhodia stránku."""
    if btype == "bank":
        return None
    rev = built["data"].get("revenue", {})
    total = rev.get(end)
    if not total:
        return None
    try:
        if mode == "annual":
            return filings.revenue_breakdown(comp, end, 12, total)
        qends = [e for e in built["ends"] if e <= end][-4:]
        fy = nine = None
        if len(qends) == 4 and 250 <= (qends[-1] - qends[0]).days <= 290 \
                and all(rev.get(e) for e in qends):
            fy = sum(rev[e] for e in qends)
            nine = sum(rev[e] for e in qends[:3])
        return filings.revenue_breakdown(comp, end, 3, total, fy, nine)
    except Exception:  # noqa: BLE001 - členenie je doplnok, nie nutnosť
        return None


def _flow_costs(comp, built, end, btype, mode):
    """Presné položky prevádzkových nákladov a nákladov na tržby z výkazu firmy."""
    if btype == "bank":
        return None, None
    data = built["data"]
    try:
        opex, cogs = flow.cost_targets(data, end)
        if mode == "annual":
            return (filings.cost_components(comp, end, 12, opex) if opex else None,
                    filings.cost_components(comp, end, 12, cogs) if cogs else None)
        qends = [e for e in built["ends"] if e <= end][-4:]
        fy_o = nine_o = fy_c = nine_c = None
        if len(qends) == 4 and 250 <= (qends[-1] - qends[0]).days <= 290:
            t = [flow.cost_targets(data, e) for e in qends]
            if all(x[0] is not None for x in t):
                fy_o, nine_o = sum(x[0] for x in t), sum(x[0] for x in t[:3])
            if all(x[1] for x in t):
                fy_c, nine_c = sum(x[1] for x in t), sum(x[1] for x in t[:3])
        return (filings.cost_components(comp, end, 3, opex, fy_o, nine_o) if opex else None,
                filings.cost_components(comp, end, 3, cogs, fy_c, nine_c) if cogs else None)
    except Exception:  # noqa: BLE001 - doplnok, nie nutnosť
        return None, None


def _flow_options(built, mode):
    out = []
    for e in reversed(built["display"]):
        lab = (f"Rok {e.year}" if mode == "annual" else
               f"Q{(e.month - 1) // 3 + 1} {e.year}") + f" ({e.strftime('%d.%m.%Y')})"
        out.append((e.isoformat(), lab))
    return out


def build_context(ticker, section):
    p = _params()
    match, _ = edgar.find_company(ticker)
    if not match:
        raise edgar.EdgarError(f"Ticker „{ticker}“ sa nenašiel.")
    ctx = {"ticker": match[0], "name": match[2], "section": section, "mode": p["mode"],
           "typ": p["typ"], "price": p["price_raw"], "years": p["years"], "detail": p["detail"],
           "years_options": YEARS_OPTIONS, "types": BUSINESS_TYPES, "sections": SECTIONS,
           "qs": _qs(p), "today": date.today()}
    if section in ("fundamental", "technical"):
        return ctx

    comp = edgar.load_company(*match)
    is_demo = comp["is_demo"]
    quote = DEMO_QUOTE if is_demo else prices.get_price(match[0])
    n = p["years"] if p["mode"] == "annual" else p["years"] * 4
    built = statements.build(comp, mode=p["mode"], n=n)
    user_price = parse_price(p["price_raw"])
    price = user_price
    quote = dict(quote) if quote else None
    if quote and quote["currency"] != built["currency"]:
        quote["mismatch"] = True
    elif price is None and quote:
        price = quote["price"]
    auto_type = metrics.detect_type(comp, built)
    btype = p["typ"] if p["typ"] != "auto" else auto_type
    result = metrics.compute(comp, built, btype)
    val = metrics.valuation(comp, built, result, price)
    ctx.update(comp=comp, built=built, auto_type=auto_type, btype=btype, result=result,
               val=val, quote=quote, price_used=price, user_price=user_price,
               n_req=0 if p["years"] == 30 else n, name=comp["name"])
    if section == "overview":
        profile = DEMO_PROFILES.get(match[0]) if is_demo else prices.get_profile(match[0])
        ctx["profile"] = profile
    elif section == "statements":
        ctx["stm"] = statements.all_statements(built)
        if p["detail"]:
            try:
                ctx["det"] = filings.get_detailed(comp, p["mode"], p["years"])
            except edgar.EdgarError as e:
                ctx["det_error"] = str(e)
    elif section == "charts":
        ctx["trend"] = trends.build_trends(comp, btype, p["mode"], min(p["years"], 20))
        opts = _flow_options(built, p["mode"])
        chosen = request.args.get("flow", "")
        flow_end = next((e for e in built["display"] if e.isoformat() == chosen),
                        built["display"][-1])
        streams = _flow_streams(comp, built, flow_end, btype, p["mode"])
        opex_items, cogs_items = _flow_costs(comp, built, flow_end, btype, p["mode"])
        fl = flow.build_flow(built, flow_end, btype, streams, opex_items, cogs_items)
        if fl:
            fl["has_streams"] = any(n["id"].startswith("stream") or n["id"] == "int_income"
                                    for n in fl["nodes"])
        ctx.update(flow=fl, flow_opts=opts, flow_end=flow_end.isoformat())
    return ctx


@app.route("/")
def index():
    return render_template("index.html", types=BUSINESS_TYPES, section=None)


@app.route("/search")
def search():
    q = request.args.get("q", "")
    try:
        match, cands = edgar.find_company(q)
    except edgar.EdgarError as e:
        return render_template("error.html", message=str(e), section=None), 400
    if match:
        return redirect(url_for("section_view", ticker=match[0], section="overview"))
    return render_template("search.html", q=q, cands=cands, section=None)


@app.route("/company/<ticker>", defaults={"section": "overview"})
@app.route("/company/<ticker>/<section>")
def section_view(ticker, section):
    if section not in SECTION_KEYS:
        abort(404)
    try:
        ctx = build_context(ticker.upper(), section)
    except edgar.EdgarError as e:
        return render_template("error.html", message=str(e), section=None), 400
    return render_template(f"{section}.html", **ctx)


@app.route("/company/<ticker>/export.csv")
def export(ticker):
    try:
        ctx = build_context(ticker.upper(), "statements")
    except edgar.EdgarError as e:
        return Response(str(e), status=400)
    comp, built, result, stm = ctx["comp"], ctx["built"], ctx["result"], ctx["stm"]
    out = io.StringIO()
    w = csv.writer(out, delimiter=";")
    disp = list(reversed(built["display"]))
    w.writerow([comp["name"], comp["ticker"], f"mena: {built['currency']}",
                "hodnoty v jednotkách meny (nie v miliónoch)"])
    names = {"income": "VÝKAZ ZISKOV A STRÁT", "balance": "SÚVAHA", "cashflow": "CASH FLOW"}
    for key, title in names.items():
        w.writerow([])
        w.writerow([title] + [d.isoformat() for d in disp])
        for r in stm[key]:
            w.writerow([r["label"]] + ["" if r["vals"][d] is None else r["vals"][d]
                                       for d in disp])
    w.writerow([])
    w.writerow([f"METRIKY ({result['type_label']})"] + [d.isoformat() for d in disp])
    for g in result["groups"]:
        for r in g["rows"]:
            w.writerow([r["label"]] + ["" if r["vals"][d] is None else r["vals"][d]
                                       for d in disp])
    data = "\ufeff" + out.getvalue()
    return Response(data, mimetype="text/csv; charset=utf-8", headers={
        "Content-Disposition": f"attachment; filename={comp['ticker']}_{ctx['mode']}.csv"})


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)

"""Investičná aplikácia – výkazy a metriky verejne obchodovaných firiem zo SEC EDGAR.

Spustenie:  python app.py   a potom otvor http://127.0.0.1:5000
"""
import csv
import io
import os
import re
from datetime import date, timedelta

from flask import (Flask, Response, abort, flash, jsonify, redirect, render_template, request,
                   url_for)

import edgar
import filings
import flow
import metrics
import perf
import portfolio
import prices
import trends
import updater
import statements
from taxonomy import BUSINESS_TYPES

app = Flask(__name__)
app.secret_key = os.urandom(16).hex()      # len na hlásenia po importe
app.config["MAX_CONTENT_LENGTH"] = 25 * 1024 * 1024


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
    if fmt == "amt":
        return f"{v:,.2f}"
    if fmt == "sh":
        return f"{v:,.6f}".rstrip("0").rstrip(".")
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


def signed_pct(v, digits=1):
    if v is None:
        return "–"
    return f"{'+' if v >= 0 else '−'}{abs(v) * 100:.{digits}f} %".replace(".", ",")


def signed_amt(v):
    if v is None:
        return "–"
    return f"{'+' if v >= 0 else '−'}{abs(v):,.2f}"


app.jinja_env.filters["fmt"] = fmt_value
app.jinja_env.filters["spct"] = signed_pct
def signed_pp(v):
    if v is None:
        return "–"
    return f"{'+' if v >= 0 else '−'}{abs(v) * 100:.1f}".replace(".", ",") + " p. b."


def plain_pct(v):
    return "–" if v is None else f"{v * 100:.1f} %".replace(".", ",")


app.jinja_env.filters["pct"] = plain_pct
app.jinja_env.filters["samt"] = signed_amt
app.jinja_env.filters["spp"] = signed_pp
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
        base = {k: v for k, v in ctx["qs"].items() if k != "mode"}
        ctx.update(flow=fl, flow_opts=opts, flow_end=flow_end.isoformat(),
                   mode_links={
                       "annual": url_for("section_view", ticker=match[0], section="charts", **base),
                       "quarterly": url_for("section_view", ticker=match[0], section="charts",
                                            **dict(base, mode="quarterly"))})
    return ctx


# ------------------------------------------------------------------ portfólio
DEMO_QUOTES = {   # ukážkové portfólio funguje aj bez internetu
    "DEMOCO": {"price": 50.0, "currency": "USD", "change_pct": 0.012},
    "DEMOBANK": {"price": 50.0, "currency": "USD", "change_pct": -0.004},
    "DEMOEU": {"price": 110.0, "currency": "EUR", "change_pct": 0.003},
    "DEMOUK": {"price": 2300.0, "currency": "GBp", "change_pct": 0.006},   # pence
    "DEMOSPIN": {"price": 20.0, "currency": "EUR", "change_pct": 0.0},
}
DEMO_SYMBOLS = set(DEMO_QUOTES)
DEMO_FX = {("USD", "EUR"): 0.92, ("EUR", "USD"): 1 / 0.92, ("GBP", "EUR"): 1.15,
           ("EUR", "GBP"): 1 / 1.15, ("GBP", "USD"): 1.25, ("USD", "GBP"): 0.8}
US_SYMBOL = re.compile(r"^[A-Z]{1,5}(-[AB])?$")


def _pf_symbol_fn(store):
    def fn(isin, ticker):
        if isin in store["symbols"]:
            return store["symbols"][isin]
        if ticker in DEMO_SYMBOLS:
            return ticker
        sym = prices.search_symbol(isin) if isin else None
        return sym or ticker or None
    return fn


def _pf_quote(sym):
    if sym in DEMO_QUOTES:
        return dict(DEMO_QUOTES[sym])
    return prices.get_price(sym)


def _pf_fx_factory(demo):
    def fx(frm, to):
        if demo:
            return DEMO_FX.get((frm, to))
        q = prices.get_price(f"{frm}{to}=X")
        if q:
            return q["price"]
        inv = prices.get_price(f"{to}{frm}=X")
        return 1 / inv["price"] if inv and inv["price"] else None
    return fx


def _read_upload(f):
    raw = f.read()
    for enc in ("utf-8-sig", "utf-8", "cp1250", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


@app.route("/portfolio")
def portfolio_view():
    store = portfolio.load_store()
    txns = list(store["txns"].values())
    ctx = {"page": "portfolio", "ticker": None, "section": None, "files": store["files"]}
    if not txns:
        return render_template("portfolio.html", has_data=False, **ctx)
    data = portfolio.build_positions(txns)
    currencies = sorted(set(data["currencies"]) | {"EUR", "USD"})
    base = request.args.get("base", "").upper()
    base = base if base in currencies else (store.get("base") if store.get("base") in currencies
                                            else portfolio.default_base(txns))
    demo = any(t.get("ticker") in DEMO_SYMBOLS for t in txns)
    conv = portfolio.Converter(_pf_fx_factory(demo))
    ctx["demo"] = demo
    valued = portfolio.value_positions(data["open"], base, _pf_symbol_fn(store), _pf_quote, conv)
    summary = portfolio.summarize(data, valued, base, conv)
    priced = sorted([p for p in valued if p.get("value_b") is not None],
                    key=lambda p: -p["value_b"])
    alloc = [{"label": p["ticker"] or p["isin"], "name": p["name"], "pct": p["weight"],
              "value": p["value_b"]} for p in priced[:12]]
    if len(priced) > 12:
        rest = priced[12:]
        alloc.append({"label": "Ostatné", "name": f"{len(rest)} ďalších",
                      "value": sum(p["value_b"] for p in rest),
                      "pct": sum(p["weight"] for p in rest)})
    recent = sorted(txns, key=lambda t: t["time"], reverse=True)[:400]
    closed = sorted(data["closed"], key=lambda p: p["last"], reverse=True)
    return render_template(
        "portfolio.html", has_data=True, base=base, currencies=currencies, data=data,
        positions=valued, summary=summary, alloc=alloc, txns=recent, n_txn=len(txns),
        us_symbol=US_SYMBOL, closed=closed, **ctx)


# --------------------------------------------------- výkonnosť portfólia a indexy
BENCHMARKS = [
    ("^GSPC", "S&P 500", "cenový index"),
    ("^SP500TR", "S&P 500 s dividendami", "celkový výnos"),
    ("^NDX", "Nasdaq-100", "cenový index"),
    ("^IXIC", "Nasdaq Composite", "cenový index"),
    ("URTH", "MSCI World (ETF URTH)", "ETF vrátane dividend"),
    ("^STOXX50E", "Euro Stoxx 50", "cenový index"),
    ("^GDAXI", "DAX", "výkonnostný index"),
]
BENCH_LABEL = {b[0]: b[1] for b in BENCHMARKS}
DEFAULT_BENCH = ["^GSPC", "^NDX"]
BENCH_COLORS = ["#334155", "#94a3b8", "#b45309", "#64748b", "#d99a2b", "#7c2d12", "#475569", "#cbd5e1"]


def _demo_history(symbol, start, end=None):
    """Vymyslené denné ceny pre ukážkové portfólio (deterministické, bez internetu)."""
    import random
    from datetime import timedelta
    end = end or date.today()
    if symbol.endswith("=X") and len(symbol) >= 8:      # kurz, napr. USDEUR=X
        rate = DEMO_FX.get((symbol[:3], symbol[3:6]))
        ccy = symbol[3:6]
        if rate is None:
            return None
        base_p, mu, sig = rate, 0.0, 0.0
    else:
        rnd_seed = sum(ord(c) * (i + 1) for i, c in enumerate(symbol))
        q = DEMO_QUOTES.get(symbol)
        ccy = q["currency"] if q else ("EUR" if symbol in ("^STOXX50E", "^GDAXI") else "USD")
        anchors = {"DEMOCO": 40.0, "DEMOBANK": 30.0, "DEMOEU": 100.0, "DEMOUK": 2000.0,
                   "DEMOSPIN": 20.0, "DEMOOLD": 30.0}
        base_p = anchors.get(symbol) or {"^GSPC": 5000.0, "^SP500TR": 9000.0, "^NDX": 17000.0,
                                         "^IXIC": 16000.0, "URTH": 130.0}.get(symbol, 4000.0)
        mu, sig = (0.0004, 0.012) if q else (0.0003, 0.008)
    rnd = random.Random(rnd_seed if not symbol.endswith("=X") else 1)
    dates, close, p = [], [], base_p
    d = start
    while d <= end:
        if d.weekday() < 5:
            p *= 1 + mu + sig * rnd.gauss(0, 1)
            dates.append(d.isoformat())
            close.append(round(p, 4))
        d += timedelta(days=1)
    return {"dates": dates, "close": close, "adj": close, "currency": ccy}


def _parse_dates(s, default):
    try:
        return date.fromisoformat(s)
    except (TypeError, ValueError):
        return default


def _whatif_build(data, isins, sym_of, results, rates, base, benches, sel, rb, wi_rows, wi_hist,
                  r_start, r_end, rf):
    """Simulácia „čo keby“: aktuálne pozície v dnešných váhach + pridané tituly (podiel z celku)."""
    out = {"ok": False, "notes": [], "rows": wi_rows}
    bid = rb if rb in benches else next((b for b in sel if b in benches), None)
    if bid is None:
        bid = next(iter(benches), None)
    if bid is None:
        out["error"] = "Chýba história indexu na porovnanie."
        return out
    if not wi_rows:
        out["error"] = "Zadaj aspoň jeden titul (Yahoo symbol) a jeho váhu v %."
        return out
    if sum(w for _s, w in wi_rows) > 100:
        out["error"] = "Súčet váh pridaných titulov presahuje 100 %."
        return out
    missing = [s_ for s_, _w in wi_rows if s_ not in wi_hist]
    if missing:
        out["error"] = "Nenašiel som históriu cien pre: " + ", ".join(missing) + " (skontroluj Yahoo symbol)."
        return out

    def in_base(series, ccy):
        days = [date.fromordinal(o) for o in series.o]
        vals = []
        for d, v in zip(days, series.v):
            r = rates.rate(ccy, base, d)
            vals.append(v * r if r is not None else None)
        return perf.Series(days, vals)

    held, wt, skipped = {}, {}, []
    for p in data["open"]:
        h = results.get(("p", p["isin"]))
        s_, c_ = perf.to_series(h, "adj") if h else (None, None)
        if not s_:
            skipped.append(p["ticker"] or p["isin"])
            continue
        ser = in_base(s_, c_ or p["ccy"])
        px = ser.at(r_end)
        if px is None or p["shares"] <= 0:
            skipped.append(p["ticker"] or p["isin"])
            continue
        held[p["isin"]] = ser
        wt[p["isin"]] = p["shares"] * px
    if not held:
        out["error"] = "Nemám ceny aktuálnych pozícií na porovnanie."
        return out
    adds = {s_: in_base(*wi_hist[s_]) for s_, _w in wi_rows}
    bench = benches[bid]
    firsts = [max(x.first for x in list(held.values()) + list(adds.values()) + [bench])]
    start = max(r_start, firsts[0])
    days = [date.fromordinal(o) for o in bench.o if start < date.fromordinal(o) <= r_end]
    days = [d for d in days if all(x.at(d) for x in list(held.values()) + list(adds.values()))]
    if len(days) < perf.MIN_OBS + 1:
        out["error"] = (f"Spoločná história je príliš krátka ({max(0, len(days) - 1)} dní, treba aspoň "
                        f"{perf.MIN_OBS}). Vyber dlhšie obdobie alebo titul s dlhšou históriou.")
        return out

    def rets(ser):
        return [ser.at(days[i]) / ser.at(days[i - 1]) - 1.0 for i in range(1, len(days))]

    res = perf.whatif({k: rets(v) for k, v in held.items()}, wt, {k: rets(v) for k, v in adds.items()},
                      {s_: w / 100.0 for s_, w in wi_rows}, rets(bench), rf)
    res.update(ok=True, notes=out["notes"], rows=wi_rows, bench=bid, start=days[0], end=days[-1],
               weights={k: wt[k] / sum(wt.values()) for k in wt}, skipped=skipped)
    if skipped:
        res["notes"].append("Bez cien (vynechané zo simulácie): " + ", ".join(skipped) + ".")
    if days[0] > r_start + timedelta(days=10):
        res["notes"].append(f"Spoločná história začína až {days[0].strftime('%d.%m.%Y')} (kratšie obdobie ako vybrané).")
    return res


@app.route("/portfolio/performance")
def portfolio_performance():
    from concurrent.futures import ThreadPoolExecutor
    from datetime import timedelta
    store = portfolio.load_store()
    txns = list(store["txns"].values())
    if not txns:
        return redirect(url_for("portfolio_view"))
    data = portfolio.build_positions(txns)
    currencies = sorted(set(data["currencies"]) | {"EUR", "USD"})
    base = request.args.get("base", "").upper()
    base = base if base in currencies else (store.get("base") if store.get("base") in currencies
                                            else portfolio.default_base(txns))
    demo = any(t.get("ticker") in DEMO_SYMBOLS for t in txns)
    hist_fn = _demo_history if demo else prices.get_history
    sel = [b for b in request.args.getlist("bm") if b]
    custom = request.args.get("custom", "").strip().upper()
    if custom and custom not in sel:
        sel.append(custom)
    if not sel and "bm" not in request.args:
        sel = list(DEFAULT_BENCH)
    rb = request.args.get("rb", "").strip()
    rb = rb if rb and (rb in BENCH_LABEL or rb == custom) else ""
    fetch_list = list(sel) + ([rb] if rb and rb not in sel else [])
    trades = [t for t in txns if t["kind"] in ("buy", "sell", "spinoff", "dividend")]
    first = min(t["time"][:10] for t in trades)
    start = date.fromisoformat(first) - timedelta(days=10)
    today = date.today()
    symbol_fn = _pf_symbol_fn(store)
    isins = {}
    for t in trades:
        if t["kind"] != "dividend":
            isins.setdefault(t["isin"], (t["ticker"], t["price_ccy"] or t["ccy"]))
    sym_of = {i: symbol_fn(i, tk) for i, (tk, _c) in isins.items()}
    jobs = {("p", i): sym for i, sym in sym_of.items() if sym}
    for b in fetch_list:
        jobs[("b", b)] = b
    wi_rows = []
    for sym_in, w_in in zip(request.args.getlist("wi_s"), request.args.getlist("wi_w")):
        sym_in = sym_in.strip().upper()
        try:
            wv = float((w_in or "0").replace(",", "."))
        except ValueError:
            wv = 0.0
        if sym_in and 0 < wv <= 100 and len(wi_rows) < 5 and sym_in not in [x[0] for x in wi_rows]:
            wi_rows.append((sym_in, wv))
    for sym_in, _w in wi_rows:
        jobs[("w", sym_in)] = sym_in
    with ThreadPoolExecutor(max_workers=6) as ex:
        results = dict(zip(jobs, ex.map(lambda sym: hist_fn(sym, start), jobs.values())))
    price_hist = {}
    for i, (tk, pccy) in isins.items():
        h = results.get(("p", i))
        s, c = perf.to_series(h, "close") if h else (None, None)
        price_hist[i] = (s, c or pccy, perf.split_list(h))
    # kurzy: všetky meny cien, obchodov a indexov -> základná mena
    need = {(v[1], base) for v in price_hist.values() if v[1]}
    need |= {(t["ccy"], base) for t in trades if t.get("ccy")}
    need |= {(t["price_ccy"], base) for t in trades if t.get("price_ccy")}
    bser, bccy = {}, {}
    for b in fetch_list:
        h = results.get(("b", b))
        s, c = perf.to_series(h, "adj") if h else (None, None)
        if s:
            bser[b], bccy[b] = s, c
            need.add((c, base))
    wi_hist = {}
    for sym_in, _w in wi_rows:
        h = results.get(("w", sym_in))
        s_, c_ = perf.to_series(h, "adj") if h else (None, None)
        if s_:
            wi_hist[sym_in] = (s_, c_ or base)
            need.add((c_ or base, base))
    need = {p for p in need if p[0] and p[0] != base}
    with ThreadPoolExecutor(max_workers=6) as ex:
        fxres = dict(zip(need, ex.map(lambda p: hist_fn(f"{p[0]}{p[1]}=X", start), need)))
    fx = {p: perf.to_series(h, "close")[0] for p, h in fxres.items() if h}
    rates = perf.Rates(fx)
    res = perf.compute(txns, base, price_hist, rates, today)
    tl = perf.Timeline(res["days"])
    benches = {}
    for b, s in bser.items():
        days = [date.fromordinal(o) for o in s.o]
        vals = []
        for d, v in zip(days, s.v):
            r = rates.rate(bccy[b], base, d)
            vals.append(v * r if r is not None else None)
        benches[b] = perf.Series(days, vals)
    windows = perf.standard_windows(tl, today)
    all_rows = perf.period_rows(tl, windows, benches)
    hidden_keys = set(store.get("hidden_periods", []))
    bad_rows = [r for r in all_rows if r["bad"]]
    hidden_rows = [r for r in all_rows if r["key"] in hidden_keys and not r["bad"]]
    rows = [r for r in all_rows if not r["bad"] and r["key"] not in hidden_keys]
    ytd = next((r for r in rows if r["key"] == f"y{today.year}" or r["label"].startswith("YTD")), None)
    allr = next((r for r in rows if r["key"] == "all"), None)
    twelve = next((r for r in rows if r["key"] == "12m"), None)
    rw = request.args.get("rw", "all")
    rw = rw if rw in ("all", "12m", "ytd") else "all"
    try:
        rf_pct = float((request.args.get("rf", "0") or "0").replace(",", "."))
    except ValueError:
        rf_pct = 0.0
    rf_pct = min(max(rf_pct, 0.0), 25.0)
    r_end = min(today, tl.last) if tl.last else today
    r_start = {"all": (tl.first or r_end) - timedelta(days=1), "12m": r_end - timedelta(days=365),
               "ytd": date(r_end.year - 1, 12, 31)}[rw]
    rb_set = {rb: benches[rb]} if rb in benches else {b: benches[b] for b in sel if b in benches}
    risk = perf.risk_stats(tl, rb_set, r_start, r_end, rf_pct / 100.0) if rb_set and tl.first else None
    whatif_res = None
    if wi_rows or "wi_s" in request.args:
        whatif_res = _whatif_build(data, isins, sym_of, results, rates, base, benches, sel, rb, wi_rows,
                                   wi_hist, r_start, r_end, rf_pct / 100.0)
    chart_days = [d["d"] for d in res["days"] if d["idx"] is not None and (d["d"].weekday() < 5 or d is res["days"][-1])]
    row_by = {d["d"]: d for d in res["days"]}
    payload = {
        "dates": [d.isoformat() for d in chart_days],
        "portfolio": [round(row_by[d]["idx"], 4) for d in chart_days],
        "value": [round(row_by[d]["v"], 2) for d in chart_days],
        "bench": [{"id": b, "label": BENCH_LABEL.get(b, b), "color": BENCH_COLORS[k % len(BENCH_COLORS)],
                   "values": [None if benches[b].at(d) is None else round(benches[b].at(d), 4)
                              for d in chart_days]}
                  for k, b in enumerate([x for x in sel if x in benches])],
        "currency": base,
    }
    warns = list(res["warnings"]) + [w for w in data["warnings"] if "staršia história" in w]
    for r in bad_rows:
        warns.append(f"Obdobie „{r['label']}“ som skryl: výnos vyšiel mimo reálneho rozsahu "
                     f"({'neznámy' if r['twr'] is None else signed_pct(r['twr'])}). Býva to neúplná "
                     "história alebo chyba v cenách. Po doplnení starších exportov sa zobrazí.")
    missing_bm = [b for b in fetch_list if b not in benches]
    if missing_bm:
        warns.append("Nepodarilo sa načítať históriu indexu: " + ", ".join(missing_bm) + ".")
    if any("staršia história" in w for w in data["warnings"]):
        warns.append("Výnosy portfólia sú orientačné, kým nenahráš aj staršie exporty od prvého "
                     "vkladu (pozície kúpené pred začiatkom exportu nie sú vo výpočte).")
    return render_template(
        "performance.html", page="portfolio", ticker=None, section=None, base=base, demo=demo,
        currencies=currencies, rows=rows, hidden_rows=hidden_rows, ytd=ytd, allr=allr, twelve=twelve, payload=payload,
        benchmarks=BENCHMARKS, selected=sel, custom=custom, bench_colors=BENCH_COLORS,
        bench_label=BENCH_LABEL, first=tl.first, last=tl.last, warns=warns, n_txn=len(txns),
        data_first=data["first"], data_last=data["last"], sel_ok=[b for b in sel if b in benches],
        risk=risk, rw=rw, rf_pct=rf_pct, rb=rb, whatif=whatif_res, wi_rows=wi_rows)


@app.route("/portfolio/import", methods=["POST"])
def portfolio_import():
    files = [(f.filename or "súbor", _read_upload(f)) for f in request.files.getlist("files")
             if f and f.filename]
    if not files:
        flash("Nevybral si žiadny súbor.", "warn")
        return redirect(url_for("portfolio_view"))
    res = portfolio.import_files(files)
    if res["added"]:
        flash(f"Načítaných {res['added']} nových transakcií"
              + (f", {res['duplicates']} už bolo nahratých." if res["duplicates"] else "."), "ok")
    elif res["duplicates"]:
        flash("Všetky transakcie z týchto súborov už v portfóliu sú.", "ok")
    for w in res["warnings"]:
        flash(w, "warn")
    return redirect(url_for("portfolio_view"))


@app.route("/portfolio/demo", methods=["POST"])
def portfolio_demo():
    p = os.path.join(edgar.DEMO_DIR, "portfolio_demo.csv")
    with open(p, encoding="utf-8") as f:
        res = portfolio.import_files([("ukážkové portfólio.csv", f.read())])
    flash("Načítané ukážkové (fiktívne) portfólio. Zmažeš ho tlačidlom nižšie.", "ok")
    for w in res["warnings"]:
        flash(w, "warn")
    return redirect(url_for("portfolio_view"))


@app.route("/portfolio/performance/hide", methods=["POST"])
def portfolio_hide_period():
    key = request.form.get("key", "")
    if re.fullmatch(r"y\d{4}|12m|all", key):
        portfolio.set_hidden(key, request.form.get("action") != "show")
    return redirect(request.referrer or url_for("portfolio_performance"))


@app.route("/portfolio/clear", methods=["POST"])
def portfolio_clear():
    portfolio.clear_store()
    flash("Portfólio je zmazané.", "ok")
    return redirect(url_for("portfolio_view"))


@app.route("/portfolio/symbol", methods=["POST"])
def portfolio_symbol():
    isin = request.form.get("isin", "").strip()
    if isin:
        portfolio.set_symbol(isin, request.form.get("symbol", ""))
        flash("Symbol uložený.", "ok")
    return redirect(url_for("portfolio_view"))


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


@app.route("/update/check")
def update_check():
    return jsonify(updater.check())


@app.route("/update/apply", methods=["POST"])
def update_apply():
    res = updater.apply()
    return jsonify(res), (200 if res["ok"] else 502)


@app.route("/update/ping")
def update_ping():
    return jsonify({"ok": True, "version": updater.current_version()})


if __name__ == "__main__":
    # use_reloader: po aktualizácii (zmene .py súborov) sa server sám znova spustí, okno nemusíš zatvárať
    app.config["TEMPLATES_AUTO_RELOAD"] = True
    app.run(host="127.0.0.1", port=5000, debug=False, use_reloader=True)

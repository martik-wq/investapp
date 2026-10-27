"""Investičná aplikácia – výkazy a metriky verejne obchodovaných firiem zo SEC EDGAR.

Spustenie:  python app.py   a potom otvor http://127.0.0.1:5000
"""
import csv
import io
from datetime import date

from flask import Flask, Response, redirect, render_template, request, url_for

import edgar
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
@app.route("/")
def index():
    return render_template("index.html", types=BUSINESS_TYPES)


@app.route("/search")
def search():
    q = request.args.get("q", "")
    try:
        match, cands = edgar.find_company(q)
    except edgar.EdgarError as e:
        return render_template("error.html", message=str(e)), 400
    if match:
        return redirect(url_for("company", ticker=match[0]))
    return render_template("search.html", q=q, cands=cands)


YEARS_OPTIONS = (5, 8, 10, 15, 20)


def parse_years(v):
    try:
        y = int(v)
    except (TypeError, ValueError):
        return 8
    return y if y in YEARS_OPTIONS else 8


def _prepare(ticker, mode, typ, price, years=8):
    match, _ = edgar.find_company(ticker)
    if not match:
        raise edgar.EdgarError(f"Ticker „{ticker}“ sa nenašiel.")
    comp = edgar.load_company(*match)
    quote = None
    if price is None and not comp["is_demo"]:
        quote = prices.get_price(match[0])
        if quote:
            price = quote["price"]
    built = statements.build(comp, mode=mode, n=years if mode == "annual" else years * 4)
    if quote and quote["currency"] != built["currency"]:
        quote["mismatch"] = True
        price = None
    auto_type = metrics.detect_type(comp, built)
    btype = typ if typ in BUSINESS_TYPES else auto_type
    result = metrics.compute(comp, built, btype)
    val = metrics.valuation(comp, built, result, price)
    return comp, built, auto_type, btype, result, val, quote, price


@app.route("/company/<ticker>")
def company(ticker):
    mode = request.args.get("mode", "annual")
    mode = mode if mode in ("annual", "quarterly") else "annual"
    typ = request.args.get("type", "auto")
    price_raw = request.args.get("price", "")
    price = parse_price(price_raw)
    years = parse_years(request.args.get("years"))
    try:
        comp, built, auto_type, btype, result, val, quote, price = _prepare(
            ticker.upper(), mode, typ, price, years)
    except edgar.EdgarError as e:
        return render_template("error.html", message=str(e)), 400
    stm = statements.all_statements(built)
    trend = trends.build_trends(comp, btype, mode, years)
    return render_template(
        "company.html", comp=comp, built=built, stm=stm, result=result, val=val,
        mode=mode, typ=typ if typ in BUSINESS_TYPES else "auto", auto_type=auto_type,
        btype=btype, types=BUSINESS_TYPES, price=price_raw, quote=quote,
        price_used=price, trend=trend, years=years, years_options=YEARS_OPTIONS,
        n_req=years if mode == "annual" else years * 4, today=date.today())


@app.route("/company/<ticker>/export.csv")
def export(ticker):
    mode = request.args.get("mode", "annual")
    mode = mode if mode in ("annual", "quarterly") else "annual"
    try:
        comp, built, _, btype, result, *_ = _prepare(
            ticker.upper(), mode, request.args.get("type", "auto"), None,
            parse_years(request.args.get("years")))
    except edgar.EdgarError as e:
        return Response(str(e), status=400)
    stm = statements.all_statements(built)
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
    data = "﻿" + out.getvalue()
    return Response(data, mimetype="text/csv; charset=utf-8", headers={
        "Content-Disposition": f"attachment; filename={comp['ticker']}_{mode}.csv"})


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)

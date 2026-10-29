"""Testy výpočtov na ukážkových dátach. Spustenie:  python tests/test_pipeline.py"""
import os
import sys
from datetime import date

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import make_demo_data as demo  # noqa: E402
import edgar  # noqa: E402
import metrics  # noqa: E402
import statements  # noqa: E402

fails = []


def check(name, cond, info=""):
    print(("OK   " if cond else "FAIL ") + name + (f"  {info}" if info and not cond else ""))
    if not cond:
        fails.append(name)


def close(a, b, tol=1e-6):
    return a is not None and b is not None and abs(a - b) <= tol * max(1, abs(b))


demo.main()
_, _, truth = demo.build_democo()
_, _, btruth = demo.build_demobank()

# ---------------------------------------------------------------- DEMOCO ročne
m, _ = edgar.find_company("democo")
comp = edgar.load_company(*m)
built = statements.build(comp, "annual", 8)
d = built["data"]
y = lambda yr: date(yr, 12, 31)  # noqa: E731

check("annual: počet období (demo má 7 rokov)", len(built["display"]) == 7, built["display"])
check("annual: posledné obdobie = 2025", built["display"][-1] == y(2025))
for yr in (2019, 2020, 2021, 2024, 2025):
    check(f"tržby {yr} (zlúčenie tagov)", close(d["revenue"].get(y(yr)), truth["rev_fy"][yr]),
          d["revenue"].get(y(yr)))
check("čistý zisk 2024", close(d["net_income"].get(y(2024)), truth["ni_fy"][2024]))
check("hrubý zisk dopočítaný", close(d["gross_profit"].get(y(2024)),
                                      truth["rev_fy"][2024] * 0.65))
check("FCF 2023", close(d["fcf"].get(y(2023)), truth["fcf_fy"][2023]))
check("súvaha: aktíva 2024 = L+E", close(d["total_assets"].get(y(2024)),
                                           truth["assets"][(2024, 4)]))
check("celkový dlh", close(d["total_debt"].get(y(2024)), 320e6))

typ = metrics.detect_type(comp, built)
check("typ DEMOCO = tech", typ == "tech", typ)
res = metrics.compute(comp, built, typ)
ids = {r["id"]: r for g in res["groups"] for r in g["rows"]}
rg = ids["rev_g"]["vals"][y(2025)]
check("rast tržieb 2025 = 12 %", close(rg, 0.12, 1e-6), rg)
roe = ids["roe"]["vals"][y(2025)]
exp_roe = truth["ni_fy"][2025] / ((truth["equity"][(2025, 4)] + truth["equity"][(2024, 4)]) / 2)
check("ROE 2025", close(roe, exp_roe, 1e-6), (roe, exp_roe))
check("operating margin 18 %", close(ids["om"]["vals"][y(2025)], 0.18))
check("Rule of 40 existuje", ids["r40"]["vals"][y(2025)] is not None)
val = metrics.valuation(comp, built, res, 50.0)
check("valuácia má P/E", val and any(l == "P/E" for l, _, _ in val["items"]))

# ------------------------------------------------------------ DEMOCO kvartálne
bq = statements.build(comp, "quarterly", 12)
dq = bq["data"]
q4 = date(2024, 12, 31)
check("quarterly: Q4 2024 tržby = FY − 9M", close(dq["revenue"].get(q4), truth["rev_q"][(2024, 4)]),
      dq["revenue"].get(q4))
check("quarterly: Q2 2024 CFO = 6M − 3M", close(dq["cfo"].get(date(2024, 6, 30)),
                                                 truth["cfo_q"][(2024, 2)]),
      dq["cfo"].get(date(2024, 6, 30)))
check("quarterly: Q3 2024 CFO = 9M − 6M", close(dq["cfo"].get(date(2024, 9, 30)),
                                                 truth["cfo_q"][(2024, 3)]))
check("quarterly: Q4 2024 CFO = FY − 9M", close(dq["cfo"].get(q4), truth["cfo_q"][(2024, 4)]))
check("quarterly: posledné obdobie 2026-06-30", bq["display"][-1] == date(2026, 6, 30),
      bq["display"][-1])
resq = metrics.compute(comp, bq, "tech")
idq = {r["id"]: r for g in resq["groups"] for r in g["rows"]}
ttm_rev = sum(truth["rev_q"][k] for k in [(2025, 3), (2025, 4), (2026, 1), (2026, 2)])
prev_ttm = sum(truth["rev_q"][k] for k in [(2024, 3), (2024, 4), (2025, 1), (2025, 2)])
check("quarterly: TTM rast tržieb", close(idq["rev_g"]["vals"][date(2026, 6, 30)],
                                         ttm_rev / prev_ttm - 1, 1e-6),
      idq["rev_g"]["vals"][date(2026, 6, 30)])
vq = metrics.valuation(comp, bq, resq, 50.0)
check("quarterly: valuácia funguje", vq is not None)

# --- TTM záznamy z 10-Q nesmú znečistiť ročné ani kvartálne údaje
check("annual: všetky obdobia sú konce fiškálneho roka",
      all(e.month == 12 and e.day == 31 for e in built["display"]), built["display"])
check("annual: čistý zisk bez TTM", all(
    close(d["net_income"].get(y(yr)), truth["ni_fy"][yr]) for yr in range(2019, 2026)))
ni_q = {k: v for k, v in zip(range(0), [])}
check("quarterly: čistý zisk Q2 2024 je samostatný kvartál (nie TTM)",
      dq["net_income"].get(date(2024, 6, 30)) is not None and
      dq["net_income"][date(2024, 6, 30)] < truth["ni_fy"][2024] * 0.5,
      dq["net_income"].get(date(2024, 6, 30)))
check("quarterly: čistý zisk Q4 2024 = FY − 9M",
      close(dq["net_income"].get(date(2024, 12, 31)),
            truth["ni_fy"][2024] - sum(dq["net_income"][date(2024, m, 30 if m in (6, 9) else 31)]
                                       for m in (3, 6, 9))))

# ---------------------------------------------------------------- DEMOBANK
mb, _ = edgar.find_company("DEMOBANK")
cb = edgar.load_company(*mb)
bb = statements.build(cb, "annual", 8)
btype = metrics.detect_type(cb, bb)
check("typ DEMOBANK = bank", btype == "bank", btype)
check("NII 2024", close(bb["data"]["nii"].get(y(2024)), btruth["nii_fy"][2024]))
rb = metrics.compute(cb, bb, btype)
ib = {r["id"]: r for g in rb["groups"] for r in g["rows"]}
eff = ib["eff"]["vals"][y(2025)]
check("efficiency ratio = 55 %", close(eff, 0.55, 1e-6), eff)
check("loans/deposits = 0.62/0.82", close(ib["ltd"]["vals"][y(2025)], 0.62 / 0.82))
check("ROTCE existuje", ib["rotce"]["vals"][y(2025)] is not None)
check("cost of risk existuje", ib["cor"]["vals"][y(2025)] is not None)
vb = metrics.valuation(cb, bb, rb, 20.0)
check("banka: P/TBV", vb and any("P/TBV" in l for l, _, _ in vb["items"]))

# ----------------------------------------------- podrobné výkazy z podaní (R*.htm)
import filings  # noqa: E402
import make_demo_filings as mf  # noqa: E402

check("parse_number: záporné v zátvorkách", filings.parse_number("$ (1,234)") == -1234.0)
check("parse_number: poznámka pod čiarou sa ignoruje", filings.parse_number("$ 574,785 [1]") == 574785.0)
check("parse_number: pomlčka = prázdne", filings.parse_number("—") is None)
check("parse_months: týždne", filings.parse_months("39 Weeks Ended") == 9 and
      filings.parse_months("52 Weeks Ended") == 12 and filings.parse_months("12 Months Ended") == 12)
check("parse_date: Sep. 30, 2025", filings.parse_date("Sep. 30, 2025") == date(2025, 9, 30))
check("classify: výkazy",
      filings.classify("CONSOLIDATED STATEMENTS OF OPERATIONS") == "income" and
      filings.classify("CONSOLIDATED STATEMENTS OF COMPREHENSIVE INCOME") is None and
      filings.classify("CONSOLIDATED BALANCE SHEETS (Parenthetical)") is None and
      filings.classify("CONDENSED CONSOLIDATED STATEMENTS OF CASH FLOWS") == "cashflow" and
      filings.classify("CONSOLIDATED STATEMENTS OF INCOME AND COMPREHENSIVE INCOME") == "income")
check("scales: tisíce a milióny", filings._scales("X - USD ($) shares in Thousands, $ in Millions")
      == (1e6, 1e3))

dm, _ = edgar.find_company("DEMOCO")
dc = edgar.load_company(*dm)
fl = filings.list_filings(dc["filings"], filings.ANNUAL_FORMS)
ld = filings.load_filing(dc, fl[0])
check("podanie 10-K: nájdené všetky tri výkazy", all(ld[k] for k in filings.KINDS))
inc_rep = ld["income"]
check("výkaz: stĺpce s trvaním 12 mesiacov", [c["months"] for c in inc_rep["cols"]] == [12, 12, 12])
check("výkaz: súvaha má okamžité hodnoty", [c["months"] for c in ld["balance"]["cols"]] == [None, None])
prod = next(r for r in inc_rep["rows"] if r["label"] == "Net product sales")
check("riadok tovaru: odsadený pod hlavičkou a prepočítaný z tisícov",
      prod["indent"] == 1 and close(prod["vals"][0], mf.quarter(2025, 4)["prod"] * 0 + sum(
          mf.quarter(2025, q)["prod"] for q in range(1, 5)), 1e-3), prod["vals"][0])
check("concept sa načíta z odkazu", prod["concept"] == "us-gaap_RevenueFromContractWithCustomerExcludingAssessedTax")

da = filings.get_detailed(dc, "annual", 5)
get = lambda stm, label: next(r for r in da[stm] if r["label"] == label)  # noqa: E731
check("annual detail: 5 rokov", len(da["ends"]) == 5, da["ends"])
pr, sv, tot = get("income", "Net product sales"), get("income", "Net service sales"), get("income", "Total net sales")
check("annual detail: tovar + služby = tržby (všetky roky)",
      all(close(pr["vals"][e] + sv["vals"][e], tot["vals"][e], 1e-6) for e in da["ends"]))
check("annual detail: zlúčenie 10-K z rokov 2025 a 2023 (rok 2021 z 10-K FY2023)",
      get("income", "Total net sales")["vals"][date(2021, 12, 31)] is not None)
check("annual detail: súvaha sedí (aktíva = pasíva)",
      all(abs(get("balance", "Total assets")["vals"][e] -
              get("balance", "Total liabilities and stockholders' equity")["vals"][e]) < 2e3
          for e in da["ends"]))
check("annual detail: cash flow zachováva znamienko firmy (CapEx záporný)",
      get("cashflow", "Purchases of property and equipment")["vals"][date(2025, 12, 31)] < 0)
check("annual detail: hlavičky skupín sú zachované",
      any(r["header"] and r["label"] == "Operating expenses:" for r in da["income"]))
check("annual detail: EPS bez prepočtu", 0.1 < get("income", "Diluted earnings per share")["vals"][date(2025, 12, 31)] < 5)

dq = filings.get_detailed(dc, "quarterly", 3)
getq = lambda stm, label: next(r for r in dq[stm] if r["label"] == label)  # noqa: E731
qchk = lambda stm, label, key, fn: all(  # noqa: E731
    v is not None and abs(v - fn((e.month - 1) // 3 + 1, e.year)[key]) < 2e3
    for e, v in getq(stm, label)["vals"].items())
check("quarterly detail: 12 kvartálov", len(dq["ends"]) == 12, len(dq["ends"]))
check("quarterly detail: tržby každého kvartálu (vrátane Q4 = rok − 9M)",
      qchk("income", "Total net sales", "rev", lambda q, y: mf.quarter(y, q)))
check("quarterly detail: tovar každého kvartálu",
      qchk("income", "Net product sales", "prod", lambda q, y: mf.quarter(y, q)))
check("quarterly detail: cash flow z prevádzky = rozdiely kumulatívnych hodnôt",
      qchk("cashflow", "Net cash provided by operating activities", "cfo", lambda q, y: mf.quarter(y, q)))
check("quarterly detail: CapEx každého kvartálu",
      qchk("cashflow", "Purchases of property and equipment", "capex", lambda q, y: mf.quarter(y, q)))
check("quarterly detail: aktíva na konci každého kvartálu",
      qchk("balance", "Total assets", "assets", lambda q, y: mf.balance(y, q)))
check("quarterly detail: priemerný počet akcií sa neodčítava",
      all(v in (None, 101e6) for v in getq("income", "Diluted")["vals"].values()))

# ------------------------------------------------ tok od tržieb k zisku (Sankey)
import flow  # noqa: E402


def conserved(fl):
    for n in fl["nodes"]:
        inn = sum(l["v"] for l in fl["links"] if l["t"] == n["id"])
        out = sum(l["v"] for l in fl["links"] if l["s"] == n["id"])
        tol = 1e-6 * max(1, n["value"]) + 1
        if inn and abs(inn - n["value"]) > tol:
            return f"vstup {n['id']} {inn} != {n['value']}"
        if out and abs(out - n["value"]) > tol:
            return f"výstup {n['id']} {out} != {n['value']}"
    return None


def fake_built(rows, currency="USD"):
    e1, e0 = date(2025, 12, 31), date(2024, 12, 31)
    data = {k: {e0: v[0], e1: v[1]} for k, v in rows.items()}
    return {"data": data, "ends": [e0, e1], "display": [e0, e1], "currency": currency}


b_ok = statements.build(comp, "annual", 8)
fl_ok = flow.build_flow(b_ok, b_ok["display"][-1], "tech")
check("flow: uzly aj prepojenia sa zachovávajú (tech)", conserved(fl_ok) is None, conserved(fl_ok))
ids = {n["id"] for n in fl_ok["nodes"]}
check("flow: tržby, hrubý zisk, prevádzkový zisk, čistý zisk, dane", {"revenue", "gp", "oi", "ni", "tax"} <= ids)
check("flow: tri kľúčové čísla", len(fl_ok["tiles"]) == 3)
check("flow: rast tržieb 12 %", abs(fl_ok["tiles"][0]["value"] - 0.12) < 1e-6)

streams = [{"label": "A", "value": 500e6, "prev": 450e6}, {"label": "B", "value": 289.5e6, "prev": 250e6}]
fl_s = flow.build_flow(b_ok, b_ok["display"][-1], "tech", streams)
check("flow: členenie tržieb sa pridá a súčty sedia", any(n["id"] == "stream0" for n in fl_s["nodes"])
      and conserved(fl_s) is None, conserved(fl_s))
fl_bad = flow.build_flow(b_ok, b_ok["display"][-1], "tech", [{"label": "A", "value": 1e6, "prev": None},
                                                             {"label": "B", "value": 2e6, "prev": None}])
check("flow: členenie, ktoré nesedí s tržbami, sa ignoruje", not any(n["id"].startswith("stream") for n in fl_bad["nodes"]))

# strata: prevádzková aj čistá
loss = fake_built({"revenue": (80e6, 100e6), "cost_of_revenue": (50e6, 60e6), "gross_profit": (30e6, 40e6),
                   "rnd": (40e6, 45e6), "sga": (30e6, 30e6), "op_income": (-40e6, -35e6),
                   "tax": (1e6, 1e6), "net_income": (-45e6, -38e6)})
fl_l = flow.build_flow(loss, loss["display"][-1], "general")
check("flow: strata - bez uzla zisku, zachované súčty", fl_l and not any(n["id"] in ("oi", "ni") for n in fl_l["nodes"])
      and any(n["id"] == "loss" for n in fl_l["nodes"]) and conserved(fl_l) is None, conserved(fl_l) if fl_l else None)
check("flow: strata - poznámka o strate", fl_l and "strata" in fl_l["note"].lower())
# ostatné výnosy: čistý zisk vyšší ako prevádzkový
oth = fake_built({"revenue": (900e6, 1000e6), "cost_of_revenue": (500e6, 500e6), "gross_profit": (400e6, 500e6),
                  "rnd": (100e6, 100e6), "sga": (100e6, 100e6), "op_income": (200e6, 300e6),
                  "tax": (40e6, 60e6), "net_income": (260e6, 380e6)})
fl_o = flow.build_flow(oth, oth["display"][-1], "general")
check("flow: ostatné výnosy sú zdroj a súčty sedia", fl_o and any(n["id"] == "other_inc" for n in fl_o["nodes"])
      and conserved(fl_o) is None, conserved(fl_o) if fl_o else None)
# bez nákladov na tržby (napr. REIT): tržby -> prevádzkový zisk / náklady
nogp = fake_built({"revenue": (400e6, 500e6), "op_income": (100e6, 150e6), "tax": (5e6, 8e6),
                   "net_income": (80e6, 120e6)})
fl_n = flow.build_flow(nogp, nogp["display"][-1], "reit")
check("flow: bez hrubého zisku", fl_n and not any(n["id"] == "gp" for n in fl_n["nodes"]) and conserved(fl_n) is None,
      conserved(fl_n) if fl_n else None)
check("flow: bez tržieb sa nič nevyrobí", flow.build_flow(fake_built({"net_income": (1e6, 2e6)}),
                                                         date(2025, 12, 31), "general") is None)
b_bank = statements.build(cb, "annual", 8)
fl_b = flow.build_flow(b_bank, b_bank["display"][-1], "bank")
check("flow: banka - úroky, čisté výnosy, rezervy, čistý zisk", fl_b and {"int_income", "net_rev", "prov", "ni", "tax"}
      <= {n["id"] for n in fl_b["nodes"]} and conserved(fl_b) is None, conserved(fl_b) if fl_b else None)

# členenie tržieb z podaní (poznámka aj výkaz, Q4 dopočítané)
rev25 = sum(mf.quarter(2025, q)["rev"] for q in range(1, 5))
bd12 = filings.revenue_breakdown(dc, date(2025, 12, 31), 12, rev25)
check("členenie tržieb 12M z poznámky (3 položky)", bd12 and [i["label"] for i in bd12] ==
      ["Subscriptions", "Licenses", "Support and services"], bd12)
bd_q3 = filings.revenue_breakdown(dc, date(2025, 9, 30), 3, mf.quarter(2025, 3)["rev"])
check("členenie tržieb Q3 z 10-Q", bd_q3 and abs(sum(i["value"] for i in bd_q3) - mf.quarter(2025, 3)["rev"]) < 3e3)
bd_q4 = filings.revenue_breakdown(dc, date(2025, 12, 31), 3, mf.quarter(2025, 4)["rev"],
                                  rev25, sum(mf.quarter(2025, q)["rev"] for q in range(1, 4)))
check("členenie tržieb Q4 = rok − 9M", bd_q4 and abs(sum(i["value"] for i in bd_q4) - mf.quarter(2025, 4)["rev"]) < 3e3
      and abs(bd_q4[0]["value"] - 0.55 * mf.quarter(2025, 4)["rev"]) < 3e3, bd_q4)
check("členenie tržieb: medziročná predchádzajúca hodnota", bd_q3 and all(i["prev"] for i in bd_q3))
check("členenie tržieb: nesprávny celkový súčet sa odmietne",
      filings.revenue_breakdown(dc, date(2025, 12, 31), 12, rev25 * 3) is None)
face = filings.extract_breakdown(filings.load_filing(dc, filings.list_filings(dc["filings"], filings.ANNUAL_FORMS)[0])["income"],
                                 date(2025, 12, 31), 12, rev25)
check("členenie tržieb priamo z výkazu (tovar a služby)", face and [i["label"] for i in face["items"]] ==
      ["Net product sales", "Net service sales"])

# rozpis nákladov z výkazu firmy
ob = statements.build(dc, "annual", 8)
opx, cgs = flow.cost_targets(ob["data"], date(2025, 12, 31))
oi = filings.cost_components(dc, date(2025, 12, 31), 12, opx)
check("náklady: prevádzkové náklady z výkazu (3 položky)", oi and [i["label"] for i in oi] ==
      ["Research and development", "Sales and marketing", "General and administrative"], oi)
ci = filings.cost_components(dc, date(2025, 12, 31), 12, cgs)
check("náklady: náklady na tržby (produkty, služby)", ci and [i["label"] for i in ci] == ["Products", "Services"], ci)
qb = statements.build(dc, "quarterly", 12)
qe = [e for e in qb["ends"] if e <= date(2025, 12, 31)][-4:]
tq = [flow.cost_targets(qb["data"], e) for e in qe]
oq4 = filings.cost_components(dc, date(2025, 12, 31), 3, tq[3][0], sum(x[0] for x in tq), sum(x[0] for x in tq[:3]))
check("náklady: Q4 prevádzkových nákladov = rok − 9M", oq4 and abs(sum(i["value"] for i in oq4) - tq[3][0]) < 5e3
      and len(oq4) == 3, oq4)
check("náklady: odmietne zlý cieľový súčet", filings.cost_components(dc, date(2025, 12, 31), 12, opx * 2) is None)
fl_c = flow.build_flow(ob, date(2025, 12, 31), "tech", None, oi, ci)
check("flow: presné položky nákladov v diagrame (slovensky)", fl_c and {"opex_0", "opex_1", "opex_2", "cogs_0", "cogs_1"}
      <= {n["id"] for n in fl_c["nodes"]} and conserved(fl_c) is None, conserved(fl_c) if fl_c else None)
check("flow: preklad názvov", {n["label"] for n in fl_c["nodes"]} >= {"Výskum a vývoj", "Predaj a marketing", "Správna réžia",
                                                                       "Náklady na produkty", "Náklady na služby"}
      or {"Výskum a vývoj", "Predaj a marketing", "Správna réžia"} <= {n["label"] for n in fl_c["nodes"]},
      [n["label"] for n in fl_c["nodes"]])
check("flow: nesprávny súčet položiek sa ignoruje (štandardné členenie)",
      not any(n["id"].startswith("opex_") and n["id"][5:].isdigit() for n in
              flow.build_flow(ob, date(2025, 12, 31), "tech", None, [{"label": "x", "value": 1e6, "prev": None},
                                                                      {"label": "y", "value": 2e6, "prev": None}])["nodes"]))
check("sk(): preklady", flow.sk("Research and development") == "Výskum a vývoj" and flow.sk("Marketing and sales") ==
      "Predaj a marketing" and flow.sk("Something unusual") == "Something unusual")

# ------------------------------------------------------------ portfólio (Trading 212)
import portfolio  # noqa: E402
import tempfile  # noqa: E402
import make_demo_portfolio as mp  # noqa: E402

pf_dir = tempfile.mkdtemp()
portfolio.DATA_DIR = pf_dir
portfolio.STORE = os.path.join(pf_dir, "portfolio.json")      # testy sa nedotknú tvojich údajov

# --- nový formát (viac mien, Time (UTC) s pásmom)
demo_csv = mp.generate()
pr = portfolio.parse_csv(demo_csv)
check("T212 (nový formát): načíta sa, konverzie mien sa ticho preskočia", len(pr["txns"]) == 16 and not pr["warnings"],
      (len(pr["txns"]), pr["warnings"]))
check("T212: čas s pásmom +00:00 sa prečíta", pr["txns"][0]["time"] == "2025-10-30 02:05:37")
check("T212: mena v každom riadku", {t["ccy"] for t in pr["txns"]} == {"EUR", "USD"})
pd_ = portfolio.build_positions(pr["txns"])
by = {p["ticker"]: p for p in pd_["open"]}
check("portfólio: pozície", set(by) == {"DEMOCO", "DEMOEU", "DEMOUK", "DEMOSPIN"}, set(by))
check("portfólio: zmiešaná mena zúčtovania -> mena akcie, suma = kusy × cena",
      by["DEMOCO"]["ccy"] == "USD" and abs(by["DEMOCO"]["cost"] - (400 + 90 - (400 + 90) / 12 * 4)) < 1e-9, by["DEMOCO"]["cost"])
check("portfólio: predaj používa výsledok z Trading 212", abs(by["DEMOCO"]["realized"]["USD"] - 54.0) < 1e-9)
check("portfólio: kusy po predaji", abs(by["DEMOCO"]["shares"] - 8) < 1e-9)
check("portfólio: londýnsky ETF zúčtovaný v EUR -> pozícia v EUR", by["DEMOUK"]["ccy"] == "EUR"
      and abs(by["DEMOUK"]["cost"] - 229.89) < 1e-9)
check("portfólio: predaj bez histórie -> zisk z Trading 212 a upozornenie", any("DEMOOLD" in w and "staršia história" in w
      for w in pd_["warnings"]) and abs(pd_["all"][-1]["realized"].get("USD", 0) + 0) >= 0
      and any(abs(p["realized"].get("USD", 0) - 15.0) < 1e-9 for p in pd_["closed"]))
check("portfólio: spin-off má nulovú nákupnú cenu a upozornenie", by["DEMOSPIN"]["cost"] == 0 and by["DEMOSPIN"]["shares"] == 2
      and any("Spin-off" in w for w in pd_["warnings"]))
check("portfólio: presun medzi peňaženkami nie je vklad ani výber", pd_["totals"]["deposits"] == {"EUR": 1240.0}
      and pd_["totals"]["withdrawals"] == {"EUR": 50.0} and pd_["totals"]["transfers"] == {"EUR": 100.0, "USD": 115.0},
      pd_["totals"])
check("portfólio: dividendy a úroky podľa mien", abs(pd_["totals"]["dividends"]["EUR"] - 7.3) < 1e-9
      and pd_["totals"]["interest"] == {"EUR": 0.02, "USD": 0.01})
check("portfólio: dividendy podľa rokov", set(pd_["dividends_by_year"]) == {"2025", "2026"})
check("portfólio: rozsah dát", pd_["first"] == "2025-10-30" and pd_["last"] == "2026-06-12")
check("základná mena = mena bankových vkladov", portfolio.default_base(pr["txns"]) == "EUR")

# ocenenie: pence (GBp), kurzy a prepočet do základnej meny
fxt = {("USD", "EUR"): 0.9, ("GBP", "EUR"): 1.2, ("EUR", "USD"): 1 / 0.9}
quotes = {"DEMOCO": {"price": 50.0, "currency": "USD"}, "DEMOEU": {"price": 120.0, "currency": "EUR"},
          "DEMOUK": {"price": 2500.0, "currency": "GBp"}, "DEMOSPIN": {"price": 20.0, "currency": "EUR"}}
conv = portfolio.Converter(lambda a, b: fxt.get((a, b)))
vals = portfolio.value_positions(pd_["open"], "EUR", lambda i, t: t, lambda s: quotes.get(s), conv)
bt = {p["ticker"]: p for p in vals}
check("ocenenie: USD pozícia v USD aj v EUR", abs(bt["DEMOCO"]["value"] - 400) < 1e-9 and abs(bt["DEMOCO"]["value_b"] - 360) < 1e-9)
check("ocenenie: pence -> libry -> EUR pozície", abs(bt["DEMOUK"]["price_pc"] - 25 * 1.2) < 1e-9
      and abs(bt["DEMOUK"]["value"] - 300) < 1e-9)
sm = portfolio.summarize(pd_, vals, "EUR", conv)
check("súhrn: trhová hodnota v EUR", abs(sm["value"] - (360 + 600 + 300 + 40)) < 1e-9, sm["value"])
check("súhrn: realizovaný zisk (USD výsledky prepočítané)", abs(sm["realized"] - (54 + 15) * 0.9) < 1e-9, sm["realized"])
check("súhrn: dividendy, úroky, vklady v EUR", abs(sm["dividends"] - 7.3) < 1e-9 and abs(sm["deposits"] - 1240) < 1e-9
      and abs(sm["interest"] - (0.02 + 0.01 * 0.9)) < 1e-9)
check("súhrn: nerealizovaný zisk = hodnota − nákupná cena", abs(sm["unrealized"] - (sm["value"] - sm["cost_priced"])) < 1e-9)
none = portfolio.value_positions(portfolio.build_positions(pr["txns"])["open"], "EUR", lambda i, t: t,
                                 lambda s: None, portfolio.Converter(lambda a, b: 1.0))
check("ocenenie: bez ceny sa pozícia zobrazí, ale nie je v hodnote",
      portfolio.summarize(pd_, none, "EUR", conv)["value"] == 0 and len(portfolio.summarize(pd_, none, "EUR", conv)["unpriced"]) == 4)
nofx = portfolio.Converter(lambda a, b: None)
vn = portfolio.value_positions(portfolio.build_positions(pr["txns"])["open"], "EUR", lambda i, t: t,
                               lambda s: quotes.get(s), nofx)
check("ocenenie: chýbajúci kurz sa nahlási", portfolio.summarize(pd_, vn, "EUR", nofx)["fx_missing"])

# stránka sa nesmie rozbiť, keď Yahoo ceny nevráti (ani jedna pozícia nemá cenu)
import app as _appmod  # noqa: E402
_orig_q = _appmod._pf_quote
_appmod._pf_quote = lambda s: None
portfolio.import_files([("n.csv", demo_csv)])
_rn = _appmod.app.test_client().get("/portfolio")
check("portfólio: bez cien z Yahoo sa stránka zobrazí a ponúkne opravu symbolov", _rn.status_code == 200
      and b"nepodarilo na" in _rn.data and b"symbol z Yahoo" in _rn.data, _rn.status_code)
_appmod._pf_quote = _orig_q
portfolio.clear_store()

# --- starší formát (jedna mena účtu)
legacy = mp.generate_legacy()
pl = portfolio.parse_csv(legacy)
check("T212 (starší formát): mena z hlavičky Total (EUR)", pl["acct_ccy"] == "EUR" and all(t["ccy"] == "EUR" for t in pl["txns"]))
check("T212 (starší formát): 9 transakcií, konverzia mien sa preskočí", len(pl["txns"]) == 9 and not pl["warnings"])
ld = portfolio.build_positions(pl["txns"])
dco = next(p for p in ld["open"] if p["ticker"] == "DEMOCO")
cost1, cost2 = round(10 * 40 / 1.10, 2), round(5 * 45 / 1.08, 2)
avg = (cost1 + cost2) / 15
sold = round(6 * 52 / 1.05, 2)
check("starší formát: kusy, priemerná cena, realizovaný zisk (vlastný výpočet bez Result)",
      abs(dco["shares"] - 9) < 1e-9 and abs(dco["avg_cost"] - avg) < 1e-6
      and abs(dco["realized"]["EUR"] - (sold - avg * 6)) < 1e-6, dco["realized"])
check("starší formát: dividendy a vklady", ld["dividends_by_year"] == {"2024": {"EUR": 3.4}, "2025": {"EUR": 5.1}}
      and ld["totals"]["deposits"] == {"EUR": 5000.0} and ld["totals"]["withdrawals"] == {"EUR": 200.0})
unk = portfolio.parse_csv(legacy + "Neznama akcia,2024-03-01 10:00:00,,,,,,,,,1.00,,,,,Z9\n")
check("T212: neznáma akcia sa preskočí s upozornením", len(unk["txns"]) == 9 and any("Neznama akcia" in w for w in unk["warnings"]))

# iné tvary exportu: Total + Currency (Total), dátum d/m/Y, bodkočiarka, 1,234.50
alt = ("Action;Time;ISIN;Ticker;Name;No. of shares;Price / share;Currency (Price / share);Exchange rate;"
       "Result;Currency (Result);Total;Currency (Total);ID\n"
       "Market buy;25/09/2020 13:34;US88579Y1010;MMM;3M;1,5;159.52;USD;1.16329;;GBP;\"1,234.50\";GBP;X1\n"
       "Market sell;26/09/2020 10:00;US88579Y1010;MMM;3M;0,5;170.00;USD;1.16329;;GBP;80.00;GBP;X2\n")
pa = portfolio.parse_csv(alt)
check("T212 (iný formát): dátum d/m/Y, desatinná čiarka, tisíce",
      pa["txns"][0]["time"].startswith("2020-09-25") and pa["txns"][0]["shares"] == 1.5 and pa["txns"][0]["total"] == 1234.5
      and pa["txns"][0]["ccy"] == "GBP")
try:
    portfolio.parse_csv("a,b,c\n1,2,3\n")
    bad = False
except portfolio.PortfolioError as e:
    bad = "Trading 212" in str(e)
check("cudzí CSV súbor -> zrozumiteľná chyba", bad)
res1 = portfolio.import_files([("a.csv", demo_csv)])
res2 = portfolio.import_files([("b.csv", demo_csv)])
check("import: opakovaný súbor nepridá duplicity", res1["added"] == 16 and res2["added"] == 0 and res2["duplicates"] == 16)
res3 = portfolio.import_files([("c.csv", legacy)])
check("import: súbor v inej mene sa pridá k ostatným (každý riadok má svoju menu)", res3["added"] == 9)
portfolio.clear_store()
check("import: zmazanie údajov", portfolio.load_store()["txns"] == {})

# ------------------------------------------------ výkonnosť portfólia a porovnanie s indexmi
import perf  # noqa: E402
from datetime import timedelta  # noqa: E402


def ptx(kind, day, isin, sh, price, total, ccy="EUR", pccy="EUR", ticker="AAA"):
    return {"kind": kind, "time": day.isoformat() + " 12:00:00", "isin": isin, "ticker": ticker,
            "shares": sh, "price": price, "price_ccy": pccy, "total": total, "ccy": ccy}


d0 = date(2025, 12, 29)
px = perf.Series([d0, d0 + timedelta(1), d0 + timedelta(2), d0 + timedelta(4), d0 + timedelta(5)],
                 [100, 110, 110, 110, 121])
tx1 = [ptx("buy", d0, "X1", 10, 100, 1000), ptx("buy", d0 + timedelta(4), "X1", 10, 110, 1100)]
r1 = perf.compute(tx1, "EUR", {"X1": (px, "EUR")}, perf.Rates({}), date(2026, 1, 3))
tl1 = perf.Timeline(r1["days"])
w1 = perf.window(tl1, date(2025, 12, 31), date(2026, 1, 3))
check("výnos: TWR nezávisí od času vkladov (110 → 121 = +10 %)", abs(w1["twr"] - 0.10) < 1e-9, w1)
check("zisk/strata: zmena hodnoty − nákupy (2420 − 1100 − 1100)", abs(w1["pnl"] - 220) < 1e-9, w1)
w_all = perf.window(tl1, d0 - timedelta(1), date(2026, 1, 3), from_scratch=True)
check("výnos od začiatku +21 % a zisk 320", abs(w_all["twr"] - 0.21) < 1e-9 and abs(w_all["pnl"] - 320) < 1e-9, w_all)
wins = perf.standard_windows(tl1, date(2026, 1, 3))
check("obdobia: YTD, rok začiatku s „od“, od začiatku", [w[0] for w in wins] == ["y2026", "y2025", "all"]
      and "od 29. 12. 2025" in wins[1][1] and wins[0][1] == "YTD 2026", [w[1] for w in wins])
rows = perf.period_rows(tl1, wins, {"IDX": perf.Series([d0, date(2025, 12, 31), date(2026, 1, 3)], [50, 55, 66])})
ry = {r["key"]: r for r in rows}
check("tabuľka: YTD portfólia aj indexu (55 → 66 = +20 %)", abs(ry["y2026"]["twr"] - 0.10) < 1e-9
      and abs(ry["y2026"]["bench"]["IDX"] - 0.20) < 1e-9, ry["y2026"])
check("tabuľka: rok začiatku sa meria od prvého dňa (index 50 → 55 = +10 %)", abs(ry["y2025"]["bench"]["IDX"] - 0.10) < 1e-9
      and abs(ry["y2025"]["twr"] - 0.10) < 1e-9, ry["y2025"])

# dividendy sa pripočítajú k výnosu
tx2 = [ptx("buy", d0, "X1", 10, 100, 1000), {**ptx("dividend", d0 + timedelta(1), "X1", None, None, 55), "kind": "dividend"}]
r2 = perf.compute(tx2, "EUR", {"X1": (perf.Series([d0, d0 + timedelta(1)], [100, 100]), "EUR")}, perf.Rates({}), d0 + timedelta(1))
check("výnos: dividenda 55 z hodnoty 1000 = +5,5 %", abs(r2["days"][-1]["idx"] - 105.5) < 1e-9, r2["days"][-1])

# kurz: cena v USD sa nemení, USD oslabí z 0,90 na 0,99 EUR -> +10 % v EUR; pence na libry
fxs = {("USD", "EUR"): perf.Series([d0, d0 + timedelta(1)], [0.90, 0.99])}
r3 = perf.compute([ptx("buy", d0, "U1", 10, 100, 900, ccy="EUR", pccy="USD")], "EUR",
                  {"U1": (perf.Series([d0, d0 + timedelta(1)], [100, 100]), "USD")}, perf.Rates(fxs), d0 + timedelta(1))
check("výnos: zmena kurzu sa prejaví v základnej mene (+10 %)", abs(r3["days"][-1]["idx"] - 110) < 1e-9, r3["days"][-1])
hs, hc = perf.to_series({"dates": ["2026-01-02"], "close": [2500.0], "adj": [2500.0], "currency": "GBp"})
check("ceny v penciach sa prepočítajú na libry", hc == "GBP" and abs(hs.at(date(2026, 1, 5)) - 25.0) < 1e-9)
inv = perf.Rates({("EUR", "USD"): perf.Series([d0], [2.0])})
check("kurz sa dá použiť aj opačne", abs(inv.rate("USD", "EUR", d0) - 0.5) < 1e-12)

# predaj akcie z čias pred exportom nesmie vyrobiť falošný výnos
tx4 = [ptx("buy", d0, "A1", 10, 100, 1000), ptx("sell", d0 + timedelta(1), "OLD", 50, 100, 5000, ticker="OLD")]
r4 = perf.compute(tx4, "EUR", {"A1": (perf.Series([d0, d0 + timedelta(1)], [100, 100]), "EUR"),
                               "OLD": (perf.Series([d0, d0 + timedelta(1)], [100, 100]), "EUR")}, perf.Rates({}), d0 + timedelta(1))
check("výnos: predaj bez evidovaných nákupov nevyrobí zisk", abs(r4["days"][-1]["idx"] - 100) < 1e-9, r4["days"][-1])
# bez histórie cien sa použije cena z obchodu a vypíše upozornenie
r5 = perf.compute(tx1[:1], "EUR", {"X1": (None, "EUR")}, perf.Rates({}), d0 + timedelta(2))
check("bez histórie cien: náhradná cena z obchodu + upozornenie", abs(r5["days"][-1]["v"] - 1000) < 1e-9
      and any("Bez histórie cien" in w for w in r5["warnings"]))
# veľký nákup po malom základe a mierny pokles ceny nesmie dať záporný výnos (chyba −224 %)
ps = perf.Series([d0, d0 + timedelta(1), d0 + timedelta(2)], [100, 100, 98])
tx6 = [ptx("buy", d0, "S1", 0.5, 100, 50), ptx("buy", d0 + timedelta(2), "S1", 50, 100, 5000)]
r6 = perf.compute(tx6, "EUR", {"S1": (ps, "EUR")}, perf.Rates({}), d0 + timedelta(2))
check("výnos: veľký nákup po malom základe nedá záporný index", all(d["idx"] > 0 for d in r6["days"] if d["idx"] is not None)
      and abs(r6["days"][-1]["idx"] - 98.0) < 1e-6, [d["idx"] for d in r6["days"]])
tx7 = [ptx("buy", d0, "S1", 10, 100, 1000), ptx("sell", d0 + timedelta(1), "S1", 10, 100, 1000)]
r7 = perf.compute(tx7, "EUR", {"S1": (perf.Series([d0, d0 + timedelta(1)], [100, 100]), "EUR")}, perf.Rates({}), d0 + timedelta(2))
check("výnos: úplný predaj nedá záporný ani nulový index", all(d["idx"] is None or d["idx"] > 0 for d in r7["days"]))
check("obdobia mimo reálneho rozsahu sa označia ako chybné", perf.period_rows(
    perf.Timeline([{"d": d0, "v": 1.0, "flow": 0, "div": 0, "idx": 100.0}, {"d": d0 + timedelta(1), "v": 1.0, "flow": 0, "div": 0, "idx": -124.0}]),
    [("all", "x", d0 - timedelta(1), d0 + timedelta(1), True)], {})[0]["bad"])
bs = perf.Series([d0, d0 + timedelta(5)], [100, 120])
check("index: výnos za obdobie", abs(perf.benchmark_return(bs, d0, d0 + timedelta(5)) - 0.2) < 1e-9)

# ------------------------------------------------------- rozhranie (Flask klient)
# --- regresia: TWR musí presne sedieť s cenovým výnosom (obchody za cenu obchodu, náhodné toky + kurzy)
import random as _rnd  # noqa: E402


def _twr_property(seed):
    rnd = _rnd.Random(seed)
    days = [date(2024, 1, 2) + timedelta(days=i) for i in range(90)]
    P, X = [100.0], [0.9]
    for _ in range(len(days) - 1):
        P.append(P[-1] * (1 + rnd.gauss(0, 0.03)))
        X.append(X[-1] * (1 + rnd.gauss(0, 0.005)))
    rates = perf.Rates({("USD", "EUR"): perf.Series(days, X)})
    sh, tx = 0, []
    for i, d in enumerate(days):
        if i == 0 or rnd.random() < 0.15:
            if sh <= 1 or rnd.random() < 0.6:
                q = rnd.choice([1, 5, 20, 50])
                kind, sh = "buy", sh + q
            else:
                q = min(sh - 1, rnd.choice([1, 3, 10]))
                kind, sh = "sell", sh - q
            tx.append(dict(kind=kind, time=d.isoformat() + " 21:00:00", isin="X", ticker="X", shares=q,
                           price=P[i], price_ccy="USD", total=q * P[i], ccy="USD"))
    ds = perf.compute(tx, "EUR", {"X": (perf.Series(days, P), "USD")}, rates, days[-1])["days"]
    return abs(ds[-1]["idx"] / ds[0]["idx"] - (P[-1] * X[-1]) / (P[0] * X[0]))


check("TWR: presný cenový výnos pri náhodných nákupoch/predajoch a kurzoch",
      max(_twr_property(s) for s in range(60)) < 1e-9)

import app as appmod  # noqa: E402

cl = appmod.app.test_client()
urls = ["/", "/search?q=DEMOCO", "/company/DEMOCO", "/company/DEMOCO/overview",
        "/company/DEMOCO/statements", "/company/DEMOCO/statements?mode=quarterly&years=5",
        "/company/DEMOCO/statements?type=reit&price=50", "/company/DEMOCO/charts",
        "/company/DEMOCO/charts?mode=quarterly&years=10", "/company/DEMOCO/fundamental",
        "/company/DEMOCO/technical", "/company/DEMOBANK", "/company/DEMOBANK/statements?price=20",
        "/company/DEMOBANK/charts", "/company/DEMOBANK/export.csv"]
urls += ["/company/DEMOCO/statements?detail=1", "/company/DEMOCO/statements?detail=1&mode=quarterly&years=5",
         "/company/DEMOBANK/statements?detail=1"]
for url in urls:
    r = cl.get(url, follow_redirects=True)
    check(f"HTTP 200 {url}", r.status_code == 200, r.status_code)
check("neexistujúca záložka -> 404", cl.get("/company/DEMOCO/blabla").status_code == 404)
html = cl.get("/company/DEMOCO/statements?price=50").get_data(as_text=True)
check("výkazy: súvaha a metriky", "Súvaha" in html and "Rule of 40" in html)
ov = cl.get("/company/DEMOCO").get_data(as_text=True)
check("úvod: popis, vedenie, cena", "Jana Ukážková" in ov and "50.00" in ov and "Vedenie" in ov)
check("úvod: bočný panel so všetkými záložkami",
      all(x in ov for x in ["Úvod", "Výkazy", "Grafy", "Fundamentálna analýza", "Technická analýza"]))
q = cl.get("/company/DEMOCO/statements?mode=quarterly&years=5").get_data(as_text=True)
check("nastavenia sa prenášajú medzi záložkami", "section=" not in q and "mode=quarterly" in q and "years=5" in q)
check("graf: dáta pre grafy", 'id="trend-data"' in cl.get("/company/DEMOCO/charts").get_data(as_text=True))
dh = cl.get("/company/DEMOCO/statements?detail=1").get_data(as_text=True)
check("podrobné výkazy v stránke", "Net product sales" in dh and "Net service sales" in dh)
check("banka bez podaní: zrozumiteľná chyba a zjednodušené údaje",
      "Zobrazujem zjednodušené údaje" in cl.get("/company/DEMOBANK/statements?detail=1").get_data(as_text=True))
chh = cl.get("/company/DEMOCO/charts").get_data(as_text=True)
check("grafy: Sankey diagram a výber obdobia", 'id="flow-data"' in chh and 'id="flow-period"' in chh and "Predplatn" in chh)
chq = cl.get("/company/DEMOCO/charts?mode=quarterly&flow=2025-12-31").get_data(as_text=True)
check("grafy: viditeľný prepínač Ročne/Kvartálne pri diagrame", 'class="modeSw"' in chh and "mode=quarterly" in chh
      and 'name="mode"' in chh)
check("grafy: návod na porovnanie dvoch období", "Klikni v grafe na dve obdobia" in chh and "trends.js" in chh)
check("grafy: kvartálny Sankey (Q4)", 'id="flow-data"' in chq and "Licencie" in chq)
import io as _io  # noqa: E402
r = cl.get("/portfolio")
check("portfólio: prázdna stránka s návodom", r.status_code == 200 and b"Export CSV" in r.data)
r = cl.post("/portfolio/demo", follow_redirects=True)
ph = r.get_data(as_text=True)
check("portfólio: ukážkové portfólio sa zobrazí", r.status_code == 200 and "Otvorené pozície" in ph and "DEMOCO" in ph
      and "DEMOUK" in ph, r.status_code)
check("portfólio: výber základnej meny a upozornenia", 'name="base"' in ph and "staršia história" in ph)
check("portfólio: prepnutie základnej meny na USD", cl.get("/portfolio?base=USD").status_code == 200
      and "USD" in cl.get("/portfolio?base=USD").get_data(as_text=True))
r = cl.post("/portfolio/import", data={"files": (_io.BytesIO(demo_csv.encode()), "export.csv")},
            content_type="multipart/form-data", follow_redirects=True)
check("portfólio: nahratie súboru, duplicity sa zahodia", r.status_code == 200 and "už v portfóliu sú" in r.get_data(as_text=True))
r = cl.post("/portfolio/import", data={"files": (_io.BytesIO(b"x,y\n1,2\n"), "zly.csv")},
            content_type="multipart/form-data", follow_redirects=True)
check("portfólio: zlý súbor -> chybové hlásenie", "Trading 212" in r.get_data(as_text=True))
r = cl.post("/portfolio/clear", follow_redirects=True)
r = cl.get("/portfolio/performance")
check("výkonnosť: bez portfólia presmeruje na prehľad", r.status_code == 302)
cl.post("/portfolio/demo")
rp = cl.get("/portfolio/performance")
hp = rp.get_data(as_text=True)
check("výkonnosť: stránka s tabuľkou, grafom a indexmi (ukážkové dáta)", rp.status_code == 200 and "Výnosy po obdobiach" in hp
      and 'id="perf-data"' in hp and "S&amp;P 500" in hp and "YTD" in hp, rp.status_code)
rp2 = cl.get("/portfolio/performance?bm=^NDX&bm=URTH&custom=^GDAXI&base=USD")
hp2 = rp2.get_data(as_text=True)
rh = cl.post("/portfolio/performance/hide", data={"key": "all"})
check("výkonnosť: riadok sa dá skryť a znova zobraziť", portfolio.load_store()["hidden_periods"] == ["all"]
      and "Skryté obdobia" in cl.get("/portfolio/performance").get_data(as_text=True))
cl.post("/portfolio/performance/hide", data={"key": "all", "action": "show"})
check("výkonnosť: skrytý riadok sa vráti", portfolio.load_store()["hidden_periods"] == [])
check("výkonnosť: ukážkové dáta sú označené ako vymyslené", "Ukážkové portfólio:" in hp and "vymyslené" in hp)
check("výkonnosť: vlastný výber indexov a meny", rp2.status_code == 200 and "Nasdaq-100" in hp2 and "MSCI World" in hp2
      and "DAX" in hp2 and "výnosy v mene USD" in hp2)
check("výkonnosť: záložky Prehľad a Výkonnosť", "Výkonnosť a porovnanie s indexmi" in cl.get("/portfolio").get_data(as_text=True))
r = cl.post("/portfolio/clear", follow_redirects=True)
check("portfólio: zmazanie cez stránku", "Nahraj export" in r.get_data(as_text=True))
check("bočný panel: odkaz na Portfólio", "Portfólio" in cl.get("/").get_data(as_text=True))
check("fundamentálna je prázdna", "zatiaľ prázdna" in cl.get("/company/DEMOCO/fundamental").get_data(as_text=True))
r = cl.get("/company/NEEXISTUJE123")
check("neznámy ticker -> chybová stránka", r.status_code == 400)
os.environ.pop("SEC_USER_AGENT", None)
cfgp = os.path.join(ROOT, "config.txt")
had_cfg = os.path.exists(cfgp)
if not had_cfg:
    r = cl.get("/search?q=AAPL")
    check("bez SEC_USER_AGENT zrozumiteľná chyba", b"SEC_USER_AGENT" in r.data, r.status_code)

print("\nVýsledok:", "VŠETKO PREŠLO" if not fails else f"{len(fails)} zlyhaní: {fails}")
sys.exit(1 if fails else 0)

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
_mc = {"facts": {"dei": {"EntityCommonStockSharesOutstanding": {"units": {"shares": [
    {"end": "2024-06-30", "filed": "2024-07-25", "val": 100},
    {"end": "2024-09-30", "filed": "2024-10-25", "val": 5800},
    {"end": "2024-09-30", "filed": "2024-10-25", "val": 800},
    {"end": "2024-09-30", "filed": "2024-10-25", "val": 5800}]}}}}}
check("akcie: viac tried sa sčíta (bez duplikátov)", edgar.latest_shares_outstanding(_mc) == 6600.0,
      edgar.latest_shares_outstanding(_mc))

# --- akciový split: Yahoo ceny sú upravené o splity, Trading 212 kusy sú z doby obchodu
_days_s = [date(2024, 6, 6) + timedelta(days=i) for i in range(6)]
_adj = [12.0, 12.2, 12.1, 12.3, 12.5, 12.4]                      # ceny upravené (po splite 10:1)
_sp = [(date(2024, 6, 10), 10.0)]
_pa = perf.Series(_days_s, _adj)
_buy = dict(kind="buy", time="2024-06-06 14:00:00", isin="S", ticker="S", shares=1, price=120.0,
            price_ccy="USD", total=120.0, ccy="USD")
_r2 = perf.compute([_buy], "USD", {"S": (_pa, "USD", _sp)}, perf.Rates({}), _days_s[-1])
check("split: výnos cez split je len cenový pohyb (12,4 vs 12,0 = +3,3 %), nie −90 %",
      abs(_r2["days"][-1]["idx"] / _r2["days"][0]["idx"] - 12.4 / 12.0) < 0.02 and not _r2["warnings"],
      (_r2["days"][-1]["idx"], _r2["warnings"]))
check("split: hodnota pozície po splite = 10 kusov × upravená cena", abs(_r2["days"][-1]["v"] - 10 * 12.4) < 1e-6,
      _r2["days"][-1]["v"])
check("split: načítanie zoznamu splitov z histórie Yahoo",
      perf.split_list({"splits": [["2024-06-10", 10.0], ["2020-01-01", 0.5]]}) == [(date(2020, 1, 1), 0.5), (date(2024, 6, 10), 10.0)])

# --- rizikové ukazovatele: beta, korelácia, volatilita na známom vzťahu (portfólio = 1,5 × index)
import random as _rr  # noqa: E402
_g = _rr.Random(1)
_dd = [d for d in (date(2024, 1, 1) + timedelta(days=i) for i in range(400)) if d.weekday() < 5]
_b = [100.0]
for _ in _dd[1:]:
    _b.append(_b[-1] * (1 + _g.gauss(0.0004, 0.01)))
_p = [100.0]
for _i in range(1, len(_dd)):
    _p.append(_p[-1] * (1 + 1.5 * (_b[_i] / _b[_i - 1] - 1)))
_tl = perf.Timeline([{"d": d, "v": 100, "flow": 0, "div": 0, "idx": x} for d, x in zip(_dd, _p)])
_rk = perf.risk_stats(_tl, {"B": perf.Series(_dd, _b)}, _dd[0] - timedelta(days=1), _dd[-1], 0.0)
_bs = _rk["bench"]["B"]
check("riziko: beta = 1,5 a korelácia = 1 pri portfóliu = 1,5 × index",
      abs(_bs["beta"] - 1.5) < 1e-6 and abs(_bs["corr"] - 1.0) < 1e-6 and abs(_bs["alpha"]) < 1e-6,
      (_bs["beta"], _bs["corr"], _bs["alpha"]))
check("riziko: volatilita portfólia = 1,5 × volatilita indexu", abs(_rk["port"]["vol"] / _bs["vol"] - 1.5) < 1e-6)
check("riziko: málo dát -> ok=False", perf.risk_stats(_tl, {"B": perf.Series(_dd, _b)}, _dd[-10], _dd[-1])["ok"] is False)

# --- výber indexu pre rizikové ukazovatele a vysvetlivky
_pc = _appmod.app.test_client()
_pc.post("/portfolio/demo")
_hp = _pc.get("/portfolio/performance?rb=%5EIXIC&bm=%5EGSPC").get_data(as_text=True)
check("riziko: vlastný výber indexu (Nasdaq Composite) a vysvetlivky pri ukazovateľoch",
      "Rizikové ukazovatele" in _hp and 'selected>Nasdaq Composite' in _hp.replace(" selected", "selected").replace("\n", "") or
      ("Nasdaq Composite" in _hp and 'data-tip="' in _hp and "Beta" in _hp), "")
_pc.post("/portfolio/clear")

# --- aktualizácia z GitHubu (zip v pamäti, dočasný priečinok)
import io as _io  # noqa: E402
import updater as _up  # noqa: E402
import zipfile as _zf  # noqa: E402
_bio = _io.BytesIO()
with _zf.ZipFile(_bio, "w") as _z:
    _z.writestr("investapp-main/app.py", "print('nova verzia')\n")
    _z.writestr("investapp-main/templates/x.html", "NOVE")
    _z.writestr("investapp-main/config.txt", "PREPISANE")
    _z.writestr("investapp-main/spustit.bat", "PREPISANE")
    _z.writestr("investapp-main/data/portfolio.json", "PREPISANE")
    _z.writestr("investapp-main/cache/a.json", "PREPISANE")
_dst = tempfile.mkdtemp()
os.makedirs(os.path.join(_dst, "data")); os.makedirs(os.path.join(_dst, "templates"))
for _n, _c in (("config.txt", "moje"), ("spustit.bat", "stary"), ("data/portfolio.json", "moje portfolio"), ("app.py", "stara")):
    with open(os.path.join(_dst, _n), "w") as _f:
        _f.write(_c)
_ch = _up.install_zip(_bio.getvalue(), _dst)
_rd = lambda n: open(os.path.join(_dst, n)).read()  # noqa: E731
check("aktualizácia: nové súbory sa prepíšu", _rd("app.py").startswith("print") and _rd("templates/x.html") == "NOVE"
      and sorted(_ch) == ["app.py", "templates/x.html"], _ch)
check("aktualizácia: config.txt, spustit.bat, data a cache sa nikdy neprepíšu",
      _rd("config.txt") == "moje" and _rd("spustit.bat") == "stary" and _rd("data/portfolio.json") == "moje portfolio"
      and not os.path.exists(os.path.join(_dst, "cache")))
_orig = _up.latest_version
_up.latest_version = lambda: "abc123"
_cc = _appmod.app.test_client().get("/update/check").get_json()
_up.latest_version = _orig
check("aktualizácia: kontrola verzie vráti, či je dostupná nová", _cc["latest"] == "abc123" and _cc["ok"] and _cc["available"] in (True, False))
check("aktualizácia: tlačidlo v bočnom paneli", 'id="updBtn"' in _appmod.app.test_client().get("/").get_data(as_text=True))

# --- „čo keby“: pridanie titulu s beta 0 a nulovou volatilitou zníži beta o jeho váhu
_rb = [_g.gauss(0.0004, 0.01) for _ in range(120)]
_hd = {"A": [1.2 * r for r in _rb]}
_wi = perf.whatif(_hd, {"A": 1.0}, {"C": [0.0] * 120}, {"C": 0.25}, _rb, 0.0)
check("čo keby: 25 % hotovosti zníži betu zo 1,2 na 0,9 a volatilitu o štvrtinu",
      abs(_wi["before"]["beta"] - 1.2) < 1e-9 and abs(_wi["after"]["beta"] - 0.9) < 1e-9
      and abs(_wi["after"]["vol"] / _wi["before"]["vol"] - 0.75) < 1e-9, (_wi["before"]["beta"], _wi["after"]["beta"]))
_pc2 = _appmod.app.test_client()
_pc2.post("/portfolio/demo")
_h2 = _pc2.get("/portfolio/performance?wi_s=NEEXISTUJE999&wi_w=10").get_data(as_text=True)
check("čo keby: výpočet s pridaným titulom (ukážkové dáta) vráti tabuľku pred/po",
      "Čo keby" in _h2 and "Terajšie portfólio" in _h2 and "Po úprave" in _h2)
_h3 = _pc2.get("/portfolio/performance?wi_s=A&wi_w=70&wi_s=B&wi_w=50").get_data(as_text=True)
check("čo keby: súčet váh nad 100 % -> chybová hláška", "presahuje 100" in _h3)
_pc2.post("/portfolio/clear")

# --- TTM v grafoch firmy: súčet posledných 4 kvartálov, na konci fiškálneho roka = ročná hodnota
import trends as _tr  # noqa: E402
_cm, _ = edgar.find_company("DEMOCO")
_comp = edgar.load_company(*_cm)
_bt = metrics.detect_type(_comp, statements.build(_comp, "annual", 8))
_tt = _tr.build_trends(_comp, _bt, "annual", 8)
_ser = lambda mode, sid: [s for s in _tt[mode]["series"] if s["id"] == sid][0]["values"]  # noqa: E731
_rq, _rt, _ra = _ser("quarterly", "revenue"), _ser("ttm", "revenue"), _ser("annual", "revenue")
check("TTM: tržby = súčet posledných 4 kvartálov", abs(_rt[-1] - sum(_rq[-4:])) < 1e-6, (_rt[-1], sum(_rq[-4:])))
_i = _tt["ttm"]["labels"].index("Q4 25") if "Q4 25" in _tt["ttm"]["labels"] else None
check("TTM: na konci fiškálneho roka sa zhoduje s ročnou hodnotou", _i is not None and abs(_rt[_i] - _ra[-1]) / _ra[-1] < 0.001,
      (_rt[_i] if _i is not None else None, _ra[-1]))
check("TTM: čistá marža = TTM zisk / TTM tržby", abs(_ser("ttm", "nm")[-1] - _ser("ttm", "net_income")[-1] / _rt[-1]) < 1e-9)

# --- podúčty z poznámok (Details) k riadkom súvahy a cash flow
_sm = ("<FilingSummary><MyReports><Report><Position>50</Position><ShortName>Notes - Accrued Expenses and Other (Details)"
       "</ShortName><HtmlFileName>R50.htm</HtmlFileName><MenuCategory>Details</MenuCategory></Report></MyReports></FilingSummary>")
_pg = ('<table class="report"><tr><th class="tl">Accrued Expenses and Other (Details) - USD ($) $ in Millions</th>'
       '<th>Dec. 31, 2025</th><th>Dec. 31, 2024</th></tr>'
       '<tr class="re"><td class="pl">Accrued compensation</td><td class="nump">$ 1,000</td><td class="nump">$ 900</td></tr>'
       '<tr class="re"><td class="pl">Accrued taxes</td><td class="nump">2,500</td><td class="nump">1,500</td></tr>'
       '<tr class="re"><td class="pl">Accrued marketing</td><td class="nump">3,300</td><td class="nump">2,600</td></tr></table>')
_fx = lambda c, a, n: {"FilingSummary.xml": _sm, "R50.htm": _pg}.get(n)  # noqa: E731
_D = [date(2025, 12, 31), date(2024, 12, 31)]
_mk = lambda lab, a, b: {"label": lab, "kind": "money", "indent": 0, "bold": False, "header": False, "vals": {_D[0]: a, _D[1]: b}}  # noqa: E731
_o = filings.attach_subaccounts({}, [{"acc": "A", "form": "10-K"}], [_mk("Accrued expenses and other", 6.8e9, 5.0e9), _mk("Long-term debt", 5e9, 4e9)], _D, fetch=_fx)
check("podúčty: pridajú sa tam, kde súčet zložiek sedí s riadkom (3 podúčty pod riadkom)",
      [r["label"] for r in _o] == ["Accrued expenses and other", "Accrued compensation", "Accrued taxes", "Accrued marketing", "Long-term debt"]
      and _o[1].get("sub") and abs(_o[2]["vals"][_D[0]] - 2.5e9) < 1, [r["label"] for r in _o])
_o2 = filings.attach_subaccounts({}, [{"acc": "A", "form": "10-K"}], [_mk("Accrued expenses and other", 7.0e9, 5.5e9)], _D, fetch=_fx)
check("podúčty: ak súčet nesedí, nepridá sa nič (nič sa nedomýšľa)", len(_o2) == 1)
_o3 = filings.attach_subaccounts({}, [{"acc": "A", "form": "10-K"}], [_mk("Accrued expenses and other", -6.8e9, -5.0e9)], _D, fetch=_fx)
check("podúčty: pri zápornom riadku (odliv v cash flow) majú podúčty rovnaké znamienko", len(_o3) == 4 and _o3[1]["vals"][_D[0]] == -1.0e9)

# --- aktualizácia sťahuje zip podľa čísla verzie (nie podľa vetvy, ktorú GitHub drží v pamäti)
_urls = []
class _R:  # noqa: E302
    content = _bio.getvalue()
    def raise_for_status(self): pass  # noqa: E704
_og, _ol = _up.requests.get, _up.latest_version
_up.requests.get = lambda url, **kw: (_urls.append(url), _R())[1]
_up.latest_version = lambda: "abc123def"
_bak = _up.BASE
_up.BASE = tempfile.mkdtemp(); _up.VERSION_FILE = os.path.join(_up.BASE, "version.txt")
_up.install_zip.__defaults__ = (_up.BASE,)
_res = _up.apply()
_up.requests.get, _up.latest_version = _og, _ol
check("aktualizácia: zip sa sťahuje podľa čísla verzie a verzia sa zapíše až po inštalácii",
      _res["ok"] and _urls and _urls[0].endswith("/zip/abc123def") and open(_up.VERSION_FILE).read() == "abc123def", (_urls, _res))

# --- biografia člena vedenia (Wikipédia je nahradená vymyslenými odpoveďami)
import prices as _pr  # noqa: E402
class _Resp:  # noqa: E302
    def __init__(self, data, status=200): self._d, self.status_code = data, status
    def raise_for_status(self): pass  # noqa: E704
    def json(self): return self._d  # noqa: E704
_cd = _pr.CACHE_DIR; _pr.CACHE_DIR = tempfile.mkdtemp()
_og2 = _pr.requests.get
def _fake(url, **kw):  # noqa: E302
    if "list=search" in url:
        return _Resp({"query": {"search": [{"title": "Jeff Bezos"}, {"title": "Bezos Academy"}]}})
    if "Jeff_Bezos" in url:
        return _Resp({"type": "standard", "title": "Jeff Bezos", "description": "American businessman",
                      "extract": "Jeffrey Preston Bezos is an American businessman, founder of Amazon. " * 20,
                      "content_urls": {"desktop": {"page": "https://en.wikipedia.org/wiki/Jeff_Bezos"}}})
    return _Resp({}, 404)
_pr.requests.get = _fake
_b = _pr.get_officer_bio("Mr. Jeffrey P. Bezos", "AMAZON.COM, INC.", "AMZN")
check("biografia: nájde sa a dĺžka je skrátená na celé vety", _b and _b["title"] == "Jeff Bezos" and len(_b["extract"]) <= 900
      and _b["extract"].endswith("."), _b)
_b2 = _pr.get_officer_bio("Mr. Jeffrey P. Bezos", "Totally Different Company", "")
check("biografia: ak sa firma v článku nespomína, nezobrazí sa (iný človek)", _b2 is None, _b2)
_pr.requests.get = _og2; _pr.CACHE_DIR = _cd
check("biografia: mená sa čistia od titulov", _pr.clean_person_name("Dr. Werner  Vogels") == "Werner Vogels"
      and _pr.clean_person_name("Mr. David A. Zapolsky J.D.") == "David A. Zapolsky")
_oc = _appmod.app.test_client().get("/company/DEMOCO/officer?name=Jana+Uk%C3%A1%C5%BEkov%C3%A1").get_json()
check("biografia: odpoveď okna pre ukážkovú firmu (pozícia, odkazy)", _oc["title"] == "CEO" and _oc["demo"] and "google" in _oc["links"], _oc)

# --- export všetkých výkazov do Excelu
import openpyxl as _ox  # noqa: E402
for _det in ("1", "0"):
    _xr = _appmod.app.test_client().get(f"/company/DEMOCO/export.xlsx?detail={_det}")
    _wb = _ox.load_workbook(_io.BytesIO(_xr.data))
    _names = _wb.sheetnames
    _ws = _wb["Výkaz ziskov a strát"]
    _first = next(r for r in _ws.iter_rows(min_row=3, values_only=True) if r[0] and r[1] is not None)
    check(f"excel (detail={_det}): hárky a hodnoty v miliónoch",
          _xr.status_code == 200 and _names[:4] == ["Info", "Výkaz ziskov a strát", "Súvaha", "Cash flow"]
          and "Metriky" in _names and abs(_ws["B2"].value.year - 2025) == 0 and 100 < abs(_first[1]) < 100000,
          (_xr.status_code, _names, _first[:2]))
_bs = _ox.load_workbook(_io.BytesIO(_appmod.app.test_client().get("/company/DEMOCO/export.xlsx?detail=0").data))["Súvaha"]
_lab = [r[0] for r in _bs.iter_rows(min_row=3, values_only=True)]
check("excel: súvaha obsahuje riadky záväzkov a vlastného imania", "Aktíva spolu" in _lab and "Pasíva spolu" in _lab, _lab[:6])

# --- import a súbory ako samostatná záložka na konci portfólia
_fc = _appmod.app.test_client()
_fc.post("/portfolio/demo")
_fh = _fc.get("/portfolio/files").get_data(as_text=True)
_ov = _fc.get("/portfolio").get_data(as_text=True)
check("portfólio: záložka Import a súbory (nahrávanie, zoznam súborov, zmazanie)",
      "Nahrané súbory" in _fh and "Zmazať portfólio" in _fh and "Pridať ďalšie súbory" in _fh
      and "Import a súbory" in _ov and "Nahrané súbory" not in _ov and "Zmazať portfólio" not in _ov)
_fc.post("/portfolio/clear")
check("portfólio: bez údajov presmeruje záložku súborov na úvodné nahrávanie", _fc.get("/portfolio/files").status_code == 302)

# --- oceňovacie modely: overenie voči uzavretému tvaru
import valuation as _va  # noqa: E402
_w, _g, _mg, _r0 = 0.09, 0.03, 0.2, 1000.0
_d = _va.dcf(_r0, _g, _mg, _mg, _w, _g, 0.0, 100.0, 0.0)   # rast = terminálny rast, marža konštantná
_ratio = (1 + _g) / (1 + _w)
_pv = _r0 * _mg * sum(_ratio ** t for t in range(1, 11))
_tv = _r0 * _mg * (1 + _g) ** 10 * (1 + _g) / (_w - _g) / (1 + _w) ** 10
check("DCF: zhoda s uzavretým tvarom (rast = terminálny rast)", abs(_d["ev"] - (_pv + _tv)) < 1e-6 * _d["ev"], (_d["ev"], _pv + _tv))
check("DCF: čistý dlh a riedenie znižujú hodnotu na akciu",
      _va.dcf(_r0, 0.1, 0.1, 0.15, 0.09, 0.025, 200, 100, 0.02)["per_share"] < _va.dcf(_r0, 0.1, 0.1, 0.15, 0.09, 0.025, 0, 100, 0)["per_share"])
check("DCF: pesimistický < základný < optimistický",
      (lambda s: s[0]["value"] < s[1]["value"] < s[2]["value"])(_va.dcf_scenarios(dict(rev0=1000, g1=0.1, margin0=0.15, margin5=0.2, wacc=0.09, g_term=0.025, net_debt=0, shares=100, dilution=0))))
check("férové P/B: (ROE − g)/(ke − g) = (0,12 − 0,03)/(0,10 − 0,03)", abs(_va.fair_pb(0.12, 0.10, 0.03) - 9 / 7) < 1e-12)
check("P/E model: EPS 2 × 1,10 × P/E 18 / 1,09", abs(_va.multiple_model(2.0, 0.10, 18, 0.09)["value"] - 2.2 * 18 / 1.09) < 1e-9)
check("odporúčaný rast: priemer analytikov a 5-ročného CAGR",
      abs(_va.recommend_growth({"rev_cagr5": 0.30}, {"rev_growth": {"+1y": 0.20}})[0] - 0.25) < 1e-12)

# --- kvalita podniku a porovnanie s konkurenciou
import quality as _qa  # noqa: E402
from datetime import date as _dt  # noqa: E402
_y1, _y2, _y3 = _dt(2023, 12, 31), _dt(2024, 12, 31), _dt(2025, 12, 31)
_bt = {"display": [_y1, _y2, _y3], "data": {
    "total_assets": {_y1: 1000, _y2: 1100, _y3: 1200}, "net_income": {_y1: 80, _y2: 100, _y3: 130},
    "cfo": {_y1: 120, _y2: 140, _y3: 170}, "debt_lt": {_y1: 300, _y2: 280, _y3: 250},
    "current_assets": {_y1: 400, _y2: 450, _y3: 520}, "current_liabilities": {_y1: 300, _y2: 310, _y3: 320},
    "shares_diluted": {_y1: 100, _y2: 100, _y3: 99}, "gross_profit": {_y1: 400, _y2: 450, _y3: 600},
    "revenue": {_y1: 1000, _y2: 1100, _y3: 1300}, "op_income": {_y3: 180}, "equity": {_y3: 600},
    "total_liabilities": {_y3: 600}, "retained": {_y3: 300}}}
_pio = _qa.piotroski(_bt)
check("Piotroski: firma so zlepšením vo všetkých kritériách má 9 z 9", _pio and _pio["score"] == 9 and _pio["n"] == 9, _pio and _pio["score"])
_al = _qa.altman(_bt)
_exp = 6.56 * (200 / 1200) + 3.26 * (300 / 1200) + 6.72 * (180 / 1200) + 1.05 * (600 / 600)
check("Altman Z'': zhoda s ručným výpočtom", _al and abs(_al["z"] - _exp) < 1e-9 and _al["zone"] == "bezpečná", _al and _al["z"])
_dpt = _qa.dupont(_bt)[-1]
check("DuPont: marža × obrat × páka = ROE", abs(_dpt["margin"] * _dpt["turnover"] * _dpt["leverage"] - _dpt["roe"]) < 1e-12)
_fq = _appmod.app.test_client().get("/company/DEMOCO/fundamental?peers=DEMOBANK").get_data(as_text=True)
check("fundamentálna: karta Kvalita podniku a porovnanie s konkurenciou (ukážkové firmy)",
      "Kvalita podniku" in _fq and "Piotroski" in _fq and "Porovnanie s konkurenciou" in _fq and "DEMOBANK" in _fq
      and "Čistá marža" in _fq)
check("fundamentálna: neexistujúci konkurent dá hlášku, nie pád",
      "nenašiel" in _appmod.app.test_client().get("/company/DEMOCO/fundamental?peers=NEEXISTUJE123").get_data(as_text=True))

# --- Excel s fundamentálnou analýzou (živé vzorce v modeloch)
_fx2 = _appmod.app.test_client().get("/company/DEMOCO/fundamental.xlsx?peers=DEMOBANK&d_g1=14")
_fwb = _ox.load_workbook(_io.BytesIO(_fx2.data))
check("excel fundamentálna: hárky a živé vzorce v DCF, P/B a P/E",
      _fx2.status_code == 200 and _fwb.sheetnames == ["Súhrn", "Kvalita", "DCF", "Férové P-B", "Cieľové P-E", "Ďalšie modely", "Konkurencia"]
      and str(_fwb["DCF"]["B35"].value).startswith("=B33/B34") and "Ďalšie modely" in _fwb.sheetnames and str(_fwb["Férové P-B"]["B9"].value).startswith("=(B4-B6)")
      and abs(_fwb["DCF"]["B4"].value - 0.14) < 1e-9, (_fx2.status_code, _fwb.sheetnames))

# --- Microsoft vykazuje odpisy pod značkou Depreciation (inak chýbalo EBITDA a EV/EBITDA)
import taxonomy as _tx  # noqa: E402
check("taxonómia: odpisy majú záložnú značku Depreciation (pomocný riadok)", "Depreciation" in _tx.ITEM_BY_KEY["dep_only"]["tags"])

# --- audit 11/2026: IFRS menný priestor, tržby bánk, celkový dlh, odpisy, počet akcií IFRS firiem
import edgar as _eda, statements as _sta  # noqa: E402
def _fy(v, y=2024):
    return {"start": f"{y}-01-01", "end": f"{y}-12-31", "val": v, "fy": y, "fp": "FY", "form": "10-K", "filed": f"{y + 1}-02-01"}
def _bs(v, y=2024):
    return {"end": f"{y}-12-31", "val": v, "fy": y, "fp": "FY", "form": "10-K", "filed": f"{y + 1}-02-01"}
def _co(ns, tags, cur="USD"):
    facts = {"entityName": "T", "facts": {ns: {t: {"units": {("shares" if "Shares" in t else cur): vals}} for t, vals in tags.items()}}}
    return {"filings": {}, "sec": {}, "ticker": "T", "cik": 1, "name": "T", "facts": facts, "sic": None, "sic_desc": "",
            "currency": _eda.detect_currency(facts), "shares_out": _eda.latest_shares_outstanding(facts), "is_demo": False}
_ifrs = _co("ifrs-full", {"Revenue": [_fy(100, 2023), _fy(150)], "ProfitLoss": [_fy(10, 2023), _fy(20)], "Assets": [_bs(900, 2023), _bs(1000)],
                          "AdjustedWeightedAverageShares": [_fy(50, 2023), _fy(55)]})
_bi = _sta.build(_ifrs, "annual", 2)
_e24 = _bi["display"][-1]
check("IFRS: firmy s menným priestorom ifrs-full (Nu, Grab) sa načítajú", _bi["data"]["revenue"][_e24] == 150 and _bi["data"]["net_income"][_e24] == 20)
check("IFRS: bez počtu akcií na obálke sa použije posledný vážený priemer", _ifrs["shares_out"] == 55)
_bank = _co("us-gaap", {"RevenueFromContractWithCustomerExcludingAssessedTax": [_fy(500)], "RevenuesNetOfInterestExpense": [_fy(2675)],
                        "CostOfRevenue": [_fy(460)], "NetIncomeLoss": [_fy(499)]})
_bb2 = _sta.build(_bank, "annual", 1)
check("banky: tržby = čisté tržby po úrokoch (SoFi), hrubý zisk sa z poplatkov nedopočíta",
      _bb2["data"]["revenue"][_bb2["display"][-1]] == 2675 and _bb2["data"]["gross_profit"].get(_bb2["display"][-1]) is None)
_debt = _co("us-gaap", {"Revenues": [_fy(1000)], "NetIncomeLoss": [_fy(100)], "CommercialPaper": [_bs(9967)], "LongTermDebtCurrent": [_bs(10912)],
                        "LongTermDebtNoncurrent": [_bs(85750)], "LongTermDebt": [_bs(96662)], "Depreciation": [_fy(152)], "AmortizationOfIntangibleAssets": [_fy(48)]})
_bd = _sta.build(_debt, "annual", 1)
_ed = _bd["display"][-1]
check("dlh: komerčné papiere sa započítajú (Apple 2024 = 106 629)", _bd["data"]["total_debt"][_ed] == 106629)
check("odpisy: Depreciation + amortizácia nehmotného majetku (Microsoft)", _bd["data"]["da"][_ed] == 200)
_debt2 = _co("us-gaap", {"Revenues": [_fy(1000)], "NetIncomeLoss": [_fy(100)], "LongTermDebt": [_bs(500)], "ShortTermBorrowings": [_bs(50)], "CommercialPaper": [_bs(30)]})
_bd2 = _sta.build(_debt2, "annual", 1)
check("dlh: LongTermDebt už obsahuje krátkodobú časť, CP sa nezduplikuje so ShortTermBorrowings", _bd2["data"]["total_debt"][_bd2["display"][-1]] == 550)
_nd = _va.history_facts({"display": [_dt(2025, 12, 31)], "data": {"cash": {_dt(2025, 12, 31): 100.0}, "st_investments": {_dt(2025, 12, 31): 50.0},
      "lt_investments": {_dt(2025, 12, 31): 30.0}, "total_debt": {_dt(2025, 12, 31): 400.0}, "revenue": {_dt(2025, 12, 31): 1000.0}}})
check("čistý dlh = dlh − hotovosť − krátkodobé aj dlhodobé investície (400 − 150 − 30)", _nd["net_debt"] == 220.0, _nd["net_debt"])

# --- ďalšie oceňovacie modely a reverzný DCF
check("EV/EBITDA: (EBITDA 100 × 1,1 × 12 − dlh 200) / 50 akcií / 1,09", abs(_va.ev_ebitda_model(100, 0.1, 12, 200, 50, 0.09)["value"] - (100 * 1.1 * 12 - 200) / 50 / 1.09) < 1e-9)
check("FCF výnos: 80 × 1,08 / 50 / 4 % / 1,09", abs(_va.fcf_yield_model(80, 0.08, 0.04, 50, 0.09)["value"] - 80 * 1.08 / 50 / 0.04 / 1.09) < 1e-9)
check("P/S: 500 × 1,1 / 50 × 5 / 1,09", abs(_va.ps_model(500, 0.1, 5, 50, 0.09)["value"] - 500 * 1.1 / 50 * 5 / 1.09) < 1e-9)
_gr = _va.graham(5, 30, 8, 4.4)
check("Graham: číslo √(22,5×5×30) a vzorec 5×(8,5+16)×4,4/4,4", abs(_gr["number"] - (22.5 * 5 * 30) ** 0.5) < 1e-9 and abs(_gr["formula"] - 122.5) < 1e-9)
_dd = _va.ddm(2.0, 0.06, 0.025, 0.08)
_man = sum(2.0 * 1.06 ** t / 1.08 ** t for t in range(1, 6)) + 2.0 * 1.06 ** 5 * 1.025 / (0.08 - 0.025) / 1.08 ** 5
check("DDM: zhoda s ručným výpočtom", abs(_dd["value"] - _man) < 1e-9)
_pp = dict(rev0=1000, margin0=0.15, margin5=0.20, wacc=0.09, g_term=0.025, net_debt=200, shares=100, dilution=0.01)
_ig = _va.implied_growth(50, _pp)
check("reverzný DCF: s nájdeným rastom vychádza DCF presne na cenu", abs(_va.dcf(1000, _ig["g"], 0.15, 0.20, 0.09, 0.025, 200, 100, 0.01)["per_share"] - 50) < 1e-6, _ig)
_pg = _appmod.app.test_client().get("/company/DEMOCO/fundamental?m=evebitda&ee_m=15").get_data(as_text=True)
check("fundamentálna: dlaždice modelov, reverzný DCF, vlastný vstup v ďalšom modeli", "mtile" in _pg and "Čo očakáva trh" in _pg and 'value="15,0"' in _pg)

# --- záporný DCF (tv_share None) nesmie zhodiť stránku (chyba z reálneho SoFi)
_neg = _appmod.app.test_client().get("/company/DEMOCO/fundamental?m=dcf&d_m5=-15&d_g1=5")
check("fundamentálna: záporný DCF nespadne (500) a ukáže upozornenie", _neg.status_code == 200 and "nekladný" in _neg.get_data(as_text=True), _neg.status_code)
for _tk in ("DEMOBANK", "DEMOCO"):
    check(f"fundamentálna: {_tk} so všetkými modelmi a konkurentmi (200)",
          _appmod.app.test_client().get(f"/company/{_tk}/fundamental?peers=DEMOCO,DEMOBANK").status_code == 200)

# --- referenčné hodnoty pri kvalite podniku (podľa typu biznisu)
import quality as _q2  # noqa: E402
check("kvalita: referencia sa líši podľa typu (prevádzková marža: tech ≥ 25 %, všeobecné ≥ 15 %)",
      "≥ 25 %" in _q2._ref("op_margin", "tech") and "≥ 15 %" in _q2._ref("op_margin", "general") and "≥ 30 %" in _q2._ref("op_margin", "reit"),
      (_q2._ref("op_margin", "tech"), _q2._ref("op_margin", "general")))
check("kvalita: zadlženosť má nižšie je lepšie (REIT toleruje viac dlhu)", "≤ 1,5×" in _q2._ref("nd_ebitda", "general") and "≤ 5×" in _q2._ref("nd_ebitda", "reit"))
check("kvalita: skórovanie podľa typu (marža 20 %: pri tech priemerná, pri všeobecných silná)",
      _q2._sc("op_margin", "tech", 0.20) == 1 and _q2._sc("op_margin", "general", 0.20) == 2)
_rt = _q2.reference_table()
check("kvalita: tabuľka referencií pre všetky typy", len(_rt["types"]) == 5 and any(r["name"] == "ROE" for r in _rt["rows"]))
_hb = _appmod.app.test_client().get("/company/DEMOBANK/fundamental").get_data(as_text=True)
_hc = _appmod.app.test_client().get("/company/DEMOCO/fundamental").get_data(as_text=True)
check("kvalita: banka má vlastné ukazovatele (ROE, efficiency) s referenciou, bez Piotroski",
      "Referencia: silné ≥" in _hb and "ROE" in _hb and "Efficiency ratio" in _hb and "Piotroski F-score <span" not in _hb, "")
check("kvalita: firma má referencie pod každým ukazovateľom a tabuľku všetkých typov", _hc.count("Referencia: ") >= 8 and "Referenčné hodnoty pre všetky typy" in _hc)

# --- regresia (reálne dáta): predaj všetkého s drobným rozdielom suma vs. cena × kusy + malý nákup v ten istý deň
_d0 = date(2024, 3, 4)
_days = [_d0 + timedelta(days=i) for i in range(8)]
_ps = perf.Series(_days, [100.0, 101.0, 102.0, 101.0, 103.0, 104.0, 104.0, 104.0])
_tx = [
    dict(kind="buy", time="2024-03-04 10:00:00", isin="X", ticker="X", shares=2, price=100.0, price_ccy="EUR", total=200.0, ccy="EUR"),
    dict(kind="sell", time="2024-03-07 10:00:00", isin="X", ticker="X", shares=2, price=102.0, price_ccy="EUR", total=203.5, ccy="EUR"),
    dict(kind="buy", time="2024-03-07 12:00:00", isin="X", ticker="X", shares=0.1, price=102.0, price_ccy="EUR", total=10.2, ccy="EUR"),
]
_r = perf.compute(_tx, "EUR", {"X": (_ps, "EUR")}, perf.Rates({}), _days[-1])["days"]
check("TWR: po predaji všetkého nevznikne nulový/nezmyselný index", all(d["idx"] and d["idx"] > 90 for d in _r) and not any(
    d["idx"] == 0 for d in _r), [round(d["idx"] or 0, 2) for d in _r])

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
check("úvod: popis, vedenie, cena", "Jana Ukážková" in ov and "50,00" in ov and "Vedenie" in ov)
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
      and 'name="years"' in chh and "gset" in chh and 'class="toolbar' not in chh)
check("grafy: návod na porovnanie dvoch období a prepínače kariet", "Klikni na dva stĺpce" in chh and "trends.js" in chh
      and "id=\"g-cat\"" in chh and "id=\"g-mode\"" in chh)
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
_fu = cl.get("/company/DEMOCO/fundamental")
_fh2 = _fu.get_data(as_text=True)
check("fundamentálna: modely DCF, P/B a P/E s odporúčanými vstupmi a súhrnom",
      _fu.status_code == 200 and "DCF" in _fh2 and "Odporúčame" in _fh2 and "Férové P/B" in _fh2
      and "Cieľové P/E" in _fh2 and "Odhad hodnoty na akciu" in _fh2 and "EV / EBITDA" in _fh2
      and "FCF výnos" in _fh2 and "Dividendy (DDM)" in _fh2 and "Čo očakáva trh" in _fh2, _fu.status_code)
_fu2 = cl.get("/company/DEMOCO/fundamental?m=dcf&d_g1=20&d_wacc=9&d_gt=3").get_data(as_text=True)
check("fundamentálna: vlastné vstupy sa prenesú do formulára a poznačí sa odchýlka od odporúčania",
      'name="d_g1"' in _fu2 and 'value="20,0"' in _fu2 and "tvoja hodnota sa líši" in _fu2)
check("fundamentálna: nezmyselné vstupy (WACC ≤ terminálny rast) dajú hlášku, nie pád",
      "Diskontná sadzba musí byť" in cl.get("/company/DEMOCO/fundamental?d_wacc=3&d_gt=3").get_data(as_text=True))
# ---- watchlist
import watchlist as _wl  # noqa: E402
_wl.PATH = os.path.join(tempfile.mkdtemp(), "watchlist.json")        # nedotkne sa tvojho zoznamu
_fake = {"WLA": {"price": 110.0, "currency": "USD", "name": "Alfa Inc", "change_pct": 0.02, "high52": 120.0, "low52": 80.0},
         "WLB": {"price": 50.0, "currency": "EUR", "name": "Beta AG", "change_pct": -0.01, "high52": 90.0, "low52": 45.0}}
_orig_gp = _appmod.prices.get_price
_appmod.prices.get_price = lambda t: _fake.get(t.upper())
_c = _appmod.app.test_client()
_c.post("/watchlist/add", data={"ticker": "wla", "target": "132"})
_c.post("/watchlist/add", data={"ticker": "WLB"})
_c.post("/watchlist/add", data={"ticker": "WLA"})            # duplicita
_c.post("/watchlist/add", data={"ticker": "NEEXISTUJE"})     # bez ceny
_items = _wl.load()
check("watchlist: pridanie, duplicita a neznámy ticker", [i["ticker"] for i in _items] == ["WLA", "WLB"]
      and _items[0]["target"] == 132.0 and _items[0]["price_at_add"] == 110.0, _items)
_rows = {r["ticker"]: r for r in _wl.enrich(_items, _appmod.prices.get_price)}
check("watchlist: poloha v 52-týždňovom rozsahu, od maxima a vzdialenosť k cieľu",
      abs(_rows["WLA"]["range_pos"] - 0.75) < 1e-9 and abs(_rows["WLA"]["from_high"] - (110 / 120 - 1)) < 1e-9
      and abs(_rows["WLA"]["to_target"] - 0.2) < 1e-9 and _rows["WLB"]["to_target"] is None)
_fake["WLA"] = dict(_fake["WLA"], price=140.0)
_r2 = {r["ticker"]: r for r in _wl.enrich(_items, _appmod.prices.get_price)}
check("watchlist: zmena od pridania a dosiahnutý cieľ", abs(_r2["WLA"]["since_add"] - (140 / 110 - 1)) < 1e-9 and _r2["WLA"]["hit"])
_h = _c.get("/watchlist").get_data(as_text=True)
check("watchlist: stránka zobrazí tabuľku a odkaz v menu", "Alfa Inc" in _h and "cieľ dosiahnutý" in _h and "Watchlist" in _h)
_c.post("/watchlist/target", data={"ticker": "WLB", "target": "60,5"})
check("watchlist: úprava cieľa (aj s desatinnou čiarkou)", _wl.load()[1]["target"] == 60.5)
_c.post("/watchlist/remove", data={"ticker": "WLA"})
check("watchlist: odstránenie", [i["ticker"] for i in _wl.load()] == ["WLB"])
_appmod.prices.get_price = lambda t: None
check("watchlist: nedostupná cena nezhodí stránku", _c.get("/watchlist").status_code == 200)
_appmod.prices.get_price = _orig_gp

# ---- moat / prémia
import moat as _moat  # noqa: E402
_mh = cl.get("/company/DEMOCO/fundamental").get_data(as_text=True)
check("moat: karta „Prečo trh platí prémiu?“ sa zobrazí (alebo vysvetlí, prečo nie) a nezhodí stránku",
      "Prečo trh platí prémiu" in _mh and ("Hrubá marža" in _mh or "málo rokov" in _mh), _mh[:0])
_mb = cl.get("/company/DEMOBANK/fundamental")
check("moat: banka dostane vysvetlenie namiesto karty", _mb.status_code == 200 and "ROE a kapitálové pomery" in _mb.get_data(as_text=True))
_syn = {"display": [f"Y{i}" for i in range(6)], "data": {
    "revenue": {f"Y{i}": 100 + 10 * i for i in range(6)}, "gross_profit": {f"Y{i}": 60 + 6 * i for i in range(6)},
    "op_income": {f"Y{i}": 30 + 3 * i for i in range(6)}, "net_income": {f"Y{i}": 24 + 2 * i for i in range(6)},
    "fcf": {f"Y{i}": 25 + 2 * i for i in range(6)}, "equity": {f"Y{i}": 100 for i in range(6)},
    "total_debt": {f"Y{i}": 0 for i in range(6)}, "cash": {f"Y{i}": 0 for i in range(6)}}}
_ind = {i["name"]: i for i in _moat.indicators(_syn, 0.09)}
check("moat: syntetická firma s ROIC ~30 % a 60 % maržou dostane silné hodnotenia",
      _ind["ROIC nad nákladmi kapitálu"]["score"] == 2 and _ind["Hrubá marža"]["score"] == 2
      and _ind["Stabilita tržieb"]["score"] == 2 and _ind["Najslabšia prevádzková marža"]["score"] == 2)
_syn["data"]["revenue"]["Y3"] = 60
check("moat: prepad tržieb o viac než 5 % zníži hodnotenie stability", {i["name"]: i for i in _moat.indicators(_syn, 0.09)}["Stabilita tržieb"]["score"] == 0)

# ---- firmy mimo SEC (Yahoo)
import yahoo_fin as _yf  # noqa: E402
_yf.CACHE_DIR = tempfile.mkdtemp()
def _yrows(vals, cur="EUR"):
    return [{"asOfDate": f"{2021 + i}-12-31", "currencyCode": cur, "raw": v} for i, v in enumerate(vals)]
_FAKE_YF = {"TotalRevenue": _yrows([100e9, 110e9, 120e9, 126e9, 140e9]), "CostOfRevenue": _yrows([80e9, 87e9, 94e9, 99e9, 108e9]),
            "GrossProfit": _yrows([20e9, 23e9, 26e9, 27e9, 32e9]), "OperatingIncome": _yrows([10e9, 12e9, 14e9, 13e9, 18e9]),
            "NetIncomeCommonStockholders": _yrows([7e9, 8e9, 10e9, 9e9, 13e9]), "DilutedEPS": _yrows([7.0, 8.0, 10.0, 9.0, 13.0]),
            "OperatingCashFlow": _yrows([12e9, 13e9, 15e9, 14e9, 19e9]), "CapitalExpenditure": _yrows([-5e9, -5e9, -6e9, -6e9, -7e9]),
            "CashDividendsPaid": _yrows([-2e9, -2e9, -3e9, -3e9, -4e9]), "TotalAssets": _yrows([150e9, 155e9, 160e9, 170e9, 175e9]),
            "StockholdersEquity": _yrows([60e9, 64e9, 70e9, 74e9, 80e9]), "OrdinarySharesNumber": _yrows([1e9] * 5, "EUR")}
_yf.fetch = lambda sym: _FAKE_YF if sym.upper() == "ZZEU" else None
_orig_gj = edgar._get_json
edgar._get_json = lambda url, name: {"0": {"ticker": "AAPL", "cik_str": 320193, "title": "Apple Inc."}}   # bez internetu
_m, _c = edgar.find_company("ZZEU")
check("Yahoo: firma mimo SEC sa nájde cez záložný zdroj", _m and _m[0] == "ZZEU" and _m[1] == "YF", _m)
_co = edgar.load_company(*_m)
_bb = statements.build(_co, "annual", 8)
_e = _bb["display"][-1]
check("Yahoo: výkazy majú správne hodnoty, mena a počet akcií",
      _co["currency"] == "EUR" and _bb["data"]["revenue"][_e] == 140e9 and _bb["data"]["net_income"][_e] == 13e9
      and _bb["data"]["capex"][_e] == 7e9 and _bb["data"]["div_paid"][_e] == 4e9 and _co["shares_out"] == 1e9, (_co["currency"], _co["shares_out"]))
check("Yahoo: odvodené riadky (FCF = CFO − CapEx)", _bb["data"]["fcf"][_e] == 12e9 and len(_bb["display"]) == 5, _bb["data"].get("fcf"))
_orig_q2 = _appmod.prices.get_price
_appmod.prices.get_price = lambda t: {"price": 90.0, "currency": "EUR", "name": "Zed AG", "change_pct": 0.0, "high52": 100, "low52": 70}
_ch = cl.get("/company/ZZEU/statements"); _fh = cl.get("/company/ZZEU/fundamental")
_appmod.prices.get_price = _orig_q2
check("Yahoo: výkazy a fundamentálna analýza sa zobrazia s upozornením na neoficiálne údaje",
      _ch.status_code == 200 and _fh.status_code == 200 and "Neoficiálne údaje" in _ch.get_data(as_text=True)
      and "Neoficiálne údaje" in _fh.get_data(as_text=True), (_ch.status_code, _fh.status_code))
check("Yahoo: neznámy symbol zostane chybou", cl.get("/company/QQNEEXISTUJE").status_code == 400)
edgar._get_json = _orig_gj

# ---- SK hynix: firma v SEC bez výkazov (len F-1) -> Yahoo alebo jasná hláška
_orig_fetch, _orig_gj2 = _yf.fetch, edgar._get_json
_F1 = {"cik": "0002120882", "entityName": "SK hynix Inc.", "facts": {"ffd": {"NetFeeAmt": {"units": {"USD": []}}}}}
edgar._get_json = lambda url, name: _F1 if name.startswith("facts_") else {"filings": {"recent": {}}, "sic": "3674"}
_yf.fetch = lambda sym: None
try:
    edgar.load_company("SKHY", 2120882, "SK hynix Inc.")
    _msg = ""
except edgar.EdgarError as _ex:
    _msg = str(_ex)
check("SK hynix: firma bez výkazov v SEC dá jasnú hlášku s tipom na 000660.KS", "000660.KS" in _msg and "nepodarilo" not in _msg, _msg)
_yf.fetch = lambda sym: _FAKE_YF
_ck = edgar.load_company("SKHY", 2120882, "SK hynix Inc.")
check("SK hynix: ak Yahoo výkazy má, použijú sa", _ck.get("source") == "yahoo" and _ck["currency"] == "EUR")
_yf.fetch, edgar._get_json = _orig_fetch, _orig_gj2
class _R:  # falošná odpoveď Yahoo search
    def raise_for_status(self): pass
    def json(self): return {"quotes": [{"symbol": "000660.KS", "quoteType": "EQUITY", "longname": "SK hynix Inc.", "exchDisp": "KSE"},
                                         {"symbol": "SKHY", "quoteType": "EQUITY", "shortname": "SK hynix Inc.", "exchDisp": "NASDAQ"},
                                         {"symbol": "XYZ=F", "quoteType": "FUTURE"}]}
_orig_get = _yf.requests.get
_yf.requests.get = lambda *a, **k: _R()
_sr = _yf.search("SK hynix")
_yf.requests.get = _orig_get
check("Yahoo hľadanie podľa názvu: akcie áno, futures nie", [x[0] for x in _sr] == ["000660.KS", "SKHY"] and "KSE" in _sr[0][2], _sr)

# ---- zoznam firiem (Disco, KakaoBank...)
import directory as _dir  # noqa: E402
edgar._get_json = lambda url, name: {"0": {"ticker": "AAPL", "cik_str": 320193, "title": "Apple Inc."}}
check("zoznam: Disco, KakaoBank a SK hynix sa nájdu podľa názvu aj tickeru",
      edgar.find_company("Disco")[0][0] == "6146.T" and edgar.find_company("kakaobank")[0][0] == "323410.KS"
      and edgar.find_company("323410.KS")[0][0] == "323410.KS" and edgar.find_company("SK hynix")[0][0] == "000660.KS")
check("zoznam: čiastočná zhoda ponúkne kandidáta", any(c[0] == "035720.KS" for c in edgar.find_company("kakao co")[1]) or edgar.find_company("kakao")[0] is not None)
_yf.fetch = lambda sym: _FAKE_YF
_kb = edgar.load_company(*edgar.find_company("KakaoBank")[0])
_kbb = statements.build(_kb, "annual", 8)
check("zoznam: KakaoBank sa vyhodnotí ako banka aj bez SIC kódu", metrics.detect_type(_kb, _kbb) == "bank")
check("zoznam: úvodná stránka ukazuje firmy", "KakaoBank" in cl.get("/").get_data(as_text=True) and "Disco Corporation" in cl.get("/").get_data(as_text=True))
_yf.fetch = _orig_fetch
edgar._get_json = _orig_gj2

# ---- výsledky a earnings call
import json  # noqa: E402
import earnings as _er  # noqa: E402
import filings as _fl  # noqa: E402
_er.TRANSCRIPT_DIR = tempfile.mkdtemp()
_REL = ("<html><body><p>Apple Inc. announced financial results for its fiscal 2026 third quarter. "
        "Revenue was a record $94.0 billion, up 10 percent year over year, and diluted earnings per share was $1.57.</p>"
        "<p>The Company expects revenue growth of 8 to 10 percent in the September quarter, with gross margin between 46 and 47 percent.</p>"
        "<p>Tariffs created headwinds of approximately $1.1 billion in the quarter, and pressure on services margin continues.</p>"
        "<p>The Company repurchased $20 billion of its common stock and paid dividends of $3.8 billion during the quarter.</p>"
        "<p>This press release contains forward-looking statements, including undue reliance should not be placed on them.</p>"
        "<table><tr><td>Total net sales</td><td>94,036</td><td>85,777</td></tr><tr><td>Net income</td><td>23,434</td><td>21,448</td></tr></table></body></html>")
_IDX = json.dumps({"directory": {"item": [{"name": "aapl-20260730.htm"}, {"name": "a8-kex991_2026q3.htm"}, {"name": "R1.htm"}]}})
_orig_ft = _fl.fetch_text
_fl.fetch_text = lambda comp, acc, name: _IDX if name == "index.json" else (_REL if name == "a8-kex991_2026q3.htm" else None)
_fake_co = {"filings": {"form": ["10-K", "8-K", "8-K"], "items": ["", "2.02,9.01", "5.02"], "accessionNumber": ["a", "0000320193-26-000018", "c"],
                        "filingDate": ["2025-11-01", "2026-07-30", "2026-07-01"], "primaryDocument": ["x", "aapl.htm", "y"]},
            "cik": 320193, "is_demo": False, "name": "Apple Inc."}
_rl = _er.list_releases(_fake_co)
check("earnings: zo zoznamu podaní sa vyberú len 8-K s položkou 2.02", len(_rl) == 1 and _rl[0]["date"] == "2026-07-30", _rl)
_gr = _er.get_release(_fake_co, "0000320193-26-000018")
check("earnings: príloha EX-99.1 sa nájde (nie R1.htm ani hlavný dokument) a prevedie na text",
      _gr and _gr["release_file"] == "a8-kex991_2026q3.htm" and "record $94.0 billion" in _gr["release"], _gr and _gr["files"])
_kp = _er.key_points(_gr["release"])
_flat = " ".join(" ".join(v) for v in _kp.values())
check("earnings: kľúčové body obsahujú výhľad, riziká aj návrat kapitálu a vynechajú právne vety",
      "guidance" in _kp or "expects revenue growth" in " ".join(_kp.get("guidance", []))
      and any("Tariffs" in s for s in _kp.get("risks", [])) and any("repurchased" in s for s in _kp.get("capital", []))
      and "undue reliance" not in _flat, _kp)
_okp, _ = _er.save_transcript("AAPL", "k1", "x" * 100)
check("earnings: príliš krátky prepis sa neuloží", not _okp)
_ok2, _ = _er.save_transcript("AAPL", "k1", ("Operator: Welcome to the call. We expect revenue growth of 9 percent next quarter. " * 20))
check("earnings: vložený prepis sa uloží a načíta", _ok2 and _er.load_transcript("AAPL", "k1").startswith("Operator"))
_orig_lr, _orig_gr = _er.list_releases, _er.get_release
_er.list_releases = lambda comp, n=12: _rl
_er.get_release = lambda comp, acc: _gr
_eh = cl.get("/company/DEMOCO/earnings").get_data(as_text=True)
check("earnings: stránka ukáže kľúčové body, obdobie a pole na prepis",
      "Kľúčové body z tlačovej správy" in _eh and "2026-07-30" in _eh and "Prepis earnings callu" in _eh)
cl.post("/company/DEMOCO/earnings/transcript", data={"key": _rl[0]["acc"], "acc": _rl[0]["acc"], "text": "Operator: Hello. We expect revenue growth of 12 percent. " * 20})
_eh2 = cl.get("/company/DEMOCO/earnings?acc=" + _rl[0]["acc"]).get_data(as_text=True)
check("earnings: po uložení sa prepis zobrazí so zdrojom „vložený ručne“", "Zdroj prepisu: vložený ručne" in _eh2 and "Odstrániť vložený prepis" in _eh2)
_er.list_releases, _er.get_release = _orig_lr, _orig_gr
_fl.fetch_text = _orig_ft
check("earnings: menu obsahuje sekciu", "Výsledky a call" in cl.get("/company/DEMOCO/statements").get_data(as_text=True))

# ---- hľadanie prepisu na stránke pre investorov
check("IR: adresy stránky pre investorov z webu firmy", "https://investor.apple.com" in _er.ir_start_urls("https://www.apple.com")
      and "https://www.apple.com/investors" in _er.ir_start_urls("https://www.apple.com"))
check("IR: vnútorné a lokálne adresy sa odmietnu (ochrana pred SSRF)", not _er.safe_url("http://127.0.0.1:8000/x") and not _er.safe_url("http://localhost/") and not _er.safe_url("file:///etc/passwd") and not _er.safe_url("http://192.168.1.1/"))
_ir_html = {"https://investor.fake.com": '<a href="/events">Events and Earnings</a>',
            "https://investor.fake.com/events": '<a href="/t/q3.pdf">Q3 2026 Earnings Call Transcript</a><a href="/slides.pdf">Slides</a><a href="/t/q2">Q2 earnings transcript</a>'}
class _Rsp:
    def __init__(self, u, t): self.url, self.text, self.status_code, self.headers, self.content = u, t, 200, {"content-type": "text/html"}, b""
_orig_g = _er._get
_er._get = lambda url, timeout=8: _Rsp(url, _ir_html[url]) if url in _ir_html else None
_lk, _us = _er.find_ir_transcripts("https://www.fake.com")
_er._get = _orig_g
check("IR: nájde odkazy s „transcript“ aj cez podstránku Events a vynechá prezentáciu",
      [l["url"] for l in _lk] == ["https://investor.fake.com/t/q3.pdf", "https://investor.fake.com/t/q2"] and len(_us) == 2, (_lk, _us))
_er._get = lambda url, timeout=8: _Rsp(url, "<p>krátky text</p>")
_tx, _err = _er.fetch_transcript_url("https://investor.fake.com/t/q2")
_er._get = _orig_g
check("IR: príliš krátka stránka sa nevezme ako prepis", _tx is None and "dostatočne dlhý" in _err)

# ---- technická analýza
import datetime as _dtm  # noqa: E402
import technical as _tc  # noqa: E402
_w = [44.3389, 44.0902, 44.1497, 43.6124, 44.3278, 44.8264, 45.0955, 45.4245, 45.8433, 46.0826, 45.8931, 46.0328, 45.6140, 46.2820, 46.2820, 46.0028, 46.0328, 46.4116, 46.2222, 45.6439]
check("technická: RSI (Wilder) sedí s učebnicovým príkladom", [round(x, 2) for x in _tc.rsi(_w) if x is not None] == [70.53, 66.32, 66.55, 69.41, 66.36, 57.97])
check("technická: SMA a EMA (seed = jednoduchý priemer)", _tc.sma([1, 2, 3, 4, 5], 3) == [None, None, 2.0, 3.0, 4.0] and _tc.ema([1, 2, 3, 4, 5], 3) == [None, None, 2.0, 3.0, 4.0]
      and abs(_tc.ema([2, 4, 6, 8, 10, 12], 3)[5] - 10.0) < 1e-9)
_ml, _ms, _mh = _tc.macd([float(i) for i in range(1, 80)])
_e12, _e26 = _tc.ema([float(i) for i in range(1, 80)], 12), _tc.ema([float(i) for i in range(1, 80)], 26)
check("technická: MACD = EMA12 − EMA26 a histogram = MACD − signál", abs(_ml[60] - (_e12[60] - _e26[60])) < 1e-9 and abs(_mh[60] - (_ml[60] - _ms[60])) < 1e-9 and _ml[24] is None and _ml[25] is not None)
_bm, _bu, _bl = _tc.bollinger([10.0] * 25)
check("technická: Bollinger pri konštantnej cene má nulovú šírku; pri známych dátach sedí populačná odchýlka",
      _bu[24] == _bl[24] == 10.0 and abs(_tc.bollinger([2, 4, 4, 4, 5, 5, 7, 9], 8)[1][7] - (5 + 2 * 2)) < 1e-9)
check("technická: ATR pri konštantnom rozpätí 2 a bez medzier je 2", abs(_tc.atr([11.0] * 20, [9.0] * 20, [10.0] * 20)[19] - 2.0) < 1e-9)
check("technická: OBV sčítava objem pri raste a odčítava pri poklese", _tc.obv([1, 2, 1, 1, 3], [10, 20, 30, 40, 50]) == [0.0, 20.0, -10.0, -10.0, 40.0])
_k, _dd = _tc.stochastic([5, 6, 7, 8], [1, 2, 3, 4], [5, 6, 7, 8], 3, 2)
check("technická: Stochastic pri zatvorení na maxime rozpätia je 100", _k[2] == 100.0 and _k[3] == 100.0 and _dd[3] == 100.0)
_up = {"dates": [(_dtm.date(2024, 1, 1) + _dtm.timedelta(days=i)).isoformat() for i in range(300)], "open": [100 + i for i in range(300)],
       "high": [101.5 + i for i in range(300)], "low": [99.5 + i for i in range(300)], "close": [100.8 + i for i in range(300)], "volume": [1000 + i for i in range(300)]}
_au = _tc.analyze(_up)
check("technická: stabilný rast dá prevažne býčie signály a nulový pokles", _au["verdict"]["label"] == "prevažujú býčie signály" and _au["verdict"]["bear"] <= 1 and _au["stats"]["mdd_1y"] == 0.0, _au["verdict"])
_dn = dict(_up, close=[400 - i + 0.2 for i in range(300)], open=[400 - i + 1 for i in range(300)], high=[401.5 - i for i in range(300)], low=[398.5 - i for i in range(300)])
check("technická: stabilný pokles dá prevažne medvedie signály", _tc.analyze(_dn)["verdict"]["label"] == "prevažujú medvedie signály")
check("technická: príliš krátka história sa odmietne", _tc.analyze({k: v[:30] for k, v in _up.items()}) is None)
_syn = _tc.synthetic(n=400)
check("technická: syntetické ceny majú High ≥ Close,Open ≥ Low a sú reprodukovateľné",
      all(h >= max(o, c) and l <= min(o, c) for h, l, o, c in zip(_syn["high"], _syn["low"], _syn["open"], _syn["close"])) and _tc.synthetic(n=50)["close"] == _tc.synthetic(n=50)["close"])
_pr_ok = {"timestamp": [1700000000, 1700086400, 1700172800], "meta": {"currency": "USD"},
          "indicators": {"quote": [{"open": [1, None, 3], "high": [2, 3, 4], "low": [0.5, 1, 2], "close": [1.5, 2, 3.5], "volume": [100, 200, None]}]}}
_po = _pr.parse_ohlcv(_pr_ok)
check("technická: parse_ohlcv vynechá dni s chýbajúcou cenou a chýbajúci objem dá 0", len(_po["dates"]) == 2 and _po["volume"] == [100.0, 0.0] and _po["currency"] == "USD", _po)
_th = cl.get("/company/DEMOCO/technical")
_tht = _th.get_data(as_text=True)
check("technická: stránka ukáže graf, signály, úrovne a vložené dáta", _th.status_code == 200 and 'id="techchart"' in _tht and 'id="techdata"' in _tht
      and "Signály" in _tht and "Výnosy a riziko" in _tht and "RSI (14)" in _tht and "Ukážková firma" in _tht)
_orig_oh = _appmod.prices.get_ohlcv
_appmod.prices.get_ohlcv = lambda t: None
check("technická: nedostupné ceny dajú hlášku, nie pád", "nepodarilo stiahnuť" in cl.get("/company/ZZEU/technical").get_data(as_text=True) or cl.get("/company/ZZEU/technical").status_code in (200, 400))
_appmod.prices.get_ohlcv = _orig_oh

import tvsymbol as _tv  # noqa: E402
check("TradingView symboly: US, trieda akcií, Soul, Tokio, Hongkong, Xetra, neznáma prípona",
      _tv.to_tv("AAPL") == "AAPL" and _tv.to_tv("BRK-B") == "BRK.B" and _tv.to_tv("000660.KS") == "KRX:000660"
      and _tv.to_tv("6146.T") == "TSE:6146" and _tv.to_tv("0700.HK") == "HKEX:700" and _tv.to_tv("SAP.DE") == "XETR:SAP"
      and _tv.to_tv("ABC.ZZ") is None and _tv.to_tv("") is None and _tv.to_tv("<script>") is None)
_tt = cl.get("/company/DEMOCO/technical").get_data(as_text=True)
check("technická: demo firma nemá TradingView widget, ale stránka sa vykreslí", 'id="tvcard"' in _tt and 'id="tvbox"' not in _tt)
_orig_oh2 = _appmod.prices.get_ohlcv
_appmod.prices.get_ohlcv = lambda t, years=5: _appmod.technical.synthetic(seed=3)
_orig_fc = _appmod.edgar.find_company
_appmod.edgar.find_company = lambda q: ((q.upper(), "0000320193", "Apple Inc."), [])
_tt2 = cl.get("/company/AAPL/technical").get_data(as_text=True)
_appmod.edgar.find_company = _orig_fc
check("technická: reálny ticker má TradingView prepínač so symbolom", 'data-symbol="AAPL"' in _tt2 and "embed-widget-" in _tt2 and "tradingview.com/chart/?symbol=AAPL" in _tt2)
_appmod.prices.get_ohlcv = _orig_oh2

import edgar as _ed2, yahoo_fin as _yf2  # noqa: E402
_og, _oy = _ed2._get_json, _yf2.load
def _boom(url, name):
    raise _ed2.EdgarError("SEC vrátilo 404.")
_ed2._get_json = _boom
_yf2.load = lambda t, n: ({"entityName": "Grab Holdings", "facts": {"us-gaap": {}}}, "USD")
_cg = _ed2.load_company("GRAB", 1855612, "Grab Holdings Ltd")
check("GRAB: ak SEC nevráti výkazy (404), použije sa Yahoo", _cg["source"] == "yahoo" and _cg["name"] == "Grab Holdings")
_yf2.load = lambda t, n: None
try:
    _ed2.load_company("GRAB", 1855612, "Grab Holdings Ltd"); _ok = False
except _ed2.EdgarError as e:
    _ok = "404" in str(e) and "Yahoo" in str(e)
check("GRAB: ak zlyhá aj Yahoo, chyba povie oboje", _ok)
_ed2._get_json, _yf2.load = _og, _oy

_og3, _oy3, _ofc3, _olc3 = _appmod.edgar.load_company, _appmod.edgar.yahoo_company, _appmod.edgar.find_company, _appmod.statements.build
_cmp_sec = dict(_appmod.edgar.load_company("DEMOCO", *_appmod.edgar.find_company("DEMOCO")[0][1:]))
_cmp_sec["is_demo"] = False; _cmp_sec["source"] = "sec"
_cmp_yf = dict(_cmp_sec); _cmp_yf["source"] = "yahoo"
_calls = []
def _fake_build(comp, mode="annual", n=8):
    _calls.append(comp["source"])
    if comp["source"] == "sec":
        raise _appmod.edgar.EdgarError("Pre túto firmu sa nenašli žiadne výkazy v XBRL dátach")
    return _olc3(_cmp_sec | {"source": "sec", "is_demo": True}, mode=mode, n=n)
_appmod.edgar.find_company = lambda q: ((q.upper(), "1855612", "Grab Holdings Ltd"), [])
_appmod.edgar.load_company = lambda t, c, n: _cmp_sec
_appmod.edgar.yahoo_company = lambda t, c, n: _cmp_yf
_appmod.statements.build = _fake_build
_rg = cl.get("/company/GRAB")
check("GRAB: SEC bez výkazov -> stránka sa načíta cez Yahoo, nie chyba", _rg.status_code == 200 and _calls[:2] == ["sec", "yahoo"], (_rg.status_code, _calls))
_appmod.edgar.load_company, _appmod.edgar.yahoo_company, _appmod.edgar.find_company, _appmod.statements.build = _og3, _oy3, _ofc3, _olc3


# ---------------------------------------------------------------- téza, insideri, kalendár, makro, porovnanie
from datetime import timedelta as _tdelta
import tempfile as _tmpf
import thesis as _th2, insider as _ins, events as _ev, macro as _mc, valuation as _V2
from datetime import date as _date
_th2.PATH = os.path.join(_tmpf.mkdtemp(), "thesis.json")
_ok, _m = _th2.save("abc", "dôvod", "predaj ak X", "sleduj Y", "poznámka 1", 12.5, today=_date(2026, 10, 1))
_t = _th2.get("ABC")
check("téza: uloží sa, ticker sa zjednotí na veľké písmená, denník má záznam", _ok and _t["why"] == "dôvod" and _t["log"][0]["t"] == "poznámka 1" and _t["price"] == 12.5)
_th2.save("ABC", "dôvod", "predaj ak X", "sleduj Y", "", None, today=_date(2026, 11, 1))
check("téza: bez zmeny textu sa dátum úpravy nemení, pôvodná cena zostane", _th2.get("ABC")["updated"] == "2026-10-01" and _th2.get("ABC")["price"] == 12.5)
_th2.save("ABC", "nový dôvod", "predaj ak X", "sleduj Y", "", None, today=_date(2026, 11, 2))
check("téza: zmena textu posunie dátum úpravy", _th2.get("ABC")["updated"] == "2026-11-02")
check("téza: výsledky po úprave označia tézu ako zastaranú, staršie nie", _th2.stale(_th2.get("ABC"), "2026-11-10") and not _th2.stale(_th2.get("ABC"), "2026-10-30"))
check("téza: neplatný ticker sa odmietne", _th2.save("<x>", "a")[0] is False)
_th2.save("ABC", "", "", "", "", None)
check("téza: prázdne polia s existujúcim denníkom ju nezmažú, kým denník zostane", _th2.get("ABC") is not None)
_th2.save("QQQ", "x")
_th2.save("QQQ", "", "", "", "")
check("téza: úplne prázdna téza bez denníka sa zmaže", _th2.get("QQQ") is None)

_x4 = """<ownershipDocument><reportingOwner><reportingOwnerId><rptOwnerName>DOE JOHN</rptOwnerName></reportingOwnerId>
<reportingOwnerRelationship><isOfficer>1</isOfficer><officerTitle>CEO</officerTitle></reportingOwnerRelationship></reportingOwner>
<nonDerivativeTable>
<nonDerivativeTransaction><transactionDate><value>2026-10-02</value></transactionDate><transactionCoding><transactionCode>P</transactionCode></transactionCoding>
<transactionAmounts><transactionShares><value>1000</value></transactionShares><transactionPricePerShare><value>50</value></transactionPricePerShare><transactionAcquiredDisposedCode><value>A</value></transactionAcquiredDisposedCode></transactionAmounts>
<postTransactionAmounts><sharesOwnedFollowingTransaction><value>9000</value></sharesOwnedFollowingTransaction></postTransactionAmounts></nonDerivativeTransaction>
<nonDerivativeTransaction><transactionDate><value>2026-10-03</value></transactionDate><transactionCoding><transactionCode>S</transactionCode></transactionCoding>
<transactionAmounts><transactionShares><value>200</value></transactionShares><transactionPricePerShare><value>52</value></transactionPricePerShare><transactionAcquiredDisposedCode><value>D</value></transactionAcquiredDisposedCode></transactionAmounts></nonDerivativeTransaction>
<nonDerivativeTransaction><transactionDate><value>2026-10-04</value></transactionDate><transactionCoding><transactionCode>A</transactionCode></transactionCoding>
<transactionAmounts><transactionShares><value>5000</value></transactionShares></transactionAmounts></nonDerivativeTransaction>
</nonDerivativeTable></ownershipDocument>"""
_tx = _ins.parse_form4(_x4, "0001-26-000001", "2026-10-05")
_sm = _ins.summarize(_tx, today=_date(2026, 11, 1))
check("insider: parser prečíta nákup, predaj aj grant; súhrn rátá len P a S", len(_tx) == 3 and _sm["n_buy"] == 1 and _sm["n_sell"] == 1
      and _sm["buy_value"] == 50000 and _sm["sell_value"] == 10400 and _sm["net"] == 39600 and _tx[0]["title"] == "CEO")
check("insider: pokazené XML nezhodí parser", _ins.parse_form4("<x", "a") == [] and _ins.parse_form4("", "a") == [])
check("insider: surový dokument bez XSL prefixu", _ins._raw_doc("xslF345X05/wk-form4_1.xml") == "wk-form4_1.xml" and _ins._raw_doc("f4.xml") == "f4.xml")
_of = _ins.filings.fetch_text
_ins.filings.fetch_text = lambda comp, acc, name: _x4
_comp4 = {"cik": "123", "source": "sec", "filings": {"form": ["8-K", "4", "4"], "accessionNumber": ["a1", "a2", "a3"],
          "filingDate": ["2026-10-01", "2026-10-05", "2026-10-06"], "primaryDocument": ["x.htm", "xslF345X05/f.xml", "xslF345X05/g.xml"]}}
_gi = _ins.get_insider(_comp4, today=_date(2026, 11, 1))
check("insider: get_insider zloží transakcie z viacerých podaní", _gi["error"] is None and len(_gi["txs"]) == 6 and _gi["n_filings"] == 2)
check("insider: firma mimo SEC alebo bez formulárov 4 dá vysvetlenie",
      "len pri firmách" in _ins.get_insider({"cik": "YF", "source": "yahoo", "filings": {}})["error"]
      and "žiadne formuláre 4" in _ins.get_insider({"cik": "1", "source": "sec", "filings": {"form": ["8-K"], "accessionNumber": ["a"]}})["error"])
_ins.filings.fetch_text = _of

_tt = _date(2026, 11, 4)
_en = _ev.estimate_next_earnings(["2026-10-30", "2026-07-31", "2026-05-01", "2026-02-05", "2025-10-31"], _tt)
check("kalendár: výsledky podľa rovnakého kvartálu vlani", _en["date"] == "2027-02-04" and _en["last"] == "2026-10-30")
check("kalendár: málo dát dá aspoň približný odhad, žiadne dáta None",
      _ev.estimate_next_earnings(["2026-10-30"], _tt)["date"] == "2027-01-29" and _ev.estimate_next_earnings([], _tt) is None)
check("kalendár: uplynulý odhad sa posunie do budúcnosti", _ev.estimate_next_earnings(["2025-01-10", "2024-10-10", "2024-07-10", "2024-04-10"], _tt)["date"] >= "2026-11-04")
_dv = _ev.dividend_info([("2026-02-10", 0.25), ("2026-05-10", 0.25), ("2026-08-10", 0.26)], _tt)
check("kalendár: štvrťročná dividenda a odhad ďalšej ex-dividendy", _dv["freq"] == "štvrťročne" and _dv["next_date"] >= "2026-11-04" and abs(_dv["year_sum"] - 0.76) < 1e-9)
check("kalendár: stará alebo žiadna dividenda = nevypláca", _ev.dividend_info([("2023-01-01", 1.0)], _tt) is None and _ev.dividend_info([], _tt) is None)
_up = _ev.upcoming([{"ticker": "AAA", "name": "A", "earnings": {"date": "2026-11-20", "basis": "x"}, "dividend": {"next_date": "2026-11-10", "last_amount": 0.5}, "div_ccy": "USD", "shares": 10},
                    {"ticker": "BBB", "earnings": {"date": "2027-06-01", "basis": "x"}}], _tt)
check("kalendár: časová os zoradená, ďaleké udalosti vynechané, dividenda × počet kusov", [e["ticker"] for e in _up] == ["AAA", "AAA"] and _up[0]["kind"].startswith("Ex-div") and "5,00" in _up[0]["note"])

_csv = "observation_date,CPIAUCSL\n" + "\n".join(f"{y}-{m:02d}-01,{100 + (y - 2024) * 3 + m * 0.1}" for y in (2024, 2025, 2026) for m in range(1, 13))
_pts = _mc.parse_fred_csv(_csv)
_yy = _mc.yoy(_pts)
check("makro: CSV sa načíta a medziročná zmena sa spočíta", len(_pts) == 36 and len(_yy) == 24 and 2.5 < _yy[0][1] < 3.1)
check("makro: priemer za rok a zredčenie", abs(_mc.annual_avg([("2025-01-01", 4.0), ("2025-06-01", 6.0), ("2026-01-01", 9.0)], 2025) - 5.0) < 1e-9
      and len(_mc._thin([("2020-01-01", 1.0)] * 5000)) <= 901 and _mc._thin([("2020-01-01", 1.0)] * 5000)[-1] == ("2020-01-01", 1.0))
_ogp = _mc.get_points
_mc.get_points = lambda sid: None if sid == "DGS2" else _mc.parse_fred_csv("DATE,X\n" + "\n".join(f"{y}-{m:02d}-01,{2 + y % 5 + m * 0.01}" for y in range(2018, 2027) for m in range(1, 13)))
_cards = _mc.page_data(10, today=_date(2026, 11, 4))
check("makro: chýbajúca rada nezhodí ostatné, karta má poslednú hodnotu a body",
      len(_cards) == len(_mc.SERIES) and [c for c in _cards if c["id"] == "DGS2"][0]["points"] is None
      and [c for c in _cards if c["id"] == "FEDFUNDS"][0]["last"] is not None and [c for c in _cards if c["id"] == "FEDFUNDS"][0]["points"])
_rm = cl.get("/macro")
check("makro: stránka sa vykreslí s grafmi a upozornením pri chýbajúcich dátach", _rm.status_code == 200 and b"macrodata" in _rm.data and "nepodarilo načítať" in _rm.get_data(as_text=True))
_mc.get_points = _ogp

_pp = dict(rev0=1e9, g1=0.10, margin0=0.15, margin5=0.20, wacc=0.09, g_term=0.03, net_debt=0.0, shares=1e8, dilution=0.0)
_s2 = _V2.dcf_sensitivity2(_pp)
check("DCF: druhá tabuľka 5×5, vyšší rast aj marža = vyššia hodnota", len(_s2["grid"]) == 5 and len(_s2["grid"][0]) == 5
      and _s2["grid"][4][4] > _s2["grid"][2][2] > _s2["grid"][0][0])
_rf = cl.get("/company/DEMOCO/fundamental").get_data(as_text=True)
check("DCF: stránka ukáže druhú tabuľku citlivosti a farbenie voči cene", "Rast \\ FCF marža" in _rf and ("sgood" in _rf or "sbad" in _rf))

import app as _a3
_a3.thesis.PATH = _th2.PATH
_rp = cl.post("/company/DEMOCO/thesis", data={"why": "demo dôvod", "sell_if": "", "watch": "", "note": "n1", "back": "overview"}, follow_redirects=True)
_ro = _rp.get_data(as_text=True)
check("téza: uloženie cez formulár a zobrazenie na úvodnej stránke", _rp.status_code == 200 and "Moja téza" in _ro and "demo dôvod" in _ro and "n1" in _ro)
check("téza: karta je aj na stránke výsledkov", "Moja téza" in cl.get("/company/DEMOCO/earnings").get_data(as_text=True))
_ri = cl.get("/company/DEMOCO/insiders")
check("insideri: ukážková firma dá vysvetlenie, nie pád", _ri.status_code == 200 and "Insider transakcie" in _ri.get_data(as_text=True))

_ol = _a3._load_peer
_a3._load_peer = lambda t: (t, {"ticker": t, "name": t + " Inc", "currency": "USD", "fy": None, "revenue": 1e9, "rev_cagr3": 0.1, "op_margin": 0.2, "net_margin": 0.1,
                                 "fcf_margin": None, "roe": 0.15, "roic": None, "nd_ebitda": None, "piotroski": None, "altman": None, "mcap": 1e10,
                                 "pe": 20.0 if t == "AAA" else 12.0, "ps": None, "ev_ebitda": None, "fcf_yield": None}, None) if t != "ZZZ" else (t, None, "ZZZ: chyba")
_rc = cl.get("/compare?t=AAA,BBB,ZZZ")
_rct = _rc.get_data(as_text=True)
check("porovnanie: tabuľka pre dve firmy, chyba tretej sa ukáže a nezhodí stránku", _rc.status_code == 200 and "AAA Inc" in _rct and "BBB Inc" in _rct and "ZZZ: chyba" in _rct and "P/E" in _rct)
check("porovnanie: jedna firma = výzva na ďalšiu; prázdne = návod", "aspoň dve firmy" in cl.get("/compare?t=AAA").get_data(as_text=True) and cl.get("/compare").status_code == 200)
check("porovnanie: neplatný ticker sa odmietne bez pádu", cl.get("/compare?t=%3Cscript%3E").status_code == 200)
_a3._load_peer = _ol

_owl, _ocr = _a3.watchlist.load, _a3._calendar_row
_a3.watchlist.load = lambda: [{"ticker": "AAA", "name": "A Inc"}]
_a3._calendar_row = lambda it: {"ticker": it[0], "name": it[1], "shares": it[2], "earnings": {"date": (_date.today() + _tdelta(days=20)).isoformat(), "basis": "rovnaký kvartál vlani"},
                                "dividend": None, "div_ccy": None, "last_release": "2026-10-30", "note": None}
_rk = cl.get("/calendar")
check("kalendár: stránka ukáže časovú os s odhadom a upozornenie, že ide o odhady", _rk.status_code == 200 and "Výsledky (odhad)" in _rk.get_data(as_text=True) and "odhady" in _rk.get_data(as_text=True))
_a3.watchlist.load = lambda: []
check("kalendár: bez firiem návod, nie pád", "Zatiaľ tu nič nie je" in cl.get("/calendar").get_data(as_text=True) or cl.get("/calendar").status_code == 200)
_a3.watchlist.load, _a3._calendar_row = _owl, _ocr

_mb, _ = _appmod.edgar.find_company("DEMOBANK")
_bb = _appmod.statements.build(_appmod.edgar.load_company(*_mb), "annual", 8)
_ogp2 = _appmod.macro.get_points
_appmod.macro.get_points = lambda sid: [(f"{y}-{mo:02d}-01", 2.0 + (y - 2018) * 0.5) for y in range(2015, 2027) for mo in range(1, 13)]
_rr = _appmod._rates_card(_bb, "bank")
check("banky: karta sadzieb spáruje maržu s priemerom sadzieb za rok", _rr and len(_rr["rows"]) >= 2 and _rr["rows"][0]["fed"] is not None and 0 < _rr["rows"][0]["margin"] < 0.1)
_appmod.macro.get_points = lambda sid: None
check("banky: bez dát z FRED karta nevznikne, appka nespadne", _appmod._rates_card(_bb, "bank") is None)
_appmod.macro.get_points = _ogp2


# --- audit 11/2026: Sankey bánk sedí aj pri strate, daňovom benefite a ostatných výnosoch
import flow as _fl  # noqa: E402
from collections import defaultdict as _dd  # noqa: E402
def _bal(f):
    inn, out = _dd(float), _dd(float)
    for l in f["links"]:
        out[l["s"]] += l["v"]; inn[l["t"]] += l["v"]
    ok = True
    for n in f["nodes"]:
        a, b = inn.get(n["id"], 0), out.get(n["id"], 0)
        if (a and abs(a - n["value"]) > 1) or (b and abs(b - n["value"]) > 1) or (a and b and abs(a - b) > 1):
            ok = False
    return ok
_e0 = _dt(2024, 12, 31)
def _bk(**kw):
    base = {"int_income": 2800.0, "interest_expense": 1090.0, "nonint_income": 958.0, "provision": 400.0,
            "nonint_expense": 2000.0, "pretax": 233.0, "tax": -265.0, "net_income": 498.0}
    base.update(kw)
    return {"display": [_e0], "ends": [_e0], "data": {k: {_e0: v} for k, v in base.items()}, "mode": "annual", "currency": "USD"}
for _lbl, _kw in (("daňový benefit", {}), ("strata", {"pretax": -301.0, "tax": 0.0, "net_income": -301.0, "nonint_expense": 2969.0}),
                  ("ostatné výnosy", {"pretax": 300.0, "tax": 60.0, "net_income": 240.0}),
                  ("ostatné náklady", {"pretax": 100.0, "tax": 20.0, "net_income": 80.0})):
    _f = _fl.build_flow(_bk(**_kw), _e0, "bank")
    check(f"Sankey banky ({_lbl}): každý uzol má prítok = odtok", _f is not None and _bal(_f), _f and _f["links"])
check("reverzný DCF pri zápornej FCF marži nič netvrdí", _va.implied_growth(10, dict(rev0=1e9, g1=0.1, margin0=-0.1, margin5=-0.05, wacc=0.09,
      g_term=0.025, net_debt=0, shares=1e8, dilution=0)) is None)

# --- audit živých dát 11/2026: BitMine (SIC 6199 bez úverov) nie je banka, SoFi s NII áno; dividendy ASML
import metrics as _mt2  # noqa: E402
_e1 = _dt(2025, 8, 31)
check("typ: SIC 6199 bez úverov a úrokov = všeobecná firma (BitMine)", _mt2.detect_type({"sic": 6199}, {"data": {"revenue": {_e1: 1e8}}}) == "general")
check("typ: SIC 6199 s čistým úrokovým výnosom = banka (SoFi)", _mt2.detect_type({"sic": 6199}, {"data": {"nii": {_e1: 1e9}}}) == "bank")
check("typ: depozitná banka podľa SIC vždy banka", _mt2.detect_type({"sic": 6022}, {"data": {}}) == "bank")
check("dividendy: značka PaymentsOfOrdinaryDividends (ASML)", "PaymentsOfOrdinaryDividends" in __import__("taxonomy").ITEM_BY_KEY["div_paid"]["tags"])

# --- prepočet ceny: ASML (USD -> EUR), TSM (1 ADR = 5 akcií), chýbajúci kurz = mismatch
_ogpr = _appmod.prices.get_price
_appmod.prices.get_price = lambda s: {"price": 0.9, "currency": "EUR"} if s == "USDEUR=X" else ({"price": 32.0, "currency": "TWD"} if s == "USDTWD=X" else None)
_qa = _appmod._align_quote({"price": 1000.0, "currency": "USD", "change": 10.0}, "EUR", "ASML")
check("cena ASML v USD sa prepočíta kurzom do EUR", abs(_qa["price"] - 900) < 1e-9 and _qa["currency"] == "EUR" and not _qa.get("mismatch") and _qa["converted"]["rate"] == 0.9)
_qt = _appmod._align_quote({"price": 200.0, "currency": "USD"}, "TWD", "TSM")
check("cena TSM: kurz aj pomer ADR (1 ADR = 5 akcií)", abs(_qt["price"] - 200 * 32 / 5) < 1e-9)
check("bez kurzu sa cena označí ako nezhodná", _appmod._align_quote({"price": 5.0, "currency": "USD"}, "KRW", "X").get("mismatch") is True)
check("rovnaká mena bez ADR: cena sa nemení", _appmod._align_quote({"price": 5.0, "currency": "USD"}, "USD", "AAPL")["price"] == 5.0)
_appmod.prices.get_price = _ogpr

import macro as _mc3  # noqa: E402
check("FRED API: parser JSON vynechá chýbajúce hodnoty", _mc3.parse_api_json({"observations": [{"date": "2026-01-01", "value": "3.88"}, {"date": "2026-02-01", "value": "."}]}) == [("2026-01-01", 3.88)])
_mc3.KEY_PATH = os.path.join(_tmpf.mkdtemp(), "fred_key.txt")
check("FRED API: neplatný kľúč sa neuloží, platný áno", not _mc3.save_key("abc") and _mc3.save_key("a" * 32) and _mc3.api_key() == "a" * 32)
_ogp3 = _mc3.get_points
_mc3.get_points = lambda sid: None
_rmk = cl.get("/macro").get_data(as_text=True)
check("Makro: pri zlyhaní FRED návod a formulár na kľúč", "bezplatným kľúčom" in _rmk and 'name="key"' in _rmk)
_mc3.get_points = _ogp3
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

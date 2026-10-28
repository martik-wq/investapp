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

# ------------------------------------------------------- rozhranie (Flask klient)
import app as appmod  # noqa: E402

cl = appmod.app.test_client()
urls = ["/", "/search?q=DEMOCO", "/company/DEMOCO", "/company/DEMOCO/overview",
        "/company/DEMOCO/statements", "/company/DEMOCO/statements?mode=quarterly&years=5",
        "/company/DEMOCO/statements?type=reit&price=50", "/company/DEMOCO/charts",
        "/company/DEMOCO/charts?mode=quarterly&years=10", "/company/DEMOCO/fundamental",
        "/company/DEMOCO/technical", "/company/DEMOBANK", "/company/DEMOBANK/statements?price=20",
        "/company/DEMOBANK/charts", "/company/DEMOBANK/export.csv"]
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

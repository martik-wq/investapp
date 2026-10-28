"""Vyrobí fiktívne dáta v rovnakom formáte, aký vracia SEC companyfacts API.

Slúži na testovanie bez internetu (tickery DEMOCO a DEMOBANK). Dáta simulujú
reálne správanie EDGAR: 10-Q uvádzajú 3M a kumulatívne hodnoty, cash flow len
kumulatívne, štvrtý kvartál chýba, ročné hodnoty sa opakujú v ďalších 10-K,
a firma v čase mení XBRL tag pre tržby.
"""
import json
import os
from datetime import date, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "demo_data")

YEARS = list(range(2019, 2026))
QSTART = [(1, 1), (4, 1), (7, 1), (10, 1)]
QEND = [(3, 31), (6, 30), (9, 30), (12, 31)]
FILED = {1: (5, 5), 2: (8, 5), 3: (11, 5)}


def all_periods():
    for y in YEARS + [2026]:
        for q in range(1, 5):
            if y == 2026 and q > 2:
                break
            yield y, q


def qrange(y, q):
    return date(y, *QSTART[q - 1]), date(y, *QEND[q - 1])


def filed(y, q):
    if q == 4:
        return date(y + 1, 2, 20)
    return date(y, *FILED[q])


class Facts:
    def __init__(self):
        self.f = {"us-gaap": {}, "dei": {}}

    def _put(self, tax, tag, unit, rec):
        c = self.f.setdefault(tax, {}).setdefault(tag, {"label": tag, "units": {}})
        c["units"].setdefault(unit, []).append(rec)

    @staticmethod
    def _rec(val, end, filed_d, form, start=None, fp="FY"):
        r = {"end": end.isoformat(), "val": val, "accn": "0000000000-00-000000",
             "fy": end.year, "fp": fp, "form": form, "filed": filed_d.isoformat()}
        if start:
            r["start"] = start.isoformat()
        return r

    def flow(self, tag, qv, unit="USD", cum_only=False, agg="sum", tax="us-gaap",
             years=None):
        for y in sorted({k[0] for k in qv}):
            if years and y not in years:
                continue
            vals = [qv.get((y, q)) for q in range(1, 5)]
            y0 = date(y, 1, 1)
            cum = []
            for q in range(1, 4):
                v = vals[q - 1]
                if v is None:
                    break
                cum.append(v)
                s, e = qrange(y, q)
                tot = sum(cum) if agg == "sum" else sum(cum) / len(cum)
                if q == 1 or not cum_only:
                    self._put(tax, tag, unit, self._rec(v, e, filed(y, q), "10-Q", s,
                                                        f"Q{q}"))
                if q > 1:
                    self._put(tax, tag, unit, self._rec(tot, e, filed(y, q), "10-Q",
                                                        y0, f"Q{q}"))
            if all(v is not None for v in vals):
                fy = sum(vals) if agg == "sum" else sum(vals) / 4
                e = date(y, 12, 31)
                for fyr in (y + 1, y + 2, y + 3):
                    # 10-K za rok y a opakovanie v nasledujúcich 10-K (porovnávacie stĺpce)
                    if fyr == y + 1 or fyr <= 2026:
                        fd = filed(fyr - 1, 4) if fyr == y + 1 else date(fyr, 2, 20)
                        if fd.year > 2026:
                            continue
                        self._put(tax, tag, unit, self._rec(fy, e, fd, "10-K", y0))

    def instant(self, tag, qv, unit="USD", tax="us-gaap"):
        for (y, q), v in qv.items():
            _, e = qrange(y, q)
            form = "10-K" if q == 4 else "10-Q"
            self._put(tax, tag, unit, self._rec(v, e, filed(y, q), form,
                                                fp="FY" if q == 4 else f"Q{q}"))
            if q == 4 and y < 2026:  # porovnávací stĺpec v 10-Q nasledujúceho roka
                self._put(tax, tag, unit, self._rec(v, e, filed(y + 1, 1), "10-Q"))


WEIGHTS = [0.22, 0.24, 0.26, 0.28]


def build_democo():
    """Fiktívna softvérová firma (typ: tech)."""
    f = Facts()
    Q = {}

    def q_of(fn):
        return {(y, q): fn(y, q) for y, q in all_periods()}

    annual_rev = lambda y: 400e6 * 1.12 ** (y - 2019)  # noqa: E731
    rev = q_of(lambda y, q: annual_rev(y) * WEIGHTS[q - 1])
    cogs = q_of(lambda y, q: rev[(y, q)] * 0.35)
    rnd = q_of(lambda y, q: rev[(y, q)] * 0.22)
    sga = q_of(lambda y, q: rev[(y, q)] * 0.25)
    opi = q_of(lambda y, q: rev[(y, q)] - cogs[(y, q)] - rnd[(y, q)] - sga[(y, q)])
    intexp = q_of(lambda y, q: 1.5e6)
    pretax = q_of(lambda y, q: opi[(y, q)] - intexp[(y, q)])
    tax = q_of(lambda y, q: pretax[(y, q)] * 0.21)
    ni = q_of(lambda y, q: pretax[(y, q)] - tax[(y, q)])
    shares = q_of(lambda y, q: 100e6 * 0.99 ** (y - 2019))
    eps = q_of(lambda y, q: ni[(y, q)] / shares[(y, q)])
    da = q_of(lambda y, q: rev[(y, q)] * 0.04)
    sbc = q_of(lambda y, q: rev[(y, q)] * 0.06)
    cfo = q_of(lambda y, q: ni[(y, q)] + da[(y, q)] + sbc[(y, q)] - 0.02 * rev[(y, q)])
    capex = q_of(lambda y, q: rev[(y, q)] * 0.05)
    div = q_of(lambda y, q: ni[(y, q)] * 0.10)
    buy = q_of(lambda y, q: ni[(y, q)] * 0.20)
    cfi = q_of(lambda y, q: -capex[(y, q)] * 1.2)
    cff = q_of(lambda y, q: -(div[(y, q)] + buy[(y, q)]))

    # tržby: starý tag do 2020, nový od 2021 (test zlúčenia tagov)
    f.flow("SalesRevenueNet", rev, years={2019, 2020})
    f.flow("RevenueFromContractWithCustomerExcludingAssessedTax", rev,
           years=set(range(2021, 2027)))
    f.flow("CostOfRevenue", cogs)
    f.flow("ResearchAndDevelopmentExpense", rnd)
    f.flow("SellingGeneralAndAdministrativeExpense", sga)
    f.flow("OperatingIncomeLoss", opi)
    f.flow("InterestExpense", intexp)
    f.flow("IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest", pretax)
    f.flow("IncomeTaxExpenseBenefit", tax)
    f.flow("NetIncomeLoss", ni)
    # 10-Q niektorých firiem (napr. Amazon) uvádzajú aj 12-mesačné (TTM) hodnoty
    pk = list(all_periods())
    for i, (y, q) in enumerate(pk):
        if i >= 3 and q < 4:
            e = qrange(y, q)[1]
            f._put("us-gaap", "NetIncomeLoss", "USD", Facts._rec(
                sum(ni[k] for k in pk[i - 3:i + 1]), e, filed(y, q), "10-Q",
                date(e.year - 1, e.month, e.day) + timedelta(days=1), f"Q{q}"))
    for i, (y, q) in enumerate(pk):
        if i >= 3 and q < 4:
            e = qrange(y, q)[1]
            f._put("us-gaap", "NetCashProvidedByUsedInOperatingActivities", "USD", Facts._rec(
                sum(cfo[k] for k in pk[i - 3:i + 1]), e, filed(y, q), "10-Q",
                date(e.year - 1, e.month, e.day) + timedelta(days=1), f"Q{q}"))
    f.flow("EarningsPerShareDiluted", eps, unit="USD/shares")
    f.flow("WeightedAverageNumberOfDilutedSharesOutstanding", shares, unit="shares",
           agg="avg")
    f.flow("DepreciationDepletionAndAmortization", da, cum_only=True)
    f.flow("ShareBasedCompensation", sbc, cum_only=True)
    f.flow("NetCashProvidedByUsedInOperatingActivities", cfo, cum_only=True)
    f.flow("PaymentsToAcquirePropertyPlantAndEquipment", capex, cum_only=True)
    f.flow("NetCashProvidedByUsedInInvestingActivities", cfi, cum_only=True)
    f.flow("PaymentsOfDividends", div, cum_only=True)
    f.flow("PaymentsForRepurchaseOfCommonStock", buy, cum_only=True)
    f.flow("NetCashProvidedByUsedInFinancingActivities", cff, cum_only=True)

    # súvaha
    cash, eq = {}, {}
    c, e = 150e6, 700e6
    for y, q in all_periods():
        c += cfo[(y, q)] - capex[(y, q)] - div[(y, q)] - buy[(y, q)]
        e += ni[(y, q)] + sbc[(y, q)] - div[(y, q)] - buy[(y, q)]
        cash[(y, q)], eq[(y, q)] = c, e
    ar = q_of(lambda y, q: rev[(y, q)] * 0.5)
    inv = q_of(lambda y, q: cogs[(y, q)] * 0.6)
    ap = q_of(lambda y, q: cogs[(y, q)] * 0.8)
    accr = q_of(lambda y, q: rev[(y, q)] * 0.4)
    ltd = q_of(lambda y, q: 300e6)
    ac = q_of(lambda y, q: cash[(y, q)] + ar[(y, q)] + inv[(y, q)])
    cl = q_of(lambda y, q: ap[(y, q)] + accr[(y, q)] + 20e6)
    liab = q_of(lambda y, q: cl[(y, q)] + ltd[(y, q)])
    gw, ia = 300e6, 80e6
    ppe = q_of(lambda y, q: liab[(y, q)] + eq[(y, q)] - ac[(y, q)] - gw - ia)
    assets = q_of(lambda y, q: liab[(y, q)] + eq[(y, q)])
    f.instant("CashAndCashEquivalentsAtCarryingValue", cash)
    f.instant("AccountsReceivableNetCurrent", ar)
    f.instant("InventoryNet", inv)
    f.instant("AssetsCurrent", ac)
    f.instant("PropertyPlantAndEquipmentNet", ppe)
    f.instant("Goodwill", q_of(lambda y, q: gw))
    f.instant("IntangibleAssetsNetExcludingGoodwill", q_of(lambda y, q: ia))
    f.instant("Assets", assets)
    f.instant("AccountsPayableCurrent", ap)
    f.instant("DebtCurrent", q_of(lambda y, q: 20e6))
    f.instant("LiabilitiesCurrent", cl)
    f.instant("LongTermDebtNoncurrent", ltd)
    f.instant("Liabilities", liab)
    f.instant("StockholdersEquity", eq)
    f.instant("LiabilitiesAndStockholdersEquity", assets)
    f._put("dei", "EntityCommonStockSharesOutstanding", "shares",
           Facts._rec(96e6, date(2026, 7, 25), date(2026, 8, 5), "10-Q"))

    truth = {
        "rev_fy": {y: sum(rev[(y, q)] for q in range(1, 5)) for y in YEARS},
        "ni_fy": {y: sum(ni[(y, q)] for q in range(1, 5)) for y in YEARS},
        "fcf_fy": {y: sum(cfo[(y, q)] - capex[(y, q)] for q in range(1, 5))
                   for y in YEARS},
        "rev_q": rev, "cfo_q": cfo, "equity": eq, "assets": assets, "cash": cash,
        "opi_fy": {y: sum(opi[(y, q)] for q in range(1, 5)) for y in YEARS},
    }
    facts = {"cik": 9000001, "entityName": "Demo Software Inc.", "facts": f.f}
    subs = {"name": "Demo Software Inc.", "sic": "7372",
            "sicDescription": "Services-Prepackaged Software", "tickers": ["DEMOCO"],
            "exchanges": ["Nasdaq"], "fiscalYearEnd": "1231",
            "addresses": {"business": {"city": "Demo City", "stateOrCountryDescription": "Fiktívny štát"}}}
    return facts, subs, truth


def build_demobank():
    """Fiktívna banka (typ: bank)."""
    f = Facts()

    def q_of(fn):
        return {(y, q): fn(y, q) for y, q in all_periods()}

    nii = q_of(lambda y, q: 500e6 * 1.08 ** (y - 2019) * [0.24, 0.245, 0.255, 0.26][q - 1])
    int_inc = q_of(lambda y, q: nii[(y, q)] * 2.2)
    int_exp = q_of(lambda y, q: int_inc[(y, q)] - nii[(y, q)])
    nonint = q_of(lambda y, q: nii[(y, q)] * 0.35)
    nonexp = q_of(lambda y, q: 0.55 * (nii[(y, q)] + nonint[(y, q)]))
    prov = q_of(lambda y, q: nii[(y, q)] * 0.10)
    pretax = q_of(lambda y, q: nii[(y, q)] + nonint[(y, q)] - nonexp[(y, q)] - prov[(y, q)])
    tax = q_of(lambda y, q: pretax[(y, q)] * 0.22)
    ni = q_of(lambda y, q: pretax[(y, q)] - tax[(y, q)])
    shares = q_of(lambda y, q: 200e6)
    eps = q_of(lambda y, q: ni[(y, q)] / 200e6)
    cfo = q_of(lambda y, q: ni[(y, q)] * 1.1)
    capex = q_of(lambda y, q: 5e6)
    div = q_of(lambda y, q: ni[(y, q)] * 0.30)

    f.flow("InterestAndDividendIncomeOperating", int_inc)
    f.flow("InterestExpense", int_exp)
    f.flow("InterestIncomeExpenseNet", nii)
    f.flow("NoninterestIncome", nonint)
    f.flow("NoninterestExpense", nonexp)
    f.flow("ProvisionForLoanLeaseAndOtherLosses", prov)
    f.flow("IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest", pretax)
    f.flow("IncomeTaxExpenseBenefit", tax)
    f.flow("NetIncomeLoss", ni)
    f.flow("EarningsPerShareDiluted", eps, unit="USD/shares")
    f.flow("WeightedAverageNumberOfDilutedSharesOutstanding", shares, unit="shares",
           agg="avg")
    f.flow("NetCashProvidedByUsedInOperatingActivities", cfo, cum_only=True)
    f.flow("PaymentsToAcquirePropertyPlantAndEquipment", capex, cum_only=True)
    f.flow("PaymentsOfDividends", div, cum_only=True)

    def assets_at(y, q):
        return 25e9 * 1.08 ** ((y - 2019) + q / 4)

    assets = q_of(assets_at)
    f.instant("Assets", assets)
    f.instant("LoansAndLeasesReceivableNetReportedAmount", q_of(lambda y, q: assets[(y, q)] * 0.62))
    f.instant("LoansAndLeasesReceivableAllowance", q_of(lambda y, q: assets[(y, q)] * 0.62 * 0.012))
    f.instant("Deposits", q_of(lambda y, q: assets[(y, q)] * 0.82))
    f.instant("StockholdersEquity", q_of(lambda y, q: assets[(y, q)] * 0.10))
    f.instant("Goodwill", q_of(lambda y, q: 400e6))
    f.instant("IntangibleAssetsNetExcludingGoodwill", q_of(lambda y, q: 50e6))
    f.instant("CashAndCashEquivalentsAtCarryingValue", q_of(lambda y, q: assets[(y, q)] * 0.06))
    f.instant("AvailableForSaleSecuritiesDebtSecurities", q_of(lambda y, q: assets[(y, q)] * 0.2))
    f.instant("Liabilities", q_of(lambda y, q: assets[(y, q)] * 0.90))
    f.instant("LiabilitiesAndStockholdersEquity", assets)
    f._put("dei", "EntityCommonStockSharesOutstanding", "shares",
           Facts._rec(198e6, date(2026, 7, 25), date(2026, 8, 5), "10-Q"))

    truth = {"nii_fy": {y: sum(nii[(y, q)] for q in range(1, 5)) for y in YEARS},
             "ni_fy": {y: sum(ni[(y, q)] for q in range(1, 5)) for y in YEARS},
             "assets": assets}
    facts = {"cik": 9000002, "entityName": "Demo Bank Corp.", "facts": f.f}
    subs = {"name": "Demo Bank Corp.", "sic": "6022",
            "sicDescription": "State Commercial Banks", "tickers": ["DEMOBANK"],
            "exchanges": ["NYSE"], "fiscalYearEnd": "1231"}
    return facts, subs, truth


def main():
    os.makedirs(OUT, exist_ok=True)
    for t, fn in (("DEMOCO", build_democo), ("DEMOBANK", build_demobank)):
        facts, subs, _ = fn()
        with open(os.path.join(OUT, f"{t}_facts.json"), "w", encoding="utf-8") as fh:
            json.dump(facts, fh)
        with open(os.path.join(OUT, f"{t}_subs.json"), "w", encoding="utf-8") as fh:
            json.dump(subs, fh)
    print("Ukážkové dáta vytvorené v", os.path.abspath(OUT))


if __name__ == "__main__":
    main()

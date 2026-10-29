"""Vytvorí fiktívne podania vo formáte SEC (FilingSummary.xml + R*.htm) pre firmu DEMOCO.

Strany R*.htm sú vyrobené podľa skutočného vzhľadu stránok SEC (tabuľka
class="report", riadky class="re"/"ro", bunky class="nump"/"num"/"text",
odkazy s onclick="...defref_us-gaap_...") a slúžia na testovanie čítania
podrobných výkazov bez internetu. Čísla sú vymyslené.
"""
import os

MONTH_ABBR = ["Jan.", "Feb.", "Mar.", "Apr.", "May", "Jun.", "Jul.", "Aug.", "Sep.",
              "Oct.", "Nov.", "Dec."]
QEND = {1: (3, 31), 2: (6, 30), 3: (9, 30), 4: (12, 31)}
W = [0.22, 0.24, 0.26, 0.28]
FIRST_YEAR, LAST_Q = 2021, (2026, 2)


# ------------------------------------------------------------------ čísla
def quarter(y, q):
    """Výsledky jedného kvartálu v dolároch (rovnaké pomery ako v DEMOCO companyfacts)."""
    w = W[q - 1]
    rev = 400e6 * 1.12 ** (y - 2019) * w
    prod, serv = 0.6 * rev, 0.4 * rev
    cogs = 0.35 * rev
    gross = rev - cogs
    rnd, sm, ga = 0.22 * rev, 0.15 * rev, 0.10 * rev
    opex = rnd + sm + ga
    opinc = gross - opex
    intexp = 1.5e6
    pretax = opinc - intexp
    tax = 0.21 * pretax
    ni = pretax - tax
    da, sbc = 0.04 * rev, 0.06 * rev
    d_ar, d_inv, d_ap = -0.02 * rev, -0.01 * rev, 0.015 * rev
    cfo = ni + da + sbc + d_ar + d_inv + d_ap
    capex = -0.05 * rev
    div, buy = -0.10 * ni, -0.20 * ni
    return dict(prod=prod, serv=serv, rev=rev, cogs=cogs, gross=gross, rnd=rnd, sm=sm, ga=ga,
                opex=opex, opinc=opinc, intexp=intexp, pretax=pretax, tax=tax, ni=ni,
                da=da, sbc=sbc, d_ar=d_ar, d_inv=d_inv, d_ap=d_ap, cfo=cfo, capex=capex,
                cfi=capex, div=div, buy=buy, cff=div + buy, net_change=cfo + capex + div + buy)


def ytd(y, q_end):
    """Kumulatívne hodnoty od začiatku roka do kvartálu q_end."""
    out = {}
    for q in range(1, q_end + 1):
        for k, v in quarter(y, q).items():
            out[k] = out.get(k, 0) + v
    return out


def balance(y, q):
    """Súvaha na konci kvartálu."""
    cash = 100e6
    for yy in range(FIRST_YEAR, y + 1):
        for qq in range(1, 5):
            if (yy, qq) > (y, q):
                break
            cash += quarter(yy, qq)["net_change"]
    c = quarter(y, q)
    ar, inv = 0.5 * c["rev"], 0.6 * c["cogs"]
    tca = cash + ar + inv
    ppe, gw = 300e6, 200e6
    assets = tca + ppe + gw
    ap, accr = 0.8 * c["cogs"], 0.4 * c["rev"]
    tcl = ap + accr
    debt = 250e6
    tl = tcl + debt
    eq = assets - tl
    return dict(cash=cash, ar=ar, inv=inv, tca=tca, ppe=ppe, gw=gw, assets=assets, ap=ap,
                accr=accr, tcl=tcl, debt=debt, tl=tl, cs=1e6, re=eq - 1e6, eq=eq,
                tle=tl + eq)


# ------------------------------------------------------------------ HTML
def fdate(y, q):
    m, d = QEND[q]
    return f"{MONTH_ABBR[m - 1]} {d}, {y}"


def fnum(v, dollar=False, dec=0, scale=1e3):
    x = v / scale
    s = f"{abs(x):,.{dec}f}"
    if x < 0:
        return (f"$ ({s})" if dollar else f"({s})"), "num"
    return (f"$ {s}" if dollar else s), "nump"


def report_html(title, scale_text, groups, rows):
    """groups: [(popis_skupiny|None, [dátumy])]. rows: [(label, concept, hodnoty|None,
    dollar, dec)]; hodnoty None = hlavičkový riadok."""
    ncol = sum(len(d) for _, d in groups)
    h = ['<html><body><table class="report" border="0" cellspacing="2" id="idm1">']
    two = groups[0][0] is not None
    th = (f'<th class="tl" colspan="1" rowspan="{2 if two else 1}"><div style="width: 200px;">'
          f'<strong>{title} - USD ($)<br> {scale_text}</strong></div></th>')
    if two:
        h.append("<tr>" + th + "".join(
            f'<th class="th" colspan="{len(d)}"><div>{g}</div></th>' for g, d in groups) +
            "</tr>")
        h.append("<tr>" + "".join(f'<th class="th"><div>{x}</div></th>'
                                  for _, d in groups for x in d) + "</tr>")
    else:
        h.append("<tr>" + th + "".join(f'<th class="th"><div>{x}</div></th>'
                                       for _, d in groups for x in d) + "</tr>")
    for i, (label, concept, vals, dollar, dec) in enumerate(rows):
        cls = "re" if i % 2 == 0 else "ro"
        a = (f'<a class="a" href="javascript:void(0);" onclick="top.Show.showAR( this, '
             f"'defref_{concept}', window );\">{label}</a>")
        cells = f'<td class="pl " style="border-bottom: 0px;" valign="top">{a}</td>'
        if vals is None:
            cells += "".join('<td class="text">&nbsp;<span></span></td>' for _ in range(ncol))
        else:
            for v in vals:
                txt, c = fnum(v, dollar, dec, 1.0 if dec else 1e3)
                cells += f'<td class="{c}">{txt}<span></span></td>'
        h.append(f'<tr class="{cls}">{cells}</tr>')
    h.append('</table><table class="outerFootnotes"><tr><td>[1] Poznámka pod čiarou</td>'
             "</tr></table></body></html>")
    return "\n".join(h)


def income_rows(cols):
    """cols = [(y, kvartál_do|None, mesiace)] -> riadky výkazu ziskov a strát."""
    def col(fn, key):
        return [fn(y, q, m)[key] for (y, q, m) in cols]

    def val(y, q, m):
        return quarter(y, q) if m == 3 else ytd(y, q)

    g = lambda key: col(val, key)  # noqa: E731
    eps_b = [val(y, q, m)["ni"] / 100e6 for (y, q, m) in cols]
    eps_d = [val(y, q, m)["ni"] / 101e6 for (y, q, m) in cols]
    sh_b = [100e6] * len(cols)
    sh_d = [101e6] * len(cols)
    return [
        ("Net sales:", "us-gaap_RevenueFromContractWithCustomerExcludingAssessedTax", None, 0, 0),
        ("Net product sales", "us-gaap_RevenueFromContractWithCustomerExcludingAssessedTax",
         g("prod"), True, 0),
        ("Net service sales", "us-gaap_RevenueFromContractWithCustomerExcludingAssessedTax",
         g("serv"), False, 0),
        ("Total net sales", "us-gaap_Revenues", g("rev"), False, 0),
        ("Cost of sales", "us-gaap_CostOfRevenue", g("cogs"), False, 0),
        ("Gross profit", "us-gaap_GrossProfit", g("gross"), False, 0),
        ("Operating expenses:", "us-gaap_OperatingExpenses", None, 0, 0),
        ("Research and development", "us-gaap_ResearchAndDevelopmentExpense", g("rnd"), False, 0),
        ("Sales and marketing", "us-gaap_SellingAndMarketingExpense", g("sm"), False, 0),
        ("General and administrative", "us-gaap_GeneralAndAdministrativeExpense", g("ga"),
         False, 0),
        ("Total operating expenses", "us-gaap_OperatingExpenses", g("opex"), False, 0),
        ("Operating income", "us-gaap_OperatingIncomeLoss", g("opinc"), False, 0),
        ("Interest expense", "us-gaap_InterestExpense", g("intexp"), False, 0),
        ("Income before income taxes", "us-gaap_IncomeLossFromContinuingOperationsBeforeIncomeTaxes"
         "ExtraordinaryItemsNoncontrollingInterest", g("pretax"), False, 0),
        ("Provision for income taxes", "us-gaap_IncomeTaxExpenseBenefit", g("tax"), False, 0),
        ("Net income", "us-gaap_NetIncomeLoss", g("ni"), True, 0),
        ("Basic earnings per share", "us-gaap_EarningsPerShareBasic", eps_b, True, 2),
        ("Diluted earnings per share", "us-gaap_EarningsPerShareDiluted", eps_d, True, 2),
        ("Weighted-average shares used in computation of earnings per share:",
         "us-gaap_WeightedAverageNumberOfSharesOutstandingBasic", None, 0, 0),
        ("Basic", "us-gaap_WeightedAverageNumberOfSharesOutstandingBasic", sh_b, False, 0),
        ("Diluted", "us-gaap_WeightedAverageNumberOfDilutedSharesOutstanding", sh_d, False, 0),
    ]


def cashflow_rows(cols):
    def val(y, q, m):
        return ytd(y, q)

    g = lambda key: [val(y, q, m)[key] for (y, q, m) in cols]  # noqa: E731
    return [
        ("OPERATING ACTIVITIES:", "us-gaap_NetCashProvidedByUsedInOperatingActivities", None, 0, 0),
        ("Net income", "us-gaap_NetIncomeLoss", g("ni"), True, 0),
        ("Depreciation and amortization", "us-gaap_DepreciationDepletionAndAmortization",
         g("da"), False, 0),
        ("Stock-based compensation", "us-gaap_ShareBasedCompensation", g("sbc"), False, 0),
        ("Changes in accounts receivable", "us-gaap_IncreaseDecreaseInAccountsReceivable",
         g("d_ar"), False, 0),
        ("Changes in inventories", "us-gaap_IncreaseDecreaseInInventories", g("d_inv"), False, 0),
        ("Changes in accounts payable", "us-gaap_IncreaseDecreaseInAccountsPayable",
         g("d_ap"), False, 0),
        ("Net cash provided by operating activities",
         "us-gaap_NetCashProvidedByUsedInOperatingActivities", g("cfo"), False, 0),
        ("INVESTING ACTIVITIES:", "us-gaap_NetCashProvidedByUsedInInvestingActivities", None, 0, 0),
        ("Purchases of property and equipment",
         "us-gaap_PaymentsToAcquirePropertyPlantAndEquipment", g("capex"), False, 0),
        ("Net cash used in investing activities",
         "us-gaap_NetCashProvidedByUsedInInvestingActivities", g("cfi"), False, 0),
        ("FINANCING ACTIVITIES:", "us-gaap_NetCashProvidedByUsedInFinancingActivities", None, 0, 0),
        ("Dividends paid", "us-gaap_PaymentsOfDividends", g("div"), False, 0),
        ("Repurchases of common stock", "us-gaap_PaymentsForRepurchaseOfCommonStock",
         g("buy"), False, 0),
        ("Net cash used in financing activities",
         "us-gaap_NetCashProvidedByUsedInFinancingActivities", g("cff"), False, 0),
        ("Net increase in cash", "us-gaap_CashAndCashEquivalentsPeriodIncreaseDecrease",
         g("net_change"), False, 0),
    ]


def balance_rows(cols):
    g = lambda key: [balance(y, q)[key] for (y, q, m) in cols]  # noqa: E731
    return [
        ("Current assets:", "us-gaap_AssetsCurrent", None, 0, 0),
        ("Cash and cash equivalents", "us-gaap_CashAndCashEquivalentsAtCarryingValue",
         g("cash"), True, 0),
        ("Accounts receivable, net", "us-gaap_AccountsReceivableNetCurrent", g("ar"), False, 0),
        ("Inventories", "us-gaap_InventoryNet", g("inv"), False, 0),
        ("Total current assets", "us-gaap_AssetsCurrent", g("tca"), False, 0),
        ("Property and equipment, net", "us-gaap_PropertyPlantAndEquipmentNet", g("ppe"),
         False, 0),
        ("Goodwill", "us-gaap_Goodwill", g("gw"), False, 0),
        ("Total assets", "us-gaap_Assets", g("assets"), True, 0),
        ("Current liabilities:", "us-gaap_LiabilitiesCurrent", None, 0, 0),
        ("Accounts payable", "us-gaap_AccountsPayableCurrent", g("ap"), False, 0),
        ("Accrued expenses", "us-gaap_AccruedLiabilitiesCurrent", g("accr"), False, 0),
        ("Total current liabilities", "us-gaap_LiabilitiesCurrent", g("tcl"), False, 0),
        ("Long-term debt", "us-gaap_LongTermDebtNoncurrent", g("debt"), False, 0),
        ("Total liabilities", "us-gaap_Liabilities", g("tl"), False, 0),
        ("Stockholders' equity:", "us-gaap_StockholdersEquity", None, 0, 0),
        ("Common stock", "us-gaap_CommonStockValue", g("cs"), False, 0),
        ("Retained earnings", "us-gaap_RetainedEarningsAccumulatedDeficit", g("re"), False, 0),
        ("Total stockholders' equity", "us-gaap_StockholdersEquity", g("eq"), False, 0),
        ("Total liabilities and stockholders' equity",
         "us-gaap_LiabilitiesAndStockholdersEquity", g("tle"), True, 0),
    ]


# ------------------------------------------------------------------ podania
def revenue_detail_rows(cols):
    """Členenie tržieb podľa typu (poznámka „Revenue (Details)“)."""
    def val(y, q, m):
        return quarter(y, q) if m == 3 else ytd(y, q)

    rev = [val(y, q, m)["rev"] for (y, q, m) in cols]
    return [
        ("Revenue from External Customers by Type [Axis]", "us-gaap_RevenuesAbstract", None, 0, 0),
        ("Subscriptions [Member]", "us-gaap_Revenues", [0.55 * r for r in rev], True, 0),
        ("Licenses [Member]", "us-gaap_Revenues", [0.25 * r for r in rev], False, 0),
        ("Support and services [Member]", "us-gaap_Revenues", [0.20 * r for r in rev], False, 0),
        ("Total revenues", "us-gaap_Revenues", rev, False, 0),
    ]


def summary_xml(order):
    """order = [(R-súbor, názov, kategória)] v poradí zobrazenia."""
    parts = ['<?xml version="1.0" encoding="utf-8"?><FilingSummary><Version>3.25.1</Version>'
             "<Reports>"]
    for i, (fname, short, cat) in enumerate(order, 1):
        parts.append(
            '<Report instance="democo.htm"><IsDefault>false</IsDefault>'
            "<HasEmbeddedReports>false</HasEmbeddedReports>"
            f"<HtmlFileName>{fname}</HtmlFileName><LongName>{i:07d} - {cat} - {short}</LongName>"
            f"<ReportType>Sheet</ReportType><Role>http://democo/role/{i}</Role>"
            f"<ShortName>{short}</ShortName><MenuCategory>{cat}</MenuCategory>"
            f"<Position>{i}</Position></Report>")
    parts.append("</Reports></FilingSummary>")
    return "".join(parts)


def write(root, acc, name, text):
    d = os.path.join(root, acc)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, name), "w", encoding="utf-8") as f:
        f.write(text)


def make_10k(root, acc, fy):
    cols = [(fy - i, 4, 12) for i in range(3)]
    dates = [fdate(y, 4) for y, _, _ in cols]
    write(root, acc, "R2.htm", report_html(
        "CONSOLIDATED STATEMENTS OF OPERATIONS", "$ in Thousands",
        [("12 Months Ended", dates)], income_rows(cols)))
    write(root, acc, "R3.htm", report_html(
        "CONSOLIDATED STATEMENTS OF COMPREHENSIVE INCOME", "$ in Thousands",
        [("12 Months Ended", dates)],
        [("Net income", "us-gaap_NetIncomeLoss", [quarter(y, 4)["ni"] for y, _, _ in cols],
          True, 0)]))
    write(root, acc, "R7.htm", report_html(
        "Revenue (Details)", "$ in Thousands", [("12 Months Ended", dates)],
        revenue_detail_rows(cols)))
    bcols = cols[:2]
    write(root, acc, "R4.htm", report_html(
        "CONSOLIDATED BALANCE SHEETS", "$ in Thousands",
        [(None, [fdate(y, 4) for y, _, _ in bcols])], balance_rows(bcols)))
    write(root, acc, "R5.htm", report_html(
        "CONSOLIDATED BALANCE SHEETS (Parenthetical)", "$ in Thousands",
        [(None, [fdate(y, 4) for y, _, _ in bcols])],
        [("Common stock, shares issued", "us-gaap_CommonStockSharesIssued", [100e6, 100e6],
          False, 0)]))
    write(root, acc, "R6.htm", report_html(
        "CONSOLIDATED STATEMENTS OF CASH FLOWS", "$ in Thousands",
        [("12 Months Ended", dates)], cashflow_rows(cols)))
    write(root, acc, "FilingSummary.xml", summary_xml([
        ("R1.htm", "Cover Page", "Cover"),
        ("R2.htm", "CONSOLIDATED STATEMENTS OF OPERATIONS", "Statements"),
        ("R3.htm", "CONSOLIDATED STATEMENTS OF COMPREHENSIVE INCOME", "Statements"),
        ("R4.htm", "CONSOLIDATED BALANCE SHEETS", "Statements"),
        ("R5.htm", "CONSOLIDATED BALANCE SHEETS (Parenthetical)", "Statements"),
        ("R6.htm", "CONSOLIDATED STATEMENTS OF CASH FLOWS", "Statements"),
        ("R7.htm", "Revenue (Details)", "Details")]))


def make_10q(root, acc, y, q):
    cur, pri = (y, q), (y - 1, q)
    groups = [("3 Months Ended", [fdate(y, q), fdate(y - 1, q)])]
    cols = [(y, q, 3), (y - 1, q, 3)]
    if q > 1:
        groups.append((f"{3 * q} Months Ended", [fdate(y, q), fdate(y - 1, q)]))
        cols += [(y, q, 3 * q), (y - 1, q, 3 * q)]
    # R-čísla v 10-Q: súvaha prvá, potom výsledky (iné poradie než v 10-K)
    bcols = [(y, q, 3), (y - 1, 4, 12)]
    write(root, acc, "R2.htm", report_html(
        "CONDENSED CONSOLIDATED BALANCE SHEETS", "$ in Thousands",
        [(None, [fdate(y, q), fdate(y - 1, 4)])], balance_rows(bcols)))
    write(root, acc, "R4.htm", report_html(
        "CONDENSED CONSOLIDATED STATEMENTS OF OPERATIONS", "$ in Thousands",
        groups, income_rows(cols)))
    write(root, acc, "R8.htm", report_html(
        "Revenue (Details)", "$ in Thousands", groups, revenue_detail_rows(cols)))
    cfc = [(y, q, 3 * q), (y - 1, q, 3 * q)]
    write(root, acc, "R7.htm", report_html(
        "CONDENSED CONSOLIDATED STATEMENTS OF CASH FLOWS", "$ in Thousands",
        [(f"{3 * q} Months Ended", [fdate(y, q), fdate(y - 1, q)])], cashflow_rows(cfc)))
    write(root, acc, "FilingSummary.xml", summary_xml([
        ("R1.htm", "Cover Page", "Cover"),
        ("R2.htm", "CONDENSED CONSOLIDATED BALANCE SHEETS", "Statements"),
        ("R3.htm", "CONDENSED CONSOLIDATED BALANCE SHEETS (Parenthetical)", "Statements"),
        ("R4.htm", "CONDENSED CONSOLIDATED STATEMENTS OF OPERATIONS", "Statements"),
        ("R5.htm", "CONDENSED CONSOLIDATED STATEMENTS OF COMPREHENSIVE INCOME", "Statements"),
        ("R7.htm", "CONDENSED CONSOLIDATED STATEMENTS OF CASH FLOWS", "Statements"),
        ("R8.htm", "Revenue (Details)", "Details")]))


def generate(root):
    """Vytvorí súbory podaní v `root` a vráti zoznam podaní vo formáte submissions API."""
    recent = {"accessionNumber": [], "filingDate": [], "reportDate": [], "form": [],
              "primaryDocument": []}
    n = 0
    items = []
    for y in range(FIRST_YEAR, LAST_Q[0] + 1):
        for q in range(1, 4):
            if (y, q) > LAST_Q:
                break
            m, d = QEND[q]
            items.append(("10-Q", y, q, f"{y}-{m + 1:02d}-05", f"{y}-{m:02d}-{d:02d}"))
        if y < LAST_Q[0]:
            items.append(("10-K", y, 4, f"{y + 1}-02-20", f"{y}-12-31"))
    for form, y, q, filed, rdate in items:
        n += 1
        acc = f"0009000001-{str(y)[2:]}-{n:06d}"
        accnd = acc.replace("-", "")
        if form == "10-K":
            make_10k(root, accnd, y)
        else:
            make_10q(root, accnd, y, q)
        recent["accessionNumber"].append(acc)
        recent["filingDate"].append(filed)
        recent["reportDate"].append(rdate)
        recent["form"].append(form)
        recent["primaryDocument"].append("democo.htm")
    return recent

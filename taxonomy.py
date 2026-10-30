"""Mapovanie XBRL tagov (us-gaap / ifrs-full) na riadky výkazov.

Každý riadok má zoznam tagov v poradí priority. Ak firma v rôznych rokoch
používa rôzne tagy, hodnoty sa pre každé obdobie vezmú z prvého tagu, ktorý
pre dané obdobie existuje. Tagy z IFRS majú prefix "ifrs:".
"""


def I(key, label, tags, kind="flow", unit="cur", bold=False, indent=0, additive=True):
    return dict(key=key, label=label, tags=tags, kind=kind, unit=unit,
                bold=bold, indent=indent, additive=additive)


# ---------------------------------------------------------------- VÝKAZ ZISKOV A STRÁT
INCOME = [
    I("revenue", "Tržby (výnosy)", [
        "Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax",
        "RevenueFromContractWithCustomerIncludingAssessedTax", "SalesRevenueNet",
        "SalesRevenueGoodsNet", "SalesRevenueServicesNet", "ifrs:Revenue",
    ], bold=True),
    I("cost_of_revenue", "Náklady na tržby", [
        "CostOfRevenue", "CostOfGoodsAndServicesSold", "CostOfGoodsSold",
        "ifrs:CostOfSales",
    ], indent=1),
    I("gross_profit", "Hrubý zisk", ["GrossProfit", "ifrs:GrossProfit"], bold=True),
    I("rnd", "Výskum a vývoj", ["ResearchAndDevelopmentExpense"], indent=1),
    I("sga", "Predaj, všeobecné a administratívne náklady", [
        "SellingGeneralAndAdministrativeExpense"], indent=1),
    I("ga", "Všeobecné a administratívne náklady", [
        "GeneralAndAdministrativeExpense"], indent=1),
    I("opex_total", "Prevádzkové náklady spolu", ["OperatingExpenses"], indent=1),
    I("costs_expenses", "Náklady a výdavky spolu", ["CostsAndExpenses"], indent=1),
    I("op_income", "Prevádzkový zisk", [
        "OperatingIncomeLoss", "ifrs:ProfitLossFromOperatingActivities"], bold=True),
    # banky / fintech
    I("int_income", "Úrokové výnosy", [
        "InterestAndDividendIncomeOperating", "InterestIncomeOperating",
        "InterestAndFeeIncomeLoansAndLeases",
        "ifrs:InterestRevenueCalculatedUsingEffectiveInterestMethod"]),
    I("interest_expense", "Úrokové náklady", [
        "InterestExpense", "InterestExpenseOperating", "InterestExpenseDebt",
        "ifrs:InterestExpense", "ifrs:FinanceCosts"]),
    I("nii", "Čistý úrokový výnos", [
        "InterestIncomeExpenseNet", "ifrs:InterestRevenueExpense"], bold=True),
    I("provision", "Opravné položky / náklady na úverové straty", [
        "ProvisionForLoanLeaseAndOtherLosses", "ProvisionForLoanAndLeaseLosses",
        "ProvisionForCreditLosses", "CreditLossExpenseReversal",
        "ProvisionForLoanLossesExpensed"], indent=1),
    I("nonint_income", "Neúrokové výnosy", ["NoninterestIncome"]),
    I("nonint_expense", "Neúrokové náklady", ["NoninterestExpense"]),
    # poisťovne
    I("premiums", "Zaslúžené poistné", [
        "PremiumsEarnedNet", "ifrs:InsuranceRevenue"]),
    I("claims", "Poistné plnenia a škody", [
        "PolicyholderBenefitsAndClaimsIncurredNet",
        "IncurredClaimsPropertyCasualtyAndLiability"]),
    I("total_benefits_expenses", "Plnenia a náklady spolu", ["BenefitsLossesAndExpenses"]),
    I("inv_income", "Výnosy z investícií", ["NetInvestmentIncome"]),
    # spoločné
    I("pretax", "Zisk pred zdanením", [
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments",
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesDomestic",
        "ifrs:ProfitLossBeforeTax"], bold=True),
    I("tax", "Daň z príjmu", ["IncomeTaxExpenseBenefit",
                              "ifrs:IncomeTaxExpenseContinuingOperations"], indent=1),
    I("net_income", "Čistý zisk", [
        "NetIncomeLoss", "ProfitLoss", "NetIncomeLossAvailableToCommonStockholdersBasic",
        "ifrs:ProfitLossAttributableToOwnersOfParent", "ifrs:ProfitLoss"], bold=True),
    I("eps_basic", "EPS – základný", ["EarningsPerShareBasic",
                                       "ifrs:BasicEarningsLossPerShare"], unit="eps"),
    I("eps_diluted", "EPS – zriedený", ["EarningsPerShareDiluted",
                                         "ifrs:DilutedEarningsLossPerShare"], unit="eps"),
    I("shares_diluted", "Vážený priemer akcií – zriedený", [
        "WeightedAverageNumberOfDilutedSharesOutstanding",
        "WeightedAverageNumberOfSharesOutstandingBasicAndDiluted",
        "WeightedAverageNumberOfSharesOutstandingBasic",
        "ifrs:WeightedAverageShares"], unit="shares", additive=False),
]

# ---------------------------------------------------------------------- SÚVAHA
BALANCE = [
    I("cash", "Hotovosť a ekvivalenty", [
        "CashAndCashEquivalentsAtCarryingValue",
        "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
        "CashAndDueFromBanks", "ifrs:CashAndCashEquivalents"], "instant"),
    I("st_investments", "Krátkodobé investície", [
        "ShortTermInvestments", "MarketableSecuritiesCurrent",
        "AvailableForSaleSecuritiesDebtSecuritiesCurrent"], "instant"),
    I("receivables", "Pohľadávky", [
        "AccountsReceivableNetCurrent", "ReceivablesNetCurrent",
        "ifrs:TradeAndOtherCurrentReceivables"], "instant"),
    I("inventory", "Zásoby", ["InventoryNet", "ifrs:Inventories"], "instant"),
    I("other_current_assets", "Ostatné obežné aktíva (vr. platených nákladov)", [
        "PrepaidExpenseAndOtherAssetsCurrent", "OtherAssetsCurrent", "PrepaidExpenseCurrent"], "instant"),
    I("current_assets", "Obežné aktíva spolu", ["AssetsCurrent", "ifrs:CurrentAssets"],
      "instant", bold=True),
    # banky
    I("securities_afs", "Cenné papiere na predaj (AFS)", [
        "AvailableForSaleSecuritiesDebtSecurities"], "instant"),
    I("securities_htm", "Cenné papiere držané do splatnosti", [
        "HeldToMaturitySecurities"], "instant"),
    I("loans", "Úvery (netto)", [
        "LoansAndLeasesReceivableNetReportedAmount",
        "LoansAndLeasesReceivableNetOfDeferredIncome"], "instant"),
    I("allowance", "Opravná položka k úverom", [
        "LoansAndLeasesReceivableAllowance",
        "FinancingReceivableAllowanceForCreditLosses"], "instant", indent=1),
    I("ppe", "Pozemky, budovy a zariadenia", [
        "PropertyPlantAndEquipmentNet", "ifrs:PropertyPlantAndEquipment"], "instant"),
    I("lt_investments", "Dlhodobé investície a cenné papiere", [
        "MarketableSecuritiesNoncurrent", "LongTermInvestments", "AvailableForSaleSecuritiesNoncurrent"],
      "instant"),
    I("rou_assets", "Právo na užívanie majetku (lízingy)", ["OperatingLeaseRightOfUseAsset"], "instant"),
    I("goodwill", "Goodwill", ["Goodwill", "ifrs:Goodwill"], "instant"),
    I("intangibles", "Nehmotný majetok", [
        "IntangibleAssetsNetExcludingGoodwill",
        "FiniteLivedIntangibleAssetsNet",
        "ifrs:IntangibleAssetsOtherThanGoodwill"], "instant"),
    I("other_assets_nc", "Ostatné dlhodobé aktíva", ["OtherAssetsNoncurrent", "OtherAssetsMiscellaneousNoncurrent"],
      "instant"),
    I("total_assets", "Aktíva spolu", ["Assets", "ifrs:Assets"], "instant", bold=True),
    I("payables", "Záväzky z obchodného styku", [
        "AccountsPayableCurrent", "ifrs:TradeAndOtherCurrentPayables"], "instant"),
    I("accrued", "Časovo rozlíšené náklady a ostatné záväzky", ["AccruedLiabilitiesCurrent"], "instant"),
    I("employee_liab", "Záväzky voči zamestnancom", ["EmployeeRelatedLiabilitiesCurrent"], "instant"),
    I("taxes_payable", "Splatné dane z príjmov (krátkodobé)", ["AccruedIncomeTaxesCurrent", "TaxesPayableCurrent",
                                                              "IncomeTaxesPayableCurrent"], "instant"),
    I("deferred_rev", "Výnosy budúcich období (krátkodobé)", [
        "ContractWithCustomerLiabilityCurrent", "DeferredRevenueCurrent"], "instant"),
    I("other_cl", "Ostatné krátkodobé záväzky", ["OtherLiabilitiesCurrent"], "instant"),
    I("deposits", "Vklady", ["Deposits", "ifrs:DepositsFromCustomers"], "instant"),
    I("debt_current", "Krátkodobý dlh", [
        "DebtCurrent", "LongTermDebtCurrent", "ShortTermBorrowings"], "instant"),
    I("current_liabilities", "Krátkodobé záväzky spolu", [
        "LiabilitiesCurrent", "ifrs:CurrentLiabilities"], "instant", bold=True),
    I("debt_lt", "Dlhodobý dlh", [
        "LongTermDebtNoncurrent", "LongTermDebt", "ifrs:NoncurrentPortionOfNoncurrentLoansReceived"],
      "instant"),
    I("lease_nc", "Dlhodobé záväzky z lízingov (operatívne)", ["OperatingLeaseLiabilityNoncurrent"], "instant"),
    I("deferred_rev_nc", "Výnosy budúcich období (dlhodobé)", [
        "ContractWithCustomerLiabilityNoncurrent", "DeferredRevenueNoncurrent"], "instant"),
    I("deferred_tax_liab", "Odložené daňové záväzky", ["DeferredIncomeTaxLiabilitiesNet",
                                                       "DeferredIncomeTaxLiabilities"], "instant"),
    I("other_liab_nc", "Ostatné dlhodobé záväzky", ["OtherLiabilitiesNoncurrent"], "instant"),
    I("total_liabilities", "Záväzky spolu", ["Liabilities", "ifrs:Liabilities"],
      "instant", bold=True),
    I("common_stock", "Základné imanie a emisné ážio", [
        "CommonStocksIncludingAdditionalPaidInCapital", "CommonStockValue"], "instant", indent=1),
    I("apic", "Dodatočne splatený kapitál", ["AdditionalPaidInCapital", "AdditionalPaidInCapitalCommonStock"],
      "instant", indent=1),
    I("treasury", "Vlastné akcie v držbe (odpočítava sa)", ["TreasuryStockValue", "TreasuryStockCommonValue"],
      "instant", indent=1),
    I("retained", "Nerozdelený zisk", ["RetainedEarningsAccumulatedDeficit"], "instant", indent=1),
    I("aoci", "Ostatný súhrnný zisk/strata (AOCI)", ["AccumulatedOtherComprehensiveIncomeLossNetOfTax"],
      "instant", indent=1),
    I("equity", "Vlastné imanie", [
        "StockholdersEquity",
        "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
        "ifrs:EquityAttributableToOwnersOfParent", "ifrs:Equity"], "instant", bold=True),
    I("total_liab_equity", "Pasíva spolu", [
        "LiabilitiesAndStockholdersEquity", "ifrs:EquityAndLiabilities"], "instant",
      bold=True),
]

# ------------------------------------------------------------------- CASH FLOW
CASHFLOW = [
    I("cf_net_income", "Čistý zisk (cash flow)", ["NetIncomeLoss", "ProfitLoss",
                                                  "ifrs:ProfitLoss"]),
    I("da", "Odpisy a amortizácia", [
        "DepreciationDepletionAndAmortization", "DepreciationAndAmortization",
        "DepreciationAmortizationAndAccretionNet",
        "DepreciationAmortizationAndOther",
        "ifrs:DepreciationAndAmortisationExpense"], indent=1),
    I("sbc", "Akciová kompenzácia", [
        "ShareBasedCompensation", "AllocatedShareBasedCompensationExpense",
        "ifrs:AdjustmentsForSharebasedPayments"], indent=1),
    I("gain_on_sale", "Zisk z predaja nehnuteľností", [
        "GainLossOnSaleOfPropertiesNetOfApplicableIncomeTaxes",
        "GainLossOnSaleOfRealEstateInvestmentPropertyNetOfTax",
        "GainLossOnSaleOfPropertyPlantEquipment",
        "GainLossOnSaleOfRealEstate"], indent=1),
    I("cfo", "Cash flow z prevádzkovej činnosti", [
        "NetCashProvidedByUsedInOperatingActivities",
        "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
        "ifrs:CashFlowsFromUsedInOperatingActivities"], bold=True),
    I("capex", "Kapitálové výdavky (CapEx)", [
        "PaymentsToAcquirePropertyPlantAndEquipment",
        "PaymentsToAcquireProductiveAssets",
        "PaymentsToAcquirePropertyPlantAndEquipmentAndIntangibleAssets",
        "ifrs:PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities"],
      indent=1),
    I("capex_sw", "Kapitalizovaný softvér (vývoj/nákup)", [
        "PaymentsToDevelopSoftware", "PaymentsForSoftware",
        "PaymentsToAcquireIntangibleAssets",
        "ifrs:PurchaseOfIntangibleAssetsClassifiedAsInvestingActivities"], indent=1),
    I("cfi", "Cash flow z investičnej činnosti", [
        "NetCashProvidedByUsedInInvestingActivities",
        "NetCashProvidedByUsedInInvestingActivitiesContinuingOperations",
        "ifrs:CashFlowsFromUsedInInvestingActivities"], bold=True),
    I("div_paid", "Vyplatené dividendy", [
        "PaymentsOfDividends", "PaymentsOfDividendsCommonStock",
        "ifrs:DividendsPaidClassifiedAsFinancingActivities"], indent=1),
    I("buybacks", "Spätné odkupy akcií", ["PaymentsForRepurchaseOfCommonStock"], indent=1),
    I("debt_issued", "Emisia dlhu", ["ProceedsFromIssuanceOfLongTermDebt",
                                     "ProceedsFromIssuanceOfDebt"], indent=1),
    I("debt_repaid", "Splátky dlhu", ["RepaymentsOfLongTermDebt", "RepaymentsOfDebt"],
      indent=1),
    I("cff", "Cash flow z finančnej činnosti", [
        "NetCashProvidedByUsedInFinancingActivities",
        "NetCashProvidedByUsedInFinancingActivitiesContinuingOperations",
        "ifrs:CashFlowsFromUsedInFinancingActivities"], bold=True),
]

ALL_ITEMS = INCOME + BALANCE + CASHFLOW
ITEM_BY_KEY = {it["key"]: it for it in ALL_ITEMS}

# Tagy pre počet akcií na obálke 10-K/10-Q (namespace dei)
SHARES_OUT_TAGS = ["dei:EntityCommonStockSharesOutstanding"]

# Pomocné (odvodené) riadky, ktoré sa zobrazujú vo výkazoch
DERIVED_LABELS = {
    "total_debt": ("Celkový dlh", True),
    "fcf": ("Voľný cash flow (FCF = CFO − CapEx)", True),
}

# Riadky zobrazené v jednotlivých výkazoch (poradie)
IS_ROWS = [it["key"] for it in INCOME]
BS_ROWS = [it["key"] for it in BALANCE]
CF_ROWS = [it["key"] for it in CASHFLOW]

# Ktoré kľúče sú "toky" (sčítavajú sa do TTM)
FLOW_KEYS = {it["key"] for it in ALL_ITEMS if it["kind"] == "flow" and it["additive"]}

# SIC kódy -> typ biznisu
BANK_SIC = {6021, 6022, 6029, 6035, 6036, 6099, 6111, 6141, 6153, 6159, 6162, 6163,
            6172, 6199}
INSURANCE_SIC = set(range(6300, 6400)) | {6411}
REIT_SIC = {6798}
TECH_SIC = {3571, 3572, 3575, 3576, 3577, 3578, 3579, 3661, 3663, 3669, 3674, 3672,
            3690, 4899} | set(range(7370, 7380))

BUSINESS_TYPES = {
    "general": "Všeobecný (priemysel, spotrebný tovar, služby)",
    "tech": "Technológie / softvér / rastové firmy",
    "bank": "Banka / fintech / úverová spoločnosť",
    "insurance": "Poisťovňa",
    "reit": "REIT (nehnuteľnostný fond)",
}

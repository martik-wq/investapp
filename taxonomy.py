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
    I("rnd", "Výskum a vývoj", ["ResearchAndDevelopmentExpense", "ifrs:ResearchAndDevelopmentExpense"], indent=1),
    I("sales_mkt", "Predaj a marketing", ["SellingAndMarketingExpense", "ifrs:SalesAndMarketingExpense",
                                          "ifrs:SellingExpense", "ifrs:DistributionCosts"], indent=1),
    I("sga", "Predaj, všeobecné a administratívne náklady", [
        "SellingGeneralAndAdministrativeExpense", "ifrs:SellingGeneralAndAdministrativeExpense"], indent=1),
    I("ga", "Všeobecné a administratívne náklady", [
        "GeneralAndAdministrativeExpense", "ifrs:GeneralAndAdministrativeExpense",
        "ifrs:AdministrativeExpense"], indent=1),
    I("other_op_income", "Ostatné prevádzkové výnosy", ["ifrs:OtherIncome", "ifrs:OtherOperatingIncomeExpense"],
      indent=1),
    I("other_op_expense", "Ostatné prevádzkové náklady", ["ifrs:OtherExpenseByFunction", "ifrs:OtherExpense"],
      indent=1),
    I("impair_fin", "Znehodnotenie finančných aktív (úverové straty)", [
        "ifrs:ImpairmentLossImpairmentGainAndReversalOfImpairmentLossDeterminedInAccordanceWithIFRS9",
        "ifrs:ImpairmentLossReversalOfImpairmentLossRecognisedInProfitOrLoss"], indent=1),
    I("opex_total", "Prevádzkové náklady spolu", ["OperatingExpenses", "ifrs:OperatingExpense"], indent=1),
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
    I("fee_income", "Výnosy z poplatkov a provízií", ["ifrs:FeeAndCommissionIncome",
                                                       "ifrs:FeeAndCommissionIncomeExpense"]),
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
    # finančný výsledok (IFRS: finance income / finance costs)
    I("fin_income", "Finančné výnosy", ["ifrs:FinanceIncome"], indent=1),
    I("fin_costs", "Finančné náklady", ["ifrs:FinanceCosts"], indent=1),
    I("fin_net", "Čisté finančné výnosy / náklady", ["ifrs:FinanceIncomeCost"]),
    I("fx_gain", "Kurzové zisky / straty (netto)", ["ifrs:NetForeignExchangeGain",
                                                     "ForeignCurrencyTransactionGainLossBeforeTax"], indent=1),
    I("equity_method", "Podiel na zisku / strate pridružených spoločností", [
        "IncomeLossFromEquityMethodInvestments",
        "ifrs:ShareOfProfitLossOfAssociatesAndJointVenturesAccountedForUsingEquityMethod"], indent=1),
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
    I("ni_total", "Čistý zisk vrátane menšinových podielov", ["ProfitLoss", "ifrs:ProfitLoss"], indent=1),
    I("ni_nci", "z toho menšinovým (nekontrolujúcim) podielom", [
        "NetIncomeLossAttributableToNoncontrollingInterest",
        "ifrs:ProfitLossAttributableToNoncontrollingInterests"], indent=1),
    I("eps_basic", "EPS – základný", ["EarningsPerShareBasic",
                                       "ifrs:BasicEarningsLossPerShare"], unit="eps"),
    I("eps_diluted", "EPS – zriedený", ["EarningsPerShareDiluted",
                                         "ifrs:DilutedEarningsLossPerShare"], unit="eps"),
    I("shares_diluted", "Vážený priemer akcií – zriedený", [
        "WeightedAverageNumberOfDilutedSharesOutstanding",
        "WeightedAverageNumberOfSharesOutstandingBasicAndDiluted",
        "WeightedAverageNumberOfSharesOutstandingBasic",
        "ifrs:AdjustedWeightedAverageShares",          # IFRS: „adjusted“ = zriedený počet
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
        "AvailableForSaleSecuritiesDebtSecuritiesCurrent", "ifrs:OtherCurrentFinancialAssets",
        "ifrs:CurrentInvestments"], "instant"),
    I("receivables", "Pohľadávky", [
        "AccountsReceivableNetCurrent", "ReceivablesNetCurrent",
        "ifrs:TradeAndOtherCurrentReceivables"], "instant"),
    I("inventory", "Zásoby", ["InventoryNet", "ifrs:Inventories"], "instant"),
    I("fin_assets_amc_cur", "Poskytnuté úvery a fin. aktíva v amortizovanej hodnote (krátkodobé)", [
        "ifrs:CurrentFinancialAssetsAtAmortisedCost", "ifrs:CurrentLoansAndReceivables"], "instant"),
    I("prepayments_cur", "Preddavky a platené náklady (krátkodobé)", ["ifrs:CurrentPrepayments"], "instant",
      indent=1),
    I("other_current_assets", "Ostatné obežné aktíva (vr. platených nákladov)", [
        "PrepaidExpenseAndOtherAssetsCurrent", "OtherAssetsCurrent", "PrepaidExpenseCurrent",
        "ifrs:OtherCurrentAssets", "ifrs:OtherCurrentNonfinancialAssets"], "instant"),
    I("current_assets", "Obežné aktíva spolu", ["AssetsCurrent", "ifrs:CurrentAssets"],
      "instant", bold=True),
    # banky
    I("securities_afs", "Cenné papiere na predaj (AFS)", [
        "AvailableForSaleSecuritiesDebtSecurities"], "instant"),
    I("securities_htm", "Cenné papiere držané do splatnosti", [
        "HeldToMaturitySecurities"], "instant"),
    I("loans", "Úvery (netto)", [
        "LoansAndLeasesReceivableNetReportedAmount",
        "LoansAndLeasesReceivableNetOfDeferredIncome", "ifrs:LoansAndAdvancesToCustomers"], "instant"),
    I("allowance", "Opravná položka k úverom", [
        "LoansAndLeasesReceivableAllowance",
        "FinancingReceivableAllowanceForCreditLosses"], "instant", indent=1),
    I("ppe", "Pozemky, budovy a zariadenia", [
        "PropertyPlantAndEquipmentNet", "ifrs:PropertyPlantAndEquipment",
        "ifrs:PropertyPlantAndEquipmentIncludingRightofuseAssets"], "instant"),
    I("lt_investments", "Dlhodobé investície a cenné papiere", [
        "MarketableSecuritiesNoncurrent", "LongTermInvestments", "AvailableForSaleSecuritiesNoncurrent",
        "ifrs:NoncurrentInvestmentsOtherThanInvestmentsAccountedForUsingEquityMethod",
        "ifrs:OtherNoncurrentFinancialAssets", "ifrs:NoncurrentInvestments"], "instant"),
    I("equity_method_inv", "Investície v pridružených a spoločných podnikoch", [
        "EquityMethodInvestments", "ifrs:InvestmentsAccountedForUsingEquityMethod",
        "ifrs:InvestmentsInAssociates", "ifrs:InvestmentsInSubsidiariesJointVenturesAndAssociates"], "instant"),
    I("fin_assets_amc_nc", "Poskytnuté úvery a fin. aktíva v amortizovanej hodnote (dlhodobé)", [
        "ifrs:NoncurrentFinancialAssetsAtAmortisedCost", "ifrs:NoncurrentLoansAndReceivables"], "instant"),
    I("rou_assets", "Právo na užívanie majetku (lízingy)", ["OperatingLeaseRightOfUseAsset", "ifrs:RightofuseAssets"],
      "instant"),
    I("goodwill", "Goodwill", ["Goodwill", "ifrs:Goodwill"], "instant"),
    I("intangibles", "Nehmotný majetok", [
        "IntangibleAssetsNetExcludingGoodwill",
        "FiniteLivedIntangibleAssetsNet",
        "ifrs:IntangibleAssetsOtherThanGoodwill"], "instant"),
    I("intangibles_gw", "Nehmotný majetok vrátane goodwillu", ["IntangibleAssetsNetIncludingGoodwill",
                                                               "ifrs:IntangibleAssetsAndGoodwill"], "instant"),
    I("dta", "Odložené daňové pohľadávky", ["DeferredIncomeTaxAssetsNet", "ifrs:DeferredTaxAssets"], "instant"),
    I("other_assets_nc", "Ostatné dlhodobé aktíva", ["OtherAssetsNoncurrent", "OtherAssetsMiscellaneousNoncurrent",
                                                    "ifrs:OtherNoncurrentAssets"], "instant"),
    I("noncurrent_assets", "Dlhodobé aktíva spolu", ["NoncurrentAssets", "ifrs:NoncurrentAssets"], "instant",
      bold=True),
    I("total_assets", "Aktíva spolu", ["Assets", "ifrs:Assets"], "instant", bold=True),
    I("payables", "Záväzky z obchodného styku", [
        "AccountsPayableCurrent", "ifrs:TradeAndOtherCurrentPayables"], "instant"),
    I("accrued", "Časovo rozlíšené náklady a ostatné záväzky", [
        "AccruedLiabilitiesCurrent", "ifrs:CurrentAccruedExpensesAndOtherCurrentLiabilities",
        "ifrs:AccrualsClassifiedAsCurrent"], "instant"),
    I("employee_liab", "Záväzky voči zamestnancom", ["EmployeeRelatedLiabilitiesCurrent"], "instant"),
    I("taxes_payable", "Splatné dane z príjmov (krátkodobé)", ["AccruedIncomeTaxesCurrent", "TaxesPayableCurrent",
                                                              "IncomeTaxesPayableCurrent", "ifrs:CurrentTaxLiabilities",
                                                              "ifrs:CurrentTaxLiabilitiesCurrent"], "instant"),
    I("deferred_rev", "Výnosy budúcich období (krátkodobé)", [
        "ContractWithCustomerLiabilityCurrent", "DeferredRevenueCurrent", "ifrs:CurrentContractLiabilities",
        "ifrs:ContractLiabilities"], "instant"),
    I("provisions_cur", "Rezervy (krátkodobé)", ["ifrs:CurrentProvisions"], "instant"),
    I("lease_cur", "Záväzky z lízingov (krátkodobé)", ["OperatingLeaseLiabilityCurrent",
                                                        "ifrs:CurrentLeaseLiabilities"], "instant"),
    I("other_cl", "Ostatné krátkodobé záväzky", ["OtherLiabilitiesCurrent", "ifrs:OtherCurrentLiabilities"],
      "instant"),
    I("deposits", "Vklady", ["Deposits", "ifrs:DepositsFromCustomers"], "instant"),
    I("debt_current", "Krátkodobý dlh", [
        "DebtCurrent", "LongTermDebtCurrent", "ShortTermBorrowings",
        "ifrs:CurrentBorrowingsAndCurrentPortionOfNoncurrentBorrowings", "ifrs:ShorttermBorrowings"], "instant"),
    I("current_liabilities", "Krátkodobé záväzky spolu", [
        "LiabilitiesCurrent", "ifrs:CurrentLiabilities"], "instant", bold=True),
    I("debt_lt", "Dlhodobý dlh", [
        "LongTermDebtNoncurrent", "LongTermDebt", "ifrs:LongtermBorrowings",
        "ifrs:NoncurrentPortionOfNoncurrentBorrowings", "ifrs:NoncurrentPortionOfNoncurrentLoansReceived"],
      "instant"),
    I("lease_nc", "Dlhodobé záväzky z lízingov", ["OperatingLeaseLiabilityNoncurrent",
                                                 "ifrs:NoncurrentLeaseLiabilities"], "instant"),
    I("provisions_nc", "Rezervy (dlhodobé)", ["ifrs:NoncurrentProvisions"], "instant"),
    I("deferred_rev_nc", "Výnosy budúcich období (dlhodobé)", [
        "ContractWithCustomerLiabilityNoncurrent", "DeferredRevenueNoncurrent"], "instant"),
    I("deferred_tax_liab", "Odložené daňové záväzky", ["DeferredIncomeTaxLiabilitiesNet",
                                                       "DeferredIncomeTaxLiabilities", "ifrs:DeferredTaxLiabilities"],
      "instant"),
    I("other_liab_nc", "Ostatné dlhodobé záväzky", ["OtherLiabilitiesNoncurrent", "ifrs:OtherNoncurrentFinancialLiabilities",
                                                   "ifrs:OtherNoncurrentLiabilities"], "instant"),
    I("noncurrent_liabilities", "Dlhodobé záväzky spolu", ["LiabilitiesNoncurrent", "ifrs:NoncurrentLiabilities"],
      "instant", bold=True),
    I("total_liabilities", "Záväzky spolu", ["Liabilities", "ifrs:Liabilities"],
      "instant", bold=True),
    I("temp_equity", "Dočasné vlastné imanie (odkúpiteľné prioritné akcie / menšinové podiely)", [
        "TemporaryEquityCarryingAmountIncludingPortionAttributableToNoncontrollingInterests",
        "TemporaryEquityCarryingAmountAttributableToParent",
        "RedeemableNoncontrollingInterestEquityCarryingAmount",
        "RedeemableNoncontrollingInterestEquityCommonCarryingAmount"], "instant", bold=True),
    I("common_stock", "Základné imanie a emisné ážio", [
        "CommonStocksIncludingAdditionalPaidInCapital", "CommonStockValue", "ifrs:IssuedCapital"], "instant", indent=1),
    I("share_premium", "Emisné ážio", ["ifrs:SharePremium"], "instant", indent=1),
    I("apic", "Dodatočne splatený kapitál", ["AdditionalPaidInCapital", "AdditionalPaidInCapitalCommonStock"],
      "instant", indent=1),
    I("treasury", "Vlastné akcie v držbe (odpočítava sa)", ["TreasuryStockValue", "TreasuryStockCommonValue"],
      "instant", indent=1),
    I("retained", "Nerozdelený zisk / neuhradená strata", ["RetainedEarningsAccumulatedDeficit", "ifrs:RetainedEarnings"],
      "instant", indent=1),
    I("aoci", "Ostatný súhrnný zisk/strata (AOCI)", ["AccumulatedOtherComprehensiveIncomeLossNetOfTax",
                                                     "ifrs:AccumulatedOtherComprehensiveIncome"], "instant", indent=1),
    I("other_reserves", "Ostatné fondy (rezervy vo vlastnom imaní)", ["ifrs:OtherReserves"], "instant", indent=1),
    I("nci", "Menšinové (nekontrolujúce) podiely", ["MinorityInterest", "ifrs:NoncontrollingInterests"], "instant",
      indent=1),
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
        "ifrs:DepreciationAndAmortisationExpense", "ifrs:AdjustmentsForDepreciationAndAmortisationExpense"], indent=1),
    I("sbc", "Akciová kompenzácia", [
        "ShareBasedCompensation", "AllocatedShareBasedCompensationExpense",
        "ifrs:AdjustmentsForSharebasedPayments"], indent=1),
    I("cf_impairment", "Znehodnotenie a opravné položky", [
        "ifrs:ImpairmentLossReversalOfImpairmentLossRecognisedInProfitOrLoss",
        "ifrs:AdjustmentsForImpairmentLossReversalOfImpairmentLossRecognisedInProfitOrLoss"], indent=1),
    I("cf_fin_net", "Úprava o finančné náklady", ["ifrs:AdjustmentsForFinanceCosts"], indent=1),
    I("cf_before_wc", "Cash flow pred zmenou pracovného kapitálu", [
        "ifrs:CashFlowsFromUsedInOperationsBeforeChangesInWorkingCapital"]),
    # US GAAP má pri zmenách pracovného kapitálu opačné znamienko (+ = nárast pohľadávok), preto len IFRS
    I("cf_wc_receiv", "Zmena pohľadávok", ["ifrs:AdjustmentsForDecreaseIncreaseInTradeAccountReceivable",
                                          "ifrs:AdjustmentsForDecreaseIncreaseInTradeAndOtherReceivables"], indent=1),
    I("cf_wc_inv", "Zmena zásob", ["ifrs:AdjustmentsForDecreaseIncreaseInInventories"], indent=1),
    I("cf_wc_pay", "Zmena záväzkov z obchodného styku", ["ifrs:AdjustmentsForIncreaseDecreaseInTradeAccountPayable",
                                                         "ifrs:AdjustmentsForIncreaseDecreaseInTradeAndOtherPayables"],
      indent=1),
    I("cf_from_ops", "Hotovosť z prevádzky (pred daňami a úrokmi)", ["ifrs:CashFlowsFromUsedInOperations"]),
    I("tax_paid", "Zaplatená daň z príjmu", ["IncomeTaxesPaidNet", "IncomeTaxesPaid",
                                             "ifrs:IncomeTaxesPaidRefundClassifiedAsOperatingActivities"], indent=1),
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
    I("ppe_sale", "Príjmy z predaja dlhodobého majetku", [
        "ProceedsFromSaleOfPropertyPlantAndEquipment",
        "ifrs:ProceedsFromSalesOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities"], indent=1),
    I("acquisitions", "Akvizície firiem (po odpočítaní získanej hotovosti)", [
        "PaymentsToAcquireBusinessesNetOfCashAcquired",
        "ifrs:CashFlowsUsedInObtainingControlOfSubsidiariesOrOtherBusinessesClassifiedAsInvestingActivities"], indent=1),
    I("equity_inv_paid", "Investície do pridružených a spoločných podnikov", [
        "PaymentsToAcquireEquityMethodInvestments",
        "ifrs:PurchaseOfInterestsInInvestmentsAccountedForUsingEquityMethod"], indent=1),
    I("interest_received", "Prijaté úroky", ["ifrs:InterestReceivedClassifiedAsInvestingActivities",
                                             "ifrs:InterestReceivedClassifiedAsOperatingActivities"], indent=1),
    I("cfi", "Cash flow z investičnej činnosti", [
        "NetCashProvidedByUsedInInvestingActivities",
        "NetCashProvidedByUsedInInvestingActivitiesContinuingOperations",
        "ifrs:CashFlowsFromUsedInInvestingActivities"], bold=True),
    I("div_paid", "Vyplatené dividendy", [
        "PaymentsOfDividends", "PaymentsOfDividendsCommonStock", "PaymentsOfOrdinaryDividends",   # ASML: Ordinary
        "ifrs:DividendsPaidClassifiedAsFinancingActivities"], indent=1),
    I("buybacks", "Spätné odkupy akcií", ["PaymentsForRepurchaseOfCommonStock",
                                          "ifrs:PaymentsToAcquireOrRedeemEntitysShares"], indent=1),
    I("debt_issued", "Emisia dlhu / prijaté úvery", ["ProceedsFromIssuanceOfLongTermDebt",
                                                    "ProceedsFromIssuanceOfDebt",
                                                    "ifrs:ProceedsFromBorrowingsClassifiedAsFinancingActivities"],
      indent=1),
    I("notes_issued", "Emisia dlhopisov (vrátane konvertibilných)", [
        "ProceedsFromConvertibleDebt", "ifrs:ProceedsFromIssueOfBondsNotesAndDebentures"], indent=1),
    I("debt_repaid", "Splátky dlhu", ["RepaymentsOfLongTermDebt", "RepaymentsOfDebt",
                                      "ifrs:RepaymentsOfBorrowingsClassifiedAsFinancingActivities",
                                      "ifrs:RepaymentsOfBondsNotesAndDebentures"], indent=1),
    I("lease_paid", "Splátky lízingov", ["FinanceLeasePrincipalPayments",
                                         "ifrs:PaymentsOfLeaseLiabilitiesClassifiedAsFinancingActivities"], indent=1),
    I("interest_paid", "Zaplatené úroky", ["InterestPaidNet",
                                           "ifrs:InterestPaidClassifiedAsFinancingActivities",
                                           "ifrs:InterestPaidClassifiedAsOperatingActivities"], indent=1),
    I("nci_paid", "Odkup menšinových podielov", ["PaymentsForRepurchaseOfRedeemableNoncontrollingInterest",
                                                 "ifrs:PaymentsFromChangesInOwnershipInterestsInSubsidiaries"],
      indent=1),
    I("cff", "Cash flow z finančnej činnosti", [
        "NetCashProvidedByUsedInFinancingActivities",
        "NetCashProvidedByUsedInFinancingActivitiesContinuingOperations",
        "ifrs:CashFlowsFromUsedInFinancingActivities"], bold=True),
    I("fx_effect", "Vplyv kurzových zmien na hotovosť", [
        "EffectOfExchangeRateOnCashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
        "EffectOfExchangeRateOnCashAndCashEquivalents",
        "ifrs:EffectOfExchangeRateChangesOnCashAndCashEquivalents"], indent=1),
    I("cash_change", "Zmena hotovosti", [
        "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalentsPeriodIncreaseDecreaseIncludingExchangeRateEffect",
        "ifrs:IncreaseDecreaseInCashAndCashEquivalents",
        "ifrs:IncreaseDecreaseInCashAndCashEquivalentsBeforeEffectOfExchangeRateChanges"], bold=True),
]

# Pomocné riadky (nezobrazujú sa), z ktorých sa skladajú odvodené hodnoty v statements.build
HIDDEN = [
    I("rev_net_int", "Čisté tržby po úrokových nákladoch", ["RevenuesNetOfInterestExpense"]),
    I("dep_only", "Odpisy hmotného majetku", ["Depreciation", "ifrs:AdjustmentsForDepreciationExpense",
                                               "ifrs:DepreciationPropertyPlantAndEquipmentIncludingRightofuseAssets"]),
    I("amort_intang", "Amortizácia nehmotného majetku", ["AmortizationOfIntangibleAssets",
                                                         "ifrs:AdjustmentsForAmortisationExpense",
                                                         "ifrs:AmortisationIntangibleAssetsOtherThanGoodwill"]),
    I("inv_total_ifrs", "Investície spolu (IFRS)", ["ifrs:InvestmentsOtherThanInvestmentsAccountedForUsingEquityMethod"],
      "instant"),
    I("debt_cur_total", "Krátkodobý dlh spolu", ["DebtCurrent"], "instant"),
    I("ltd_cur", "Krátkodobá časť dlhodobého dlhu", ["LongTermDebtCurrent"], "instant"),
    I("cp", "Komerčné papiere", ["CommercialPaper"], "instant"),
    I("stb", "Krátkodobé pôžičky", ["ShortTermBorrowings", "OtherShortTermBorrowings"], "instant"),
    I("ltd_nc", "Dlhodobý dlh bez krátkodobej časti", ["LongTermDebtNoncurrent"], "instant"),
    I("ltd_total", "Dlhodobý dlh vrátane krátkodobej časti", ["LongTermDebt"], "instant"),
    I("ifrs_borrowings", "Úvery a pôžičky spolu (IFRS)", ["ifrs:Borrowings"], "instant"),
]

ALL_ITEMS = INCOME + BALANCE + CASHFLOW + HIDDEN
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
# depozitné banky (vždy banka); ostatné „finančné“ SIC (napr. 6199) majú aj kryptofirmy či fintechy bez úverov
DEPOSITORY_SIC = {6021, 6022, 6029, 6035, 6036}
COMMODITY_FUND_SIC = {6221}          # komoditné fondy a trusty (WEAT): nie sú to firmy
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

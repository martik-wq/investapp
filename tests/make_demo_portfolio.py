"""Fiktívne exporty z Trading 212 pre testy a ukážku.

generate():        nový formát (viac peňaženiek, Time (UTC), Currency (Total) v každom riadku)
generate_legacy(): starší formát (jedna mena účtu, Total (EUR))
"""
import os

NEW_HEADER = ("Action,Time (UTC),ISIN,Ticker,Name,Notes,ID,No. of shares,Price / share,"
              "Currency (Price / share),Exchange rate,Result,Currency (Result),Total,Currency (Total),"
              "Withholding tax,Currency (Withholding tax),Currency conversion from amount,"
              "Currency (Currency conversion from amount),Currency conversion to amount,"
              "Currency (Currency conversion to amount),Currency conversion fee,"
              "Currency (Currency conversion fee)")


def q(v):
    return f'"{v}"' if v != "" else ""


def new_row(action, time, isin="", ticker="", name="", notes="", id_="", shares="", price="",
            pccy="", fx="", result="", rccy="", total="", tccy="", wht="", wccy="", cfrom="",
            cfrom_c="", cto="", cto_c="", cfee="", cfee_c=""):
    cells = [action, time + "+00:00", isin, ticker, q(name), q(notes), id_, shares, price, pccy, fx,
             result, q(rccy), total, q(tccy), wht, q(wccy), cfrom, q(cfrom_c), cto, q(cto_c),
             cfee, q(cfee_c)]
    return ",".join(str(c) for c in cells)


def generate():
    r = [NEW_HEADER]
    r.append(new_row("Interest on cash", "2025-10-30 02:05:37", notes="Interest on cash", id_="I1",
                     total="0.02", tccy="EUR"))
    r.append(new_row("Deposit", "2025-11-01 09:00:00", notes="Bank Transfer", id_="D1",
                     total="1000.00", tccy="EUR"))
    r.append(new_row("Currency conversion", "2025-11-02 10:00:00", notes="500.00 EUR -> 575.00 USD",
                     id_="C1", total="-0.50", tccy="USD", cfrom="500.00", cfrom_c="EUR", cto="575.00",
                     cto_c="USD", cfee="-0.50", cfee_c="USD"))
    # 10 ks DEMOCO po 40 USD z USD peňaženky
    r.append(new_row("Market buy", "2025-11-02 10:01:00", "US0000000001", "DEMOCO", "Demo Software Inc.",
                     id_="B1", shares="10.0000000000", price="40.0000000000", pccy="USD",
                     fx="1.00000000", total="400.00", tccy="USD"))
    # 2 ks DEMOCO po 45 USD z EUR peňaženky (iná mena zúčtovania -> zmiešaná pozícia)
    r.append(new_row("Market buy", "2025-11-05 15:00:00", "US0000000001", "DEMOCO", "Demo Software Inc.",
                     id_="B2", shares="2.0000000000", price="45.0000000000", pccy="USD",
                     fx="0.86000000", total="77.40", tccy="EUR"))
    # európska akcia v EUR
    r.append(new_row("Market buy", "2025-11-06 11:00:00", "NL0000000003", "DEMOEU", "Demo Europe NV",
                     id_="B3", shares="5.0000000000", price="100.0000000000", pccy="EUR",
                     fx="1.00000000", total="500.00", tccy="EUR"))
    # ETF kótovaný v Londýne v GBP, zúčtovaný v EUR (kurz = GBP za 1 EUR)
    r.append(new_row("Market buy", "2025-11-07 11:00:00", "IE0000000004", "DEMOUK", "Demo UK ETF",
                     id_="B4", shares="10.0000000000", price="20.0000000000", pccy="GBP",
                     fx="0.87000000", total="229.89", tccy="EUR"))
    r.append(new_row("Dividend (Dividend)", "2025-12-10 12:00:00", "NL0000000003", "DEMOEU",
                     "Demo Europe NV", id_="V1", shares="5.0000000000", price="1.000000", pccy="EUR",
                     fx="1.00000000", total="4.20", tccy="EUR", wht="0.75", wccy="EUR"))
    r.append(new_row("Dividend (Dividend)", "2026-01-15 12:00:00", "US0000000001", "DEMOCO",
                     "Demo Software Inc.", id_="V2", shares="12.0000000000", price="0.300000", pccy="USD",
                     fx="0.86000000", total="3.10", tccy="EUR", wht="0.50", wccy="USD"))
    # predaj 4 ks DEMOCO; Trading 212 uvádza vlastný výsledok (54.00 USD)
    r.append(new_row("Market sell", "2026-02-10 15:30:00", "US0000000001", "DEMOCO", "Demo Software Inc.",
                     id_="S1", shares="4.0000000000", price="55.0000000000", pccy="USD",
                     fx="1.00000000", result="54.00", rccy="USD", total="220.00", tccy="USD"))
    # predaj akcie, ktorú si kúpil pred začiatkom exportu (chýba história)
    r.append(new_row("Market sell", "2026-02-11 15:30:00", "US0000000005", "DEMOOLD", "Demo Old Inc.",
                     id_="S2", shares="3.0000000000", price="30.0000000000", pccy="USD",
                     fx="1.00000000", result="15.00", rccy="USD", total="90.00", tccy="USD"))
    r.append(new_row("Spin off", "2026-03-02 12:00:00", "US0000000006", "DEMOSPIN", "Demo Spin Co.",
                     id_="SP1", shares="2.0000000000", price="0E-10", pccy="USD", total="0.00",
                     tccy="EUR"))
    r.append(new_row("Withdrawal", "2026-04-01 12:00:00", notes="Sent to card **** 1234", id_="W1",
                     total="-50.00", tccy="EUR"))
    # presun medzi peňaženkami (výber v EUR + vklad v USD v priebehu pár sekúnd, bez poznámky)
    r.append(new_row("Withdrawal", "2026-05-21 16:57:41", id_="T1", total="-100.00", tccy="EUR"))
    r.append(new_row("Deposit", "2026-05-21 16:58:00", id_="T2", total="115.00", tccy="USD"))
    r.append(new_row("Interest on cash", "2026-06-01 02:05:37", notes="Interest on cash", id_="I2",
                     total="0.01", tccy="USD"))
    r.append(new_row("Deposit", "2026-06-12 14:30:53", notes="Bank Transfer", id_="D2",
                     total="240.00", tccy="EUR"))
    return "\n".join(r) + "\n"


LEGACY_HEADER = ("Action,Time,ISIN,Ticker,Name,No. of shares,Price / share,Currency (Price / share),"
                 "Exchange rate,Result (EUR),Total (EUR),Withholding tax,Currency (Withholding tax),"
                 "Charge amount (EUR),Notes,ID")


def lrow(action, time, isin="", ticker="", name="", shares="", price="", ccy="", fx="",
         total="", wht="", wht_ccy="", id_=""):
    return ",".join([action, time, isin, ticker, f'"{name}"' if name else "", str(shares), str(price), ccy,
                     str(fx), "", str(total), str(wht), wht_ccy, "", "", "L" + id_])


def generate_legacy():
    r = [LEGACY_HEADER]
    r.append(lrow("Deposit", "2024-01-10 09:00:00", total="5000.00", id_="D1"))
    r.append(lrow("Market buy", "2024-01-15 15:31:02", "US0000000001", "DEMOCO", "Demo Software Inc.",
                  "10.0000000000", "40.00", "USD", "1.10", f"{10 * 40 / 1.10:.2f}", id_="B1"))
    r.append(lrow("Market buy", "2024-02-01 16:02:11", "US0000000002", "DEMOBANK", "Demo Bank Corp.",
                  "20.0000000000", "30.00", "USD", "1.09", f"{20 * 30 / 1.09:.2f}", id_="B2"))
    r.append(lrow("Market buy", "2024-06-03 14:45:09", "US0000000001", "DEMOCO", "Demo Software Inc.",
                  "5.0000000000", "45.00", "USD", "1.08", f"{5 * 45 / 1.08:.2f}", id_="B3"))
    r.append(lrow("Currency conversion", "2024-06-03 14:45:09", total="-208.33", id_="C1"))
    r.append(lrow("Dividend (Ordinary)", "2024-09-01 10:00:00", "US0000000001", "DEMOCO",
                  "Demo Software Inc.", "15.0000000000", "0.25", "USD", "Not available", "3.40",
                  "0.56", "USD", "DV1"))
    r.append(lrow("Interest on cash", "2024-12-31 00:00:00", total="1.23", id_="I1"))
    r.append(lrow("Limit sell", "2025-03-10 15:30:00", "US0000000001", "DEMOCO", "Demo Software Inc.",
                  "6.0000000000", "52.00", "USD", "1.05", f"{6 * 52 / 1.05:.2f}", id_="S1"))
    r.append(lrow("Withdrawal", "2025-05-01 12:00:00", total="-200.00", id_="W1"))
    r.append(lrow("Dividend (Ordinary)", "2025-09-01 10:00:00", "US0000000002", "DEMOBANK",
                  "Demo Bank Corp.", "20.0000000000", "0.30", "USD", "Not available", "5.10",
                  "0.90", "USD", "DV2"))
    return "\n".join(r) + "\n"


def main(out_dir):
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "portfolio_demo.csv"), "w", encoding="utf-8") as f:
        f.write(generate())


if __name__ == "__main__":
    main(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "demo_data"))

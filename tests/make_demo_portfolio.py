"""Fiktívny export z Trading 212 (formát podľa skutočného exportu) pre testy a ukážku."""
import os

HEADER = ("Action,Time,ISIN,Ticker,Name,No. of shares,Price / share,Currency (Price / share),"
          "Exchange rate,Result (EUR),Total (EUR),Withholding tax,Currency (Withholding tax),"
          "Charge amount (EUR),Notes,ID")


def row(action, time, isin="", ticker="", name="", shares="", price="", ccy="", fx="",
        result="", total="", wht="", wht_ccy="", charge="", notes="", id_=""):
    f = lambda v: "" if v == "" else v  # noqa: E731
    return ",".join([action, time, isin, ticker, f'"{name}"' if name else "", str(shares), str(price),
                     ccy, str(fx), str(result), str(total), str(wht), wht_ccy, str(charge), notes, id_])


def generate():
    rows = [HEADER]
    rows.append(row("Deposit", "2024-01-10 09:00:00", total="5000.00", id_="D1"))
    # nákup 10 ks DEMOCO po 40 USD pri kurze 1.10 USD za 1 EUR
    rows.append(row("Market buy", "2024-01-15 15:31:02", "US0000000001", "DEMOCO", "Demo Software Inc.",
                    "10.0000000000", "40.00", "USD", "1.10", "", f"{10 * 40 / 1.10:.2f}", id_="B1"))
    rows.append(row("Market buy", "2024-02-01 16:02:11", "US0000000002", "DEMOBANK", "Demo Bank Corp.",
                    "20.0000000000", "30.00", "USD", "1.09", "", f"{20 * 30 / 1.09:.2f}", id_="B2"))
    rows.append(row("Market buy", "2024-06-03 14:45:09", "US0000000001", "DEMOCO", "Demo Software Inc.",
                    "5.0000000000", "45.00", "USD", "1.08", "", f"{5 * 45 / 1.08:.2f}", id_="B3"))
    rows.append(row("Currency conversion", "2024-06-03 14:45:09", total="-208.33", id_="C1"))
    rows.append(row("Dividend (Ordinary)", "2024-09-01 10:00:00", "US0000000001", "DEMOCO",
                    "Demo Software Inc.", "15.0000000000", "0.25", "USD", "Not available", "", "3.40",
                    "0.56", "USD", "", "", "DV1"))
    rows.append(row("Interest on cash", "2024-12-31 00:00:00", total="1.23", id_="I1"))
    rows.append(row("Limit sell", "2025-03-10 15:30:00", "US0000000001", "DEMOCO", "Demo Software Inc.",
                    "6.0000000000", "52.00", "USD", "1.05", "", f"{6 * 52 / 1.05:.2f}", id_="S1"))
    rows.append(row("Withdrawal", "2025-05-01 12:00:00", total="-200.00", id_="W1"))
    rows.append(row("Dividend (Ordinary)", "2025-09-01 10:00:00", "US0000000002", "DEMOBANK",
                    "Demo Bank Corp.", "20.0000000000", "0.30", "USD", "Not available", "", "5.10",
                    "0.90", "USD", "", "", "DV2"))
    return "\n".join(rows) + "\n"


def main(out_dir):
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "portfolio_demo.csv"), "w", encoding="utf-8") as f:
        f.write(generate())


if __name__ == "__main__":
    main(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "demo_data"))

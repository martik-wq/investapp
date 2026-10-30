# mkej – investičná analýza (SEC EDGAR)

Lokálna webová aplikácia: zadáš ticker a zobrazí sa súvaha, výkaz ziskov a strát,
cash flow a metriky podľa typu biznisu (všeobecný, tech, banka/fintech, poisťovňa, REIT).
Dáta idú zadarmo z oficiálneho SEC EDGAR (XBRL).

## Spustenie (jednoducho: pozri AKO_NA_TO.txt, dvojklik na spustit.bat / spustit.command)

## Spustenie ručne

1. Potrebuješ Python 3.10+.
2. V priečinku projektu:
   ```
   python -m venv venv
   venv\Scripts\activate          (Windows)   alebo   source venv/bin/activate   (Mac/Linux)
   pip install -r requirements.txt
   ```
3. SEC vyžaduje identifikáciu v požiadavkách. Nastav svoje meno a e-mail:
   - Windows (PowerShell): `$env:SEC_USER_AGENT="Meno Priezvisko tvoj@email.sk"`
   - Mac/Linux: `export SEC_USER_AGENT="Meno Priezvisko tvoj@email.sk"`
4. `python app.py` a otvor http://127.0.0.1:5000

Bez internetu si môžeš vyskúšať fiktívne firmy `DEMOCO` a `DEMOBANK`
(nepotrebujú SEC_USER_AGENT).

## Čo aplikácia robí

- **Obdobie:** ročné alebo kvartálne. Kvartály sa pri 10-Q dopočítavajú
  (Q4 = rok − 9 mesiacov, cash flow = rozdiely kumulatívnych hodnôt).
  V kvartálnom režime sú metriky počítané z posledných 12 mesiacov (TTM).
- **Typ biznisu:** určí sa podľa SIC kódu a dát, dá sa ručne zmeniť.
- **Valuácia:** zadaj aktuálnu cenu akcie (EDGAR ceny neposkytuje) a dopočítajú sa
  P/E, P/B, P/TBV, EV/EBITDA, P/FFO, dividendový výnos podľa typu.
- **Export CSV** (otvára sa v Exceli).
- Dáta zo SEC sa 24 hodín cachujú v priečinku `cache/`.

## Štruktúra

- `taxonomy.py` – mapovanie XBRL tagov na riadky výkazov (sem pridávaj ďalšie tagy)
- `edgar.py` – sťahovanie, cache, spracovanie období
- `statements.py` – zostavenie výkazov
- `metrics.py` – metriky podľa typu biznisu a valuácia
- `app.py` + `templates/` – webové rozhranie
- `tests/test_pipeline.py` – testy na ukážkových dátach (`python tests/test_pipeline.py`)

## Známe limity

- Len firmy, ktoré podávajú SEC (USA a zahraničné s 20-F/40-F). Kórejské, európske a iné
  lokálne firmy bez US kótovania treba doplniť iným zdrojom.
- Firmy pomenúvajú položky rôzne. Ak riadok chýba, doplň tag do `taxonomy.py`.
- Zahraniční emitenti (IFRS) majú pokrytie tagov slabšie než US GAAP firmy.
- Vzorce sú zjednodušené (napr. NIM z priemerných aktív, FFO bez úpravy o znehodnotenia,
  približný combined ratio). Pri dôležitých rozhodnutiach si údaje over v pôvodnom 10-K/20-F.
- Aplikácia nebola testovaná na živých dátach SEC (vývojové prostredie k nim nemalo prístup),
  iba na simulovaných dátach v rovnakom formáte. Pri prvom spustení si skontroluj niekoľko
  firiem, ktoré poznáš.

## Podrobné výkazy

V záložke Výkazy je voľba „Zobrazenie výkazov“: zjednodušené (štandardizované, z companyfacts)
alebo podrobné (riadky presne ako ich firma uvádza v podaniach, napr. tržby zvlášť za tovar a služby).
Podrobné výkazy sa čítajú zo stránok R*.htm v podaniach SEC (`filings.py`), kvartály sa dopočítavajú
(Q4 = rok − 9M, cash flow = rozdiely kumulatívnych hodnôt). Podania sa cachujú natrvalo v `cache/filings/`.
Kvartálne podrobné údaje sú obmedzené na 5 rokov, ročné na 12.

## Od tržieb k zisku (Sankey diagram)

V záložke Grafy je diagram toku od tržieb cez náklady až po čistý zisk (`flow.py`, `static/sankey.js`).
Základ tvoria štandardizované výkazy, členenie tržieb (podľa produktov/služieb) sa hľadá v podaniach SEC:
vo výkaze alebo v poznámkach „(Details)“, vždy len ak súčet položiek sedí s celkovými tržbami.
Q4 sa dopočíta ako rok − 9M. Banky majú vlastné rozloženie (úroky, rezervy, neúrokové náklady).

## Portfólio (Trading 212)

V bočnom paneli je záložka Portfólio. Nahraj CSV z Trading 212 (História → export, Objednávky + Dividendy + Transakcie,
najviac 12 mesiacov na súbor, viac súborov naraz). Aplikácia spočíta pozície (priemerná nákupná cena ako v T212),
realizovaný a nerealizovaný zisk, dividendy a aktuálnu hodnotu (ceny z Yahoo Finance podľa ISIN). Údaje sú v priečinku `data/`
(nenahrávajú sa na GitHub a aktualizácia ich neprepisuje).

## Výkonnosť portfólia a porovnanie s indexmi

V Portfóliu je záložka „Výkonnosť a porovnanie s indexmi“ (`perf.py`, `static/perf.js`). Počíta časovo vážený výnos (TWR)
z denných hodnôt pozícií (historické ceny a kurzy z Yahoo Finance), zisk/stratu YTD, po kalendárnych rokoch a od začiatku,
a porovnáva ho s indexmi (S&P 500, Nasdaq-100, MSCI World… alebo vlastný symbol) prepočítanými do tej istej meny.
Presné výsledky vyžadujú kompletnú históriu od prvého nákupu; pri neúplnom exporte je výnos orientačný a aplikácia na to upozorní.

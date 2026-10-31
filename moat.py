"""„Prečo trh platí prémiu?“ – stopy konkurenčnej výhody (moat) v hlásených číslach.

Značku, sieťové efekty ani patenty z výkazov vyčítať nejde. Dajú sa merať ich dôsledky: kapitál, ktorý dlhodobo
zarába viac, než stojí, vysoké a stabilné marže, stabilné tržby a zisk, ktorý sa mení na hotovosť. Čisté funkcie
nad ročnými výkazmi, percentá v desatinách."""
from statistics import mean, pstdev

import quality as Q
import valuation as V

LABELS = {0: "slabé", 1: "priemerné", 2: "silné"}
MIN_YEARS = 4


def _series(built, fn):
    out = []
    for e in built["display"]:
        try:
            v = fn(e)
        except (TypeError, ZeroDivisionError, KeyError):
            v = None
        if v is not None:
            out.append((e, v))
    return out


def _lvl(v, strong, ok):
    return None if v is None else (2 if v >= strong else 1 if v >= ok else 0)


def _p(v, d=1):
    return "–" if v is None else f"{v * 100:.{d}f} %".replace(".", ",")


def indicators(built, wacc):
    """Zoznam {'name','value','score','why'}; score 0/1/2 alebo None, keď nie sú údaje."""
    d = built["data"]
    g = lambda k, e: d.get(k, {}).get(e)  # noqa: E731
    out = []

    ro = _series(built, lambda e: (Q.roic_at(built, e) or {}).get("roic"))
    if len(ro) >= MIN_YEARS:
        above = sum(1 for _e, v in ro if v > wacc)
        share = above / len(ro)
        out.append({"name": "ROIC nad nákladmi kapitálu", "value": f"{above} z {len(ro)} rokov, priemer {_p(mean(v for _e, v in ro))}",
                    "score": _lvl(share, 0.9, 0.6),
                    "why": f"Kapitál, ktorý dlhodobo zarába viac než stojí (WACC {_p(wacc)}), je najpriamejšia stopa konkurenčnej výhody. Silné = aspoň 90 % rokov."})

    gm = _series(built, lambda e: V.safe_div(g("gross_profit", e), V.net_revenue(built, e)) if g("gross_profit", e) is not None else None)
    if len(gm) >= MIN_YEARS:
        avg = mean(v for _e, v in gm)
        out.append({"name": "Hrubá marža", "value": f"priemer {_p(avg)}", "score": _lvl(avg, 0.5, 0.3),
                    "why": "Vysoká hrubá marža znamená cenovú silu: firma si vie povedať viac, než ju stojí výroba. Silné = nad 50 %, priemerné 30 až 50 %."})
        sd = pstdev(v for _e, v in gm)
        out.append({"name": "Stabilita hrubej marže", "value": f"kolísanie ±{_p(sd)} (smerodajná odchýlka)",
                    "score": None if sd is None else (2 if sd <= 0.02 else 1 if sd <= 0.05 else 0),
                    "why": "Stabilná marža naznačuje, že konkurencia ju nedokáže stláčať. Silné = kolísanie do 2 p. b., priemerné do 5 p. b."})

    om = _series(built, lambda e: V.safe_div(g("op_income", e), V.net_revenue(built, e)) if g("op_income", e) is not None else None)
    if len(om) >= MIN_YEARS:
        worst = min(v for _e, v in om)
        out.append({"name": "Najslabšia prevádzková marža", "value": f"{_p(worst)} (najhorší rok z {len(om)})",
                    "score": _lvl(worst, 0.15, 0.05),
                    "why": "Firma s moatom zostáva ziskovou aj v zlom roku. Silné = ani najhorší rok pod 15 % nejde."})

    rv = _series(built, lambda e: V.net_revenue(built, e))
    if len(rv) >= MIN_YEARS:
        worst = min(y / x - 1 for (_a, x), (_b, y) in zip(rv, rv[1:]) if x)
        out.append({"name": "Stabilita tržieb", "value": f"najhorší medziročný rast {_p(worst)}",
                    "score": 2 if worst >= 0 else 1 if worst >= -0.05 else 0,
                    "why": "Zákazníci, ktorí zostávajú aj v zlej dobe, sú znakom lojality alebo nákladov na zmenu dodávateľa. Silné = tržby nikdy nepoklesli, priemerné = pokles najviac o 5 %."})

    conv = _series(built, lambda e: V.safe_div(g("fcf", e), g("net_income", e)) if (g("net_income", e) or 0) > 0 and g("fcf", e) is not None else None)
    if len(conv) >= MIN_YEARS:
        avg = mean(v for _e, v in conv)
        out.append({"name": "Zisk ako hotovosť (FCF / čistý zisk)", "value": f"priemer {_p(avg, 0)}", "score": _lvl(avg, 0.9, 0.6),
                    "why": "Ak sa zisk mení na voľné peniaze, rast nevyžaduje stále nový kapitál. Silné = nad 90 %. Pozor, FCF zahŕňa pripočítanie SBC."})
    return out


def premium(facts, price, mcap, rev, ebitda, fcf, nd):
    """Dnešné násobky (to, čo trh platí): P/E, P/S, EV/EBITDA, FCF výnos."""
    eps = facts.get("eps_ttm")
    return {"pe": price / eps if price and eps and eps > 0 else None,
            "ps": mcap / rev if mcap and rev else None,
            "ev_ebitda": (mcap + nd) / ebitda if mcap and ebitda and ebitda > 0 and nd is not None else None,
            "fcf_yield": fcf / mcap if mcap and fcf is not None else None}


def build(built, facts, btype, wacc, price, mcap, reverse=None):
    """Karta „Prečo trh platí prémiu?“. Pri bankách a poisťovniach sa nepoužíva (iné účtovníctvo)."""
    if btype in ("bank", "insurance"):
        return {"skip": True, "reason": "U bánk a poisťovní ROIC ani hrubá marža nedávajú zmysel, hodnotia sa cez ROE a kapitálové pomery v karte Kvalita."}
    try:
        w = wacc if wacc else 0.09
        ind = indicators(built, w)
        if len(ind) < 3:
            return {"skip": True, "reason": "Na posúdenie moatu je vo výkazoch málo rokov alebo chýbajú položky (hrubý zisk, investovaný kapitál)."}
        t = built["display"][-1]
        gv = lambda k: built["data"].get(k, {}).get(t)  # noqa: E731
        rev = V.net_revenue(built, t)
        ebitda = gv("op_income") + gv("da") if gv("op_income") is not None and gv("da") is not None else None
        mult = premium(facts, price, mcap, rev, ebitda, gv("fcf"), facts.get("net_debt"))
    except (TypeError, ZeroDivisionError):
        return {"skip": True, "reason": "Moat sa nepodarilo spočítať (chýbajú údaje vo výkazoch)."}
    scored = [i["score"] for i in ind if i["score"] is not None]
    total = sum(scored) / (2 * len(scored))
    verdict = "silné" if total >= 0.7 else "čiastočné" if total >= 0.4 else "slabé"
    rich = bool(reverse and reverse.get("rec") is not None and reverse.get("g") is not None and reverse["g"] > reverse["rec"] + 0.03)
    return {"skip": False, "indicators": ind, "verdict": verdict, "share": total, "mult": mult, "wacc": w,
            "implied_g": reverse.get("g") if reverse else None, "rec_g": reverse.get("rec") if reverse else None,
            "priced_for_more": rich}

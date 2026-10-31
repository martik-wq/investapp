"""Záložka Fundamentálna analýza: vstupy pre oceňovacie modely s odporúčaniami a výpočet výsledkov.

build_view(...) je čistá funkcia (bez siete): všetko potrebné dostane v argumentoch."""
import valuation as V


def _pct(v, d=1):
    return "–" if v is None else f"{v * 100:.{d}f} %".replace(".", ",")


def _num_in(args, name, default, scale=1.0, lo=None, hi=None):
    """Hodnota z formulára (čiarka alebo bodka); percentá a pod. sa delia `scale`. Pri chybe default."""
    raw = (args.get(name) or "").strip().replace(",", ".").replace(" ", "")
    if raw == "":
        return default, False
    try:
        v = float(raw) / scale
    except ValueError:
        return default, False
    if lo is not None:
        v = max(lo, v)
    if hi is not None:
        v = min(hi, v)
    return v, True


def _fld(name, label, unit, value, rec, why=None, hints=(), help_=None, step="0.1", fmt="{:.1f}"):
    """Pole formulára: value a rec sú v zobrazených jednotkách (napr. 12.5 pre 12,5 %)."""
    return {"name": name, "label": label, "unit": unit, "value": value, "rec": rec, "why": why,
            "hints": list(hints), "help": help_, "step": step, "fmt": fmt,
            "changed": rec is not None and value is not None and abs(value - rec) > 1e-9}


def build_view(args, facts, analyst, price, currency, btype, beta, rf, mcap, shares_out, quote_note=None):
    """Vráti dict pre šablónu: polia modelov, výsledky, zhrnutie. `price` môže byť None."""
    is_fin = btype in ("bank", "insurance")
    model = args.get("m") or ("pb" if is_fin else "dcf")
    if model not in ("dcf", "pb", "pe"):
        model = "dcf"
    n_an = (analyst or {}).get("n_analysts")
    an_txt = f"Yahoo Finance, {int(n_an)} analytikov" if n_an else "Yahoo Finance"
    rg = (analyst or {}).get("rev_growth") or {}
    eg = (analyst or {}).get("eps_growth") or {}
    shares = shares_out or facts.get("shares_dil")
    ke, rf_used, beta_used = V.capm(beta, rf)
    wacc_rec, w_d, kd = V.wacc_estimate(ke, facts.get("debt"), mcap, facts.get("interest_expense"))
    wacc_rec = max(0.06, min(0.15, wacc_rec))
    out = {"model": model, "currency": currency, "price": price, "facts": facts, "analyst": analyst,
           "is_fin": is_fin, "notes": []}

    # ------------------------------------------------------------------ DCF
    g_rec, g_why = V.recommend_growth(facts, analyst)
    g_rec = round(g_rec, 3)
    m_rec = round(V.recommend_margin(facts), 3)
    d_rec = round(V.recommend_dilution(facts), 3)
    wacc_rec = round(wacc_rec, 3)
    ke = round(ke, 3)
    rev_mil = round((facts.get("rev_base") or 0) / 1e6, 1)
    nd_mil = round((facts.get("net_debt") or 0) / 1e6, 1)
    sh_mil = round((shares or 0) / 1e6, 2)
    g1, _ = _num_in(args, "d_g1", g_rec * 100, 1, -20, 60)
    m5, _ = _num_in(args, "d_m5", m_rec * 100, 1, -20, 60)
    wacc, _ = _num_in(args, "d_wacc", wacc_rec * 100, 1, 3, 25)
    gt, _ = _num_in(args, "d_gt", 2.5, 1, 0, 6)
    dil, _ = _num_in(args, "d_dil", d_rec * 100, 1, -8, 12)
    nd, _ = _num_in(args, "d_nd", nd_mil, 1)
    sh, _ = _num_in(args, "d_sh", sh_mil, 1, 0.000001)
    rv, _ = _num_in(args, "d_rev", rev_mil, 1, 0.000001)
    h_g = []
    if facts.get("rev_cagr5") is not None:
        h_g.append(f"Rast tržieb za 5 rokov (CAGR): {_pct(facts['rev_cagr5'])}")
    if facts.get("rev_cagr3") is not None:
        h_g.append(f"Za 3 roky: {_pct(facts['rev_cagr3'])}")
    if rg.get("0y") is not None or rg.get("+1y") is not None:
        h_g.append("Analytici čakajú rast tržieb: " + ", ".join(
            x for x in (f"tento rok {_pct(rg.get('0y'))}" if rg.get("0y") is not None else None,
                        f"budúci rok {_pct(rg.get('+1y'))}" if rg.get("+1y") is not None else None) if x)
            + f" ({an_txt})")
    h_m = []
    if facts.get("fcf_margin_now") is not None:
        h_m.append(f"Teraz (TTM): {_pct(facts['fcf_margin_now'])}")
    if facts.get("fcf_margin_avg3") is not None:
        h_m.append(f"Priemer 3 roky: {_pct(facts['fcf_margin_avg3'])}")
    if facts.get("fcf_margin_avg5") is not None:
        h_m.append(f"Priemer 5 rokov: {_pct(facts['fcf_margin_avg5'])}")
    if facts.get("fcf_margin_max") is not None:
        h_m.append(f"Najvyššia za sledované obdobie: {_pct(facts['fcf_margin_max'])}")
    om, fm = facts.get("op_margin_fy"), facts.get("fcf_margin_now")
    if om is not None:
        h_m.append(f"Prevádzková marža (posledný rok): {_pct(om)}")
        if fm is not None and om > 0.05 and fm < 0.5 * om:
            h_m.append("Pozor: voľný cash flow je dnes oveľa nižší ako prevádzkový zisk, firma pravdepodobne veľa investuje. "
                       "Ak čakáš, že investície spomalia, marža v roku 5 môže byť vyššia než odporúčanie.")
    h_w = [f"Požadovaná návratnosť akcií (CAPM): bezriziková sadzba {_pct(rf_used)} + beta {beta_used:.2f} × prémia 5 % = {_pct(ke)}"]
    if w_d and kd:
        h_w.append(f"Podiel dlhu {_pct(w_d, 0)}, cena dlhu {_pct(kd)}, po zdanení (21 %): WACC {_pct(wacc_rec)}")
    h_d = []
    if facts.get("shares_cagr3") is not None:
        h_d.append(f"Zmena počtu akcií za 3 roky: {_pct(facts['shares_cagr3'])} ročne (záporné = spätné odkupy)")
    dcf_fields = [
        _fld("d_g1", "Rast tržieb v rokoch 1 až 5", "% ročne", g1, round(g_rec * 100, 1),
             f"Vychádza z: {g_why}.", h_g,
             "Rast sa potom v rokoch 6 až 10 postupne znižuje na terminálny rast."),
        _fld("d_m5", "FCF marža v roku 5", "% z tržieb", m5, round(m_rec * 100, 1),
             "Vychádza z: priemer FCF marže za 3 roky a dnešnej marže.", h_m,
             "Voľný cash flow (prevádzkový cash flow − CapEx) lomený tržbami. Obsahuje späť pripočítané akciové odmeny, preto počítaj aj s ročným riedením. Marža sa lineárne mení z dnešnej na túto hodnotu."),
        _fld("d_wacc", "Diskontná sadzba (WACC)", "%", wacc, round(wacc_rec * 100, 1),
             "Vychádza z: CAPM a štruktúra kapitálu (vlastné imanie a dlh).", h_w,
             "Čím vyššia, tým nižšia dnešná hodnota budúcich peňazí. Typicky 7 až 11 %."),
        _fld("d_gt", "Terminálny rast", "% ročne", gt, 2.5,
             "Vychádza z: dlhodobo nemá presiahnuť rast ekonomiky.",
             ["Dlhodobý nominálny rast HDP býva 3 až 4 %, bezpečné je 2 až 3 %."],
             "Rast po roku 10, navždy."),
        _fld("d_dil", "Ročné riedenie akcií", "% ročne", dil, round(d_rec * 100, 1),
             "Vychádza z: vývoj počtu akcií za posledné 3 roky.", h_d,
             "Nové akcie (akciové odmeny) znižujú hodnotu na akciu. Záporné číslo = odkupy."),
        _fld("d_rev", f"Základ tržieb ({facts.get('rev_base_label', '')})", f"mil. {currency}", rv, round(rev_mil, 1),
             "Z výkazov firmy.", [], None, "1", "{:.1f}"),
        _fld("d_nd", "Čistý dlh (dlh − hotovosť)", f"mil. {currency}", nd, round(nd_mil, 1),
             "Z poslednej súvahy: dlh mínus hotovosť a investície (krátkodobé aj dlhodobé cenné papiere).",
             [f"Dlh {(facts.get('debt') or 0) / 1e6:,.0f} mil., hotovosť a krátkodobé investície {(facts.get('cash') or 0) / 1e6:,.0f} mil."
              + (f", dlhodobé investície a cenné papiere {(facts.get('lt_inv') or 0) / 1e6:,.0f} mil. (tiež odpočítané)" if facts.get("lt_inv") else "")],
             "Záporný = firma má viac hotovosti ako dlhu.", "1", "{:.1f}"),
        _fld("d_sh", "Počet akcií", "mil.", sh, round(sh_mil, 2), "Z titulnej strany výkazov (všetky triedy akcií).",
             [], None, "0.01", "{:.2f}"),
    ]
    p = dict(rev0=rv * 1e6, g1=g1 / 100, margin0=facts.get("fcf_margin_now") if facts.get("fcf_margin_now") is not None else m5 / 100,
             margin5=m5 / 100, wacc=wacc / 100, g_term=gt / 100, net_debt=nd * 1e6, shares=sh * 1e6, dilution=dil / 100)
    base = V.dcf(p["rev0"], p["g1"], p["margin0"], p["margin5"], p["wacc"], p["g_term"], p["net_debt"], p["shares"], p["dilution"])
    bars = []
    if "error" not in base:
        mx = max(abs(r["fcf"]) for r in base["rows"]) or 1
        bars = [{"t": r["t"], "h": max(2, abs(r["fcf"]) / mx * 100), "v": r["fcf"] / 1e6, "neg": r["fcf"] < 0} for r in base["rows"]]
    out["dcf"] = {"fields": dcf_fields, "p": p, "bars": bars, "error": base.get("error"), "base": None if "error" in base else base,
                  "scenarios": V.dcf_scenarios(p, price) if "error" not in base else [],
                  "sens": V.dcf_sensitivity(p) if "error" not in base else None,
                  "price_value": None if "error" in base else base["per_share"]}

    # ------------------------------------------------------------------ P/B (banky, poisťovne)
    bv = (facts.get("equity") or 0) / shares if shares else None
    roe_rec = facts.get("roe_avg3") if facts.get("roe_avg3") is not None else facts.get("roe_last")
    roe_rec = 0.10 if roe_rec is None else round(max(0.0, min(0.35, roe_rec)), 3)
    bv = round(bv, 2) if bv else bv
    pb_now = (price / bv) if price and bv else None
    b_roe, _ = _num_in(args, "b_roe", roe_rec * 100, 1, 0, 50)
    b_ke, _ = _num_in(args, "b_ke", ke * 100, 1, 3, 25)
    b_g, _ = _num_in(args, "b_g", 3.0, 1, 0, 8)
    b_bv, _ = _num_in(args, "b_bv", bv if bv else 0.0, 1, 0.0001)
    h_roe = []
    for lab, k in (("posledný rok", "roe_last"), ("priemer 3 roky", "roe_avg3"), ("priemer 5 rokov", "roe_avg5")):
        if facts.get(k) is not None:
            h_roe.append(f"ROE ({lab}): {_pct(facts[k])}")
    pb_fields = [
        _fld("b_roe", "Udržateľné ROE", "%", b_roe, round(roe_rec * 100, 1),
             "Vychádza z: priemer ROE za 3 roky.", h_roe,
             "Čistý zisk lomený priemerným vlastným imaním. Pri raste firmy sa ROE zvyčajne vracia k priemeru."),
        _fld("b_ke", "Požadovaná návratnosť (cost of equity)", "%", b_ke, round(ke * 100, 1),
             "Vychádza z: CAPM.", [h_w[0]], "Čo od akcie dlhodobo požaduješ."),
        _fld("b_g", "Dlhodobý rast", "% ročne", b_g, 3.0, "Vychádza z: dlhodobý rast ekonomiky.",
             ["Pri rýchlo rastúcich digitálnych bankách môže byť vyšší, ale model počíta s trvalým rastom."], None),
        _fld("b_bv", "Účtovná hodnota na akciu (BVPS)", currency, b_bv, round(bv, 2) if bv else None,
             "Vlastné imanie lomené počtom akcií.",
             [f"Dnešné P/B: {pb_now:.2f}×" if pb_now else "Pre P/B treba cenu akcie."], None, "0.01", "{:.2f}"),
    ]
    pbp = dict(roe=b_roe / 100, ke=b_ke / 100, g=b_g / 100, bvps=b_bv)
    pbb = V.pb_model(pbp["roe"], pbp["ke"], pbp["g"], pbp["bvps"], price)
    out["pb"] = {"fields": pb_fields, "p": pbp, "error": pbb.get("error"), "base": None if "error" in pbb else pbb,
                 "scenarios": V.pb_scenarios(pbp, price) if "error" not in pbb else [],
                 "sens": V.pb_sensitivity(pbp) if "error" not in pbb else None, "pb_now": pb_now}

    # ------------------------------------------------------------------ násobky (P/E)
    eps0 = facts.get("eps_ttm")
    eg_rec = eg.get("+1y")
    hist_eps = facts.get("eps_cagr5") if facts.get("eps_cagr5") is not None else facts.get("eps_cagr3")
    if eg_rec is not None and hist_eps is not None:
        g_eps_rec, why_e = (eg_rec + hist_eps) / 2, "priemer odhadu analytikov a historického CAGR zisku na akciu"
    elif eg_rec is not None:
        g_eps_rec, why_e = eg_rec, "odhad analytikov"
    elif hist_eps is not None:
        g_eps_rec, why_e = hist_eps, "historický CAGR zisku na akciu"
    else:
        g_eps_rec, why_e = 0.08, "všeobecný predpoklad (chýbajú údaje)"
    g_eps_rec = round(max(-0.2, min(0.5, g_eps_rec)), 3)
    pe_now = (price / eps0) if price and eps0 and eps0 > 0 else None
    pe_rec = None
    if pe_now:
        pe_rec = max(8.0, min(35.0, pe_now))
    else:
        pe_rec = max(8.0, min(35.0, 100 * g_eps_rec + 10))
    pe_rec = round(pe_rec, 1)
    eps0 = round(eps0, 2) if eps0 else eps0
    e_eps, _ = _num_in(args, "p_eps", eps0 if eps0 else 0.0, 1)
    e_g, _ = _num_in(args, "p_g", g_eps_rec * 100, 1, -50, 100)
    e_pe, _ = _num_in(args, "p_pe", pe_rec, 1, 1, 100)
    e_r, _ = _num_in(args, "p_r", ke * 100, 1, 3, 25)
    h_pe = []
    if pe_now:
        h_pe.append(f"Dnešné P/E (cena / EPS za 12 mesiacov): {pe_now:.1f}×")
    h_pe.append("Pravidlo PEG = 1: pri raste zisku 15 % ročne zodpovedá P/E okolo 15.")
    h_eg = []
    if hist_eps is not None:
        h_eg.append(f"Rast zisku na akciu za 5 rokov (CAGR): {_pct(facts.get('eps_cagr5'))}, za 3 roky: {_pct(facts.get('eps_cagr3'))}")
    if eg_rec is not None:
        h_eg.append(f"Analytici čakajú rast zisku na akciu budúci rok: {_pct(eg_rec)} ({an_txt})")
    pe_fields = [
        _fld("p_eps", "EPS za posledných 12 mesiacov", currency, e_eps, round(eps0, 2) if eps0 else None,
             "Zriedený zisk na akciu z výkazov.", [], None, "0.01", "{:.2f}"),
        _fld("p_g", "Rast EPS na budúci rok", "%", e_g, round(g_eps_rec * 100, 1),
             f"Vychádza z: {why_e}.", h_eg, "O koľko vyrastie zisk na akciu za rok."),
        _fld("p_pe", "Cieľové P/E", "×", e_pe, round(pe_rec, 1),
             "Vychádza z: " + ("dnešné P/E (obmedzené na 8 až 35)." if pe_now else "odhad podľa rastu."), h_pe,
             "Koľkonásobok ročného zisku je férová cena o rok."),
        _fld("p_r", "Diskontná sadzba", "%", e_r, round(ke * 100, 1),
             "Vychádza z: CAPM.", [h_w[0]], "Ňou sa hodnota o rok prepočíta na dnes."),
    ]
    pep = dict(eps0=e_eps, g_eps=e_g / 100, target_pe=e_pe, r=e_r / 100)
    peb = V.multiple_model(pep["eps0"], pep["g_eps"], pep["target_pe"], pep["r"], price)
    out["pe"] = {"fields": pe_fields, "p": pep, "error": peb.get("error"), "base": None if "error" in peb else peb,
                 "scenarios": V.multiple_scenarios(pep, price) if "error" not in peb else [], "pe_now": pe_now}

    # ------------------------------------------------------------------ ďalšie modely
    _more_models(out, args, facts, analyst, price, currency, is_fin, ke, rf_used, g_rec, shares, sh, nd, rv, wacc, mcap, an_txt)

    # ------------------------------------------------------------------ zoznam modelov a súhrn
    out["models"] = _models_list(out, is_fin, price)
    core = [m for m in out["models"] if m["core"] and m["ok"]]
    out["summary"] = []
    for m in core:
        vals = [sc["value"] for sc in m["scenarios"]]
        out["summary"].append({"key": m["key"], "name": m["name"], "low": min(vals), "mid": m["scenarios"][1]["value"], "high": max(vals)})
    out["central"] = None
    if out["summary"]:
        mids = sorted(x["mid"] for x in out["summary"])
        n = len(mids)
        med = mids[n // 2] if n % 2 else (mids[n // 2 - 1] + mids[n // 2]) / 2
        out["central"] = {"value": med, "low": mids[0], "high": mids[-1], "n": n,
                          "upside": (med / price - 1) if price else None}
        hi = max([x["high"] for x in out["summary"]] + [price or 0]) * 1.05
        for x in out["summary"]:
            x["pl"], x["pw"], x["pm"] = x["low"] / hi * 100, (x["high"] - x["low"]) / hi * 100, x["mid"] / hi * 100
        out["price_pos"] = (price / hi * 100) if price else None
        out["axis"] = [(round(hi * f / 4, 2), f * 25) for f in range(0, 5)]
    if facts.get("rev_years", 0) < 3:
        out["notes"].append("Firma má krátku históriu (menej ako 3 roky), odporúčania sú preto menej spoľahlivé.")
    if price is None:
        out["notes"].append("Bez ceny akcie sa neukáže porovnanie s trhom. Cenu môžeš zadať v záložke Úvod.")
    if quote_note:
        out["notes"].append(quote_note)
    out["wacc_parts"] = {"ke": ke, "rf": rf_used, "beta": beta_used, "w_d": w_d, "kd": kd}
    # reverzný DCF: aký rast trh očakáva
    out["reverse"] = None
    if price and out["dcf"]["base"]:
        ig = V.implied_growth(price, out["dcf"]["p"])
        if ig:
            out["reverse"] = {"g": ig["g"], "edge": ig["edge"], "rec": g_rec, "hist": facts.get("rev_cagr5")}
    return out


def _fmt_col(v, kind):
    if v is None:
        return "–"
    if kind == "pct":
        return f"{v * 100:.1f} %".replace(".", ",")
    if kind == "x":
        return f"{v:.1f}×".replace(".", ",")
    return f"{v:,.2f}".replace(",", " ").replace(".", ",")


def _norm_scen(key, scen):
    """Zjednotí varianty modelov do tvaru {'name','value','upside','cols':[(popis, text)]}."""
    out = []
    for s in scen:
        if "cols" in s:
            cols = [(lab, _fmt_col(v, k)) for lab, v, k in s["cols"]]
        elif key == "dcf":
            cols = [("Rast tržieb", _fmt_col(s["g1"], "pct")), ("FCF marža (rok 5)", _fmt_col(s["margin5"], "pct")), ("WACC", _fmt_col(s["wacc"], "pct"))]
        elif key == "pb":
            cols = [("ROE", _fmt_col(s["roe"], "pct")), ("Požad. návratnosť", _fmt_col(s["ke"], "pct")), ("Férové P/B", _fmt_col(s["fair_pb"], "x"))]
        else:
            cols = [("Rast EPS", _fmt_col(s["g_eps"], "pct")), ("Cieľové P/E", _fmt_col(s["pe"], "x"))]
        out.append({"name": s["name"], "value": s.get("value"), "upside": s.get("upside"), "cols": cols})
    return out


MODEL_INTRO = {
    "dcf": "Odhadne sa 10 rokov voľného cash flow (FCF) a hodnota po roku 10, všetko sa diskontuje na dnešok. Od hodnoty firmy sa odpočíta čistý dlh a delí sa počtom akcií. Najlepšie pre firmy so stabilným alebo rastúcim cash flow.",
    "evebitda": "Hodnota firmy = EBITDA o rok × cieľový násobok. Odpočíta sa čistý dlh, delí sa akciami a diskontuje. Hodí sa pri firmách s kladnou EBITDA a rôznou kapitálovou štruktúrou.",
    "fcfy": "Koľko voľného cash flow na akciu požaduješ. Hodnota = FCF na akciu o rok ÷ cieľový FCF výnos, diskontované na dnes. Prístup „majiteľa firmy“.",
    "pe": "Najjednoduchší model: zisk na akciu o rok × férové P/E, diskontovaný na dnešok. Dáva zmysel len pri firmách so ziskom.",
    "ps": "Tržby na akciu o rok × férové P/S. Používa sa pri rýchlo rastúcich firmách, ktorých zisk ešte nie je stabilný. Ignoruje ziskovosť, preto ber výsledok opatrne.",
    "ddm": "Dvojstupňový dividendový model: dividenda rastie 5 rokov danou rýchlosťou, potom stabilne. Použiteľné len pri firmách, ktoré platia podstatnú dividendu (výnos aspoň 1 %).",
    "pb": "Férové P/B = (ROE − g) / (požadovaná návratnosť − g). Hodnota = férové P/B × účtovná hodnota na akciu. Vhodné hlavne pre banky a poisťovne.",
    "graham": "Klasické vzorce Benjamina Grahama: Grahamov vzorec EPS × (8,5 + 2g) × 4,4 / Y a Grahamovo číslo √(22,5 × EPS × BVPS). Hrubý odhad, v súhrne sa nepoužíva.",
}

MODEL_META = [  # kľúč, názov, krátky popis, patrí do súhrnu
    ("dcf", "DCF", "Diskontovaný voľný cash flow na 10 rokov", True),
    ("evebitda", "EV / EBITDA", "Cieľový násobok z prevádzkového zisku pred odpismi", True),
    ("fcfy", "FCF výnos", "Koľko voľného cash flow chceš za akciu", True),
    ("pe", "Cieľové P/E", "Zisk na akciu × férové P/E", True),
    ("ps", "Cieľové P/S", "Tržby na akciu × férové P/S", True),
    ("ddm", "Dividendy (DDM)", "Hodnota budúcich dividend", True),
    ("pb", "Férové P/B", "Účtovná hodnota × (ROE − g) / (ke − g)", True),
    ("graham", "Graham", "Klasický vzorec a Grahamovo číslo", False),
]


def _models_list(out, is_fin, price):
    order = ["pb", "pe", "ddm", "graham", "evebitda", "fcfy", "ps", "dcf"] if is_fin else \
        ["dcf", "evebitda", "fcfy", "pe", "ps", "ddm", "pb", "graham"]
    meta = {k: (n, d, c) for k, n, d, c in MODEL_META}
    res = []
    for key in order:
        m = out.get(key)
        if m is None:
            continue
        name, desc, core = meta[key]
        scen = _norm_scen(key, m.get("scenarios") or [])
        ok = bool(scen) and all(sc["value"] is not None for sc in scen) and not m.get("error")
        suitable = m.get("suitable", True)
        if key == "dcf" and is_fin:
            suitable = False
        if key == "pb" and not is_fin:
            suitable = False
        base = scen[1]["value"] if ok else None
        res.append({"key": key, "name": name, "desc": desc, "intro": MODEL_INTRO.get(key, ""),
                    "relative": key in ("evebitda", "fcfy", "pe", "ps"), "core": core and suitable, "ok": ok, "suitable": suitable,
                    "scenarios": scen, "base": base,
                    "upside": (base / price - 1) if base and price else None, "error": m.get("error")})
    return res


def _more_models(out, args, facts, analyst, price, currency, is_fin, ke, rf_used, g_rec, shares, sh, nd, rv, wacc, mcap, an_txt):
    """DDM, EV/EBITDA, FCF výnos, P/S a Graham s odporúčanými vstupmi."""
    ke_pct = round(ke * 100, 1)
    h_ke = [f"Požadovaná návratnosť akcií (CAPM): {_pct(ke)}"]
    shares_n = (sh or 0) * 1e6
    sh_f = shares or shares_n
    # ---------------- DDM
    dps = facts.get("dps")
    dps_g = facts.get("dps_cagr5") if facts.get("dps_cagr5") is not None else facts.get("dps_cagr3")
    g_hi_rec = round(max(0.0, min(0.12, dps_g if dps_g is not None else 0.05)), 3)
    dd_dps, _ = _num_in(args, "dd_dps", round(dps, 2) if dps else 0.0, 1)
    dd_g, _ = _num_in(args, "dd_g", g_hi_rec * 100, 1, 0, 25)
    dd_gt, _ = _num_in(args, "dd_gt", 2.5, 1, 0, 6)
    dd_ke, _ = _num_in(args, "dd_ke", ke_pct, 1, 3, 25)
    h_dps = []
    if facts.get("dps_cagr5") is not None:
        h_dps.append(f"Rast dividendy na akciu za 5 rokov (CAGR): {_pct(facts['dps_cagr5'])}")
    if facts.get("dps_cagr3") is not None:
        h_dps.append(f"Za 3 roky: {_pct(facts['dps_cagr3'])}")
    if dps and facts.get("eps_ttm"):
        h_dps.append(f"Výplatný pomer (dividenda / zisk): {_pct(dps / facts['eps_ttm'], 0)}")
    ddf = [
        _fld("dd_dps", "Dividenda na akciu (posledný rok)", currency, dd_dps, round(dps, 2) if dps else None,
             "Vyplatené dividendy lomené počtom akcií.", [], "Dividenda, z ktorej model vychádza.", "0.01", "{:.2f}"),
        _fld("dd_g", "Rast dividendy v rokoch 1 až 5", "% ročne", dd_g, round(g_hi_rec * 100, 1),
             "Vychádza z: historický rast dividendy (najviac 12 %).", h_dps, "Potom dividenda rastie terminálnym tempom."),
        _fld("dd_gt", "Terminálny rast dividendy", "% ročne", dd_gt, 2.5, "Vychádza z: dlhodobý rast ekonomiky.", [], None),
        _fld("dd_ke", "Požadovaná návratnosť", "%", dd_ke, ke_pct, "Vychádza z: CAPM.", h_ke, "Čím vyššia, tým nižšia hodnota akcie."),
    ]
    ddp = dict(dps0=dd_dps, g_high=dd_g / 100, g_term=dd_gt / 100, ke=dd_ke / 100)
    ddb = V.ddm(ddp["dps0"], ddp["g_high"], ddp["g_term"], ddp["ke"])
    ddm_ok = bool(dps) and (not price or dps / price >= 0.01)
    out["ddm"] = {"fields": ddf, "p": ddp, "error": ddb.get("error"), "base": None if "error" in ddb else ddb,
                  "scenarios": V.ddm_scenarios(ddp, price) if "error" not in ddb else [], "suitable": ddm_ok}
    # ---------------- EV / EBITDA
    eb = facts.get("ebitda")
    eb_mil = round((eb or 0) / 1e6, 1)
    ebg_rec = facts.get("ebitda_cagr3")
    ebg_rec = round(max(-0.1, min(0.4, g_rec if ebg_rec is None else (ebg_rec + g_rec) / 2)), 3)
    ev_now = ((mcap + facts["net_debt"]) / eb) if mcap and eb and eb > 0 and facts.get("net_debt") is not None else None
    mult_rec = round(max(6.0, min(30.0, ev_now)), 1) if ev_now else 12.0
    ee_eb, _ = _num_in(args, "ee_eb", eb_mil, 1)
    ee_g, _ = _num_in(args, "ee_g", ebg_rec * 100, 1, -50, 100)
    ee_m, _ = _num_in(args, "ee_m", mult_rec, 1, 1, 100)
    ee_nd, _ = _num_in(args, "ee_nd", nd, 1)
    ee_sh, _ = _num_in(args, "ee_sh", sh, 1, 0.000001)
    ee_r, _ = _num_in(args, "ee_r", ke_pct, 1, 3, 25)
    h_em = ([f"Dnešný EV/EBITDA: {ev_now:.1f}×"] if ev_now else []) + ["Zrelé firmy sa obchodujú zvyčajne za 8 až 14×, rastové technologické za 15 až 30×."]
    h_eg = []
    if facts.get("ebitda_cagr3") is not None:
        h_eg.append(f"Rast EBITDA za 3 roky (CAGR): {_pct(facts['ebitda_cagr3'])}")
    h_eg.append(f"Odporúčaný rast tržieb z DCF: {_pct(g_rec)}")
    eef = [
        _fld("ee_eb", f"EBITDA (posledný rok, mil. {currency})", f"mil. {currency}", ee_eb, eb_mil, "Prevádzkový zisk + odpisy.", [], None, "1", "{:.1f}"),
        _fld("ee_g", "Rast EBITDA na budúci rok", "%", ee_g, round(ebg_rec * 100, 1), "Vychádza z: priemer histórie EBITDA a rastu tržieb.", h_eg, None),
        _fld("ee_m", "Cieľový EV/EBITDA", "×", ee_m, mult_rec, "Vychádza z: dnešný násobok (obmedzený na 6 až 30×).", h_em, "Koľkonásobok EBITDA je férová hodnota firmy."),
        _fld("ee_nd", f"Čistý dlh (mil. {currency})", f"mil. {currency}", ee_nd, round(nd, 1), "Z poslednej súvahy.", [], None, "1", "{:.1f}"),
        _fld("ee_sh", "Počet akcií", "mil.", ee_sh, round(sh, 2), "Z titulnej strany výkazov.", [], None, "0.01", "{:.2f}"),
        _fld("ee_r", "Diskontná sadzba", "%", ee_r, ke_pct, "Vychádza z: CAPM.", h_ke, "Hodnotu o rok prepočíta na dnes."),
    ]
    eep = dict(ebitda0=ee_eb * 1e6, g=ee_g / 100, mult=ee_m, net_debt=ee_nd * 1e6, shares=ee_sh * 1e6, r=ee_r / 100)
    eeb = V.ev_ebitda_model(eep["ebitda0"], eep["g"], eep["mult"], eep["net_debt"], eep["shares"], eep["r"])
    out["evebitda"] = {"fields": eef, "p": eep, "error": eeb.get("error"), "base": None if "error" in eeb else eeb,
                       "scenarios": V.ev_ebitda_scenarios(eep, price) if "error" not in eeb else [], "ev_now": ev_now}
    # ---------------- FCF výnos
    fcf0 = facts.get("fcf_ttm") if facts.get("fcf_ttm") is not None else facts.get("fcf_fy")
    fcf_mil = round((fcf0 or 0) / 1e6, 1)
    fy_now = (fcf0 / mcap) if mcap and fcf0 is not None else None
    fy_rec = round(max(0.025, min(0.08, fy_now if fy_now and fy_now > 0 else 0.05)), 3)
    fg_rec = round(max(0.0, min(0.15, g_rec * 0.8)), 3)
    ff_f, _ = _num_in(args, "ff_f", fcf_mil, 1)
    ff_g, _ = _num_in(args, "ff_g", fg_rec * 100, 1, -30, 60)
    ff_y, _ = _num_in(args, "ff_y", fy_rec * 100, 1, 0.5, 30)
    ff_sh, _ = _num_in(args, "ff_sh", sh, 1, 0.000001)
    ff_r, _ = _num_in(args, "ff_r", ke_pct, 1, 3, 25)
    h_fy = ([f"Dnešný FCF výnos (FCF / trhová kapitalizácia): {_pct(fy_now)}"] if fy_now is not None else []) + \
           ["Štátne dlhopisy dávajú okolo 4 %, od akcie sa zvyčajne chce viac (5 až 7 %)."]
    fff = [
        _fld("ff_f", f"Voľný cash flow (mil. {currency})", f"mil. {currency}", ff_f, fcf_mil, "Posledných 12 mesiacov (alebo fiškálny rok).", [], None, "1", "{:.1f}"),
        _fld("ff_g", "Rast FCF na budúci rok", "%", ff_g, round(fg_rec * 100, 1), "Vychádza z: 80 % z odporúčaného rastu tržieb.", [f"Odporúčaný rast tržieb: {_pct(g_rec)}"], None),
        _fld("ff_y", "Cieľový FCF výnos", "%", ff_y, round(fy_rec * 100, 1), "Vychádza z: dnešný FCF výnos (obmedzený na 2,5 až 8 %).", h_fy, "Nižší požadovaný výnos = vyššia hodnota akcie."),
        _fld("ff_sh", "Počet akcií", "mil.", ff_sh, round(sh, 2), "Z titulnej strany výkazov.", [], None, "0.01", "{:.2f}"),
        _fld("ff_r", "Diskontná sadzba", "%", ff_r, ke_pct, "Vychádza z: CAPM.", h_ke, None),
    ]
    ffp = dict(fcf0=ff_f * 1e6, g=ff_g / 100, **{"yield": ff_y / 100}, shares=ff_sh * 1e6, r=ff_r / 100)
    ffb = V.fcf_yield_model(ffp["fcf0"], ffp["g"], ffp["yield"], ffp["shares"], ffp["r"])
    out["fcfy"] = {"fields": fff, "p": ffp, "error": ffb.get("error"), "base": None if "error" in ffb else ffb,
                   "scenarios": V.fcf_yield_scenarios(ffp, price) if "error" not in ffb else [], "fy_now": fy_now}
    # ---------------- P/S
    ps_now = (mcap / (rv * 1e6)) if mcap and rv else None
    psr = round(max(0.5, min(15.0, ps_now)), 1) if ps_now else 3.0
    pp_r, _ = _num_in(args, "ps_rev", rv, 1)
    pp_g, _ = _num_in(args, "ps_g", g_rec * 100, 1, -30, 80)
    pp_ps, _ = _num_in(args, "ps_ps", psr, 1, 0.1, 50)
    pp_sh, _ = _num_in(args, "ps_sh", sh, 1, 0.000001)
    pp_k, _ = _num_in(args, "ps_r", ke_pct, 1, 3, 25)
    h_ps = ([f"Dnešné P/S: {ps_now:.1f}×"] if ps_now else []) + ["P/S je užitočné pri rýchlo rastúcich firmách bez stabilného zisku, ale ignoruje maržu."]
    psf = [
        _fld("ps_rev", f"Tržby (mil. {currency})", f"mil. {currency}", pp_r, rv, "Posledných 12 mesiacov.", [], None, "1", "{:.1f}"),
        _fld("ps_g", "Rast tržieb na budúci rok", "%", pp_g, round(g_rec * 100, 1), f"Vychádza z: rovnaký odporúčaný rast ako v DCF.", [f"Odporúčaný rast tržieb: {_pct(g_rec)}"], None),
        _fld("ps_ps", "Cieľové P/S", "×", pp_ps, psr, "Vychádza z: dnešné P/S (obmedzené na 0,5 až 15×).", h_ps, "Koľkonásobok tržieb na akciu je férová cena o rok."),
        _fld("ps_sh", "Počet akcií", "mil.", pp_sh, round(sh, 2), "Z titulnej strany výkazov.", [], None, "0.01", "{:.2f}"),
        _fld("ps_r", "Diskontná sadzba", "%", pp_k, ke_pct, "Vychádza z: CAPM.", h_ke, None),
    ]
    psp = dict(rev0=pp_r * 1e6, g=pp_g / 100, target_ps=pp_ps, shares=pp_sh * 1e6, r=pp_k / 100)
    psb = V.ps_model(psp["rev0"], psp["g"], psp["target_ps"], psp["shares"], psp["r"])
    out["ps"] = {"fields": psf, "p": psp, "error": psb.get("error"), "base": None if "error" in psb else psb,
                 "scenarios": V.ps_scenarios(psp, price) if "error" not in psb else [], "ps_now": ps_now}
    # ---------------- Graham
    eps0 = facts.get("eps_ttm")
    bv = (facts.get("equity") or 0) / sh_f if sh_f else None
    g_gr = facts.get("eps_cagr5") if facts.get("eps_cagr5") is not None else facts.get("eps_cagr3")
    g_gr_rec = round(max(0.0, min(15.0, (g_gr if g_gr is not None else 0.05) * 100)), 1)
    y_rec = round((rf_used + 0.01) * 100, 1)
    gr_e, _ = _num_in(args, "gr_eps", round(eps0, 2) if eps0 else 0.0, 1)
    gr_b, _ = _num_in(args, "gr_bv", round(bv, 2) if bv else 0.0, 1)
    gr_g, _ = _num_in(args, "gr_g", g_gr_rec, 1, 0, 30)
    gr_y, _ = _num_in(args, "gr_y", y_rec, 1, 1, 15)
    grf = [
        _fld("gr_eps", "Zisk na akciu (EPS)", currency, gr_e, round(eps0, 2) if eps0 else None, "Zriedený EPS za 12 mesiacov.", [], None, "0.01", "{:.2f}"),
        _fld("gr_bv", "Účtovná hodnota na akciu", currency, gr_b, round(bv, 2) if bv else None, "Vlastné imanie lomené počtom akcií.", [], None, "0.01", "{:.2f}"),
        _fld("gr_g", "Očakávaný rast zisku (7 až 10 rokov)", "% ročne", gr_g, g_gr_rec, "Vychádza z: historický CAGR zisku na akciu (0 až 15 %).",
             [f"Rast EPS za 5 rokov: {_pct(facts.get('eps_cagr5'))}"] if facts.get("eps_cagr5") is not None else [], "Do vzorca vstupuje ako číslo v percentách."),
        _fld("gr_y", "Výnos podnikových dlhopisov AAA", "%", gr_y, y_rec, "Vychádza z: bezriziková sadzba + 1 p. b.", [], "Graham pôvodne použil 4,4 % z roku 1962."),
    ]
    grp = dict(eps=gr_e, bvps=gr_b, g=gr_g, y=gr_y)
    grb = V.graham(grp["eps"], grp["bvps"], grp["g"], grp["y"])
    out["graham"] = {"fields": grf, "p": grp, "error": grb.get("error"), "base": None if "error" in grb else grb,
                     "scenarios": V.graham_scenarios(grp, price) if "error" not in grb else [], "suitable": True}


# ------------------------------------------------------------------ porovnanie s konkurenciou
import quality as Q  # noqa: E402


def peer_metrics(name, ticker, built, facts, btype, quote, shares_out):
    """Jeden stĺpec porovnania: dict kľúč -> hodnota (None = chýba)."""
    t = built["display"][-1]
    g = lambda k: built["data"].get(k, {}).get(t)  # noqa: E731
    rev = V.net_revenue(built, t)
    ebitda = (g("op_income") + g("da")) if g("op_income") is not None and g("da") is not None else None
    ni = g("net_income")
    ro = None
    pio = alt = None
    if btype not in ("bank", "insurance"):
        try:
            ro, pio, alt = Q.roic(built), Q.piotroski(built), Q.altman(built)
        except (TypeError, ZeroDivisionError):
            pass
    price = quote.get("price") if quote and not quote.get("mismatch") else None
    mcap = price * shares_out if price and shares_out else None
    eps = facts.get("eps_ttm")
    nd = facts.get("net_debt")
    fcf = g("fcf")
    fin = btype in ("bank", "insurance")   # u bánk je prevádzkový cash flow poznačený úvermi, FCF nemá zmysel
    return {
        "ticker": ticker, "name": name, "currency": built["currency"], "fy": t,
        "revenue": rev, "rev_cagr3": facts.get("rev_cagr3"),
        "op_margin": (g("op_income") / rev) if rev and g("op_income") is not None else None,
        "net_margin": (ni / rev) if rev and ni is not None else None,
        "fcf_margin": None if fin else facts.get("fcf_margin_avg3"),
        "roe": facts.get("roe_avg3") if facts.get("roe_avg3") is not None else facts.get("roe_last"),
        "roic": ro["roic"] if ro else None,
        "nd_ebitda": (nd / ebitda) if ebitda and ebitda > 0 and nd is not None else None,
        "piotroski": pio["score"] if pio else None,
        "altman": alt["z"] if alt else None,
        "mcap": mcap,
        "pe": (price / eps) if price and eps and eps > 0 else None,
        "ps": (mcap / rev) if mcap and rev else None,
        "ev_ebitda": ((mcap + nd) / ebitda) if mcap and ebitda and ebitda > 0 and nd is not None else None,
        "fcf_yield": (fcf / mcap) if mcap and fcf is not None and not fin else None,
    }


# (kľúč, názov, formát, lepšie: 'hi' / 'lo' / None)
PEER_ROWS = [
    ("revenue", "Tržby (posledný rok)", "money", None), ("rev_cagr3", "Rast tržieb 3 roky (CAGR)", "pct", "hi"),
    ("op_margin", "Prevádzková marža", "pct", "hi"), ("net_margin", "Čistá marža", "pct", "hi"),
    ("fcf_margin", "FCF marža (priemer 3 roky)", "pct", "hi"), ("roe", "ROE (priemer 3 roky)", "pct", "hi"),
    ("roic", "ROIC", "pct", "hi"), ("nd_ebitda", "Čistý dlh / EBITDA", "x", "lo"),
    ("piotroski", "Piotroski F-score (0 až 9)", "int", "hi"), ("altman", "Altman Z''", "num2", "hi"),
    ("mcap", "Trhová kapitalizácia", "big", None), ("pe", "P/E", "x", "lo"), ("ps", "P/S", "x", "lo"),
    ("ev_ebitda", "EV / EBITDA", "x", "lo"), ("fcf_yield", "FCF výnos", "pct", "hi"),
]


def peer_table(cols):
    """cols = zoznam výstupov peer_metrics (prvý = analyzovaná firma). Označí najlepšiu hodnotu v riadku."""
    rows = []
    for key, label, fmt, better in PEER_ROWS:
        vals = [c.get(key) for c in cols]
        best = None
        known = [(v, i) for i, v in enumerate(vals) if v is not None]
        if better and len(known) >= 2:
            pool = [(v, i) for v, i in known if not (key == "nd_ebitda" and v < 0 and False)]
            best = (max(pool) if better == "hi" else min(pool))[1]
        rows.append({"key": key, "label": label, "fmt": fmt, "vals": vals, "best": best})
    return rows

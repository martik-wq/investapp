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
             "Voľný cash flow lomený tržbami. Marža sa lineárne mení z dnešnej na túto hodnotu."),
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
             "Z poslednej súvahy: dlh mínus hotovosť a krátkodobé investície.",
             [f"Dlh {(facts.get('debt') or 0) / 1e6:,.0f} mil., hotovosť a investície {(facts.get('cash') or 0) / 1e6:,.0f} mil."],
             "Záporný = firma má viac hotovosti ako dlhu.", "1", "{:.1f}"),
        _fld("d_sh", "Počet akcií", "mil.", sh, round(sh_mil, 2), "Z titulnej strany výkazov (všetky triedy akcií).",
             [], None, "0.01", "{:.2f}"),
    ]
    p = dict(rev0=rv * 1e6, g1=g1 / 100, margin0=facts.get("fcf_margin_now") if facts.get("fcf_margin_now") is not None else m5 / 100,
             margin5=m5 / 100, wacc=wacc / 100, g_term=gt / 100, net_debt=nd * 1e6, shares=sh * 1e6, dilution=dil / 100)
    base = V.dcf(p["rev0"], p["g1"], p["margin0"], p["margin5"], p["wacc"], p["g_term"], p["net_debt"], p["shares"], p["dilution"])
    out["dcf"] = {"fields": dcf_fields, "p": p, "error": base.get("error"), "base": None if "error" in base else base,
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

    # ------------------------------------------------------------------ súhrn
    summary = []
    for key, name in (("dcf", "DCF"), ("pb", "Férové P/B"), ("pe", "Cieľové P/E")):
        # DCF z FCF nedáva pri bankách a poisťovniach zmysel, P/B model zase pri bežných firmách
        if (key == "dcf" and is_fin) or (key == "pb" and not is_fin):
            continue
        sc = out[key]["scenarios"]
        vals = [s["value"] for s in sc if s.get("value") is not None]
        if len(vals) == 3:
            summary.append({"key": key, "name": name, "low": min(vals), "mid": sc[1]["value"], "high": max(vals)})
    out["summary"] = summary
    if summary:
        hi = max([s["high"] for s in summary] + [price or 0]) * 1.05
        for s in summary:
            s["pl"], s["pw"], s["pm"] = s["low"] / hi * 100, (s["high"] - s["low"]) / hi * 100, s["mid"] / hi * 100
        out["price_pos"] = (price / hi * 100) if price else None
    if facts.get("rev_years", 0) < 3:
        out["notes"].append("Firma má krátku históriu (menej ako 3 roky), odporúčania sú preto menej spoľahlivé.")
    if price is None:
        out["notes"].append("Bez ceny akcie sa neukáže porovnanie s trhom. Cenu môžeš zadať v záložke Úvod.")
    if quote_note:
        out["notes"].append(quote_note)
    out["wacc_parts"] = {"ke": ke, "rf": rf_used, "beta": beta_used, "w_d": w_d, "kd": kd}
    return out

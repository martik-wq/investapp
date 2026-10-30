"""Export všetkých výkazov firmy do jedného Excelu (.xlsx): výkaz ziskov a strát, súvaha, cash flow,
metriky a valuácia. Hodnoty v miliónoch meny (EPS a pomery v pôvodných jednotkách)."""
import io
import subprocess
import sys
from datetime import date

ORANGE, TINT = "C4570F", "FBEEE2"


def _openpyxl():
    try:
        import openpyxl  # noqa: F401
    except ImportError:
        # po aktualizácii priamo z appky ešte nemusí byť nainštalovaný, skúsime ho doinštalovať
        subprocess.run([sys.executable, "-m", "pip", "install", "-q", "openpyxl"], check=False, timeout=180)
    import openpyxl
    return openpyxl


def _rows(ctx, key):
    """[{'label','vals','kind','bold','indent','header','sub'}] z podrobných alebo zjednodušených výkazov."""
    det = ctx.get("det")
    if det:
        return [{"label": r["label"], "vals": r.get("vals", {}), "kind": r.get("kind", "money"),
                 "bold": bool(r.get("bold")), "indent": r.get("indent", 0) or 0,
                 "header": bool(r.get("header")), "sub": bool(r.get("sub"))} for r in det[key]]
    unit_kind = {"cur": "money", "shares": "shares", "eps": "eps"}
    return [{"label": r["label"], "vals": r["vals"], "kind": unit_kind.get(r["unit"], "money"),
             "bold": bool(r["bold"]), "indent": r["indent"] or 0, "header": False, "sub": False}
            for r in ctx["stm"][key]]


def _scaled(v, kind):
    if v is None:
        return None
    return v if kind == "eps" else v / 1e6


def build_workbook(ctx):
    openpyxl = _openpyxl()
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    comp, built, result = ctx["comp"], ctx["built"], ctx["result"]
    ends = list(reversed(built["display"] if not ctx.get("det") else ctx["det"]["ends"]))
    cur = built["currency"]
    wb = openpyxl.Workbook()
    head_font = Font(bold=True, color="FFFFFF")
    head_fill = PatternFill("solid", fgColor=ORANGE)
    sec_fill = PatternFill("solid", fgColor=TINT)
    NUM = {"money": '#,##0.0;[Red]-#,##0.0', "shares": '#,##0.0', "eps": '#,##0.00;[Red]-#,##0.00'}

    # ---- informácie
    ws = wb.active
    ws.title = "Info"
    info = [("Firma", comp["name"]), ("Ticker", comp["ticker"]), ("Mena výkazov", cur),
            ("Obdobie", "ročné" if ctx["mode"] == "annual" else "kvartálne"),
            ("Typ biznisu", result["type_label"]),
            ("Zobrazenie výkazov", "ako firma uvádza" if ctx.get("det") else "zjednodušené (štandardizované)"),
            ("Jednotky", f"mil. {cur} (EPS v {cur}, pomery v %, počet akcií v mil.)"),
            ("Zdroj", "SEC EDGAR (XBRL)"), ("Vytvorené", date.today().strftime("%d.%m.%Y")),
            ("Poznámka", "Údaje sú automaticky mapované z podaní, pri dôležitých rozhodnutiach ich porovnaj "
                         "s originálnym podaním. Nejde o investičné odporúčanie.")]
    for r, (k, v) in enumerate(info, start=1):
        ws.cell(r, 1, k).font = Font(bold=True)
        ws.cell(r, 2, v)
    ws.column_dimensions["A"].width = 24
    ws.column_dimensions["B"].width = 80

    def header(sheet, title):
        sheet.cell(1, 1, f"{comp['name']} ({comp['ticker']}) · {title} · mil. {cur}").font = Font(bold=True, size=13)
        sheet.cell(2, 1, "").fill = head_fill
        for i, e in enumerate(ends, start=2):
            c = sheet.cell(2, i, e)
            c.number_format = "dd.mm.yyyy"
            c.font, c.fill = head_font, head_fill
            c.alignment = Alignment(horizontal="right")
        sheet.cell(2, 1).font = head_font
        sheet.column_dimensions["A"].width = 58
        for i in range(2, len(ends) + 2):
            sheet.column_dimensions[get_column_letter(i)].width = 14
        sheet.freeze_panes = "B3"

    # ---- výkazy
    for key, title in (("income", "Výkaz ziskov a strát"), ("balance", "Súvaha"), ("cashflow", "Cash flow")):
        sh = wb.create_sheet(title)
        header(sh, title)
        r = 3
        for row in _rows(ctx, key):
            lab = sh.cell(r, 1, row["label"])
            lab.alignment = Alignment(indent=min(int(row["indent"]) + (1 if row["sub"] else 0), 6), wrap_text=False)
            if row["header"]:
                for i in range(1, len(ends) + 2):
                    sh.cell(r, i).fill = sec_fill
                lab.font = Font(bold=True, color=ORANGE)
            else:
                for i, e in enumerate(ends, start=2):
                    v = _scaled(row["vals"].get(e), row["kind"])
                    c = sh.cell(r, i, v)
                    c.number_format = NUM.get(row["kind"], NUM["money"])
                    if row["bold"]:
                        c.font = Font(bold=True)
                    if row["sub"]:
                        c.font = Font(italic=True, color="7A6A5A")
                if row["bold"]:
                    lab.font = Font(bold=True)
                if row["sub"]:
                    lab.font = Font(italic=True, color="7A6A5A")
            r += 1

    # ---- metriky
    sh = wb.create_sheet("Metriky")
    header(sh, f"Metriky ({result['type_label']})")
    mfmt = {"pct": "0.0%", "x": '0.00"×"', "days": "0", "eps": "0.00", "amt": "#,##0.00"}
    r = 3
    for g in result["groups"]:
        c = sh.cell(r, 1, g["title"])
        c.font = Font(bold=True, color=ORANGE)
        for i in range(1, len(ends) + 2):
            sh.cell(r, i).fill = sec_fill
        r += 1
        for row in g["rows"]:
            sh.cell(r, 1, row["label"])
            for i, e in enumerate(ends, start=2):
                v = row["vals"].get(e)
                f = row["fmt"]
                if v is not None and f in ("money", "num"):
                    v = v / 1e6
                cell = sh.cell(r, i, v)
                cell.number_format = mfmt.get(f, '#,##0.0;[Red]-#,##0.0')
            r += 1

    # ---- valuácia
    if ctx.get("val"):
        sh = wb.create_sheet("Valuácia")
        sh.cell(1, 1, f"Valuácia pri cene {ctx['price_used']:.2f} {cur}").font = Font(bold=True, size=13)
        sh.column_dimensions["A"].width = 46
        sh.column_dimensions["B"].width = 18
        for r, (label, v, f) in enumerate(ctx["val"]["items"], start=2):
            sh.cell(r, 1, label)
            if v is not None and f in ("money", "num"):
                v = v / 1e6
            c = sh.cell(r, 2, v)
            c.number_format = mfmt.get(f, '#,##0.0')

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()

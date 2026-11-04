"""Prevod symbolu (Yahoo štýl) na symbol TradingView, napr. 000660.KS -> KRX:000660, 6146.T -> TSE:6146.

US tickery posielame bez burzy (TradingView si nájde hlavnú burzu), triedy akcií majú bodku: BRK-B -> BRK.B.
Ak príponu nepoznáme, vrátime None a appka ukáže graf TradingView len ako odkaz na vyhľadávanie."""
import re

# prípona Yahoo -> (burza TradingView, odstrániť úvodné nuly?)
SUFFIX = {
    "T": ("TSE", False), "KS": ("KRX", False), "KQ": ("KRX", False), "DE": ("XETR", False),
    "AS": ("EURONEXT", False), "PA": ("EURONEXT", False), "BR": ("EURONEXT", False), "LS": ("EURONEXT", False),
    "L": ("LSE", False), "TW": ("TWSE", False), "TWO": ("TPEX", False), "HK": ("HKEX", True),
    "TO": ("TSX", False), "V": ("TSXV", False), "SW": ("SIX", False), "MI": ("MIL", False),
    "MC": ("BME", False), "ST": ("OMXSTO", False), "CO": ("OMXCOP", False), "HE": ("OMXHEX", False),
    "OL": ("OSL", False), "AX": ("ASX", False), "SI": ("SGX", False), "SS": ("SSE", False), "SZ": ("SZSE", False),
    "NS": ("NSE", False), "BO": ("BSE", False), "SA": ("BMFBOVESPA", False), "MX": ("BMV", False),
}


def to_tv(symbol):
    s = (symbol or "").upper().strip()
    if not re.fullmatch(r"[A-Z0-9.\-^]{1,15}", s) or s.startswith("^"):
        return None
    m = re.fullmatch(r"([A-Z0-9\-]+)\.([A-Z]{1,3})", s)
    if m and m.group(2) in SUFFIX:
        ex, strip = SUFFIX[m.group(2)]
        code = m.group(1).lstrip("0") or "0" if strip else m.group(1)
        return f"{ex}:{code}"
    if "." in s:  # neznáma prípona
        return None
    return s.replace("-", ".")

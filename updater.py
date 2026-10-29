"""Aktualizácia aplikácie z GitHubu priamo zo stránky (bez vypínania a zapínania).

Stiahne zip poslednej verzie (rovnaký repozitár ako update.ps1), prepíše súbory aplikácie
a zapíše číslo verzie do version.txt. Nikdy sa nedotkne priečinkov data, cache, venv ani
súboru config.txt. Spúšťače (spustit.bat, run.bat) sa tu nemenia, lebo práve bežia.
Server sa po zmene .py súborov reštartuje sám (reloader v app.py)."""
import io
import os
import shutil
import tempfile
import zipfile

import requests

REPO = "martik-wq/investapp"
BRANCH = "main"
BASE = os.path.dirname(os.path.abspath(__file__))
VERSION_FILE = os.path.join(BASE, "version.txt")
SKIP_DIRS = {"venv", "cache", ".git", "__pycache__", "data", "demo_data_user"}
SKIP_FILES = {"config.txt", "spustit.bat", "run.bat", "spustit.command", ".gitignore", "version.txt"}
TIMEOUT = 25


def current_version():
    try:
        with open(VERSION_FILE, encoding="ascii") as f:
            return f.read().strip() or None
    except OSError:
        return None


def latest_version():
    """Skratka (sha) posledného commitu na GitHube, alebo None pri chybe."""
    try:
        r = requests.get(f"https://api.github.com/repos/{REPO}/commits/{BRANCH}", timeout=TIMEOUT,
                         headers={"Accept": "application/vnd.github+json", "User-Agent": "investapp"})
        r.raise_for_status()
        return r.json()["sha"]
    except (requests.RequestException, KeyError, ValueError):
        return None


def check():
    cur, new = current_version(), latest_version()
    return {"current": cur, "latest": new, "ok": new is not None,
            "available": bool(new) and new != cur}


def install_zip(data, base=BASE):
    """Rozbalí zip (obsah jedného koreňového priečinka) do `base`. Vráti zoznam zmenených súborov."""
    changed = []
    with zipfile.ZipFile(io.BytesIO(data)) as z, tempfile.TemporaryDirectory() as tmp:
        z.extractall(tmp)
        roots = [d for d in os.listdir(tmp) if os.path.isdir(os.path.join(tmp, d))]
        if len(roots) != 1:
            raise ValueError("Neočakávaná štruktúra stiahnutého súboru.")
        src_root = os.path.join(tmp, roots[0])
        if not os.path.exists(os.path.join(src_root, "app.py")):
            raise ValueError("Stiahnutý súbor neobsahuje aplikáciu.")
        for dirpath, dirnames, filenames in os.walk(src_root):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
            rel_dir = os.path.relpath(dirpath, src_root)
            for fn in filenames:
                rel = fn if rel_dir == "." else os.path.join(rel_dir, fn)
                if rel_dir == "." and fn in SKIP_FILES:
                    continue
                src, dst = os.path.join(dirpath, fn), os.path.join(base, rel)
                with open(src, "rb") as a:
                    new = a.read()
                try:
                    with open(dst, "rb") as b:
                        if b.read() == new:
                            continue
                except OSError:
                    pass
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                with open(dst, "wb") as out:
                    out.write(new)
                changed.append(rel.replace(os.sep, "/"))
    return changed


def apply():
    """Stiahne a nainštaluje poslednú verziu. Vráti {'ok', 'changed', 'version', 'error'}."""
    ver = latest_version()
    try:
        r = requests.get(f"https://github.com/{REPO}/archive/refs/heads/{BRANCH}.zip", timeout=60)
        r.raise_for_status()
        changed = install_zip(r.content)
    except (requests.RequestException, zipfile.BadZipFile, ValueError, OSError) as e:
        return {"ok": False, "error": f"Aktualizácia sa nepodarila: {e}", "changed": []}
    if ver:
        try:
            with open(VERSION_FILE, "w", encoding="ascii") as f:
                f.write(ver)
        except OSError:
            pass
    return {"ok": True, "changed": changed, "version": ver}

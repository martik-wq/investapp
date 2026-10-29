#!/bin/bash
cd "$(dirname "$0")"

# --- aktualizácia z GitHubu ---
TMPD=$(mktemp -d)
if curl -fsSL -m 30 "https://github.com/martik-wq/investapp/archive/refs/heads/main.zip" -o "$TMPD/u.zip" 2>/dev/null && unzip -q "$TMPD/u.zip" -d "$TMPD" 2>/dev/null; then
  SRC=$(find "$TMPD" -mindepth 1 -maxdepth 1 -type d | head -1)
  rsync -a --exclude venv --exclude cache --exclude data --exclude .git --exclude __pycache__ --exclude config.txt --exclude spustit.bat --exclude spustit.command "$SRC"/ ./ && echo "Aplikácia je aktuálna."
else
  echo "Aktualizácia sa nepodarila, pokračujem so súčasnou verziou."
fi
rm -rf "$TMPD"
PY=$(command -v python3 || command -v python)
if [ -z "$PY" ]; then
  echo "Python nie je nainstalovaný. Stiahni ho z https://www.python.org/downloads/"
  open https://www.python.org/downloads/ 2>/dev/null
  read -p "Stlač Enter..."; exit 1
fi
[ -d venv ] || { echo "Prvá inštalácia, chvíľu to potrvá..."; "$PY" -m venv venv; }
source venv/bin/activate
pip install -q -r requirements.txt
if [ ! -f config.txt ]; then
  echo "SEC vyžaduje, aby si uviedol svoje meno a e-mail (zadáva sa len raz)."
  read -p "Zadaj meno a e-mail, napr. Jan Novak jan@email.sk: " UA
  echo "$UA" > config.txt
fi
echo "Aplikácia beží na http://127.0.0.1:5000 (okno nechaj otvorené)"
(sleep 2; open http://127.0.0.1:5000 2>/dev/null || xdg-open http://127.0.0.1:5000 2>/dev/null) &
python app.py

@echo off
chcp 65001 >nul
cd /d "%~dp0"
set PY=
where python >nul 2>nul && set PY=python
if "%PY%"=="" where py >nul 2>nul && set PY=py
if "%PY%"=="" goto nopython
if exist venv\Scripts\activate.bat goto havevenv
echo Prva instalacia, chvilu to potrva...
%PY% -m venv venv
:havevenv
call venv\Scripts\activate.bat
pip install -q -r requirements.txt
if exist config.txt goto run
echo.
echo SEC vyzaduje, aby si uviedol svoje meno a e-mail (zadava sa len raz).
set /p UA=Zadaj meno a e-mail, napr. Jan Novak jan@email.sk: 
> config.txt echo %UA%
:run
echo.
echo Aplikacia bezi na http://127.0.0.1:5000  (toto okno nechaj otvorene, zatvorenim aplikaciu vypnes)
start "" http://127.0.0.1:5000
python app.py
pause
exit /b
:nopython
echo Python nie je nainstalovany.
echo Stiahni ho z https://www.python.org/downloads/ a pri instalacii zaskrtni "Add python.exe to PATH".
start "" https://www.python.org/downloads/
pause

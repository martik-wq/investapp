@echo off
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0update.ps1"
if not exist "%~dp0run.bat" goto missing
call "%~dp0run.bat"
exit /b
:missing
echo Chyba subor run.bat. Skontroluj pripojenie na internet a spusti spustit.bat znova.
pause

@echo off
rem Startet die Monitoring-App auf diesem Rechner (Windows). Voraussetzung: Python 3.10 oder neuer.
rem Beim ersten Start werden die noetigen Pakete einmalig installiert (Internet noetig, ca. 2 bis 5 Minuten).
chcp 65001 >nul
cd /d "%~dp0"
title Monitoring KI-Agent

set "PY="
where py >nul 2>&1 && set "PY=py -3"
if not defined PY (
    where python >nul 2>&1 && set "PY=python"
)
if not defined PY goto :nopython

%PY% -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
if errorlevel 1 goto :nopython

if not exist ".venv\Scripts\python.exe" (
    echo [1/3] Richte die Programmumgebung ein ...
    %PY% -m venv .venv
    if errorlevel 1 goto :fehler
)

if not exist ".venv\installiert.txt" (
    echo [2/3] Installiere die benoetigten Pakete. Das dauert beim ersten Start einige Minuten ...
    ".venv\Scripts\python.exe" -m pip install --quiet --upgrade pip
    ".venv\Scripts\python.exe" -m pip install --quiet -r requirements.txt
    if errorlevel 1 goto :fehler
    echo ok> ".venv\installiert.txt"
)

if defined MONITORING_NUR_PRUEFEN (
    echo Einrichtung erfolgreich, Start uebersprungen.
    exit /b 0
)

echo [3/3] Starte die App. Der Browser oeffnet sich gleich. Dieses Fenster zum Beenden schliessen.
start "" /b cmd /c "timeout /t 6 >nul & start http://localhost:8501"
".venv\Scripts\streamlit.exe" run app.py --server.headless true --server.port 8501 --browser.gatherUsageStats false
goto :ende

:nopython
echo.
echo Python 3.10 oder neuer wurde nicht gefunden.
echo Bitte von https://www.python.org/downloads/ installieren. Im Installer "Add python.exe to PATH" ankreuzen.
echo Danach App-starten.bat erneut ausfuehren.
start https://www.python.org/downloads/
goto :ende

:fehler
echo.
echo Bei der Einrichtung ist ein Fehler aufgetreten. Bitte die Meldung oben lesen (meist fehlt die Internetverbindung).

:ende
pause

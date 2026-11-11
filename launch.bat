@echo off
rem IC Risk Screener: one-click start for Windows. First run sets everything up (about 3-5 minutes).
cd /d "%~dp0"

rem --- find Python 3.11+ (the py launcher comes with the python.org installer) ---
set "PY="
py -3 -c "import sys; sys.exit(sys.version_info < (3, 11))" >nul 2>nul && set "PY=py -3"
if not defined PY python -c "import sys; sys.exit(sys.version_info < (3, 11))" >nul 2>nul && set "PY=python"
if not defined PY (
    echo Python 3.11 or newer was not found.
    echo Install it from https://www.python.org/downloads/ and tick "Add python.exe to PATH", then run this again.
    pause
    exit /b 1
)

rem --- first run: private Python environment + packages ---
if not exist ".venv\installed.ok" (
    echo First-time setup: installing packages. This takes a few minutes...
    if not exist ".venv\Scripts\python.exe" %PY% -m venv .venv || goto :fail
    ".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q -r requirements.txt || goto :fail
    echo ok> ".venv\installed.ok"
)

rem --- API key: .env here or one folder up ---
if exist ".env" goto :run
if exist "..\.env" goto :run
echo.
echo No API key found. Paste your Portkey API key and press Enter.
echo (It is saved only on this computer, in a file named .env)
set /p "KEY=Key: "
> ".env" echo PORTKEY_API_KEY=%KEY%

:run
echo.
echo Starting the IC Risk Screener. Your browser will open at http://127.0.0.1:8050
echo Keep this window open while you use the app. Close it to stop the app.
".venv\Scripts\python.exe" app.py --open
pause
exit /b 0

:fail
echo.
echo Setup failed. Check your internet connection and run launch.bat again.
if exist ".venv\installed.ok" del ".venv\installed.ok"
pause
exit /b 1

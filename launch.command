#!/bin/bash
# IC Risk Screener: one-click start for Mac (double-click in Finder). First run sets everything up (about 3-5 minutes).
cd "$(dirname "$0")" || exit 1

if ! python3 -c "import sys; sys.exit(sys.version_info < (3, 11))" 2>/dev/null; then
    echo "Python 3.11 or newer was not found. Install it from https://www.python.org/downloads/ and run this again."
    read -r -p "Press Enter to close." _; exit 1
fi

if [ ! -f .venv/installed.ok ]; then
    echo "First-time setup: installing packages. This takes a few minutes..."
    { [ -x .venv/bin/python ] || python3 -m venv .venv; } &&
        .venv/bin/python -m pip install --disable-pip-version-check -q -r requirements.txt &&
        touch .venv/installed.ok || { echo "Setup failed. Check your internet connection and try again."; read -r -p "Press Enter to close." _; exit 1; }
fi

if [ ! -f .env ] && [ ! -f ../.env ]; then
    echo; echo "No API key found. Paste your Portkey API key and press Enter."
    echo "(It is saved only on this computer, in a file named .env)"
    read -r -p "Key: " KEY
    echo "PORTKEY_API_KEY=$KEY" > .env
fi

echo; echo "Starting the IC Risk Screener. Your browser will open at http://127.0.0.1:8050"
echo "Keep this window open while you use the app. Close it to stop the app."
.venv/bin/python app.py --open

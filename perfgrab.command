#!/bin/bash
# macOS launcher: creates a virtual environment on first run, then starts the app.
cd "$(dirname "$0")"
if [ ! -d .venv ]; then
  echo "Installing dependencies..."
  python3 -m venv .venv && ./.venv/bin/pip install -q -r requirements.txt || { echo "Install failed"; read -p "Press Enter to close"; exit 1; }
fi
./.venv/bin/python perfgrab_gui.py

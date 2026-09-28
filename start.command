#!/bin/bash
# Double-click (macOS) or run `bash start.command` to start Lead Finder. Needs Python 3.10+.
cd "$(dirname "$0")"
if [ ! -d .venv ]; then
  echo "First start: setting up (takes 1-3 minutes)..."
  python3 -m venv .venv || { echo "Python 3 not found. Install it from https://www.python.org/downloads/"; exit 1; }
fi
source .venv/bin/activate
echo "Checking required libraries..."
pip install --disable-pip-version-check -r requirements.txt | grep -v "already satisfied"
echo "Starting Lead Finder..."
python -m leadgen.server "$@"

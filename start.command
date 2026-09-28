#!/bin/bash
# Double-click (macOS) or run ./start.command (Linux) to start Lead Finder. Needs Python 3.10+.
cd "$(dirname "$0")"
[ -d .venv ] || python3 -m venv .venv
source .venv/bin/activate
pip install -q -r requirements.txt
python -m leadgen.server "$@"

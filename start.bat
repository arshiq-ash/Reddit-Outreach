@echo off
rem Double-click to start Lead Finder on Windows (needs Python 3.10+ from python.org).
cd /d "%~dp0"
if not exist .venv ( py -3 -m venv .venv || python -m venv .venv )
call .venv\Scripts\activate.bat
pip install -q -r requirements.txt
python -m leadgen.server %*
pause

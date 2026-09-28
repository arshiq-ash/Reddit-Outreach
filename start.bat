@echo off
rem Double-click to start Lead Finder on Windows (needs Python 3.10+ from python.org).
cd /d "%~dp0"
if not exist .venv (
  echo First start: setting up, takes 1-3 minutes...
  py -3 -m venv .venv || python -m venv .venv
)
call .venv\Scripts\activate.bat
echo Checking required libraries...
pip install --disable-pip-version-check -r requirements.txt | findstr /v /c:"already satisfied"
echo Starting Lead Finder...
python -m leadgen.server %*
pause

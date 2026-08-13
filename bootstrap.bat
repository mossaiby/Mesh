@echo off
python -m venv .venv
.venv\Scripts\pip.exe install --upgrade pip
.venv\Scripts\pip.exe install -r requirements.txt
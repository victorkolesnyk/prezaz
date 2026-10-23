@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
    py -3 -m venv .venv || python -m venv .venv
)
.venv\Scripts\python -c "import soundcard, soundfile, numpy, modal" 2>nul || .venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\modal token new
.venv\Scripts\modal deploy modal_app.py
pause

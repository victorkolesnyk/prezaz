@echo off
rem Drag one or more audio files onto this file
chcp 65001 >nul
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
    py -3 -m venv .venv || python -m venv .venv
)
.venv\Scripts\python -c "import soundcard, soundfile, numpy, modal" 2>nul || .venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python transcribe.py %*
pause

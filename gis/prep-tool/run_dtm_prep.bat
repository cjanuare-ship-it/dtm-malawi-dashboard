@echo off
REM DTM Malawi GIS workspace - data preparation tool (Windows launcher)
REM First run: creates a private Python environment next to this file and installs the GIS packages (needs internet once).
setlocal
cd /d "%~dp0"
where py >nul 2>nul && (set PY=py -3) || (set PY=python)
if not exist ".venv\Scripts\python.exe" (
  echo Setting up the tool for the first time. This takes a few minutes...
  %PY% -m venv .venv || (echo Python 3.9 or newer is needed: https://www.python.org/downloads/ & pause & exit /b 1)
  ".venv\Scripts\python.exe" -m pip install --upgrade pip
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt || (echo Package installation failed. Check the internet connection and try again. & pause & exit /b 1)
)
".venv\Scripts\python.exe" dtm_prep.py %*
if errorlevel 1 pause

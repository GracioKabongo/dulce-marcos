@echo off
cd /d "%~dp0"
where py >nul 2>&1
if errorlevel 1 (
  echo Instale Python 3.11 ou superior.
  pause
  exit /b 1
)
py -m pip install -r requirements.txt
if not exist .env copy .env.example .env
start "" "http://127.0.0.1:8000/"
py -m uvicorn main:app --host 127.0.0.1 --port 8000
pause

@echo off
rem Demo 2 (offline): may chu gia lap Cho Tot sinh tin moi lien tuc + collector that + dashboard
rem Canh bao in ra cua so nay (hoac Telegram neu da dien .env). Dashboard tu lam moi moi 60 giay.
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Hay chay 1_CAI_DAT.bat truoc.
  pause
  exit /b 1
)
echo Dang mo dashboard tai http://127.0.0.1:8002  (dong cua so nay de dung)
start "" cmd /c "timeout /t 8 >nul & start http://127.0.0.1:8002"
".venv\Scripts\python.exe" main.py mockdemo --port 8002
pause

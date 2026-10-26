@echo off
rem Chay that tren Cho Tot: tham do API, roi chay collector + dashboard trong 1 cua so.
rem Nhip quet mac dinh 120 giay/vong (doi POLL_SECONDS trong .env). Dong cua so de dung.
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Hay chay 1_CAI_DAT.bat truoc.
  pause
  exit /b 1
)
echo === Buoc 1: tham do API Cho Tot ===
".venv\Scripts\python.exe" main.py probe
echo.
echo === Buoc 2: collector + dashboard tai http://127.0.0.1:8000 ===
start "" cmd /c "timeout /t 5 >nul & start http://127.0.0.1:8000"
".venv\Scripts\python.exe" main.py all --port 8000
pause

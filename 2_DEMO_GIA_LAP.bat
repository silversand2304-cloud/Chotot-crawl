@echo off
rem Demo 1 (offline): sinh 30 ngay du lieu gia lap, cham diem bo phan tich, mo dashboard
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Hay chay 1_CAI_DAT.bat truoc.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" main.py simulate --days 30
echo.
echo Bao cao chi tiet nam trong thu muc reports\
echo Dang mo dashboard tai http://127.0.0.1:8001  (dong cua so nay de dung)
start "" cmd /c "timeout /t 3 >nul & start http://127.0.0.1:8001"
".venv\Scripts\python.exe" main.py web --db data\sim.db --port 8001
pause

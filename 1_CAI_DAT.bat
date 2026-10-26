@echo off
rem Cai dat moi truong Python cho Deal Finder (chi can chay 1 lan, hoac khi doi requirements.txt)
cd /d "%~dp0"
echo === Deal Finder: cai dat ===
echo Thu muc: %CD%
where python >nul 2>nul
if errorlevel 1 (
  echo [LOI] Chua cai Python 3.11+. Tai tai https://www.python.org/downloads/  ^(nho tick "Add python.exe to PATH"^)
  pause
  exit /b 1
)
if not exist ".venv\Scripts\python.exe" python -m venv .venv
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q -r requirements.txt
if errorlevel 1 (
  echo [LOI] Cai thu vien that bai. Kiem tra mang roi chay lai.
  pause
  exit /b 1
)
if not exist ".env" copy ".env.example" ".env" >nul
echo.
echo === Chay bo test tu dong ===
".venv\Scripts\python.exe" -m pytest -q
echo.
echo Xong. Tiep theo: double-click 2_DEMO_GIA_LAP.bat
pause

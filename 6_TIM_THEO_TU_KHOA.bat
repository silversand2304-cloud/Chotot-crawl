@echo off
rem Tim 1 tu khoa bat ky tren Cho Tot (laptop, xe may, may lanh, may anh...):
rem tai vai trang tin, luu vao data\deals.db, in gia theo nhom va xuat Excel vao thu muc exports.
rem Co the chay trong luc 4_CHAY_THAT_CHOTOT.bat dang mo (dung chung du lieu).
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Hay chay 1_CAI_DAT.bat truoc.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" main.py search --open
echo.
pause

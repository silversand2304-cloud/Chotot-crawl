@echo off
rem Dong goi ma nguon thanh deal-finder.tgz de chep len VPS (bo .venv, data, reports, .env)
cd /d "%~dp0"
cd ..
tar -czf deal-finder.tgz --exclude=deal-finder/.venv --exclude=deal-finder/data --exclude=deal-finder/reports --exclude=deal-finder/backup --exclude=deal-finder/exports --exclude=deal-finder/.env --exclude=__pycache__ --exclude=.pytest_cache deal-finder
if errorlevel 1 (
  echo [LOI] Dong goi that bai.
  pause
  exit /b 1
)
echo Da tao: %CD%\deal-finder.tgz
echo Chep len VPS:  scp "%CD%\deal-finder.tgz" root@IP_VPS:/root/
pause

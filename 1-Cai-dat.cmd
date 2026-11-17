@echo off
rem Double-click: create .venv and install the Python packages (no API call). Safe to run again.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup\setup.ps1"
if errorlevel 1 (
  echo.
  echo Cai dat CHUA xong. Chup man hinh dong loi o tren gui nguoi ho tro, roi bam dup lai 1-Cai-dat.cmd.
  pause
  exit /b 1
)
echo.
echo Xong. Tiep theo: bam dup 2-Nhap-key.cmd
pause

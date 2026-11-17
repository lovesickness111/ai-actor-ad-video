@echo off
rem Double-click: local checks only (packages, ffmpeg, fonts, which keys are present). No API call.
"%~dp0.venv\Scripts\python.exe" "%~dp0tools\doctor.py"
pause

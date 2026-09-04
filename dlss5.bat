@echo off
setlocal
set "PYTHONNOUSERSITE=1"
set "PYTHONDONTWRITEBYTECODE=1"
set "PYTHONIOENCODING=utf-8"
set "GRADIO_ANALYTICS_ENABLED=False"
"%~dp0bin\python-3.13.15-embed-amd64\python.exe" -m dlss5ve.cli %*
exit /b %ERRORLEVEL%

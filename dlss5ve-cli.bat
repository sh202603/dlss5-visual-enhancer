@echo off
setlocal
set "PYTHONNOUSERSITE=1"
set "PYTHONDONTWRITEBYTECODE=1"
set "PYTHONIOENCODING=utf-8"
rem The bundled interpreter folder carries its version (3.14.7 in v10).
rem Resolve it by pattern, the way the app launcher does, so that a runtime
rem bump in a future release needs no edit here.
set "VE_PYTHON="
for /d %%d in ("%~dp0bin\python-*-embed-amd64") do set "VE_PYTHON=%%~fd\python.exe"
if not defined VE_PYTHON goto :nopython
"%VE_PYTHON%" -m dlss5ve.cli %*
exit /b %ERRORLEVEL%

:nopython
echo dlss5ve-cli: no bundled interpreter found under "%~dp0bin".>&2
exit /b 3

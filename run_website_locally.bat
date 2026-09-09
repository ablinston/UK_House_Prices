@echo off
REM ============================================================================
REM Preview the static site locally, exactly as it will be served in production.
REM
REM This is a plain static file server - there is no build step and no app
REM process. serve.py imports nothing but the Python standard library, so this
REM needs no virtual environment and nothing from requirements.txt, which is
REM there for the data pipeline rather than for the site.
REM ============================================================================

setlocal

REM The py launcher ships with python.org installs and finds an interpreter even
REM when python.exe is not on PATH, which is the usual reason a plain "python"
REM fails on Windows. Fall back to python for installs without the launcher.
set "PY="
where /q py && set "PY=py -3"
if not defined PY (
    where /q python && set "PY=python"
)
if not defined PY goto :nopython

if not exist "%~dp0web\data\meta.json" (
    echo.
    echo ERROR: web\data\meta.json is missing, so the site has no data to show.
    echo Generate it with:
    echo     python src\06_export_web_data.py
    echo.
    echo That step is the data pipeline, which does need the dependencies in
    echo requirements.txt - unlike this preview server.
    echo.
    pause
    exit /b 1
)

echo.
echo   UK House Prices - local preview
echo   Open http://localhost:8000
echo   Press Ctrl+C to stop.
echo.

%PY% "%~dp0serve.py" --port 8000 --directory "%~dp0web"
exit /b %errorlevel%

:nopython
echo.
echo ERROR: no Python found on PATH.
echo.
echo Install Python 3 from https://www.python.org/downloads/ and tick
echo "Add python.exe to PATH" during setup, then run this again.
echo.
pause
exit /b 1
